# State Machine Specification

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## 1. Invoice (Customer Invoice)

### States
- `DRAFT` — Initial state, editable
- `SENT` — Sent to customer, immutable
- `PARTIALLY_PAID` — Partial payment received
- `PAID` — Fully paid
- `OVERDUE` — Due date passed with balance > 0 (auto background job)
- `CANCELLED` — Voided with reason

### Valid Transitions

```
DRAFT → SENT (via /send endpoint)
DRAFT → CANCELLED (via /void endpoint)
DRAFT → [soft-deleted] (via DELETE endpoint)

SENT → PARTIALLY_PAID (automatic on partial payment)
SENT → PAID (automatic on full payment)
SENT → OVERDUE (automatic background job: due_date < today AND balance_due > 0)
SENT → CANCELLED (via /void endpoint with reason)

PARTIALLY_PAID → PAID (automatic on final payment)
PARTIALLY_PAID → OVERDUE (automatic background job)
PARTIALLY_PAID → CANCELLED (via /void endpoint with reason)

OVERDUE → PARTIALLY_PAID (automatic on payment)
OVERDUE → PAID (automatic on full payment)
OVERDUE → CANCELLED (via /void endpoint with reason)

PAID → CANCELLED (via /void endpoint with reason — rare, for accounting correction)

CANCELLED → [terminal, no transitions allowed]
```

### Invalid Transitions (must be blocked)
- `SENT → DRAFT` — Cannot un-send
- `PAID → DRAFT` — Cannot un-pay
- `PAID → PARTIALLY_PAID` — Cannot reverse payment (use refund/credit note)
- `CANCELLED → any state` — Terminal state
- `DRAFT → PAID` — Must go through SENT first

### Business Rules
- Invoice can only be edited in `DRAFT` state
- Payment records are immutable (no UPDATE/DELETE)
- `OVERDUE` status set by background job daily at midnight
- Void reason is mandatory when transitioning to `CANCELLED`
- PDF watermark: CANCELLED invoices show diagonal "CANCELLED" overlay

---

## 2. Quotation

### States
- `DRAFT` — Initial state, editable
- `SENT` — Sent to customer
- `ACCEPTED` — Customer accepted
- `REJECTED` — Customer rejected
- `EXPIRED` — Valid until date passed (auto background job)
- `REVISED` — New revision created (creates new Quotation record with revision_number++)
- `CONVERTED` — Converted to Invoice/CPO

### Valid Transitions

```
DRAFT → SENT (via /send endpoint)
DRAFT → REVISED (creates new Quotation with revision_number++)
DRAFT → CANCELLED

SENT → ACCEPTED (customer acceptance)
SENT → REJECTED (customer rejection)
SENT → EXPIRED (automatic: valid_until < today)
SENT → REVISED (creates new revision)
SENT → CONVERTED (to Invoice or CPO)

ACCEPTED → CONVERTED (to Invoice/CPO)
ACCEPTED → REVISED (if customer requests changes after acceptance)

REJECTED → [terminal]
EXPIRED → REVISED (can revive with new dates)
CONVERTED → [terminal]
```

### Invalid Transitions
- `SENT → DRAFT` — Cannot un-send
- `CONVERTED → any` — Terminal state
- `REJECTED → ACCEPTED` — Cannot reverse rejection

### Business Rules
- Quotation can only be edited in `DRAFT` state
- Revision creates new record with incremented `revision_number`
- Original quotation status becomes `REVISED`
- `EXPIRED` status set by background job daily at midnight
- Converting to Invoice/CPO auto-sets status to `CONVERTED`

---

## 3. Customer Purchase Order (CPO)

### States
- `RECEIVED` — Received from customer (initial state)
- `CONFIRMED` — Confirmed after credit check
- `PARTIALLY_INVOICED` — Some items invoiced
- `FULLY_INVOICED` — All items invoiced
- `CLOSED` — Manually closed (all work complete)
- `CANCELLED` — Cancelled with reason

### Valid Transitions

