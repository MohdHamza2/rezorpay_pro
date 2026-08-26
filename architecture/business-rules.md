# Business Rules Specification

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## Category 1: Inventory Rules

### Rule 1.1: Stock Manipulation Protection
**Rule:** Never manipulate stock directly. Frontend cannot PUT a stock quantity. Only business events (GRN, DO, Adjustment, Transfer) create StockTransactions.

**Enforcement:**
- No PUT endpoint on `/warehouses/{id}/stock`
- All stock changes routed through event-specific endpoints:
  - GRN acceptance → `POST /grns/{id}/accept`
  - DO dispatch → `POST /delivery-orders/{id}/dispatch`
  - Adjustment → `POST /stock-adjustments/{id}/approve`
  - Transfer → `POST /stock-transfers/{id}/dispatch` and `/receive`

**Rationale:** Maintains immutable audit trail, prevents unauthorized stock changes.

---

### Rule 1.2: Accepted Quantity Only
**Rule:** Inventory increases by `quantity_accepted` from GRN, NOT `quantity_received`.

**Implementation:**
- `quantity_received` = what arrived
- `quantity_accepted` = passed inspection
- `quantity_rejected` = failed inspection
- `quantity_damaged` = damaged on arrival
- **Constraint:** `quantity_accepted + quantity_rejected + quantity_damaged = quantity_received`
- StockTransaction created only when `quantity_accepted > 0`

**Rationale:** Only good stock enters inventory. Rejected/damaged items tracked separately.

---

### Rule 1.3: Available Stock Calculation
**Rule:** `Available = on_hand − reserved − damaged`

**Implementation:**
```python
available_quantity = (
    warehouse_stock.quantity_on_hand
    - warehouse_stock.quantity_reserved
    - warehouse_stock.quantity_damaged
)
```

**Usage:** System must check `available_quantity` (not `on_hand`) before allowing reservations.

**Rationale:** Reserved stock is committed to orders, damaged stock is unusable.

---

### Rule 1.4: Negative Stock Control
**Rule:** No negative stock unless `workspace.allow_negative_stock = true`. Blocked at service layer with meaningful error.

**Enforcement:**
- Service layer checks `available_quantity >= requested_quantity` before reservation
- If check fails and `allow_negative_stock = false` → return 400 with "Insufficient stock available: {available} {UOM}"
- If `allow_negative_stock = true` → allow reservation, flag for procurement alert

**Rationale:** Prevents overselling. Configurable per workspace for businesses that allow backorders.

---

### Rule 1.5: Reservation Before Delivery
**Rule:** DO must have an active `StockReservation` before dispatch. Stock movements happen on dispatch, not on reservation.

**Enforcement:**
- `POST /delivery-orders/{id}/dispatch` endpoint checks for active reservation
- If no reservation → return 400 "No active stock reservation found"
- On dispatch: `StockReservation.status` → `DISPATCHED`, StockTransaction created

**Rationale:** Prevents dispatch without inventory commitment. Two-phase: reserve → dispatch.

---

### Rule 1.6: Transfer IN_TRANSIT State
**Rule:** Stock removed from source warehouse immediately on approval. Added to destination on receipt. IN_TRANSIT tracked separately.

**Implementation:**
- On `APPROVED → IN_TRANSIT`:
  - Source warehouse: `quantity_on_hand` decreases, `quantity_in_transit` increases
  - StockTransaction type `TRANSFER_OUT`
- On `IN_TRANSIT → RECEIVED`:
  - Destination warehouse: `quantity_on_hand` increases
  - Source warehouse: `quantity_in_transit` decreases
  - StockTransaction type `TRANSFER_IN`

**Rationale:** Prevents double-counting. Stock exists but is not at either location during transit.

---

### Rule 1.7: Concurrent Reservation Protection
**Rule:** Row-level `SELECT FOR NO KEY UPDATE` lock on WarehouseStock row when creating reservations to prevent race conditions while allowing concurrent audit log writes.

