# Inventory Management Rules

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## Overview

This document specifies all inventory-specific business rules, algorithms, and constraints for the multi-warehouse inventory management system.

---

## Stock Lifecycle

### Initial Stock Entry
**Rule:** Stock enters the system ONLY through:
1. GRN acceptance (supplier purchase)
2. Stock adjustment (approved by authorized user)
3. Stock transfer receipt (from another warehouse)
4. Sales return acceptance (customer return)

**Enforcement:** No direct `POST /warehouse-stock` endpoint. All stock increases routed through business event endpoints.

---

### Stock Exit Points
**Rule:** Stock leaves the system through:
1. Delivery Order dispatch (customer sale)
2. Stock adjustment (approved by authorized user)
3. Stock transfer dispatch (to another warehouse)
4. Purchase return dispatch (to supplier)
5. Damage/write-off (via adjustment)

**Enforcement:** All decreases create immutable `StockTransaction` records.

---

## Stock Transaction Rules

### Transaction Immutability
**Rule:** `StockTransaction` records are immutable — no UPDATE or DELETE allowed.

**Enforcement:**
- No PUT endpoint on `/stock-transactions/{id}`
- No DELETE endpoint on `/stock-transactions/{id}`
- Correction requires offsetting transaction (adjustment)

**Rationale:** Financial audit trail, regulatory compliance, fraud prevention.

---

### Transaction Types
**Enum Values:**
- `GRN_RECEIPT` — Goods received from supplier
- `DELIVERY_DISPATCH` — Goods shipped to customer
- `TRANSFER_OUT` — Sent to another warehouse
- `TRANSFER_IN` — Received from another warehouse
- `ADJUSTMENT_IN` — Manual increase (approved)
- `ADJUSTMENT_OUT` — Manual decrease (approved)
- `RETURN_IN` — Customer return
- `RETURN_OUT` — Return to supplier
- `DAMAGE_WRITE_OFF` — Damaged stock write-off

**Constraint:** Every transaction must link to source document:
- `GRN_RECEIPT` → `grn_id`
- `DELIVERY_DISPATCH` → `delivery_order_id`
- `TRANSFER_OUT`/`TRANSFER_IN` → `stock_transfer_id`
- `ADJUSTMENT_IN`/`ADJUSTMENT_OUT` → `stock_adjustment_id`
- `RETURN_IN` → `sales_return_id`
- `RETURN_OUT` → `purchase_return_id`

---

### Transaction Calculation
**Rule:** `quantity_after` must equal previous `quantity_after` ± current `quantity_change`.

**Enforcement:**
```python
# Get last transaction for this warehouse+product
last_txn = get_last_transaction(warehouse_id, product_id)
if transaction.transaction_type in [TxnType.GRN_RECEIPT, TxnType.TRANSFER_IN, TxnType.ADJUSTMENT_IN, TxnType.RETURN_IN]:
    transaction.quantity_after = last_txn.quantity_after + transaction.quantity_change
else:  # OUT types
    transaction.quantity_after = last_txn.quantity_after - transaction.quantity_change
```

**Rationale:** Maintains accurate running balance.

---

## Warehouse Stock Rules

### Stock Quantities Breakdown
**Fields:**
- `quantity_on_hand` — Total physical stock in warehouse
- `quantity_reserved` — Committed to orders (via StockReservation)
- `quantity_available` — `on_hand - reserved - damaged`
- `quantity_damaged` — Unusable stock (tracked separately)
- `quantity_in_transit` — Stock sent but not yet received (transfers)

**Constraint:** `quantity_on_hand >= quantity_reserved + quantity_damaged`

---

### Available Stock Calculation
**Rule:** `available = on_hand - reserved - damaged`

**Implementation:**
```python
@property
def quantity_available(self) -> Decimal:
    return (
        self.quantity_on_hand
        - self.quantity_reserved
        - self.quantity_damaged
    )
```

**Usage:** All reservation checks use `quantity_available`, not `quantity_on_hand`.

---

### Negative Stock Control
**Rule:** Negative stock prevented unless `workspace.allow_negative_stock = true`.