```
RECEIVED → CONFIRMED (after credit check passes)
RECEIVED → CANCELLED (before confirmation)

CONFIRMED → PARTIALLY_INVOICED (first invoice created against this CPO)
CONFIRMED → FULLY_INVOICED (all line items invoiced in single invoice)
CONFIRMED → CANCELLED (with reason)

PARTIALLY_INVOICED → FULLY_INVOICED (when all line items invoiced)
PARTIALLY_INVOICED → CLOSED (manual closure, even if not fully invoiced)
PARTIALLY_INVOICED → CANCELLED (with reason)

FULLY_INVOICED → CLOSED (manual closure after all deliveries complete)

CLOSED → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `RECEIVED → PARTIALLY_INVOICED` — Must confirm first
- `FULLY_INVOICED → PARTIALLY_INVOICED` — Cannot reverse invoicing
- `CLOSED → any` — Terminal state
- `CANCELLED → any` — Terminal state

### Business Rules
- CPO confirmation blocked if `client.credit_status = HOLD` (unless authorized override)
- Each CPO line item tracks `invoiced_quantity` and `delivered_quantity`
- `FULLY_INVOICED` auto-set when `SUM(invoiced_quantity) >= ordered_quantity` for all line items
- Credit check runs on transition `RECEIVED → CONFIRMED`

---

## 4. Supplier Purchase Order (SPO)

### States
- `DRAFT` — Initial state, editable
- `PENDING_APPROVAL` — Submitted for approval (if `workspace.require_po_approval = true`)
- `APPROVED` — Approved by authorized user
- `SENT` — Sent to supplier
- `ACKNOWLEDGED` — Supplier acknowledged receipt
- `REJECTED` — Supplier rejected order
- `PARTIALLY_RECEIVED` — Some items received (GRN created)
- `FULLY_RECEIVED` — All items received
- `PARTIALLY_CANCELLED` — Some line items cancelled
- `CANCELLED` — Entire order cancelled
- `CLOSED` — Manually closed

### Valid Transitions

```
DRAFT → PENDING_APPROVAL (if require_po_approval = true)
DRAFT → APPROVED (if require_po_approval = false, auto-approved)
DRAFT → SENT (if no approval required)
DRAFT → CANCELLED

PENDING_APPROVAL → APPROVED (by authorized user)
PENDING_APPROVAL → REJECTED (by approver)
PENDING_APPROVAL → CANCELLED

APPROVED → SENT (send to supplier)
APPROVED → CANCELLED

SENT → ACKNOWLEDGED (supplier confirms)
SENT → REJECTED (supplier rejects)
SENT → PARTIALLY_RECEIVED (first GRN created)
SENT → FULLY_RECEIVED (all items received in one GRN)
SENT → PARTIALLY_CANCELLED (some line items cancelled)
SENT → CANCELLED

ACKNOWLEDGED → PARTIALLY_RECEIVED (first GRN)
ACKNOWLEDGED → FULLY_RECEIVED (all in one GRN)
ACKNOWLEDGED → PARTIALLY_CANCELLED
ACKNOWLEDGED → CANCELLED

PARTIALLY_RECEIVED → FULLY_RECEIVED (when all line items received)
PARTIALLY_RECEIVED → PARTIALLY_CANCELLED (cancel remaining items)
PARTIALLY_RECEIVED → CLOSED (manual closure)

FULLY_RECEIVED → CLOSED (after invoicing complete)

REJECTED → CANCELLED
CLOSED → [terminal]
CANCELLED → [terminal]
PARTIALLY_CANCELLED → [terminal for cancelled items, CLOSED for order]
```

### Invalid Transitions
- `SENT → DRAFT` — Cannot un-send
- `APPROVED → PENDING_APPROVAL` — Cannot reverse approval
- `FULLY_RECEIVED → PARTIALLY_RECEIVED` — Cannot reverse receipt
- `CLOSED → any` — Terminal state
- `CANCELLED → any` — Terminal state

### Business Rules
- SPO can only be edited in `DRAFT` state
- Approval workflow skipped if `workspace.require_po_approval = false`
- Each line item tracks `received_quantity` and `invoiced_quantity`
- `FULLY_RECEIVED` auto-set when `SUM(received_quantity) >= ordered_quantity` for all line items
- Gapless numbering enforced via `SELECT FOR UPDATE`

---

## 5. RFQ (Request for Quotation)

### States
- `DRAFT` — Initial state, editable
- `SENT` — Sent to suppliers
- `PARTIALLY_RESPONDED` — Some suppliers responded
- `FULLY_RESPONDED` — All invited suppliers responded
- `CLOSED` — Supplier selected, RFQ complete
- `EXPIRED` — Due date passed without full response
- `CANCELLED` — RFQ cancelled

### Valid Transitions

```
DRAFT → SENT (send to suppliers)
DRAFT → CANCELLED