**Implementation:**
```python
async with session.begin():
    stock = await session.execute(
        select(WarehouseStock)
        .where(WarehouseStock.warehouse_id == warehouse_id)
        .where(WarehouseStock.product_id == product_id)
        .with_for_update(key_share=True)  # FOR NO KEY UPDATE
    )
    # Check available quantity
    # Create reservation
    # Update quantity_reserved
```

**Rationale:** `FOR NO KEY UPDATE` prevents race conditions on reservations while allowing concurrent foreign key inserts (audit logs, events).

---

### Rule 1.8: UOM Conversion Resolution Algorithm
**Rule:** When GRN/SPO quantities use different UOMs, system must resolve conversion per-product.

**Algorithm:**
1. Look up `ProductUOMConversion` for `(product_id, from_uom, to_uom)`
2. If direct conversion exists → apply and compare
3. If no direct conversion:
   - Find all conversions FROM source UOM
   - Find all conversions TO target UOM
   - Find chain through common intermediate UOM (usually `base_uom`)
   - If chain found → apply multi-hop conversion
   - If no chain found → FAIL with error "Cannot match {from_uom} to {to_uom} for Product {sku}"
4. Apply converted quantity to 3-way matching logic

**Circular Prevention:** Track visited UOMs during chain resolution; abort if loop detected.

**Example:**
- Product A: 1 DRUM = 500 MTR (direct)
- Product B: 1 CARTON = 50 PCS, 1 ROLL = 100 PCS (chain via PCS as base)

**Implementation:** `services/uom_conversion_service.py` with `resolve_conversion(product_id, from_uom_id, to_uom_id, quantity)` method.

---

## Category 2: Financial Rules

### Rule 2.1: Decimal Precision for Money
**Rule:** All money uses `Decimal(12,2)` — NEVER float.

**Enforcement:**
- Database: `NUMERIC(12,2)` for all amount/price fields
- Python: `from decimal import Decimal`
- Pydantic schemas: `amount: Decimal = Field(decimal_places=2)`
- Frontend: Display with `.toFixed(2)` (after fixing toFixed crash from Wave 1)

**Rationale:** Float arithmetic introduces rounding errors. Financial precision requires exact decimal math.

---

### Rule 2.2: Payment Immutability
**Rule:** Payments are immutable — no UPDATE or DELETE of payment records.

**Enforcement:**
- No PUT endpoint on `/payments/{id}`
- No DELETE endpoint on `/payments/{id}`
- Payment correction requires new Payment record with negative amount or CreditNote
- Regression test: `test_payment_immutability.py` asserts 405 Method Not Allowed

**Rationale:** Financial audit trail. Payment records are legal evidence.

---

### Rule 2.3: Soft Deletes Only
**Rule:** Soft deletes only for all business entities.

**Enforcement:**
- All entity models have `deleted_at: datetime | None` field
- DELETE endpoints set `deleted_at = now()`, never `db.delete()`
- List endpoints filter `WHERE deleted_at IS NULL` by default
- Admin endpoints can include `include_deleted=true` query param

**Rationale:** Data recovery, audit trail, regulatory compliance.

---

### Rule 2.4: Idempotency Keys for Payments
**Rule:** All payment endpoints require `Idempotency-Key` header — 48-hour TTL.

**Enforcement:**
- Router decorator: `@require_idempotency_key`
- Redis cache: `idempotency:{key}` → `{status_code, response_body}` (expires 48h)
- On duplicate key within TTL → return cached response (no duplicate Payment created)
- After 48h → key expired, new payment allowed

**Rationale:** Prevents duplicate payments from retries, network failures, accidental double-clicks.

---

### Rule 2.5: 3-Way Match Blocking
**Rule:** No supplier payment when `three_way_match_status = FAILED` (unless authorized override).

**Enforcement:**
- `POST /supplier-invoices/{id}/approve` blocked if match failed
- Override requires `override_reason` and `override_by` (authorized user role)
- Audit log records override with reason

**Rationale:** Prevents payment for wrong quantity/price/tax without management approval.

---

### Rule 2.6: Invoice Edit Restrictions
**Rule:** Invoice can only be edited in `DRAFT` state. All other states are immutable.

