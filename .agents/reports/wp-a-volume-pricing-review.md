# WP-A Volume / customer pricing — code review

**Date:** 2026-09-01
**Scope:** API + pytest only (`architecture/wave-volume-pricing-addendum.md` full, `.agents/reports/architect-volume-pricing-note.md`, `.claude/CLAUDE.md` Decimal / isolation 404 / never SQLite)
**No UI. No git commit. WP-B not started.**

## Verdict

**APPROVE_WITH_NITS**

No P0: Customer A never receives Customer B’s `CUSTOMER_SPECIFIC` row; convert / LPO→invoice keep frozen `unit_price`; money is `Decimal` + `money()` (no float); isolation is **404 not 403**; Alembic HEAD stays `b8d5f0c3a216` with no second price table and no `price_source` on lines.

**WP-B may start.**

## P0s

None.

## Checklist

| # | Lock | Result |
|---|---|---|
| 1 | Isolation 404 never 403 (preview + other-workspace product/client) | **Pass.** Product/client load is `id` + JWT `workspace_id` + `deleted_at IS NULL` → HTTP 404 `NOT_FOUND`. Cross-tenant client is 404, not a silent skip. Tests: `test_other_workspace_product_and_preview_client_404`, `test_workspace_b_resolved_price_404`, isolation `?workspace_id=` spoof on `/resolved-price`. Handler preserves status (no 403 remap). |
| 2 | Decimal `money()`; never float | **Pass.** `unit_price = money(_dec(row.price))`; `_dec` is `Decimal(str(value))`. `ResolvedPriceResponse` fields are `Decimal`, not `Float`. Tests use `postgresql+asyncpg` `…/invoicesaas` → `invoicesaas_test` (port 5434). No SQLite in `test_pricing.py`. |
| 3 | A qty 1 → 80; A qty 10 → 80; B qty 10 → 90; B qty 1 → 100 | **Pass.** Invoice create + quote/LPO create/PUT + preview. Customer bucket wins over TIER_1 for A at qty 10. |
| 4 | Explicit `unit_price` 12.50 kept | **Pass.** `_line_unit_price` returns body price when not `None` (JSON null / omit still resolve). |
| 5 | Convert / LPO→invoice frozen after DEFAULT_SALES → 1.00 | **Pass.** `frozen_invoice_items` / `slice_invoice_items` pass explicit `unit_price`. `copy_quote_item` copies quote line money (convert-to-lpo). Test wipes book to list 1.00 then convert + LPO `/invoices` still 80. |
| 6 | Never apply another client’s CUSTOMER_SPECIFIC; skip bucket if `client_id` None | **Pass.** `_pick` filters `row.client_id == client_id` only when `client_id is not None`. Preview with no client → TIER_1 90. MEMBER invoice for B qty 10 → 90 not 80. |
| 7 | Highest `min_quantity` wins within a bucket | **Pass.** `_best_row` sorts `(-min, id ASC)`. A min 1→80 vs min 50→70: qty 10 stays 80; qty 50 → 70. Null min treated as 0. |
| 8 | `NO_LIST_PRICE` 422 when omit price and no rows; ad-hoc still requires `unit_price` | **Pass.** 422 `NO_LIST_PRICE` `field=product_id`. Ad-hoc without price 422 (`InvoiceItemCreate` validator + service). |
| 9 | Inactive add 400; preview inactive 400; deleted/other-ws 404 | **Pass.** Document add still `_load_invoice_product` 400. `resolve` itself does **not** 400 inactive. Preview 400 `VALIDATION_ERROR` `field=product_id`. Deleted/other-ws 404 via `_load_product`. Deleted-product preview is implementation-covered, not a dedicated pytest (nit). |
| 10 | Preview returns one price + `price_type`; no other client ids | **Pass.** `GET /api/v1/products/{id}/resolved-price`. One `ResolvedPriceResponse`. A qty 10 blob must not contain client B’s id. |
| 11 | `list_prices` still all workspace rows (staff book) | **Pass.** `ProductService.list_prices` untouched. MEMBER GET `/prices` lists A and B dealer rows. |
| 12 | No Alembic; no model column edits; no `price_source` on lines | **Pass.** `alembic heads` = `b8d5f0c3a216`. `alembic check`: no new ops. `models/product.py` not in the WP-A diff. No `TIER_2` / `price_source`. New file is `pricing_service.py` only. |
| 13 | CN / send / DN not hooked | **Pass.** `PricingService` / `_resolve_line` only from invoice/quote/LPO add. CN `build_item` copies invoice line `unit_price`. `mark_as_sent` snapshots only. DN has no unit price. |
| 14 | Tests hit PostgreSQL and the assertions above | **Pass (re-run).** `tests/test_pricing.py` **13 passed**. Isolation **5 passed** (resolved-price 404 inside product isolation). Catalog / inactive / quote convert freeze / LPO convert+invoice / product isolation sanity **7 passed**. Combined this slice **20 passed**, 0 failed. |

## Nits

1. **`backend/app/routers/products.py` is 532 lines** (addendum §8: files < 500). Preview GET added ~20 lines next to `/prices` as required; overage is hygiene, not a leak.
2. **Double product fetch.** Document add already `_load_invoice_product`; `resolve` loads the same row again. Preview loads once for inactive, then `resolve` loads again.
3. **Preview `quantity` is passed through `money()`.** Matching uses the raw Decimal; the response qty is fils-rounded. Spec example is `"10.00"` so the happy path matches; qty with >2 dp would display rounded.
4. **Missing `quantity` query** is FastAPI 422 `VALIDATION_ERROR` with `details[]`, not `field=quantity`. `quantity=0` is service 422 `field=quantity` (tested). `Query(...)` has no `gt=0`.
5. **Ad-hoc 422** asserts status only, not `field=unit_price` (Pydantic validator still rejects).
6. **No dedicated pytest** for deleted-product preview 404 (same `deleted_at IS NULL` query as other-ws). Convert-to-lpo freeze after list-price change is covered by `copy_quote_item` + existing LPO freeze test, not the WP-A wipe fixture.
7. **`ResolvedPriceResponse` money fields** omit `max_digits` / `decimal_places` (create schemas have them). Values are already `money()` / Decimal.
8. **Tests still `SQLModel.metadata.create_all`** on Postgres `_test` (repo convention). Production HEAD asserted via `alembic heads` / `alembic check` inside `test_schema_not_float_and_alembic_head`.

Not P0 / not blocking WP-B: no tenant 403, no float money, no Alembic, convert does not re-resolve, CUSTOMER_SPECIFIC is never “best dealer in the book.”

## WP-B

**Yes — WP-B may start** on this tree.

UI must fill catalog lines from **preview GET** (`client_id` + `quantity`), not `getProductPrices` → `DEFAULT_SALES`. Do not scan `prices[]` for another client’s `CUSTOMER_SPECIFIC`. Dirty override stays 12.50 when qty changes. Do not rebuild `ProductDetailPanel` price CRUD. MEMBER may still see the full dealer book on GET `/prices`.