SENT → PARTIALLY_RESPONDED (first supplier response received)
SENT → FULLY_RESPONDED (all suppliers responded)
SENT → EXPIRED (automatic: due_date < today without full response)
SENT → CANCELLED

PARTIALLY_RESPONDED → FULLY_RESPONDED (all suppliers responded)
PARTIALLY_RESPONDED → CLOSED (supplier selected even with partial response)
PARTIALLY_RESPONDED → EXPIRED (due date passed)
PARTIALLY_RESPONDED → CANCELLED

FULLY_RESPONDED → CLOSED (supplier selected)
FULLY_RESPONDED → CANCELLED

EXPIRED → CLOSED (can still select supplier after expiry)
EXPIRED → CANCELLED

CLOSED → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `SENT → DRAFT` — Cannot un-send
- `CLOSED → any` — Terminal state
- `CANCELLED → any` — Terminal state

### Business Rules
- RFQ can only be edited in `DRAFT` state
- `EXPIRED` status set by background job daily at midnight
- Supplier selection creates SPO and sets RFQ status to `CLOSED`
- Other suppliers' responses set to `REJECTED` when one is `SELECTED`

---

## 6. Supplier RFQ Response

### States
- `PENDING` — Awaiting supplier response
- `RECEIVED` — Supplier submitted quote
- `SELECTED` — This supplier's quote was chosen
- `REJECTED` — Another supplier was chosen
- `DECLINED` — Supplier declined to quote
- `EXPIRED` — Valid until date passed

### Valid Transitions

```
PENDING → RECEIVED (supplier submits quote)
PENDING → DECLINED (supplier declines to quote)
PENDING → EXPIRED (automatic: valid_until < today)

RECEIVED → SELECTED (buyer chooses this supplier)
RECEIVED → REJECTED (buyer chooses another supplier)
RECEIVED → EXPIRED (quote validity expired)

SELECTED → [terminal]
REJECTED → [terminal]
DECLINED → [terminal]
EXPIRED → [terminal]
```

### Invalid Transitions
- `SELECTED → REJECTED` — Cannot reverse selection
- `REJECTED → SELECTED` — Selection is final
- All terminal states disallow transitions

### Business Rules
- Only one response can be `SELECTED` per RFQ
- When one response is `SELECTED`, all others auto-set to `REJECTED`
- `EXPIRED` status set by background job daily

---

## 7. Goods Receipt Note (GRN)

### States
- `DRAFT` — Initial state, editable
- `RECEIVING` — Receiving in progress
- `PENDING_INSPECTION` — All items received, awaiting inspection
- `PARTIALLY_ACCEPTED` — Some items accepted, some rejected
- `ACCEPTED` — All items accepted
- `PARTIALLY_REJECTED` — Some items accepted, some rejected
- `REJECTED` — All items rejected
- `CANCELLED` — GRN cancelled

### Valid Transitions

```
DRAFT → RECEIVING (start receiving process)
DRAFT → CANCELLED

RECEIVING → PENDING_INSPECTION (all items received, needs inspection)
RECEIVING → PARTIALLY_ACCEPTED (inspection started, some accepted)
RECEIVING → ACCEPTED (all items accepted without inspection required)
RECEIVING → CANCELLED

PENDING_INSPECTION → ACCEPTED (all items pass inspection)
PENDING_INSPECTION → PARTIALLY_ACCEPTED (some pass, some fail)
PENDING_INSPECTION → REJECTED (all items fail inspection)
PENDING_INSPECTION → CANCELLED

PARTIALLY_ACCEPTED → [terminal]
ACCEPTED → [terminal]
PARTIALLY_REJECTED → [terminal]
REJECTED → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `ACCEPTED → RECEIVING` — Cannot reverse acceptance
- `REJECTED → ACCEPTED` — Cannot reverse rejection
- All terminal states disallow transitions

### Business Rules
- GRN can only be edited in `DRAFT` state
- Only `quantity_accepted` increases inventory (not `quantity_received`)
- Per-item acceptance: `quantity_accepted + quantity_rejected + quantity_damaged = quantity_received`
- StockTransaction created only on acceptance
- Rejection reason mandatory for rejected items

---

## 8. Supplier Invoice

### States
- `RECEIVED` — Received from supplier (initial state)
- `PENDING_MATCHING` — Awaiting 3-way match check
- `MATCHED` — Passed 3-way match
- `DISCREPANCY` — Failed 3-way match, needs review
- `APPROVED` — Approved for payment
- `PARTIALLY_PAID` — Partial payment made
- `PAID` — Fully paid
- `CANCELLED` — Invoice cancelled

### Valid Transitions

```
RECEIVED → PENDING_MATCHING (automatic on creation)