**Enforcement:**
- `PUT /invoices/{id}` checks `status = DRAFT`
- If status ≠ DRAFT → return 400 "Cannot edit invoice in {status} state"
- After `SENT`, only void (transition to CANCELLED) allowed

**Rationale:** Sent invoices are legal documents. Changes require credit notes.

---

### Rule 2.7: Overpayment Rejection
**Rule:** Payment `amount > balance_due` returns 400.

**Enforcement:**
- `POST /payments` validates `payment.amount <= invoice.balance_due`
- If exceeded → return 400 "Payment amount {amount} exceeds balance due {balance_due}"
- Partial overpayments (<1 AED difference) logged as warning, rounded to balance_due

**Rationale:** Prevents customer overpayment errors. Overpayments require credit notes.

---

## Category 3: Credit Control Rules

### Rule 3.1: Credit Check Triggers
**Rule:** Credit check runs on: CPO confirmation, Invoice creation, DO release.

**Implementation:**
- `POST /customer-purchase-orders/{id}/confirm` → `credit_control_service.check_credit(client_id)`
- `POST /invoices` → credit check on create
- `POST /delivery-orders/{id}/dispatch` → credit check before dispatch

**Rationale:** Prevents credit limit violations at multiple transaction points.

---

### Rule 3.2: Overdue Definition
**Rule:** Overdue = any invoice where `due_date < today AND balance_due > 0`.

**Calculation:**
```python
overdue_invoices = session.query(Invoice).filter(
    Invoice.client_id == client_id,
    Invoice.due_date < date.today(),
    Invoice.balance_due > 0,
    Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE])
).all()
```

**Rationale:** Clear definition for aging calculations.

---

### Rule 3.3: Outstanding Calculation
**Rule:** Outstanding = TOTAL `balance_due` across all active invoices (not only overdue).

**Calculation:**
```python
outstanding = session.query(func.sum(Invoice.balance_due)).filter(
    Invoice.client_id == client_id,
    Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
    Invoice.balance_due > 0
).scalar() or Decimal('0.00')
```

**Rationale:** Credit limit check includes all unpaid invoices, not just overdue.

---

### Rule 3.4: HOLD Blocking Logic
**Rule:** HOLD blocks CPO confirmation and DO release. Does NOT block payments, statements, or enquiries.

**Enforcement:**
- CPO confirmation: If `client.credit_status = HOLD` and `workspace.block_po_on_hold = True` → return 403 "Customer on credit HOLD"
- DO release: If `client.credit_status = HOLD` and `workspace.block_do_on_hold = True` → return 403 "Customer on credit HOLD"
- Payments, statements, enquiries: No credit check

**Rationale:** Prevents new credit exposure while allowing debt collection.

---

### Rule 3.5: Credit Status Audit
**Rule:** Credit status changes are audited with `changed_by`, `changed_at`, `reason`.

**Implementation:**
- `Client` model has `credit_status_changed_at`, `credit_status_changed_by`, `credit_status_reason`
- Every status change updates these fields
- Separate `CreditStatusEvent` table for full history

**Rationale:** Regulatory compliance, dispute resolution, audit trail.

---

### Rule 3.6: Credit Aging Logic
**Rule:** Credit status auto-calculated by background job based on overdue age and outstanding.

**Algorithm:**
```python
if outstanding > credit_limit:
    return CreditStatus.HOLD
elif oldest_overdue_age > workspace.credit_hold_days:
    return CreditStatus.HOLD
elif oldest_overdue_age > workspace.credit_warning_days:
    return CreditStatus.WARNING
else:
    return CreditStatus.ACTIVE
```

**Execution:** Daily background job at midnight UTC updates all clients.

**Rationale:** Consistent, automated credit risk management.

---

## Category 4: Document Rules

### Rule 4.1: Gapless Numbering
**Rule:** All document numbers are gapless — `SELECT FOR UPDATE` on sequence counter.

**Implementation:**
```python
async with session.begin():
    counter = await session.execute(
        select(InvoiceCounter)
        .where(InvoiceCounter.workspace_id == workspace_id)
        .where(InvoiceCounter.year == current_year)
        .with_for_update()
    )
    counter.current_value += 1
    invoice_number = f"INV-{current_year}-{counter.current_value:04d}"
```