**Enforcement:**
```python
if quantity_available < requested_quantity:
    if not workspace.allow_negative_stock:
        raise InsufficientStockError(
            f"Insufficient stock available: {quantity_available} {uom} "
            f"(requested: {requested_quantity} {uom})"
        )
    else:
        # Allow, but flag for procurement alert
        logger.warning(
            "Negative stock allowed",
            extra={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "available": quantity_available,
                "requested": requested_quantity
            }
        )
```

**Rationale:** Configurable per workspace. Some businesses allow backorders, others don't.

---

## Stock Reservation Rules

### Reservation Lifecycle
**States:**
- `ACTIVE` — Reserved, awaiting dispatch
- `DISPATCHED` — Converted to delivery
- `CANCELLED` — Reservation released
- `EXPIRED` — Auto-cancelled after TTL

**Transitions:**
- `ACTIVE` → `DISPATCHED` (on DO dispatch)
- `ACTIVE` → `CANCELLED` (manual release)
- `ACTIVE` → `EXPIRED` (background job after 7 days)

---

### Reservation Creation
**Rule:** Reservation checks `quantity_available` and locks WarehouseStock row.

**Implementation:**
```python
async def create_reservation(
    warehouse_id: int,
    product_id: int,
    quantity: Decimal,
    cpo_id: int
) -> StockReservation:
    async with session.begin():
        # Lock stock row to prevent race conditions
        stock = await session.execute(
            select(WarehouseStock)
            .where(WarehouseStock.warehouse_id == warehouse_id)
            .where(WarehouseStock.product_id == product_id)
            .with_for_update(key_share=True)  # FOR NO KEY UPDATE
        )
        stock = stock.scalar_one()

        # Check availability
        if stock.quantity_available < quantity:
            if not workspace.allow_negative_stock:
                raise InsufficientStockError(...)

        # Create reservation
        reservation = StockReservation(
            workspace_id=workspace_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=quantity,
            cpo_id=cpo_id,
            status=ReservationStatus.ACTIVE
        )
        session.add(reservation)

        # Update reserved quantity
        stock.quantity_reserved += quantity

        await session.commit()
        return reservation
```

**Rationale:** `FOR NO KEY UPDATE` lock prevents concurrent reservation race conditions while allowing concurrent audit log inserts.

---

### Reservation Dispatch
**Rule:** On DO dispatch, reservation status → `DISPATCHED`, stock `quantity_on_hand` decreases.

**Implementation:**
```python
async def dispatch_delivery_order(do_id: int):
    async with session.begin():
        # Get active reservation
        reservation = await session.execute(
            select(StockReservation)
            .where(StockReservation.cpo_id == do.cpo_id)
            .where(StockReservation.status == ReservationStatus.ACTIVE)
        )
        reservation = reservation.scalar_one()

        # Update reservation
        reservation.status = ReservationStatus.DISPATCHED
        reservation.dispatched_at = datetime.utcnow()

        # Update stock
        stock = await get_warehouse_stock(reservation.warehouse_id, reservation.product_id)
        stock.quantity_on_hand -= reservation.quantity
        stock.quantity_reserved -= reservation.quantity

        # Create transaction
        txn = StockTransaction(
            workspace_id=workspace_id,
            warehouse_id=stock.warehouse_id,
            product_id=stock.product_id,
            transaction_type=TxnType.DELIVERY_DISPATCH,
            quantity_change=reservation.quantity,
            quantity_after=stock.quantity_on_hand,
            delivery_order_id=do_id
        )
        session.add(txn)

        await session.commit()
```

**Rationale:** Two-phase commit (reserve → dispatch) prevents overselling.

---

### Reservation Cancellation
**Rule:** On cancellation, reserved quantity released back to available stock.

**Implementation:**
```python
async def cancel_reservation(reservation_id: int, reason: str):
    async with session.begin():
        reservation = await get_reservation(reservation_id)

        if reservation.status != ReservationStatus.ACTIVE:
            raise ValidationError("Only ACTIVE reservations can be cancelled")

        # Update reservation
        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.utcnow()
        reservation.cancellation_reason = reason

        # Release stock
        stock = await get_warehouse_stock(reservation.warehouse_id, reservation.product_id)
        stock.quantity_reserved -= reservation.quantity

        await session.commit()
```

