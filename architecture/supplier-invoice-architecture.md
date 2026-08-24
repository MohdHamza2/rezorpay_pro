# Supplier Invoice + 3-Way Match Architecture
**InvoiceSaaS B2B Trading Platform — Wave 20 Specification — Step 6 Detail**

## 6.1 Architectural Principle
Supplier Invoice ≠ Supplier Payment

This distinction needs to be extremely strict.

Supplier Invoice -> Financial claim / AP liability -> 3-Way Match -> Approval -> Supplier Payment

Receiving an invoice must never automatically pay it.
GRN accepted does not mean Invoice approved.
Invoice received does not mean Invoice matched.

## 6.2 The Three Documents Have Different Truths
| Document | Answers |
|---|---|
| **SPO** | What did we agree to buy? |
| **GRN** | What physically arrived and what was accepted? |
| **Supplier Invoice** | What is the supplier asking us to pay? |

The match engine compares them:
* **Quantity**: Invoice quantity vs GRN accepted quantity vs SPO quantity
* **Price**: Invoice unit price vs SPO committed unit price
* **Tax**: Invoice VAT vs SPO expected VAT

## 6.3 Step 6 Conflict & Gap Register

* **C-35 — Invoice can cover multiple SPOs**: SupplierInvoice.spo_id is informational only. The canonical relationship remains: `SupplierInvoiceItem -> spo_item_id`.
* **C-36 — Invoice can arrive before GRN**: Invoice received -> No GRN yet -> `PENDING_MATCHING` -> `UNRECEIVED_ITEMS`. It must not be rejected merely because the GRN does not exist yet.
* **C-37 — One SPO can have multiple supplier invoices**: Invoice matching must be line-level and cumulative, not one-invoice-per-SPO.
* **C-38 — One supplier invoice can contain multiple SPOs**: `SupplierInvoice` 1 ──── N `SupplierInvoiceItem` -> `spo_item_id` is mandatory.
* **C-39 — Invoice quantity vs accepted quantity**: `invoice_qty > grn_accepted_qty` -> `FAILED_QTY`. We must distinguish Invoice > accepted from Invoice > ordered because the GRN is the physical truth.
* **C-40 — Invoice price variance**: Invoice price vs SPO price with a 2% tolerance. Invoice price variance changes AP matching status, not historical inventory cost.

## 6.4 SupplierInvoice Entity
* `id`
* `workspace_id`
* `supplier_id`
* `supplier_invoice_number`
* `our_reference`
* `invoice_date`
* `due_date`
* `currency`
* `subtotal`
* `discount_amount`
* `vat_amount`
* `total_amount`
* `amount_paid`
* `balance_due`
* `status` (RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID, CANCELLED)
* `three_way_match_status`
* `three_way_match_notes`
* `document_url`
* `ocr_job_id`
* `ocr_extracted`
* `primary_spo_id` (nullable / informational only)
* `received_at`, `matched_at`, `approved_at`, `paid_at`, `created_at`, `updated_at`

## 6.5 SupplierInvoiceItem
* `id`
* `supplier_invoice_id`
* `spo_item_id` (nullable)
* `grn_item_id` (nullable)
* `product_id`
* `description`
* `quantity`
* `uom_id`
* `unit_price`
* `discount_percent`
* `vat_rate`
* `vat_amount`
* `total_price`
* `currency`
* `match_status`
* `variance_quantity`, `variance_price`, `variance_tax`, `variance_notes`

## 6.6 3-Way Match Engine (Per Invoice Line)
* **Match #1 — Supplier**: `Invoice.supplier_id == SPO.supplier_id`. Otherwise: `SUPPLIER_MISMATCH`
* **Match #2 — Currency**: `Invoice.currency == SPO.currency`. Otherwise: `CURRENCY_MISMATCH`
* **Match #3 — Product**: `InvoiceItem.product_id == SPOItem.product_id`. Otherwise: `PRODUCT_MISMATCH`
* **Match #4 — UOM**: Normalize Invoice UOM -> Product base UOM.

## 6.7 Quantity Match
* `Invoice Qty <= GRN Accepted Qty`
* If `Invoice Qty > GRN Accepted Qty` then `FAILED_QTY`