**Enforcement:** Separate counter table per document type (InvoiceCounter, SPOCounter, etc.)

**Rationale:** Legal compliance (tax authorities require gapless numbering), fraud prevention.

---

### Rule 4.2: Invoice ≠ Delivery Independence
**Rule:** One invoice can have many DOs. One CPO can have many invoices.

**Implementation:**
- `Invoice` → `CPO` (many-to-one via `cpo_id`)
- `DeliveryOrder` → `CPO` (many-to-one via `cpo_id`)
- No direct `Invoice` ↔ `DeliveryOrder` link (independent documents)

**Rationale:** Invoices and deliveries are independent events. Customer can be invoiced before or after delivery.

---

### Rule 4.3: Quantity Reconciliation
**Rule:** System must track `invoiced_qty` and `delivered_qty` per CPO line item.

**Implementation:**
- `CustomerPurchaseOrderItem` has `invoiced_quantity` and `delivered_quantity` fields
- On Invoice creation: increment `invoiced_quantity` for linked CPO items
- On DO dispatch: increment `delivered_qty` for linked CPO items
- CPO status auto-updates to `FULLY_INVOICED` or `FULLY_DELIVERED` when complete

**Rationale:** Enables partial invoicing, partial delivery tracking, prevents overbilling.

---

### Rule 4.4: PDF Watermarks
**Rule:** CANCELLED documents show diagonal "CANCELLED" watermark.

**Implementation:**
- `@react-pdf/renderer` or backend PDF generation
- If `document.status = CANCELLED` → overlay diagonal text "CANCELLED" in red, 50% opacity

**Rationale:** Visual indicator prevents accidental use of voided documents.

---

### Rule 4.5: Document Linking
**Rule:** Documents must link to source documents for traceability.

**Implementation:**
- Enquiry → Quotation (`enquiry_id`)
- Quotation → Invoice (`quotation_id`)
- Quotation → CPO (`quotation_id`)
- CPO → Invoice (`cpo_id`)
- CPO → DO (`cpo_id`)
- ProcurementRequest → RFQ (`pr_id`)
- RFQ → SPO (`rfq_id`)
- SPO → GRN (`spo_id`)
- GRN → SupplierInvoice (`grn_id`)
- Invoice → CreditNote (`invoice_id`)
- GRN → PurchaseReturn (`grn_id`)

**Rationale:** Audit trail, dispute resolution, workflow tracking.

---

## Category 5: Agent Governance Rules

### Rule 5.1: No Invented Business Rules
**Rule:** Agents cannot invent business rules. Flag → wait for approval.

**Enforcement:**
- If agent encounters ambiguous scenario (e.g., "Should receiving 110 units against PO for 100 be allowed?"):
  1. STOP implementation
  2. Flag question in execution report (`.agents/reports/[role]-execution-report.md`)
  3. Wait for human approval with explicit rule
  4. Document approved rule in this file

**Rationale:** System behavior must match real business requirements, not AI assumptions.

---

### Rule 5.2: Mandatory Execution Reporting
**Rule:** Every agent must report in `.agents/reports/[role]-execution-report.md`.

**Content:**
- Actions taken (files created/modified, migrations run, endpoints added)
- Decisions made
- Issues encountered
- Questions flagged for human review
- Test results

**Rationale:** Audit trail for multi-agent development, debugging, quality control.

---

### Rule 5.3: Schema Change Sequence
**Rule:** Schema changes: Database Agent first, Backend Agent second, Frontend Agent third.

**Workflow:**
1. **Database Agent:** Create migration, run `alembic upgrade head`, update execution report
2. **Backend Agent:** Update models, schemas, services, routers
3. **Frontend Agent:** Update TypeScript types, forms, displays
4. **Test Pass Gate:** All tests must pass before next wave

**Rationale:** Prevents backend-frontend schema mismatches, ensures database consistency.

---

### Rule 5.4: Tests Pass Before Wave Sign-Off
**Rule:** Tests must pass before next wave begins.