---

### Reservation Expiry
**Rule:** Reservations auto-expire after 7 days (configurable per workspace).

**Background Job:**
```python
@celery.task
def expire_old_reservations():
    cutoff = datetime.utcnow() - timedelta(days=7)
    expired = session.query(StockReservation).filter(
        StockReservation.status == ReservationStatus.ACTIVE,
        StockReservation.created_at < cutoff
    ).all()

    for reservation in expired:
        cancel_reservation(reservation.id, reason="Auto-expired after 7 days")
```

**Rationale:** Prevents indefinite stock locking for abandoned orders.

---

## Stock Transfer Rules

### Transfer Lifecycle
**States:**
- `DRAFT` — Being prepared
- `APPROVED` — Approved, ready to dispatch
- `IN_TRANSIT` — Dispatched from source, not yet received
- `RECEIVED` — Arrived at destination
- `CANCELLED` — Transfer cancelled

**Transitions:**
- `DRAFT` → `APPROVED` (authorized approver)
- `DRAFT` → `CANCELLED` (before approval)
- `APPROVED` → `IN_TRANSIT` (on dispatch)
- `IN_TRANSIT` → `RECEIVED` (on receipt)
- `IN_TRANSIT` → `CANCELLED` (if lost/returned)

---

### Transfer Dispatch
**Rule:** On dispatch, stock removed from source warehouse, `quantity_in_transit` incremented.

**Implementation:**
```python
async def dispatch_transfer(transfer_id: int):
    async with session.begin():
        transfer = await get_transfer(transfer_id)

        if transfer.status != TransferStatus.APPROVED:
            raise ValidationError("Only APPROVED transfers can be dispatched")

        # Update transfer
        transfer.status = TransferStatus.IN_TRANSIT
        transfer.dispatched_at = datetime.utcnow()

        # Update source warehouse
        source_stock = await get_warehouse_stock(transfer.source_warehouse_id, transfer.product_id)
        source_stock.quantity_on_hand -= transfer.quantity
        source_stock.quantity_in_transit += transfer.quantity

        # Create transaction
        txn = StockTransaction(
            workspace_id=workspace_id,
            warehouse_id=transfer.source_warehouse_id,
            product_id=transfer.product_id,
            transaction_type=TxnType.TRANSFER_OUT,
            quantity_change=transfer.quantity,
            quantity_after=source_stock.quantity_on_hand,
            stock_transfer_id=transfer.id
        )
        session.add(txn)

        await session.commit()
```

---

### Transfer Receipt
**Rule:** On receipt, stock added to destination warehouse, `quantity_in_transit` decremented at source.

**Implementation:**
```python
async def receive_transfer(transfer_id: int, received_quantity: Decimal):
    async with session.begin():
        transfer = await get_transfer(transfer_id)

        if transfer.status != TransferStatus.IN_TRANSIT:
            raise ValidationError("Only IN_TRANSIT transfers can be received")

        # Update transfer
        transfer.status = TransferStatus.RECEIVED
        transfer.received_at = datetime.utcnow()
        transfer.received_quantity = received_quantity

        # Update source warehouse (clear in_transit)
        source_stock = await get_warehouse_stock(transfer.source_warehouse_id, transfer.product_id)
        source_stock.quantity_in_transit -= transfer.quantity

        # Update destination warehouse
        dest_stock = await get_or_create_warehouse_stock(transfer.destination_warehouse_id, transfer.product_id)
        dest_stock.quantity_on_hand += received_quantity

        # Create transaction
        txn = StockTransaction(
            workspace_id=workspace_id,
            warehouse_id=transfer.destination_warehouse_id,
            product_id=transfer.product_id,
            transaction_type=TxnType.TRANSFER_IN,
            quantity_change=received_quantity,
            quantity_after=dest_stock.quantity_on_hand,
            stock_transfer_id=transfer.id
        )
        session.add(txn)

        # Handle discrepancy
        if received_quantity < transfer.quantity:
            discrepancy = transfer.quantity - received_quantity
            logger.warning(
                "Transfer quantity discrepancy",
                extra={
                    "transfer_id": transfer.id,
                    "expected": transfer.quantity,
                    "received": received_quantity,
                    "missing": discrepancy
                }
            )
            # Auto-create adjustment at source for missing quantity
            await create_adjustment(
                warehouse_id=transfer.source_warehouse_id,
                product_id=transfer.product_id,
                quantity=-discrepancy,
                reason=f"Missing quantity from transfer #{transfer.id}"
            )

        await session.commit()
```

