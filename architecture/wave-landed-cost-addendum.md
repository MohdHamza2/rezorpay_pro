# Landed Cost Allocation (D-22) — Wave 31 Item 2.1 Architecture Addendum
*InvoiceSaaS B2B Trading Platform — Wave 31 Specification — Step 1 Detail*

## 1. Purpose & Scope

This addendum defines the landed cost allocation feature (D-22) — the allocation of freight, customs duties, insurance, handling, brokerage, and other overhead costs to received inventory items at GRN disposition.

**Scope Lock:**
- **IN:** GRN-line landed cost tracking, capitalization at GRN disposition (ACCEPTED/PARTIALLY_ACCEPTED), pre-aggregation + LEFT JOIN allocation pattern, Dashboard AR PDC Outstanding card + inline PDC breakdown in AR/AP snapshots, AR/AP Aging PDC columns, Frontend Reports AR/AP aging PDC columns + summary cards, 11 E2E tests.
- **OUT:** Inventory valuation (`on_hand_value`), WAVCO/COGS, separate freight bill document, retroactive landed-cost revaluation, full supplier-invoice landed-cost matching, purchase-return landed-cost recovery, stock-transfer landed-cost propagation, historical landed-cost reconstruction, inventory valuation report, COGS report, purchase-return landed-cost recovery, stock-transfer landed-cost propagation.

---

## 2. Locked Decisions

| Decision | Status |
|----------|--------|
| Landed cost components | freight, customs, insurance, handling, brokerage, other |
| Capitalization point | GRN disposition (ACCEPTED / PARTIALLY_ACCEPTED) |
| Supplier invoice matching | validation only; no auto-capitalization |
| Allocation bases | QUANTITY, VALUE, MANUAL (WEIGHT/VOLUME deferred) |
| Rounding | per-line 2 decimals; residual → largest allocation line |
| Idempotency | unique (workspace_id, source_document_type, source_document_id, source_line_id) |
| on_hand_value field | **NOT added** |
| WAVCO / COGS | **deferred** |
| PDC dashboard/aging | already completed in Wave 30 Item 1.5 (commit 7d896e0) |

---

## 3. Existing Physical Inventory Behavior (Unchanged)

| Operation | Quantity Effect | Accounting Effect |
|-----------|-----------------|-------------------|
| GRN Disposition (ACCEPTED) | `on_hand += quantity_accepted` | Creates `RECEIPT` transaction (qty only) |
| GRN Disposition (DAMAGED) | `damaged += qty` | No monetary entry |
| Stock Transfer DISPATCH | `on_hand -= qty`, `in_transit += qty` | Creates `TRANSFER` transaction (qty only) |
| Stock Transfer RECEIVE | `on_hand += received` | Creates `TRANSFER` transaction (qty only) |
| Purchase Return DISPATCH | `on_hand -= stock_out_qty` | Creates `ISSUE` transaction (qty only) |
| Delivery Note Confirm | `on_hand -= qty` | Creates `ISSUE` transaction (qty only) |
| Inventory Adjustment | `on_hand += qty` | Creates `ADJUSTMENT` transaction (qty only) |

**No monetary valuation anywhere in the current inventory pipeline.**
D-22 does not change this — landed cost is tracked per GRN line, not in `InventoryLevel.on_hand_value`.

---

## 4. Locked D-22 Business Rules

| Rule | Description |
|------|-------------|
| **D-22-01** | Landed cost capitalizes **only for accepted quantities** (`quantity_accepted > 0`). Rejected/damaged quantities never capitalize. |
| **D-22-02** | Capitalization point = **GRN disposition** (`ACCEPTED` / `PARTIALLY_ACCEPTED`). Not at GRN creation, not at supplier invoice approval. |
| **D-22-03** | Supplier invoice matching is **validation only** — validates landed cost lines against GRN capitalized amounts; **never auto-capitalizes**. |
| **D-22-04** | Allocation bases: **QUANTITY** (default), **VALUE** (proportional to `quantity_accepted × unit_price`), **MANUAL** (user %). WEIGHT/VOLUME deferred. |
| **D-22-05** | Rounding: per-line 2 decimals; residual → largest allocation line. |
| **D-22-06** | Idempotency: unique `(workspace_id, source_document_type, source_document_id, source_line_id)` on `landed_cost_allocations`. |
| **D-22-07** | Landed cost is **operational metric only** — does NOT reduce `balance_due` (only CLEARED payments do). |
| **D-22-08** | Historical mode (`historical=true`): financial balances reconstruct as-of `as_of`; landed cost fields reflect **current-state** (no lifecycle history). Documented limitation. |

---