**Enforcement:**
- CI/CD pipeline blocks PR merge if tests fail
- Manual wave sign-off checklist includes "✅ ALL TESTS PASS"
- No agent proceeds to next wave without confirmation

**Rationale:** Prevents regression, maintains system stability.

---

## Category 6: Multi-Tenant Rules

### Rule 6.1: Workspace ID Mandatory
**Rule:** Every query MUST filter by `workspace_id`. Cross-workspace data access is a security violation.

**Enforcement:**
- Service layer checks `workspace_id` from JWT token matches entity `workspace_id`
- All queries include `.where(Entity.workspace_id == workspace_id)`
- Automated test suite verifies isolation (from T1 of eng-review)

**Rationale:** Data isolation, regulatory compliance, prevents data leaks.

---

### Rule 6.2: Workspace ID from JWT
**Rule:** `workspace_id` comes from authenticated JWT token, never from request body.

**Enforcement:**
- JWT payload includes `workspace_id`
- Service layer extracts `workspace_id = current_user.workspace_id`
- Request body `workspace_id` ignored (prevents spoofing)

**Rationale:** Security — user cannot access other workspaces by changing request payload.

---

## Category 7: 3-Way Matching Rules

### Rule 7.1: Quantity Check
**Rule:** Supplier invoice quantity cannot exceed GRN accepted quantity.

**Check:**
```python
if invoice_item.quantity > grn_item.quantity_accepted:
    return MatchStatus.FAILED_QTY
```

**Rationale:** Cannot pay for more than received.

---

### Rule 7.2: Price Tolerance Check
**Rule:** Price variance within `workspace.price_tolerance_percent` passes, otherwise fails.

**Check:**
```python
variance_percent = abs(invoice_unit_price - spo_unit_price) / spo_unit_price * 100
if variance_percent > workspace.price_tolerance_percent:
    return MatchStatus.FAILED_PRICE
```

**Rationale:** Allows minor price adjustments (rounding, currency fluctuation) while flagging significant discrepancies.

---

### Rule 7.3: Tax Check
**Rule:** Invoice VAT must match expected VAT from SPO tax rate.

**Check:**
```python
expected_vat = (spo_item.unit_price * spo_item.quantity * spo_item.tax_rate / 100).quantize(Decimal('0.01'))
if abs(invoice_item.tax_amount - expected_vat) > Decimal('0.01'):  # 1 fils tolerance
    return MatchStatus.FAILED_TAX
```

**Rationale:** Detects incorrect tax calculations.

---

### Rule 7.4: Duplicate Invoice Check
**Rule:** Same invoice number already exists for this supplier → reject as DUPLICATE_INVOICE.

**Check:**
```python
existing = session.query(SupplierInvoice).filter(
    SupplierInvoice.supplier_id == supplier_id,
    SupplierInvoice.invoice_number == invoice_number,
    SupplierInvoice.workspace_id == workspace_id
).first()
if existing:
    return MatchStatus.DUPLICATE_INVOICE
```

**Rationale:** Prevents double-payment for same invoice.

---

### Rule 7.5: Unreceived Items Check
**Rule:** Invoice arrived before goods received → flag as UNRECEIVED_ITEMS.

**Check:**
```python
if not grn_id or grn.status not in [GRNStatus.ACCEPTED, GRNStatus.PARTIALLY_ACCEPTED]:
    return MatchStatus.UNRECEIVED_ITEMS
```

**Rationale:** Hold invoice until goods arrive and are inspected.

---

## Category 8: Performance Rules

### Rule 8.1: Eager Loading for List Endpoints
**Rule:** All list endpoints MUST eager-load required relationships to prevent N+1 queries.

**Implementation:**
- 1:N relationships → `.options(selectinload(Invoice.items))`
- 1:1 relationships → `.options(joinedload(Invoice.client))`
- Nested relationships → `.options(selectinload(Invoice.items).joinedload(InvoiceItem.product))`

**Verification:** SQL logging shows one query for parent + one per relationship type (not N queries for N items).

**Rationale:** Performance — prevents database query explosion on large lists.

---

