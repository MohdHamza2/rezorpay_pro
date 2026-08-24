# Procurement Rules — InvoiceSaaS B2B Trading Platform

> All procurement domain rules implemented through Wave 20 (Supplier Invoicing / 3-Way Match).
> References: `architecture/spo-architecture.md`, `architecture/grn-architecture.md`, `architecture/supplier-invoice-architecture.md`

---

## 1. Procurement Request (PR) Rules

### Creation
- A PR must specify `source_type` (e.g., CUSTOMER_ORDER, STOCK_REPLENISHMENT) and `destination_type` (e.g., WAREHOUSE)
- Each PR must have at least one item with `requested_quantity > 0`
- PR number is auto-generated in format `PR-YYYY-NNNNNN` (gapless, workspace-scoped)

### Status Machine
```
DRAFT → PENDING_APPROVAL → APPROVED → IN_PROGRESS → FULFILLED / CANCELLED
```

### Business Rules
- Only APPROVED PRs can be converted to RFQs or SPOs
- Cancelled PRs cannot be reverted
- `approved_quantity` ≤ `requested_quantity` always

---

## 2. RFQ Rules

### Purpose
- Competitive sourcing: invite multiple suppliers to quote
- `award_mode` = SPLIT (multiple suppliers can be awarded different items) or WHOLE (single supplier wins all)
- `evaluation_criteria` determines winner: LOWEST_LANDED_COST, BEST_VALUE, PREFERRED_SUPPLIER

### RFQ Lifecycle
```
DRAFT → PUBLISHED → CLOSED → AWARDED / CANCELLED
```

### Constraint
- RFQ `deadline` must be in the future at creation time
- Sealed RFQs cannot be viewed until `sealed_until` datetime passes

---

## 3. SPO State Machine Rules

### States
```
DRAFT → PENDING_APPROVAL → APPROVED → SENT → ACKNOWLEDGED → CLOSED
                                                          → CANCELLED (from any state except CLOSED)
```

### Rule Set

| Rule | Description |
|------|-------------|
| SPO-1 | Only OWNER or ADMIN role can approve an SPO |
| SPO-2 | Only APPROVED SPOs can be SENT to supplier |
| SPO-3 | Sending an SPO sets `sent_at` timestamp |
| SPO-4 | Acknowledgement records `quantity_confirmed` per line (supplier commits) |
| SPO-5 | Cancellation requires a reason (min 10 chars) |
| SPO-6 | A CLOSED SPO cannot be cancelled or modified |
| SPO-7 | `open_quantity` per line = `quantity_ordered - quantity_received - quantity_cancelled` |
| SPO-8 | SPO number auto-generated as `SPO-YYYY-NNNNNN` using gapless counter |
| SPO-9 | Procurement method SINGLE_SOURCE requires `single_source_justification` |

---

## 4. GRN Inspection Rules

### States
```
DRAFT → RECEIVING → STAGED_FOR_INSPECTION → ACCEPTED / PARTIALLY_ACCEPTED
                                          → CANCELLED (DRAFT only)
```

### Rule Set

| Rule | Description |
|------|-------------|
| GRN-1 | GRN must reference a valid supplier; warehouse is mandatory |
| GRN-2 | Items can only be added when GRN is in RECEIVING state |
| GRN-3 | Disposition (QC decision) requires GRN in STAGED_FOR_INSPECTION |
| GRN-4 | `quantity_accepted + quantity_damaged + quantity_rejected` should equal `quantity_received` |
| GRN-5 | `damage_reason` required when `quantity_damaged > 0` (min 10 chars) |
| GRN-6 | `rejection_reason` required when `quantity_rejected > 0` |
| GRN-7 | Only `quantity_accepted` is posted to inventory (`on_hand`) |
| GRN-8 | Inventory posting requires at least one bin on the warehouse |
| GRN-9 | Stock is posted to the **first available bin** in the warehouse |
| GRN-10 | `stock_posted = True` after successful disposition |
| GRN-11 | GRN status = ACCEPTED if all items fully accepted; PARTIALLY_ACCEPTED otherwise |
| GRN-12 | GRN number auto-generated as `GRN-YYYY-NNNNNN` |
| GRN-13 | SPO item `quantity_received` and `quantity_accepted` are updated after GRN disposition |