PENDING_MATCHING → MATCHED (3-way match passed)
PENDING_MATCHING → DISCREPANCY (3-way match failed)
PENDING_MATCHING → CANCELLED

MATCHED → APPROVED (authorized user approves)
MATCHED → CANCELLED

DISCREPANCY → MATCHED (after resolution and re-check)
DISCREPANCY → APPROVED (authorized override approval)
DISCREPANCY → CANCELLED

APPROVED → PARTIALLY_PAID (first payment made)
APPROVED → PAID (full payment made)
APPROVED → CANCELLED

PARTIALLY_PAID → PAID (final payment made)

PAID → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `MATCHED → RECEIVED` — Cannot reverse match
- `PAID → PARTIALLY_PAID` — Cannot reverse payment
- `PAID → APPROVED` — Cannot un-pay
- `CANCELLED → any` — Terminal state

### Business Rules
- 3-way match runs automatically on transition `RECEIVED → PENDING_MATCHING`
- Match checks: quantity (invoice ≤ GRN accepted), price (variance ≤ `workspace.price_tolerance_percent`), tax
- Payment blocked if `three_way_match_status = DISCREPANCY` unless authorized override
- Duplicate invoice number check per supplier
- Payment records are immutable

---

## 9. Delivery Order (DO)

### States
- `PENDING` — Initial state, awaiting dispatch
- `PARTIAL` — Partially delivered
- `DELIVERED` — Fully delivered
- `RETURNED` — Customer returned goods (creates SalesReturn)

### Valid Transitions

```
PENDING → PARTIAL (partial dispatch, some items delivered)
PENDING → DELIVERED (full dispatch, all items delivered)
PENDING → RETURNED (customer rejected delivery)

PARTIAL → DELIVERED (remaining items delivered)
PARTIAL → RETURNED (customer returned partial delivery)

DELIVERED → RETURNED (customer returns after acceptance)

RETURNED → [terminal]
```

### Invalid Transitions
- `DELIVERED → PENDING` — Cannot reverse delivery
- `RETURNED → PENDING` — Cannot reverse return

### Business Rules
- DO dispatch blocked if `client.credit_status = HOLD` and `workspace.block_do_on_hold = true`
- Must have active `StockReservation` before dispatch
- Stock movement happens on dispatch (not on reservation)
- `DELIVERED` auto-set when `SUM(delivered_quantity) >= ordered_quantity` for all line items

---

## 10. Customer Credit Status

### States
- `ACTIVE` — Normal trading status
- `WARNING` — Overdue > `workspace.credit_warning_days`
- `HOLD` — Overdue > `workspace.credit_hold_days` OR outstanding > `credit_limit`
- `SUSPENDED` — Management decision, manual only

### Valid Transitions

```
ACTIVE → WARNING (automatic: overdue_age > credit_warning_days)
ACTIVE → HOLD (automatic: overdue_age > credit_hold_days OR outstanding > credit_limit)
ACTIVE → SUSPENDED (manual by authorized user with reason)

WARNING → ACTIVE (automatic: overdue cleared)
WARNING → HOLD (automatic: overdue_age > credit_hold_days OR outstanding > credit_limit)
WARNING → SUSPENDED (manual)

HOLD → ACTIVE (automatic: overdue cleared + manual release by authorized user)
HOLD → SUSPENDED (manual)

SUSPENDED → ACTIVE (manual release by authorized user with reason)
```

### Invalid Transitions
- `HOLD → WARNING` — Must clear overdue first, then goes to ACTIVE
- `SUSPENDED → WARNING` — Suspended is manual override, goes directly to ACTIVE

