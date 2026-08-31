# Architect note — FTA tax invoice addendum

**Date:** 2026-08-31
**Code:** none.

**Addendum:** `architecture/wave-fta-tax-invoice-addendum.md`

**Alembic:** **YES.** New revision, `down_revision = "06c9b4b1dcda"`. Never rewrite history. Columns: `workspaces.address`; `invoices.supply_date`, `invoice_kind`, seller/buyer name-address-TRN snapshots; `invoice_items.product_id`, `uom_id`, `sku_snapshot`, `discount_percent`, `discount_amount`, `line_net`, `tax_amount`. No `clients.trn` (use `tax_id`). No IBAN.

**TRN names:** seller `workspaces.trn`; buyer `clients.tax_id`. Send regex `^100[0-9]{12}$`.

**Line tax:** `money()` = ROUND_HALF_UP to 0.01. `line_net = money(qty*price - discount)`; `line_vat = money(line_net * tax_rate/100)`; `total_price = line_net + line_vat` (gross). Omitted `tax_rate` → product.tax_rate else workspace `default_tax_rate` 5.00.

**WP split:** A API (math+send+tests) → B Settings/form/PDF “Tax Invoice” → C browser E2E. Quotes/LPO after A–C.