---

## 5. 3-Way Match Rules (Supplier Invoice)

Reference architecture: `architecture/supplier-invoice-architecture.md`

### Conceptual Model
```
SPO (commitment) ↔ GRN (physical truth) ↔ Supplier Invoice (financial claim)
```

**Critical distinction**: GRN ≠ Invoice. GRN is the physical receipt event. The invoice is the financial claim from the supplier. Matching validates alignment between all three documents.

### Match Process (per invoice line)

| Check | Rule | Failure Code |
|-------|------|-------------|
| Supplier | Invoice.supplier_id == SPO.supplier_id | `FAILED_SUPPLIER` |
| Currency | Invoice.currency == SPO.currency | `FAILED_CURRENCY` |
| Product | InvoiceItem.product_id == SPOItem.product_id | `FAILED_PRODUCT` |
| Quantity | InvoiceItem.quantity ≤ total accepted GRN quantity for that SPO item | `FAILED_QTY` |
| Price | \|invoice_price − spo_price\| / spo_price ≤ 2% tolerance | `FAILED_PRICE` |
| Tax | \|invoice_vat − expected_vat\| ≤ 10% of expected + 0.10 AED | `FAILED_TAX` |
| Receipt | GRN items in ACCEPTED/PARTIALLY_ACCEPTED state must exist | `UNRECEIVED_ITEMS` |
| Duplicate | Same invoice number + supplier + workspace | `DUPLICATE_INVOICE` (HTTP 409) |

### Invoice Status Rules

| Rule | Description |
|------|-------------|
| INV-1 | All checks pass → `MATCHED` status |
| INV-2 | Any check fails → `DISCREPANCY` status |
| INV-3 | `MATCHED` → `APPROVED` directly via `/approve` endpoint |
| INV-4 | `DISCREPANCY` → `APPROVED` only via `/resolve-discrepancy` with mandatory notes |
| INV-6.1 | AP cannot approve an invoice with `FAILED_*` match status directly (INV-6.1 rule) |
| INV-5 | `APPROVED` → `PARTIALLY_PAID` / `PAID` after payment recording (future wave) |

### Variance Tracking
- `variance_quantity` = `invoice_qty − accepted_grn_qty` (stored per item)
- `variance_price` = `invoice_price − spo_price` (stored per item)
- `variance_tax` = `invoice_vat − expected_vat` (stored per item)

---

## 6. Conflict/Gap Register (Procurement)

Tracked from architecture decisions and MASTER_PLAN_V3.md Section 10:

| ID | Conflict | Resolution |
|----|----------|------------|
| C-35 | GRN creates stock movement; invoice should NOT create another | Only GRN disposition posts to inventory. Invoice creates financial liability. |
| C-36 | Partial shipments across multiple GRNs | Aggregate all accepted quantities across all GRNs when matching |
| C-37 | SPO amended after GRN received | Amendment only affects open_quantity; received history immutable |
| C-38 | Duplicate invoice detection scope | Unique on (workspace_id, supplier_id, supplier_invoice_number) |
| C-39 | Price tolerance for 3-way match | 2% tolerance on unit price; separate tax tolerance |
| C-40 | GRN reversal after stock posted | Not implemented; manual stock adjustment required |

---

## 7. Document Number Formats

| Document | Format | Example |
|----------|--------|---------|
| Invoice | `INV-YYYY-NNNNNN` | INV-2026-000042 |
| SPO | `SPO-YYYY-NNNNNN` | SPO-2026-000001 |
| GRN | `GRN-YYYY-NNNNNN` | GRN-2026-000001 |
| PR | `PR-YYYY-NNNNNN` | PR-2026-000001 |
| RFQ | `RFQ-YYYY-NNNNNN` | RFQ-2026-000001 |

All counters are **gapless**, workspace-scoped, and generated with `SELECT FOR UPDATE` to prevent duplicates under concurrency.