### Business Rules
- Credit check runs on: CPO confirmation, Invoice creation, DO release
- Overdue = any invoice where `due_date < today AND balance_due > 0`
- Outstanding = TOTAL `balance_due` across all active invoices
- `HOLD` blocks CPO confirmation and DO release (unless authorized override)
- `HOLD` does NOT block payments, statements, or enquiries
- Credit status changes audited with `changed_by`, `changed_at`, `reason`
- Background job runs daily at midnight to auto-update credit status

---

## 11. PDC (Post-Dated Cheque) Lifecycle

### States
- `PDC_PENDING` — Cheque received, not yet deposited
- `PRESENTED` — Deposited to bank for clearing
- `CLEARED` — Successfully cleared (payment complete)
- `BOUNCED` — Failed to clear (alert raised, ledger reversed)

### Valid Transitions

```
PDC_PENDING → PRESENTED (deposited to bank on/after cheque_date)

PRESENTED → CLEARED (bank confirms clearing)
PRESENTED → BOUNCED (bank rejects cheque)

CLEARED → [terminal]
BOUNCED → [terminal]
```

### Invalid Transitions
- `PRESENTED → PDC_PENDING` — Cannot un-present
- `CLEARED → BOUNCED` — Cannot reverse clearing
- `BOUNCED → CLEARED` — Cannot reverse bounce

### Business Rules
- PDC cannot be presented before `cheque_date`
- On `CLEARED`: Invoice `balance_due` reduced, `amount_paid` increased
- On `BOUNCED`: Invoice `balance_due` restored, Payment record remains immutable but PDC status updated
- Customer flagged on bounce, credit status may auto-change to `HOLD`
- Alert/notification sent to authorized users on bounce

---

## 12. Stock Transfer

### States
- `DRAFT` — Initial state, editable
- `REQUESTED` — Submitted for approval
- `APPROVED` — Approved by authorized user
- `IN_TRANSIT` — Goods removed from source warehouse
- `PARTIALLY_RECEIVED` — Some items received at destination
- `RECEIVED` — All items received at destination
- `CANCELLED` — Transfer cancelled

### Valid Transitions

```
DRAFT → REQUESTED (submit for approval)
DRAFT → CANCELLED

REQUESTED → APPROVED (authorized user approves)
REQUESTED → CANCELLED (authorized user rejects)

APPROVED → IN_TRANSIT (dispatch from source warehouse)
APPROVED → CANCELLED

IN_TRANSIT → PARTIALLY_RECEIVED (some items received at destination)
IN_TRANSIT → RECEIVED (all items received)

PARTIALLY_RECEIVED → RECEIVED (remaining items received)

RECEIVED → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `IN_TRANSIT → APPROVED` — Cannot reverse dispatch
- `RECEIVED → IN_TRANSIT` — Cannot reverse receipt
- `CANCELLED → any` — Terminal state

### Business Rules
- Stock removed from source warehouse on `APPROVED → IN_TRANSIT`
- Stock added to destination warehouse on `IN_TRANSIT → RECEIVED` (or `PARTIALLY_RECEIVED`)
- `quantity_in_transit` tracked separately in WarehouseStock
- StockTransaction created at both source and destination on state changes

---

## 13. Stock Adjustment

### States
- `PENDING_APPROVAL` — Submitted for approval
- `APPROVED` — Approved and applied to inventory
- `REJECTED` — Rejected by authorized user

### Valid Transitions

```
PENDING_APPROVAL → APPROVED (authorized user approves)
PENDING_APPROVAL → REJECTED (authorized user rejects with reason)

APPROVED → [terminal]
REJECTED → [terminal]
```

### Invalid Transitions
- `APPROVED → PENDING_APPROVAL` — Cannot reverse approval
- `APPROVED → REJECTED` — Cannot reverse after inventory updated
- All terminal states disallow transitions

### Business Rules
- Adjustment creator cannot approve own adjustment
- StockTransaction created on `APPROVED`
- WarehouseStock updated on `APPROVED`
- Reason mandatory (DAMAGE, LOSS, THEFT, COUNT_CORRECTION, EXPIRY, OTHER)
- Large variances (>10% or >1000 units) may require additional authorization

---

## 14. Stock Count

### States
- `DRAFT` — Initial state, editable
- `COUNTING` — Count in progress
- `VARIANCE_REVIEW` — Count complete, variances under review
- `APPROVED` — Variances approved
- `ADJUSTMENT_POSTED` — StockAdjustment created and posted
- `CLOSED` — Count finalized

### Valid Transitions

```
DRAFT → COUNTING (start count)

