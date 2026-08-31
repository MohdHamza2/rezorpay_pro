# Architect note — Customer LPO / CPO addendum (Gap 5)

**Date:** 2026-09-01
**Code:** none. No Alembic files written this turn.

**Addendum:** `architecture/wave-customer-lpo-addendum.md`

## Alembic

**YES.** New revision, `down_revision = "cb01b6bef962"` (quotes HEAD). Never rewrite history.

Tables: `lpo_counters`, `customer_purchase_orders`, `customer_purchase_order_items`, `customer_purchase_order_events`.

Columns: `invoices.customer_purchase_order_id` (nullable, indexed, **not** unique); `invoice_items.customer_purchase_order_item_id` nullable FK. Keep unique `invoices.quotation_id`. Unique `customer_purchase_orders.quotation_id`. Partial unique `(workspace_id, client_id, customer_po_number)`.

No SPO/GRN changes. No `delivered_quantity`, retention, OCR URL, credit confirm columns.

## Number format

**Internal:** `LPO-YYYY-XXXX` via `lpo_counters` + `SELECT FOR UPDATE` (operational, not FTA-gapless). Do not reuse INV/QUO/SPO counters.

**External:** `customer_po_number` = contractor’s own PO. Not the primary key. Unique per client in a workspace when not null.

## States

`DRAFT → RECEIVED → PARTIAL → INVOICED`. `CANCELLED` from RECEIVED if zero countable invoices. DRAFT uses soft-delete.

No `CONFIRMED` / credit check. No `CLOSED`. `/receive` not `/confirm`.

INVOICED is not fully terminal: void or delete DRAFT invoice recalculates remaining.

## Convert rules

- ACCEPTED quote → `POST /quotations/{id}/convert-to-lpo` → **DRAFT** LPO, frozen lines, quote **CONVERTED**. Idempotent 200. Mutex with convert-to-invoice (409 the other way).
- Manual LPO without `quotation_id` allowed.
- `POST .../invoices` → `InvoiceService.create_invoice` **DRAFT**; many invoices per LPO; `quotation_id` null on those invoices. Omit items = all remaining. Cannot over-invoice (400). DRAFT invoices count toward qty.
- FTA send gates wait until invoice `/send`.
- PUT forbidden on LPO-linked invoices; delete DRAFT and re-post.
- Recalc `quantity_invoiced` on create / void / DRAFT delete (invoice router delete must call service).

## PDF / WP

Title **LPO**, English only. A API+Alembic+tests → B UI path `/lpos` → C Playwright.

## Out

OCR, WhatsApp, credit HOLD, delivery notes, supplier SPO changes.
