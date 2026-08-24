# Goods Receipt Note (GRN) & Receiving Architecture
*InvoiceSaaS B2B Trading Platform — Wave 0 Specification — Step 5 Detail*

## 5.1 Architectural Principle
A GRN is a quality gate, not a rubber stamp. It is the only bridge between a paper commitment (SPO) and physical reality (Inventory). Nothing increases usable stock except an ACCEPTED disposition on a GRN line — never the act of receiving alone.

Extending the document-nature table from Steps 3–4:

| Document | Nature | Legal weight | Financial effect | Inventory effect |
| :--- | :--- | :--- | :--- | :--- |
| SPO | Commitment | Binding | AP exposure begins | quantity_on_order ↑ |
| GRN | Physical + Quality event | Confirms/disputes receipt | None directly (feeds valuation) | on_hand ↑ (accepted only), on_order ↓ (full received qty), damaged ↑ |
| SupplierInvoice | AP document | Confirms debt | Payable created | None |

Governing invariants:
*   **INV-5.1:** `quantity_received = quantity_accepted + quantity_damaged + quantity_rejected` — always, per line, no exceptions (C-28).
*   **INV-5.2:** Stock only posts on a line reaching a disposition (ACCEPTED/PARTIALLY_ACCEPTED/etc.) — never during RECEIVING or PENDING_INSPECTION.
*   **INV-5.3:** `unit_cost` for StockTransaction valuation is always the frozen SPO commitment price — never the (potentially disputed) invoice price (C-34).
*   **INV-5.4:** `quantity_on_order` decrements by the full `quantity_received` (accepted + damaged + rejected combined) the moment goods physically arrive. Disposition outcome only affects which stock bucket the goods land in.

## 5.2 Core Entities