**Rationale:** Handles loss/damage during transit. Missing quantity adjusted at source.

---

## Stock Adjustment Rules

### Adjustment Approval
**Rule:** All adjustments require approval from authorized user.

**States:**
- `DRAFT` — Created, awaiting approval
- `APPROVED` — Applied to stock
- `REJECTED` — Declined

**Enforcement:**
```python
async def approve_adjustment(adjustment_id: int, approver_id: int):
    async with session.begin():
        adjustment = await get_adjustment(adjustment_id)

        if adjustment.status != AdjustmentStatus.DRAFT:
            raise ValidationError("Only DRAFT adjustments can be approved")

        # Check approver authorization
        approver = await get_user(approver_id)
        if not approver.can_approve_adjustments:
            raise AuthorizationError("User not authorized to approve adjustments")

        # Update adjustment
        adjustment.status = AdjustmentStatus.APPROVED
        adjustment.approved_by = approver_id
        adjustment.approved_at = datetime.utcnow()

        # Apply to stock
        stock = await get_warehouse_stock(adjustment.warehouse_id, adjustment.product_id)
        stock.quantity_on_hand += adjustment.quantity_change  # Can be negative

        # Create transaction
        txn_type = TxnType.ADJUSTMENT_IN if adjustment.quantity_change > 0 else TxnType.ADJUSTMENT_OUT
        txn = StockTransaction(
            workspace_id=workspace_id,
            warehouse_id=adjustment.warehouse_id,
            product_id=adjustment.product_id,
            transaction_type=txn_type,
            quantity_change=abs(adjustment.quantity_change),
            quantity_after=stock.quantity_on_hand,
            stock_adjustment_id=adjustment.id
        )
        session.add(txn)

        await session.commit()
```

---

### Adjustment Reasons
**Required:** All adjustments must include `reason` field.

**Common Reasons:**
- Physical count discrepancy
- Damage/expiry
- Theft/loss
- Data entry correction
- Transfer discrepancy
- Quality rejection

**Enforcement:** Schema validation requires `reason: str` with minimum 10 characters.

---

## Stock Count Rules

### Count Cycle
**Rule:** Stock counts are periodic (monthly/quarterly) or ad-hoc.

**States:**
- `SCHEDULED` — Planned count
- `IN_PROGRESS` — Counting underway
- `COMPLETED` — Count finished, discrepancies identified
- `RECONCILED` — Adjustments applied

---

### Count Recording
**Rule:** Count records expected vs actual quantities per product.

**Implementation:**
```python
@dataclass
class StockCountItem:
    product_id: int
    expected_quantity: Decimal  # From system
    counted_quantity: Decimal   # Physical count
    variance: Decimal           # counted - expected
    notes: str
```

**Workflow:**
1. Create count with `expected_quantity` from `WarehouseStock.quantity_on_hand`
2. Team performs physical count, enters `counted_quantity`
3. System calculates `variance`
4. Manager reviews variances
5. Approved variances auto-create `StockAdjustment` records

---

### Variance Tolerance
**Rule:** Variances within tolerance (e.g., 2%) auto-approved. Larger variances require manager approval.

**Implementation:**
```python
variance_percent = abs(variance) / expected_quantity * 100
if variance_percent > workspace.stock_count_tolerance_percent:
    count_item.requires_approval = True
else:
    count_item.auto_approved = True
```

---

## UOM Conversion Rules