COUNTING → VARIANCE_REVIEW (count complete, variances found)
COUNTING → CLOSED (count complete, zero variance)

VARIANCE_REVIEW → APPROVED (authorized user approves variances)
VARIANCE_REVIEW → COUNTING (re-count required)

APPROVED → ADJUSTMENT_POSTED (StockAdjustment created and posted)

ADJUSTMENT_POSTED → CLOSED (finalize count)

CLOSED → [terminal]
```

### Invalid Transitions
- `APPROVED → DRAFT` — Cannot reverse approval
- `ADJUSTMENT_POSTED → VARIANCE_REVIEW` — Cannot reverse after posting
- `CLOSED → any` — Terminal state

### Business Rules
- Count locks product in that warehouse (no other stock movements allowed during count)
- Variance = `counted_quantity - system_quantity`
- Zero variance → direct to `CLOSED`
- Non-zero variance → requires approval
- StockAdjustment auto-created on approval
- All variances logged with notes

---

## 15. Procurement Request

### States
- `DRAFT` — Initial state, editable
- `SUBMITTED` — Submitted for review
- `UNDER_REVIEW` — Being reviewed by authorized user
- `APPROVED` — Approved, ready to create RFQ/SPO
- `REJECTED` — Rejected with reason
- `PARTIALLY_ORDERED` — Some items ordered (SPO created)
- `FULLY_ORDERED` — All items ordered
- `FULFILLED` — All items received and closed
- `CANCELLED` — PR cancelled

### Valid Transitions

```
DRAFT → SUBMITTED (submit for review)
DRAFT → CANCELLED

SUBMITTED → UNDER_REVIEW (reviewer opens PR)
SUBMITTED → CANCELLED

UNDER_REVIEW → APPROVED (reviewer approves)
UNDER_REVIEW → REJECTED (reviewer rejects with reason)
UNDER_REVIEW → CANCELLED

APPROVED → PARTIALLY_ORDERED (first SPO created)
APPROVED → FULLY_ORDERED (all items ordered in one SPO)
APPROVED → CANCELLED

PARTIALLY_ORDERED → FULLY_ORDERED (remaining items ordered)
PARTIALLY_ORDERED → FULFILLED (early closure, not all items ordered)
PARTIALLY_ORDERED → CANCELLED

FULLY_ORDERED → FULFILLED (all SPOs received and GRNs complete)

FULFILLED → [terminal]
REJECTED → [terminal]
CANCELLED → [terminal]
```

### Invalid Transitions
- `APPROVED → DRAFT` — Cannot reverse approval
- `FULLY_ORDERED → PARTIALLY_ORDERED` — Cannot reverse ordering
- `FULFILLED → any` — Terminal state

### Business Rules
- PR can only be edited in `DRAFT` state
- Each line item tracks `ordered_quantity` (linked to SPO items)
- `FULLY_ORDERED` auto-set when all line items have SPOs
- `FULFILLED` auto-set when all linked SPOs are `FULLY_RECEIVED`

---

## Common State Machine Rules (All Document Types)

1. **Terminal states** (`CLOSED`, `CANCELLED`, `FULFILLED`, `REJECTED`, `PAID`, `DELIVERED`, `RECEIVED`) disallow all transitions
2. **Audit trail** — Every state transition logged with `changed_by`, `changed_at`, `previous_status`, `new_status`, `reason`
3. **Authorization** — Certain transitions require specific roles (e.g., `APPROVED`, `CANCELLED`)
4. **Immutability** — Documents in non-DRAFT states cannot be edited (fields locked)
5. **Validation** — Service layer validates transitions before persisting
6. **Reason mandatory** — Transitions to `CANCELLED`, `REJECTED`, `SUSPENDED` require `reason` field
7. **Background jobs** — Auto-transitions (`OVERDUE`, `EXPIRED`, `WARNING`, `HOLD`) run daily at midnight UTC
8. **Idempotency** — Applying same transition twice returns success (no-op)

---

**End of State Machine Specification**
