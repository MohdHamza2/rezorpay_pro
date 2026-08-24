# Supplier Purchase Order (SPO) Architecture
*InvoiceSaaS B2B Trading Platform — Wave 0 Specification — Step 4 Detail*

## 4.1 Architectural Principle
An SPO is the first document in the chain that is legally binding and financially material. Everything before it (PR, RFQ, Quote, Award) is reversible with zero external consequence. Everything after it (GRN, SupplierInvoice, SupplierPayment) is reconciliation against this commitment — never a new commitment.

Extending Step 3's document-nature table:

| Document | Nature | Legal weight | Financial effect | Inventory effect |
| :--- | :--- | :--- | :--- | :--- |
| PR / RFQ / Quote / Award | Discovery/decision | None | None | None |
| SPO | Commitment | Binding | AP exposure begins | quantity_on_order ↑ (C-17) |
| GRN | Physical event | None (confirms SPO) | None directly | quantity_on_hand ↑, quantity_on_order ↓ |
| SupplierInvoice | AP document | Confirms debt | Payable created | None |

Three governing invariants:

*   **INV-4.1 (Commitment Freeze):** Once SENT, quantity_ordered, unit_price, and delivery_terms are frozen. The only way to change them is a tracked SPOAmendment — never a silent edit (mirrors Step 1's Master/Transaction Snapshot Rule).
*   **INV-4.2 (Three-Axis Separation):** ordered (what we committed), confirmed (what supplier promised), and received/accepted (physical reality) are independent counters that must never be conflated or overwritten by each other.
*   **INV-4.3 (No Backward Contamination):** A later change to SupplierProduct.current_purchase_price or Supplier.payment_terms_days must never mutate an already-sent SPO's snapshotted values.

## 4.2 Core Entities

### SupplierPurchaseOrder (Header)
*   `id`, `workspace_id`, `supplier_id`
*   `spo_number`: str (gapless, SPO-2026-000001) (C-26)
*   `rfq_id`: UUID (nullable) (denormalized convenience C-18)
*   `procurement_request_id`: UUID (nullable) (direct-path only, no RFQ involved)
*   `procurement_method`: Enum [RFQ, DIRECT, CONTRACT, EMERGENCY]
*   `single_source_justification`: Text (MANDATORY if procurement_method = EMERGENCY)
*   `supplier_reference`: str (their PO/order ref)
*   `status`: Enum [DRAFT, PENDING_APPROVAL, APPROVED, SENT, PARTIALLY_ACKNOWLEDGED, ACKNOWLEDGED, REJECTED, PARTIALLY_RECEIVED, FULLY_RECEIVED, SHORT_CLOSED, PARTIALLY_CANCELLED, CANCELLED, CLOSED]
*   `po_date`, `expected_delivery_date`: date (header default; overridden per-tranche if schedule exists)
*   `warehouse_id`: UUID
*   `currency`: str
*   `payment_terms_days`: int
*   `delivery_terms`: str
*   `subtotal`, `vat_amount`, `total_amount`: Decimal(12,2)
*   `quantity_ordered_total`: Decimal(12,4) (derived, Σ items C-25)
*   `quantity_confirmed_total`: Decimal(12,4) (derived, Σ items C-25)
*   `quantity_backordered_total`: Decimal(12,4) (derived C-25)
*   `has_open_amendment`: bool (derived — blocks certain transitions)
*   `approved_by`, `approved_at`, `sent_at`, `acknowledged_at`, `closed_at`
*   `created_at`, `updated_at`
*   → `items`: List[SupplierPurchaseOrderItem]
*   → `amendments`: List[SPOAmendment]
*   → `status_history`: List[SPOStatusHistory]

### SupplierPurchaseOrderItem
*   `id`, `spo_id`
*   `line_number`: int
*   `rfq_award_line_id`: UUID (nullable) (true traceability link C-18)
*   `procurement_request_item_id`: UUID (nullable)
*   `product_id`, `internal_sku`, `supplier_sku`, `description`: str
*   `uom_id`: UUID
*   `quantity_ordered`: Decimal(12,4) (FROZEN once SENT INV-4.1)
*   `quantity_confirmed`: Decimal(12,4) (default = ordered until supplier responds)
*   `quantity_backordered`: Decimal(12,4) (derived = ordered − confirmed)
*   `quantity_received`: Decimal(12,4) (derived, Σ GRNItem.quantity_received)
*   `quantity_accepted`: Decimal(12,4) (derived, Σ GRNItem.quantity_accepted)
*   `quantity_damaged_rejected`: Decimal(12,4) (derived, Σ GRNItem damaged+rejected)
*   `quantity_invoiced`: Decimal(12,4) (derived, Σ SupplierInvoiceItem.quantity C-23)
*   `quantity_cancelled`: Decimal(12,4) (default 0, set only via cancellation flow)
*   `open_quantity`: Decimal(12,4) (derived = confirmed − received − cancelled)
*   `unit_price`: Decimal(12,2) (FROZEN once SENT INV-4.1)
*   `discount_percent`, `vat_rate`: Decimal(5,2)
*   `vat_amount`, `total_price`: Decimal(12,2)
*   `price_amendment_pending`: bool (true while awaiting buyer approval §4.5)
*   `expected_delivery_date`: date (implicit single-tranche default C-19)

### SPODeliverySchedule (new — C-19)
*   `id`, `spo_item_id`
*   `tranche_number`: int
*   `scheduled_quantity`: Decimal(12,4)
*   `scheduled_date`: date
*   `status`: Enum [PENDING, IN_TRANSIT, DELIVERED, DELAYED, CANCELLED]
*   `delayed_flagged_at`: datetime (nullable) (set by background job)
*   `created_at`, `updated_at`

### SPOAmendment + SPOAmendmentLine (new — C-20)
**SPOAmendment:**
*   `id`, `spo_id`
*   `amendment_number`: int (sequential per SPO)
*   `status`: Enum [PROPOSED, PENDING_APPROVAL, APPROVED, SUPPLIER_REJECTED, APPLIED, WITHDRAWN]
*   `reason`: Text (MANDATORY, min 10 chars)
*   `requires_supplier_reconfirmation`: bool
*   `amended_by`, `approved_by` (nullable)
*   `created_at`, `applied_at`

**SPOAmendmentLine:**
*   `id`, `amendment_id`, `spo_item_id`
*   `field_name`: Enum [QUANTITY_ORDERED, UNIT_PRICE, DELIVERY_DATE, DELIVERY_TERMS, OTHER]
*   `old_value`, `new_value`: str

### SPOStatusHistory (new — immutable, mirrors StockTransaction discipline)
*   `id`, `spo_id`
*   `from_status`, `to_status`: str
*   `triggered_by`: UUID (FK → users, nullable for system jobs)
*   `trigger_reason`: str
*   `occurred_at`: datetime (IMMUTABLE, never updated/deleted)

## 4.3 State Machine v2
Valid States: DRAFT, PENDING_APPROVAL, APPROVED, SENT, PARTIALLY_ACKNOWLEDGED, ACKNOWLEDGED, REJECTED, PARTIALLY_RECEIVED, FULLY_RECEIVED, SHORT_CLOSED, PARTIALLY_CANCELLED, CANCELLED, CLOSED

```
DRAFT ──submit──► PENDING_APPROVAL ──approve──► APPROVED ──send──► SENT
                                                                      │
                        ┌─────────────────────────────────────────────┤
                        ▼                     ▼                       ▼
              ACKNOWLEDGED      PARTIALLY_ACKNOWLEDGED         REJECTED (all lines rejected)
             (all lines resp.)   (mixed line responses)             [terminal]
                        │                     │
                        └──────────┬──────────┘
                                   ▼
                        PARTIALLY_RECEIVED ──all confirmed qty received──► FULLY_RECEIVED
                                   │                                              │
                                   │                                              ▼
                        supplier will never deliver rest         Invoice APPROVED/PAID (dual-gate)
                                   ▼                                              │
                            SHORT_CLOSED                                         ▼
                            [terminal, reason mandatory]                      CLOSED
                                                                              [terminal]

Any pre-receipt state ──cancel, reason──► CANCELLED [terminal]
Any partial-receipt state ──cancel remainder, reason──► PARTIALLY_CANCELLED [terminal]
```

Transition rules:
*   **SENT → PARTIALLY_ACKNOWLEDGED:** fires when ≥1 line responds but not all lines are fully resolved (confirmed or rejected).
*   **SENT/PARTIALLY_ACKNOWLEDGED → ACKNOWLEDGED:** fires when every line has a quantity_confirmed set (even if 0) and no line is pending price-amendment.
*   **SENT → REJECTED:** only when every line has quantity_confirmed = 0 (full rejection).
*   **FULLY_RECEIVED → CLOSED:** dual-gate — requires both full receipt AND linked SupplierInvoice.status ∈ {APPROVED, PAID} (SPO-020 equivalent).
*   **has_open_amendment = true blocks SENT → ACKNOWLEDGED** and blocks new GRN creation until the amendment resolves (APPLIED or WITHDRAWN) — prevents receiving against terms mid-dispute.

## 4.4 Quantity Model & Reconciliation Chain (per line item)
```
quantity_ordered      (frozen at SENT — INV-4.1)
        │
        ▼  supplier response
quantity_confirmed    (≤ ordered, unless over-confirmation override enabled)
        │
        ▼  Σ SPODeliverySchedule.scheduled_quantity  should equal confirmed
        │
        ▼  physical delivery (possibly N GRNs, possibly N tranches)
quantity_received     = Σ GRNItem.quantity_received  where spo_item_id matches
        │
        ▼  QA inspection outcome
quantity_accepted     = Σ GRNItem.quantity_accepted   ← feeds WarehouseStock
quantity_damaged_rejected = Σ GRNItem (damaged + rejected)
        │
        ▼  AP matching (possibly N invoices — C-23)
quantity_invoiced     = Σ SupplierInvoiceItem.quantity where spo_item_id matches

open_quantity = quantity_confirmed − quantity_received − quantity_cancelled
```

## 4.5 Acknowledgement Handling
Per line, the supplier response resolves one of four outcomes:
*   **Full confirm:** confirmed = ordered, same price -> Line resolved, no flags
*   **Partial confirm:** 0 < confirmed < ordered -> quantity_backordered derived; line resolved
*   **Rejection:** confirmed = 0 -> Line marked rejected; does not by itself cancel — buyer decides re-source vs wait
*   **Price change on ack:** confirmed.unit_price ≠ spo.unit_price -> price_amendment_pending = true, auto-creates a SPOAmendment (type UNIT_PRICE) requiring buyer approval before the line counts as resolved — line stays in limbo, header stays PARTIALLY_ACKNOWLEDGED

## 4.6 Amendment & Cancellation
**Amendment (SPOAmendment)**
*   Any change to quantity_ordered, unit_price, expected_delivery_date, or delivery_terms on a SENT+ SPO must go through this entity — direct field edits are rejected by the API layer.
*   requires_supplier_reconfirmation = true for UNIT_PRICE and QUANTITY_ORDERED changes (the supplier must re-ack); false for internal notes.
*   Above workspace.spo_amendment_approval_threshold (new config, mirrors RFQ's award threshold, D-13 below): amendment requires maker-checker (amended_by ≠ approved_by).
*   SPO-013: An amendment cannot reduce quantity_ordered below quantity_received already recorded — you cannot amend away goods already physically received.

**Cancellation**
*   Full cancellation: valid only while no line has quantity_received > 0. → CANCELLED.
*   Partial cancellation: any line with quantity_received > 0 forces PARTIALLY_CANCELLED — the received portion proceeds normally, the remaining open_quantity on affected lines is zeroed with quantity_cancelled set.
*   Cascade (C-24): cancelling open quantity on a line decrements ProcurementRequestItem.ordered_quantity by that amount, reopening the shortage in the PR backlog for a fresh RFQ/Award/SPO cycle (new approval required — satisfies PR-010).
*   Blocked cancellation: cannot cancel a line with an open (unresolved) SupplierInvoice referencing it (SPO-017) — invoice must be resolved first.
*   Reason is mandatory on every cancellation; cancellations are terminal, never reversible (a changed mind requires a new SPO).

**Short-Close (new state, distinct from cancellation)**
*   Used when the supplier has delivered what they're going to deliver and both parties agree not to pursue the remaining open_quantity (common in trading — a drum run short by 40m is written off, not "cancelled" as a dispute).
*   PARTIALLY_RECEIVED → SHORT_CLOSED: requires short_close_reason, decrements the source PR item's ordered_quantity by the unresolved open quantity (same cascade as cancellation), but is semantically distinct for reporting (short-close = fulfilled-as-far-as-possible; cancellation = commercial withdrawal).

## 4.7 PO-to-GRN Reconciliation & Over-Receipt Policy
*   Reconciliation view, per line (GET /spos/{id}/reconciliation): ordered · confirmed · scheduled (Σ tranches) · received · accepted · damaged_rejected · invoiced · open_quantity · variance_flag
*   Multiple GRNs per SPO line (Edge Case, MP §10): fully supported — quantity_received/quantity_accepted are cumulative rollups, never overwritten, across any number of GRN postings (including against different SPODeliverySchedule tranches — C-22).
*   Multiple SPOs per invoice / one invoice covering multiple SPOs (Edge Case, MP §10): resolved by C-23 — matching happens at SupplierInvoiceItem.spo_item_id granularity; the header spo_id on SupplierInvoice is cosmetic only.
*   Over-receipt (the flagged question): a GRN line attempting to receive beyond quantity_confirmed is evaluated against workspace.over_receipt_tolerance_percent. Within tolerance → auto-accepted with variance_flag = true (visible, never silent). Beyond tolerance → hard-blocked pending manual override + reason.
*   Under-delivery closure: handled by SHORT_CLOSED (§4.6) rather than leaving POs open indefinitely.

## 4.8 Business Rules — SPO Series
**Structural & Traceability**
*   SPO-001: Every SPO item traces to either an rfq_award_line_id (RFQ path) or a procurement_request_item_id (direct path) or carries single_source_justification (emergency path) — no orphan commitments.
*   SPO-002: One PR item's shortage may be fulfilled across multiple SPOs/suppliers; ordered_quantity on the PR item is a rolling sum across all linked SPO items, never overwritten.
*   SPO-003: Cross-workspace references (supplier, product, warehouse) are hard-rejected, mirroring RFQ-002/PR-013.

**Commitment Freeze (INV-4.1)**
*   SPO-004: quantity_ordered, unit_price, delivery_terms are immutable once SENT — changes only via SPOAmendment.
*   SPO-005: Price change on acknowledgement creates a PENDING SPOAmendment; the line cannot resolve until approved.

**Acknowledgement**
*   SPO-006: quantity_confirmed > quantity_ordered is blocked unless workspace.allow_over_confirmation = true.
*   SPO-007: quantity_backordered, header totals, and open_quantity are always derived, never directly settable (C-25).
*   SPO-008: Header REJECTED only when all lines reject; mixed responses → PARTIALLY_ACKNOWLEDGED (C-16).

**Delivery Schedule**
*   SPO-009: Σ SPODeliverySchedule.scheduled_quantity per line must equal quantity_confirmed.
*   SPO-010: Missing schedule defaults to one implicit tranche using the line's expected_delivery_date.
*   SPO-011: A background job auto-flags PENDING → DELAYED when scheduled_date < today; informational only, non-blocking.

**Amendment**
*   SPO-012: Every amendment requires reason (min 10 chars); above threshold requires maker-checker.
*   SPO-013: Cannot amend quantity_ordered below already-quantity_received.
*   SPO-014: has_open_amendment = true blocks new GRN creation and blocks → ACKNOWLEDGED transition.

**Cancellation & Short-Close**
*   SPO-015: Full cancellation valid only pre-receipt; else PARTIALLY_CANCELLED.
*   SPO-016: Cancellation/short-close of open quantity cascades a decrement to the source PR item's ordered_quantity (C-24).
*   SPO-017: Cannot cancel a line with an open unresolved SupplierInvoice.
*   SPO-018: Reason mandatory on all cancellations/short-closes; both are terminal and non-reversible.

**Reconciliation**
*   SPO-019: Multiple GRNs per line accumulate via rollup, never overwrite (supports partial shipments).
*   SPO-020: CLOSED requires dual-gate: full receipt (or short-close) and invoice APPROVED/PAID.
*   SPO-021: Reconciliation variances (over-receipt within tolerance, price/qty mismatches) are always surfaced via variance_flag, never silently absorbed.
*   SPO-022: Over-receipt beyond workspace.over_receipt_tolerance_percent is hard-blocked pending manual override + reason.

**Lifecycle & Audit**
*   SPO-023: Every state transition writes an immutable SPOStatusHistory row (who, when, from→to, trigger reason).
*   SPO-024: spo_number gapless, 6-digit, unique per workspace (C-26).
*   SPO-025: SPO cannot be hard-deleted once SENT; cancel/short-close only.
*   SPO-026: WarehouseStock.quantity_on_order increments on SENT (by quantity_ordered), decrements on GRN acceptance, cancellation, or short-close (C-17).

## 4.10 API Contracts — SPO Domain
| Method | Path | Purpose | Allowed states |
| :--- | :--- | :--- | :--- |
| POST | `/api/v1/spos` | Create draft | — |
| PATCH | `/api/v1/spos/{id}` | Edit header | DRAFT |
| POST | `/api/v1/spos/{id}/submit-approval` | → PENDING_APPROVAL | DRAFT |
| POST | `/api/v1/spos/{id}/approve` | → APPROVED | PENDING_APPROVAL |
| POST | `/api/v1/spos/{id}/send` | Dispatch to supplier, → SENT | APPROVED |
| POST | `/api/v1/spos/{id}/items/{item_id}/acknowledge` | Record supplier response per line | SENT, PARTIALLY_ACKNOWLEDGED |
| POST | `/api/v1/spos/{id}/items/{item_id}/delivery-schedule` | Create/update tranches | ACKNOWLEDGED+ |
| POST | `/api/v1/spos/{id}/amendments` | Propose amendment | any non-terminal |
| POST | `/api/v1/spos/{id}/amendments/{aid}/approve` | Maker-checker approval | PENDING_APPROVAL |
| POST | `/api/v1/spos/{id}/amendments/{aid}/apply` | Apply after supplier reconfirmation | APPROVED |
| POST | `/api/v1/spos/{id}/cancel` | Full/partial cancel, reason mandatory | any pre/partial-receipt |
| POST | `/api/v1/spos/{id}/short-close` | Short-close remaining open qty, reason mandatory | PARTIALLY_RECEIVED |
| GET | `/api/v1/spos/{id}/reconciliation` | Ordered/confirmed/received/accepted/invoiced view | — |
| GET | `/api/v1/spos?status=&supplier_id=&delayed_tranches=true` | List/filter | — |
| GET | `/api/v1/spos/{id}/status-history` | Full audit trail | — |

## Adopted Design Recommendations (D-11 to D-18)
*   **D-11:** Over-receipt tolerance is %-based via `workspace.over_receipt_tolerance_percent` (default 2%).
*   **D-12:** Short-close approval threshold matches the cancellation/amendment approval threshold.
*   **D-13:** Amendment approval threshold is `workspace.spo_amendment_approval_threshold` (default 0).
*   **D-14:** Price-change-on-ack triggers lightweight `price_amendment_pending` flag, not full re-approval.
*   **D-15:** Single warehouse per SPO in MVP (no split shipments at line level).
*   **D-16:** `SupplierInvoice.spo_id` is informational-only; matching is at the item level (`spo_item_id`).
*   **D-17:** `quantity_on_order` increments on **SENT** (not ACKNOWLEDGED).
*   **D-18:** Gapless 6-digit document numbering (`SPO-2026-000001`).