### Per-Product Conversions
**Rule:** UOM conversions are product-specific, not global.

**Example:**
- Product A (Cable): 1 DRUM = 500 MTR
- Product B (Cable): 1 DRUM = 300 MTR
- Product C (Paint): 1 DRUM = 20 LTR

**Implementation:** `ProductUOMConversion` table with `(product_id, from_uom_id, to_uom_id, conversion_factor)`.

---

### Conversion Resolution Algorithm
**Problem:** GRN receives 5 DRUMS, SPO ordered 1500 MTR. How to match?

**Algorithm:**
```python
def resolve_conversion(product_id: int, from_uom_id: int, to_uom_id: int, quantity: Decimal) -> Decimal:
    # Step 1: Direct conversion lookup
    conversion = db.query(ProductUOMConversion).filter(
        ProductUOMConversion.product_id == product_id,
        ProductUOMConversion.from_uom_id == from_uom_id,
        ProductUOMConversion.to_uom_id == to_uom_id
    ).first()

    if conversion:
        return quantity * conversion.conversion_factor

    # Step 2: Find chain through base UOM
    from_conversions = db.query(ProductUOMConversion).filter(
        ProductUOMConversion.product_id == product_id,
        ProductUOMConversion.from_uom_id == from_uom_id
    ).all()

    to_conversions = db.query(ProductUOMConversion).filter(
        ProductUOMConversion.product_id == product_id,
        ProductUOMConversion.to_uom_id == to_uom_id
    ).all()

    # Find common intermediate UOM
    for from_conv in from_conversions:
        for to_conv in to_conversions:
            if from_conv.to_uom_id == to_conv.from_uom_id:
                # Found chain: from_uom → intermediate → to_uom
                intermediate_qty = quantity * from_conv.conversion_factor
                final_qty = intermediate_qty * to_conv.conversion_factor
                return final_qty

    # Step 3: No conversion found
    raise ConversionError(f"Cannot convert {from_uom} to {to_uom} for product {product_id}")
```

**Circular Prevention:** Track visited UOMs during chain resolution; abort if loop detected.

---

### Conversion in 3-Way Matching
**Rule:** Before comparing quantities in 3-way match, normalize to same UOM.

**Implementation:**
```python
# SPO ordered 1500 MTR
spo_quantity_in_mtr = 1500

# GRN received 5 DRUMS
grn_quantity_in_uom = 5  # DRUMS
grn_quantity_in_mtr = resolve_conversion(
    product_id=grn.product_id,
    from_uom_id=grn.uom_id,  # DRUMS
    to_uom_id=spo.uom_id,    # MTR
    quantity=grn_quantity_in_uom
)

# Compare
if grn_quantity_in_mtr != spo_quantity_in_mtr:
    return MatchStatus.FAILED_QTY
```

---

## Reorder Level Rules

### Automatic Alerts
**Rule:** When `quantity_available <= reorder_level`, system triggers procurement alert.

**Background Job:**
```python
@celery.task
def check_reorder_levels():
    low_stock = db.query(WarehouseStock).filter(
        WarehouseStock.quantity_available <= WarehouseStock.reorder_level,
        WarehouseStock.deleted_at.is_(None)
    ).all()

    for stock in low_stock:
        # Check if open SPO already exists
        open_spo = db.query(SPO).filter(
            SPO.product_id == stock.product_id,
            SPO.status.in_([SPOStatus.PENDING_APPROVAL, SPOStatus.APPROVED, SPOStatus.SENT])
        ).first()

        if not open_spo:
            # Create procurement request
            pr = ProcurementRequest(
                workspace_id=stock.workspace_id,
                product_id=stock.product_id,
                quantity=stock.reorder_quantity,
                requested_by=None,  # Auto-generated
                reason="Auto-reorder: Stock below reorder level"
            )
            db.add(pr)

            # Send alert
            send_notification(
                type="LOW_STOCK_ALERT",
                warehouse_id=stock.warehouse_id,
                product_id=stock.product_id,
                current_quantity=stock.quantity_available,
                reorder_level=stock.reorder_level
            )
```