### Rule 8.2: Pagination Mandatory
**Rule:** All list endpoints use pagination: `page`, `per_page`, with `PaginationMeta`.

**Implementation:**
```python
page = query_params.page or 1
per_page = query_params.per_page or 20
offset = (page - 1) * per_page
items = query.offset(offset).limit(per_page).all()
total = query.count()
return PaginatedResponse(items=items, page=page, per_page=per_page, total=total)
```

**Rationale:** Performance — prevents returning 10,000+ records in single response.

---

## Category 9: Background Job Rules

### Rule 9.1: Daily Status Updates
**Rule:** Background jobs run daily at midnight UTC to auto-update status fields.

**Jobs:**
- Invoice `OVERDUE` status
- Quotation `EXPIRED` status
- RFQ `EXPIRED` status
- Supplier RFQ Response `EXPIRED` status
- Credit status (ACTIVE → WARNING → HOLD)
- PDC `PRESENTED` → check bank clearing status

**Implementation:** Celery Beat scheduler or similar.

**Rationale:** Automated status management, reduces manual work.

---

### Rule 9.2: PDC Clearing Checks
**Rule:** PDC status checks run daily for cheques presented to bank.

**Logic:**
- Query all PDC with `status = PRESENTED` and `pdc_clearing_date <= today`
- Call bank API or check import file
- Update status to `CLEARED` or `BOUNCED`
- On `CLEARED`: update invoice `balance_due` and `amount_paid`
- On `BOUNCED`: send alert, update customer credit status

**Rationale:** Automated payment reconciliation.

---

## Category 10: Security Rules

### Rule 10.1: JWT Token Expiry
**Rule:** Access tokens expire after 30 minutes, refresh tokens after 7 days.

**Enforcement:**
- Access token: `exp` claim set to `now() + 30 minutes`
- Refresh token: `exp` claim set to `now() + 7 days`
- Auth middleware validates `exp` on every request

**Rationale:** Balance security (short access token) with usability (refresh token avoids constant re-login).

---

### Rule 10.2: Password Hashing
**Rule:** All passwords hashed with `passlib/bcrypt`.

**Implementation:**
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash(plain_password)
verified = pwd_context.verify(plain_password, hashed)
```

**Rationale:** Industry standard, protects against rainbow table attacks.

---

### Rule 10.3: Sensitive Data Redaction
**Rule:** No sensitive data in logs — redact JWT tokens, passwords, user objects.

**Implementation:**
```python
logger.info("User logged in", extra={"user_id": user.id, "workspace_id": user.workspace_id})
# NEVER: logger.info(f"User: {user}")  # exposes email, hashed password, etc.
```

**Rationale:** Log security, compliance (GDPR, SOC 2).

---

## Category 11: India Market Rules (Wave 28)

### Rule 11.1: GST Tax Calculation
**Rule:** India market uses CGST + SGST (intra-state) or IGST (inter-state).

**Logic:**
- If `seller_state = buyer_state` → CGST + SGST (split VAT rate)
- If `seller_state ≠ buyer_state` → IGST (full VAT rate)

**Implementation:** `services/tax_calculation_service.py` with market-specific logic.

**Rationale:** India tax compliance.

---

### Rule 11.2: GSTIN Validation
**Rule:** India customers require valid GSTIN (15-character format).

**Validation:**
```python
import re
gstin_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
if market == Market.INDIA and not re.match(gstin_pattern, client.gstin):
    raise ValidationError("Invalid GSTIN format")
```

**Rationale:** Legal requirement for B2B transactions in India.

---

## Critical Business Rule Summary

**Top 10 rules that MUST be enforced at service layer:**
1. Multi-tenant isolation (workspace_id filtering)
2. Gapless document numbering (SELECT FOR UPDATE)
3. Payment immutability (no UPDATE/DELETE)
4. Stock available check before reservation
5. Credit check on CPO confirmation/DO dispatch
6. 3-way matching before supplier payment approval
7. Invoice edit only in DRAFT state
8. UOM conversion per-product (not global)
9. Soft deletes only (no hard delete)
10. Decimal precision for all money fields

---

**End of Business Rules Specification**