### GoodsReceiptNote (Header)
*   `id`, `workspace_id`, `supplier_id`
*   `grn_number`: str (gapless, 6-digit — GRN-2026-000001)
*   `spo_id`: UUID (nullable) (informational-only, primary PO for display C-27)
*   `warehouse_id`: UUID
*   `received_date`: date
*   `received_by`: UUID (FK → users)
*   `delivery_reference`: str (supplier's shipment/delivery note ref)
*   `vehicle_number`, `driver_name`: str (nullable) (optional logistics capture)
*   `status`: Enum [DRAFT, RECEIVING, PENDING_INSPECTION, PARTIALLY_ACCEPTED, ACCEPTED, PARTIALLY_REJECTED, REJECTED, CANCELLED]
*   `stock_posted`: bool (derived — true once ≥1 line has posted, blocks cancellation C-32)
*   `notes`: Text
*   `created_at`, `updated_at`
*   → `items`: List[GRNItem]

### GRNItem
*   `id`, `grn_id`
*   `spo_item_id`: UUID (TRUE link C-27)
*   `spo_delivery_schedule_id`: UUID (nullable) (settles a specific tranche)
*   `product_id`, `internal_sku`, `description`: str
*   `uom_id`: UUID
*   `location_id`: UUID (nullable) (schema-ready, not enforced C-33)
*   `quantity_ordered_snapshot`: Decimal(12,4) (cached from SPO line for display)
*   `quantity_confirmed_snapshot`: Decimal(12,4) (cached from SPO line for display)
*   `quantity_received`: Decimal(12,4)
*   `quantity_accepted`: Decimal(12,4)
*   `quantity_damaged`: Decimal(12,4)
*   `quantity_rejected`: Decimal(12,4)
*   `batch_number`: str (nullable)
*   `expiry_date`: date (nullable)
*   `damage_reason`: Text (nullable, MANDATORY if quantity_damaged > 0)
*   `rejection_reason`: Text (nullable, MANDATORY if quantity_rejected > 0)
*   `inspected_by`: UUID (nullable, FK → users)
*   `inspected_at`: datetime (nullable)
*   `notes`: str

⚠️ `unit_cost` is deliberately not stored on GRNItem — it is pulled live from `spo_item.unit_price` at the moment StockTransaction is created (INV-5.3), never duplicated/cached here to avoid drift.

## 5.3 State Machine v2
Valid States: DRAFT, RECEIVING, PENDING_INSPECTION, PARTIALLY_ACCEPTED, ACCEPTED, PARTIALLY_REJECTED, REJECTED, CANCELLED

```
DRAFT ──truck arrives──► RECEIVING ──unloaded, staged──► PENDING_INSPECTION
                                                                  │
                    ┌─────────────────┬─────────────────┬────────┤
                    ▼                 ▼                 ▼        ▼
              ACCEPTED      PARTIALLY_ACCEPTED  PARTIALLY_REJECTED  REJECTED
           (all lines OK)   (mixed dispositions)  (mixed, mostly bad)  (all lines rejected)

DRAFT / RECEIVING / PENDING_INSPECTION ──cancel, reason──► CANCELLED
```
**Rule GRN-018 (C-32):** Once `stock_posted = true` (any line reached a disposition and created a StockTransaction), CANCELLED is permanently unavailable for this GRN. Correction must go through PurchaseReturn or disposition adjustment, never a GRN-level cancel.

## 5.4 Receiving Workflow
*   **DRAFT:** data pre-populated from SPODeliverySchedule tranche(s) expected today
*   **RECEIVING:** physical unloading in progress; quantity_received being counted/entered
*   **PENDING_INSPECTION:** staged in receiving area, awaiting QA disposition per line
*   **[disposition]:** each line independently resolved to accepted/damaged/rejected split
**Rule GRN-001:** A GRN cannot skip PENDING_INSPECTION explicitly — the audit trail must always show an inspection step occurred.

## 5.5 Quality Inspection & Disposition
*   **Rule GRN-002:** `quantity_damaged > 0` requires non-empty `damage_reason` (min 10 chars). Same for `quantity_rejected` / `rejection_reason`.
*   **Rule GRN-003:** `inspected_by` and `inspected_at` are set atomically when any disposition quantity is first recorded on a line.
*   **Rule GRN-004 (Rejected Goods Handling):** Rejected quantity never touches WarehouseStock. Finalizing a REJECTED disposition auto-generates a draft PurchaseReturn pre-filled with the rejected lines.
*   **Rule GRN-005 (Damaged Goods Handling):** Damaged quantity enters `WarehouseStock.quantity_damaged` but never `quantity_on_hand`. It can later move via `StockTransaction(RECLASSIFICATION_IN/OUT)` if reclassified.

## 5.6 Batch/Lot Tracking — Scope Decision
Kept intentionally lightweight for MVP: `batch_number` and `expiry_date` are simple fields on `GRNItem`, not a dedicated BatchLot entity.

## 5.7 Multi-SPO / Multi-Tranche Linkage
Because the true link is `GRNItem.spo_item_id` (C-27), one GRN can legitimately span multiple SPOs from the same supplier ("one truck, two purchase orders").

## 5.8 Stock Posting Logic
On each line reaching a disposition, the system atomically:
1. Create `StockTransaction(PURCHASE_RECEIPT, IN, quantity = quantity_accepted, unit_cost = spo_item.unit_price, reference_type = 'grn', reference_id = grn_item.id)`
2. `WarehouseStock.quantity_on_hand += quantity_accepted`
   `WarehouseStock.quantity_damaged += quantity_damaged`
   `WarehouseStock.quantity_on_order -= quantity_received`
3. SupplierPurchaseOrderItem rollups updated:
   `quantity_received += this GRN line's quantity_received`
   `quantity_accepted += this GRN line's quantity_accepted`
4. IF `quantity_rejected > 0`: auto-create draft PurchaseReturn line (Rule GRN-004)

*   **Rule GRN-006:** Steps 1–3 are a single atomic transaction with SELECT FOR UPDATE on the WarehouseStock row.
*   **Rule GRN-007:** Over-receipt validation (Step 4's D-11 tolerance) is checked at disposition time, not at raw quantity entry.

## 5.9 Business Rules — GRN Series
*   **GRN-001:** Every GRN passes through PENDING_INSPECTION explicitly.
*   **GRN-008:** Every GRNItem.spo_item_id must belong to an SPO in the same workspace.
*   **GRN-009:** A GRN cannot be created against an SPO item that is already CLOSED, CANCELLED, or SHORT_CLOSED.
*   **GRN-010 (INV-5.1):** received = accepted + damaged + rejected, enforced at save.
*   **GRN-011:** quantity_received for a line cannot exceed quantity_confirmed on the SPO item beyond `workspace.over_receipt_tolerance_percent` at the moment of ACCEPTED disposition.
*   **GRN-012 (INV-5.3):** unit_cost on the resulting StockTransaction is always the SPO's frozen unit_price.
*   **GRN-013 (INV-5.4):** quantity_on_order decrements by full quantity_received.
*   **GRN-014:** SPO Item rollups update on every GRN posting, never independently recalculated elsewhere.
*   **GRN-015:** A GRN with any posted line can never be cancelled.
*   **GRN-016:** `grn_number` gapless, 6-digit, unique per workspace.
*   **GRN-018:** `stock_posted = true` is a permanent, one-way flag blocking all forms of GRN cancellation.
*   **GRN-019:** Every disposition entry, override, and cancellation is fully audited.

## 5.11 API Contracts — GRN Domain
| Method | Path | Purpose | Allowed states |
| :--- | :--- | :--- | :--- |
| POST | `/api/v1/grns` | Create draft, pre-filled from tranches | — |
| PATCH | `/api/v1/grns/{id}` | Edit header | DRAFT, RECEIVING |
| POST | `/api/v1/grns/{id}/start-receiving` | → RECEIVING | DRAFT |
| POST | `/api/v1/grns/{id}/items` | Add line, record quantity_received | RECEIVING |
| POST | `/api/v1/grns/{id}/stage-for-inspection` | → PENDING_INSPECTION | RECEIVING |
| POST | `/api/v1/grns/{id}/items/{item_id}/disposition` | Record accepted/damaged/rejected split, triggers posting | PENDING_INSPECTION |
| POST | `/api/v1/grns/{id}/cancel` | Reason mandatory | DRAFT, RECEIVING, PENDING_INSPECTION only |
| GET | `/api/v1/grns/{id}/reconciliation` | Ordered/confirmed/received/accepted view | — |
| GET | `/api/v1/grns?status=&supplier_id=&spo_id=` | List/filter | — |
| GET | `/api/v1/spos/{id}/grns` | All GRNs against an SPO | — |

## Adopted Design Recommendations (D-19 to D-24)
*   **D-19:** Batch tracking remains a simple string field (`batch_number`). No full BatchLot lifecycle entity for MVP.
*   **D-20:** Rejected goods automatically draft a PurchaseReturn to reduce buyer friction.
*   **D-21:** Over-receipt tolerance is checked at the disposition step, allowing free raw entry for true physical counts.
*   **D-22:** Landed cost allocation into inventory valuation is deferred to Post-Wave-29. MVP valuation strictly uses SPO unit price.
*   **D-23:** A GRN must ALWAYS link to an SPO. Non-PO receipts must go through a StockAdjustment.
*   **D-24:** `location_id` is schema-ready but not strictly enforced in business logic for MVP.