## 5. Data Model

### 5.1 New Table: `landed_cost_allocations`

```sql
CREATE TABLE landed_cost_allocations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id),
    grn_id                  UUID NOT NULL REFERENCES goods_receipt_notes(id),
    grn_item_id             UUID NOT NULL REFERENCES grn_items(id),
    spo_item_id             UUID NOT NULL REFERENCES supplier_purchase_order_items(id),

    component_type          VARCHAR(20) NOT NULL,  -- FREIGHT, CUSTOMS, INSURANCE, HANDLING, BROKERAGE, OTHER
    amount                  NUMERIC(12,2) NOT NULL,
    currency                CHAR(3) NOT NULL DEFAULT 'AED',

    allocation_basis        VARCHAR(20) NOT NULL,  -- QUANTITY, VALUE, MANUAL
    allocation_factor       NUMERIC(14,6),         -- e.g., 0.25 = 25% of GRN line

    source_document_type    VARCHAR(30),           -- GRN, SUPPLIER_INVOICE, FREIGHT_BILL, CUSTOMS_ENTRY, MANUAL
    source_document_id      UUID,
    source_line_id          UUID,

    status                  VARCHAR(20) NOT NULL,  -- DRAFT, ALLOCATED, CAPITALIZED, REVERSED

    allocated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    capitalized_at          TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              UUID NOT NULL REFERENCES users(id),

    CONSTRAINT uq_landed_cost_source
        UNIQUE (workspace_id, source_document_type, source_document_id, source_line_id)
);
```

### 5.2 GRN Item Extensions

```sql
-- grn_items additions
landed_cost_allocated   NUMERIC(12,2) NOT NULL DEFAULT 0,  -- total landed cost capitalized for this line
landed_cost_per_unit    NUMERIC(12,4) NOT NULL DEFAULT 0,  -- landed_cost_allocated / quantity_accepted
```

### 5.2 Schema Extensions (Existing in 7d896e0)
- `DashboardStatsResponse`: `ar_pdc_outstanding_count`, `ar_pdc_outstanding_amount`
- AR/AP aging schemas: `pdc_outstanding_count`, `pdc_outstanding_amount` on summary, detail, by-customer/by-supplier responses

---

## 4. Allocation Algorithm

```python
def allocate_landed_cost(total_amount: Decimal, lines: List[GRNItem], basis: AllocationBasis) -> Dict[UUID, Decimal]:
    """
    Returns: {grn_item_id: allocated_amount}
    """
    if basis == AllocationBasis.QUANTITY:
        total_qty = sum(line.quantity_accepted for line in lines)
        factor = {line.id: line.quantity_accepted / total_qty for line in lines}
    elif basis == AllocationBasis.VALUE:
        total_value = sum(line.quantity_accepted * line.unit_price for line in lines)
        factor = {line.id: (line.quantity_accepted * line.unit_price) / total_value for line in lines}
    elif basis == AllocationBasis.MANUAL:
        factor = {line.id: line.landed_cost_allocation_factor for line in lines}
    else:
        raise ValueError("Invalid allocation basis")

    # Raw allocation
    raw = {line_id: total_amount * factor[line_id] for line_id in factor}

    # Round to 2 decimals, track residual
    rounded = {line_id: round(amt, 2) for line_id, amt in raw.items()}
    residual = total_amount - sum(rounded.values())

    # Add residual to largest allocated line
    if residual != 0:
        largest_id = max(rounded, key=rounded.get)
        rounded[largest_id] += residual

    return rounded
```

---

## 5. API Contracts

### 5.1 GRN Creation (Optional Landed Cost)
```
POST /api/v1/grns
{
  "supplier_id": "...",
  "warehouse_id": "...",
  "received_date": "2026-09-11",
  "items": [{
    "spo_item_id": "...",
    "product_id": "...",
    "quantity_received": "100",
    "landed_cost_items": [{
      "component_type": "FREIGHT",
      "amount": "5000.00",
      "currency": "AED",
      "allocation_basis": "QUANTITY"
    }]
  }]
}
```
→ Creates `landed_cost_allocations` in `DRAFT` status linked to `GRNItem`.

### 5.2 GRN Disposition (Capitalization Point)
```
POST /api/v1/grns/{id}/disposition
{
  "quantity_accepted": "95",
  "quantity_damaged": "3",
  "quantity_rejected": "2"
}
```
**Server-side logic in `GRNService.record_disposition`:**
1. Validate disposition quantities sum to `quantity_received`
2. For each item with `quantity_accepted > 0`:
   - Fetch pre-aggregated landed cost allocations for `grn_item_id` where `status IN (DRAFT, ALLOCATED)`
   - Sum `amount` → `landed_cost_allocated`
   - Compute `landed_cost_per_unit = allocated / quantity_accepted`
   - Update `GRNItem`: `landed_cost_allocated = sum`, `landed_cost_per_unit = sum / quantity_accepted`
   - Update `landed_cost_allocations` status → `CAPITALIZED`, `capitalized_at = now()`

