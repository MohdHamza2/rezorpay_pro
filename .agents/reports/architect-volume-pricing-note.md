# Architect note — Volume / customer pricing wired (Gap 8)

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-volume-pricing-addendum.md`

## Alembic

**NO.** `product_prices` already has `price_type`, `client_id`, `min_quantity`, `price` Numeric(12,2), `currency`, `workspace_id` (`d3e4c7fdb29f`). Volume = multiple **TIER_1** rows, not a `TIER_2` column. Do not snapshot `price_type` onto invoice/quote/LPO lines. HEAD stays **`b8d5f0c3a216`**. Later WPs `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC history.

## Resolve

`PricingService.resolve(workspace_id, product_id, client_id, quantity)` → `money()` price. First match: CUSTOMER_SPECIFIC for **that** client (qty ≥ min, null min = 0, **highest** min wins) → TIER_1 `client_id` null (same min rule) → DEFAULT_SALES → else **422** `NO_LIST_PRICE`. Cross-tenant product/client → **404**. Inactive still **400** on add. AED only. Explicit `unit_price` **always wins**.

## Hook

Replace `_default_sales_price` inside `_line_unit_price`. Pass document `client_id` from invoice / quotation / LPO — they already share `_resolve_line`. **Not** quote convert, LPO→invoice, send, CN (frozen/copied), DN (no price), SENT PUT.

## T7

Staff GET `/prices` and product `prices[]`: **OWNER/ADMIN/MEMBER all rows** (same as today). Reason: B2B back-office; MEMBER already GET any client; `ProductDetailPanel` CRUD needs the dealer book. T7 = resolve + preview never apply or return another client’s CUSTOMER_SPECIFIC; workspace B → 404.

## Preview GET

**In WP-A:** `GET /products/{id}/resolved-price?client_id=&quantity=`. One price + `price_type`. Isolation 404. Required so WP-B does not scan all dealer rows in the browser.

## WP

- **A** API + `test_pricing.py`. No frontend. No Alembic.
- **B** invoice/quote/LPO line: preview fill; qty re-resolves until dirty override; show List / Volume / Customer. Do not rebuild product price CRUD.
- **C** Playwright: A qty 1 → 80; A qty 10 → 80; B qty 10 → 90; explicit 12.50 kept; workspace B resolved-price 404. Docker 8000 / Postgres 5434. Never SQLite.

Out: electrical specs, bilingual (next), debit notes, Peppol, WhatsApp, TIER_2 enum, purchase/SPO prices, re-pricing SENT invoices.