**Frequency:** Daily at 9:00 AM local time.

---

### Reorder Quantity Calculation
**Rule:** `reorder_quantity` = recommended order quantity when reorder level hit.

**Calculation Methods:**
1. **Fixed Quantity:** Predefined value (e.g., always order 1000 units)
2. **Up to Max:** Order enough to reach `max_stock_level`
3. **Economic Order Quantity (EOQ):** Calculated based on demand rate, ordering cost, holding cost (Wave 29)

**Default:** `reorder_quantity = max_stock_level - reorder_level`

---

## Stock Valuation Rules (Wave 29)

### FIFO Method
**Rule:** First-In-First-Out — oldest stock consumed first.

**Implementation:** Each `StockTransaction` carries `unit_cost`. On delivery dispatch, consume oldest batches first to calculate COGS.

---

### Average Cost Method
**Rule:** Moving average cost recalculated on every receipt.

**Formula:**
```python
new_avg_cost = (
    (current_on_hand * current_avg_cost) + (received_quantity * received_unit_cost)
) / (current_on_hand + received_quantity)
```

**Implementation:** `WarehouseStock.average_unit_cost` updated on GRN acceptance.

---

## Damaged Stock Rules

### Damage Recording
**Rule:** Damaged stock tracked separately, excluded from available quantity.

**Implementation:**
```python
async def record_damaged_stock(warehouse_id: int, product_id: int, quantity: Decimal, reason: str):
    async with session.begin():
        stock = await get_warehouse_stock(warehouse_id, product_id)

        # Move from on_hand to damaged
        stock.quantity_on_hand -= quantity
        stock.quantity_damaged += quantity

        # Create transaction
        txn = StockTransaction(
            workspace_id=workspace_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            transaction_type=TxnType.DAMAGE_WRITE_OFF,
            quantity_change=quantity,
            quantity_after=stock.quantity_on_hand,
            notes=reason
        )
        session.add(txn)

        await session.commit()
```

---

### Damage Write-Off
**Rule:** Damaged stock write-off requires approval and adjustment.

**Workflow:**
1. Record damage (moves to `quantity_damaged`)
2. Create adjustment with type `DAMAGE_WRITE_OFF`
3. Manager approves
4. `quantity_damaged` decreases to zero
5. Financial impact recorded (inventory loss)

---

## Multi-Warehouse Rules

### Default Warehouse
**Rule:** Each workspace has a default warehouse for new products.

**Implementation:** `Workspace.default_warehouse_id` (nullable FK to Warehouse).

---

### Inter-Warehouse Reservations
**Rule:** Reservation cannot span multiple warehouses. Each DO line item reserves from one warehouse only.

**Enforcement:** `StockReservation` has single `warehouse_id` field.

**Rationale:** Simplifies logistics. Multi-warehouse orders split into multiple DOs.

---

## Edge Cases

### Zero Stock Transfer
**Rule:** Cannot transfer zero or negative quantity.

**Validation:** Schema constraint `quantity > 0` for transfers.

---

### Receiving More Than Ordered
**Rule:** GRN `quantity_received > SPO.quantity` allowed but flagged as warning.

**Implementation:**
```python
if grn_item.quantity_received > spo_item.quantity:
    logger.warning(
        "GRN over-receipt",
        extra={
            "grn_id": grn.id,
            "spo_id": spo.id,
            "ordered": spo_item.quantity,
            "received": grn_item.quantity_received
        }
    )
    # Still accept, but flag for review
```

**Rationale:** Supplier may send extra quantity (common in bulk orders). Business decides whether to accept or return.

---

### Partial Reservation Release
**Rule:** Cannot partially release a reservation. Must cancel entire reservation.

**Rationale:** Simplifies state management. If quantity changes, cancel old reservation and create new one.

---

### Stock Count During Active Reservations
**Rule:** Expected quantity for count includes reserved stock.

**Implementation:**
```python
expected_quantity = warehouse_stock.quantity_on_hand  # Includes reserved
```

**Rationale:** Physical count counts all stock, including reserved items.

---

**End of Inventory Rules Specification**