#### 5.3 Supplier Invoice Matching (Validation Only)
- On `submit_matching`: validate landed cost lines on supplier invoice against GRN capitalized amounts
- Validate: `quantity`, `unit_price` (with 2% tolerance), `vat_rate` match
- **No auto-capitalization** from supplier invoice — capitalization only at GRN disposition

---

## 6. Allocation Algorithm

```python
def allocate_landed_cost(total_amount: Decimal, lines: List[GRNItem], basis: AllocationBasis) -> Dict[UUID, Decimal]:
    """
    Returns: {grn_item_id: allocated_amount}
    """
    if basis == AllocationBasis.QUANTITY:
        total_qty = sum(line.quantity_accepted for line in lines)
        factor = {line.id: line.quantity_accepted / total_qty for line in lines}
    elif basis == AllocationBasis.VALUE:
        total_value = sum(line.quantity_accepted * line.unit_price for line in lines)
        factor = {line.id: (line.quantity_accepted * line.unit_price) / total_value for line in lines}
    elif basis == AllocationBasis.MANUAL:
        factor = {line.id: line.landed_cost_allocation_factor for line in lines}
    else:
        raise ValueError("Invalid allocation basis")

    raw = {line_id: total_amount * factor[line_id] for line_id in factor}

    # Round to 2 decimals, track residual
    rounded = {line_id: round(amt, 2) for line_id, amt in raw.items()}
    residual = total_amount - sum(rounded.values())

    # Add residual to largest allocated line
    if residual != 0:
        largest_id = max(rounded, key=rounded.get)
        rounded[largest_id] += residual

    return rounded
```

---

## 6. Schema Extensions

### 6.1 `landed_cost_allocations` Table (New)
```python
class LandedCostAllocation(SQLModel, table=True):
    __tablename__ = "landed_cost_allocations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", nullable=False, index=True)
    grn_id: uuid.UUID = Field(foreign_key="goods_receipt_notes.id", nullable=False, index=True)
    grn_item_id: uuid.UUID = Field(foreign_key="grn_items.id", nullable=False, index=True)
    spo_item_id: uuid.UUID = Field(foreign_key="supplier_purchase_order_items.id", nullable=False, index=True)

    component_type: str = Field(max_length=20)  # FREIGHT, CUSTOMS, INSURANCE, HANDLING, BROKERAGE, OTHER
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(max_length=3, default="AED")

    allocation_basis: str = Field(max_length=20)  # QUANTITY, VALUE, MANUAL
    allocation_factor: Decimal = Field(sa_column=Column(Numeric(14, 6)), default=Decimal("1.0"))

    source_document_type: str = Field(max_length=30)  # GRN, SUPPLIER_INVOICE, FREIGHT_BILL, CUSTOMS_ENTRY, MANUAL
    source_document_id: Optional[uuid.UUID] = Field(default=None)
    source_line_id: Optional[uuid.UUID] = Field(default=None)

    status: str = Field(max_length=20, default="DRAFT")  # DRAFT, ALLOCATED, CAPITALIZED, REVERSED

    allocated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    capitalized_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "source_document_type", "source_document_id", "source_line_id", name="uq_landed_cost_source"),
    )
```

### 6.2 GRN Item Extensions
```python
# grn_items additions
landed_cost_allocated: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
landed_cost_per_unit: Decimal = Field(default=Decimal("0.0000"), sa_column=Column(Numeric(12, 4), nullable=False))
```

#### 6.2.1 Schema Extensions
```python
# GRNItemCreate
class GRNItemCreate(GRNItemBase):
    landed_cost_items: Optional[List[LandedCostItemCreate]] = None

class LandedCostItemCreate(BaseModel):
    component_type: str  # FREIGHT, CUSTOMS, INSURANCE, HANDLING, BROKERAGE, OTHER
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="AED", max_length=3)
    allocation_basis: str = Field(default="QUANTITY")  # QUANTITY, VALUE, MANUAL
    allocation_factor: Optional[Decimal] = None  # Required for MANUAL
```

### 6.3 Schema Extensions (Already in 7d896e0)
- `DashboardStatsResponse`: `ar_pdc_outstanding_count`, `ar_pdc_outstanding_amount`
- AR/AP aging schemas: `pdc_outstanding_count`, `pdc_outstanding_amount` on summary, detail, by-customer/by-supplier responses

