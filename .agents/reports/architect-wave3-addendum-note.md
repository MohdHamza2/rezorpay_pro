# Architect note — Wave 3 Product Master addendum

**Date:** 2026-08-31
**Code:** none.

**Addendum path:** `architecture/wave-3-product-master-addendum.md`

**UOM:** Live model wins. No `from_uom_id`. Implied from = `Product.base_uom_id`; store `to_uom_id` + `conversion_factor` `Numeric(14,6)`. 1 `to_uom` = factor × base UOM.

**Alembic:** **No** WP-1 revision. Do not rewrite `d3e4c7fdb29f`. HEAD remains `06c9b4b1dcda`.

**VAT:** Keep optional `Product.tax_rate`. Null = inherit workspace `default_tax_rate` 5.00 at invoice time (later). `hs_code` / `vat_category` **deferred** (no columns).

**Identifiers:** DB `type` str; allow-list MPN, BARCODE, SUPPLIER_CODE, EAN, UPC, CUSTOMER_CODE.

**PDC/payment PUT:** untouched this WP.