## 6.8 Price Match
* Compare `InvoiceItem.unit_price` vs `SPOItem.unit_price`
* Variance % = `ABS(invoice_price - spo_price) / spo_price * 100`
* `<= 2%` -> PASS
* `> 2%` -> `FAILED_PRICE`

## 6.9 Tax Match
* Invoice VAT vs SPO expected VAT. If mismatch: `FAILED_TAX`.

## 6.10 Duplicate Invoice Protection
* Within a supplier/workspace: `supplier_id` + `supplier_invoice_number` must be protected against duplicates (Result: `DUPLICATE_INVOICE`).

## 6.11 Match Result
NOT_CHECKED, PASSED, FAILED_QTY, FAILED_PRICE, FAILED_TAX, FAILED_SUPPLIER, FAILED_CURRENCY, FAILED_PRODUCT, FAILED_UOM, DUPLICATE_INVOICE, UNRECEIVED_ITEMS, MANUAL_REVIEW.

## 6.12 Supplier Invoice State Machine
RECEIVED -> PENDING_MATCHING -> (MATCHED | DISCREPANCY).
DISCREPANCY -> human review -> APPROVED.
MATCHED -> APPROVED -> PARTIALLY_PAID -> PAID.

## 6.13 The Most Important Step 6 Invariant (INV-6.1)
**AP cannot approve an invoice that has an unresolved 3-Way Match discrepancy.**
FAILED_QTY, FAILED_PRICE, FAILED_TAX, etc. -> DISCREPANCY -> Authorized resolution -> APPROVED.

## 6.14 Critical Financial Separation
GRN ≠ Invoice. Invoice ≠ Payment. GRN ≠ Payment.

## 6.15 AP Amount Calculation
`balance_due = total_amount - amount_paid`

## 6.16 Payment Eligibility
Payment only allowed when `SupplierInvoice.status = APPROVED` AND (`three_way_match_status = PASSED` OR authorized discrepancy override has been recorded).

## 6.17 Step 6 ERD
`SPO_ITEM -> GRN_ITEM`
`SPO_ITEM -> SUPPLIER_INVOICE_ITEM -> SUPPLIER_INVOICE -> SUPPLIER_PAYMENT`

## 6.18 Step 6 API Contract
* `POST /api/v1/supplier-invoices`
* `GET /api/v1/supplier-invoices`
* `GET /api/v1/supplier-invoices/{id}`
* `PATCH /api/v1/supplier-invoices/{id}`
* `POST /api/v1/supplier-invoices/{id}/submit-matching`
* `GET /api/v1/supplier-invoices/{id}/match-result`
* `POST /api/v1/supplier-invoices/{id}/resolve-discrepancy`
* `POST /api/v1/supplier-invoices/{id}/approve`
* `POST /api/v1/supplier-invoices/{id}/cancel`
* `GET /api/v1/supplier-invoices/{id}/reconciliation`
* `POST /api/v1/supplier-invoices/{id}/upload`
* `POST /api/v1/supplier-invoices/{id}/ocr`
* `GET /api/v1/supplier-invoices/{id}/audit-log`

## 6.19 OCR Architecture
OcrJob -> Gemini Vision -> Draft SupplierInvoice -> Human review if confidence insufficient -> Deterministic 3-Way Match.

## 6.20 Step 6 Edge Cases (E-I01 to E-I20)
(As explicitly defined in the provided specification).

## Locked Decisions (D-25 to D-30)
* **D-25 (Price variance tolerance)**: Keep 2% as default and make workspace-configurable.
* **D-26 (Quantity tolerance)**: Invoice quantity must never exceed accepted GRN quantity without authorized discrepancy resolution.
* **D-27 (Invoice approval threshold)**: Maker-checker above configurable AP approval threshold, default 0.
* **D-28 (Invoice without SPO)**: No PO-less supplier invoice in normal flow.
* **D-29 (Invoice before GRN)**: Allow intake, but never allow AP approval/payment until required physical receipt exists or authorized exception.
* **D-30 (OCR confidence)**: OCR < 0.80 -> `REQUIRES_REVIEW`; never auto-approve.