---

## 7. API Contracts

### 7.1 GRN Creation (Optional Landed Cost)
```
POST /api/v1/grns
{
  "supplier_id": "...",
  "warehouse_id": "...",
  "received_date": "2026-09-11",
  "items": [{
    "spo_item_id": "...",
    "product_id": "...",
    "quantity_received": "100",
    "landed_cost_items": [{
      "component_type": "FREIGHT",
      "amount": "5000.00",
      "currency": "AED",
      "allocation_basis": "QUANTITY"
    }]
  }]
}
```
→ Creates `landed_cost_allocations` in `DRAFT` status linked to `GRNItem`.

### 7.2 GRN Disposition (Capitalization Point)
```
POST /api/v1/grns/{id}/disposition
{
  "quantity_accepted": "95",
  "quantity_damaged": "3",
  "quantity_rejected": "2"
}
```
**Server-side logic in `GRNService.record_disposition`:**
1. Validate disposition quantities sum to `quantity_received`
2. For each item with `quantity_accepted > 0`:
   - Fetch pre-aggregated landed cost allocations for `grn_item_id` where `status IN (DRAFT, ALLOCATED)`
   - Sum `amount` → `landed_cost_allocated`
   - Compute `landed_cost_per_unit = allocated / quantity_accepted`
   - Update `GRNItem`: `landed_cost_allocated = sum`, `landed_cost_per_unit = sum / quantity_accepted`
   - Update `landed_cost_allocations` status → `CAPITALIZED`, `capitalized_at = now()`

### 7.3 Supplier Invoice Matching (Validation Only)
- On `submit_matching`: validate landed cost lines on supplier invoice against GRN capitalized amounts
- Validate: `quantity`, `unit_price` (with 2% tolerance), `vat_rate` match
- **No auto-capitalization** from supplier invoice — capitalization only at GRN disposition

---

## 8. Test Matrix

| Scenario | Backend Unit | E2E |
|----------|--------------|-----|
| Single landed cost (FREIGHT) on GRN line | ✅ | ✅ |
| Multiple components (FREIGHT + CUSTOMS) on one GRN line | ✅ | ✅ |
| Multiple GRN lines with different allocation bases | ✅ | ✅ |
| Multiple allocations on one GRN line (mixed) | ✅ | ✅ |
| Invoice rows not multiplied | ✅ | ✅ |
| AR/AP totals not inflated by joins | ✅ | ✅ |
| Mixed-status: only RECEIVED+DEPOSITED count | ✅ | ✅ |
| PDC Outstanding independent of balance_due | ✅ | ✅ |
| Tenant isolation | ✅ | ✅ |
| Historical mode: PDC fields = current-state | ✅ | ✅ |

---

## 9. Documentation Updates

- `.planning/AUDIT.md` — Item 2.1 status → completed (`7d896e0`)
- `.planning/STATE.md` — Status line updated
- Schema docs — updated
- AUDIT.md change log entry

---

## 10. Out of Scope (Explicitly Deferred)

| Item | Reason |
|------|--------|
| Inventory valuation (`on_hand_value`) | Not required for landed cost tracking |
| WAVCO / Moving Average Cost | Requires full valuation overhaul |
| COGS / Cost of Goods Sold | Requires full valuation + COGS ledger |
| WAVCO / Inventory Valuation Report | Deferred |
| COGS Report | Deferred |
| Separate Freight Bill Document | Can be separate document type later |
| Retroactive Landed Cost Revaluation | Requires historical reconstruction + WAVCO |
| Supplier Invoice Landed Cost Matching (Full) | Basic validation in D-22; full matching deferred |
| Inventory Valuation Report | Deferred |
| COGS Report | Deferred |
| Purchase Return Landed Cost Recovery | Requires `on_hand_value` |
| Stock Transfer Landed Cost Propagation | Requires `on_hand_value` |
| Historical Landed Cost Reconstruction | Documented limitation: current-state only |

---

## 11. Verification Checklist

- [ ] `git diff HEAD --stat` shows only D-22 files
- [ ] `npm run build` clean
- [ ] `npm run lint` clean
- [ ] `pytest backend/tests/` passes (regression)
- [ ] `npm run test:e2e` passes (11/11 new tests + 38/38 full suite)
- [ ] `alembic check` clean
- [ ] AUDIT.md Item 2.1 → completed (`<commit-hash>`)
- [ ] STATE.md Item 2.1 → completed
- [ ] AUDIT.md Change Log updated
- [ ] AUDIT.md Item 2.1 → completed
