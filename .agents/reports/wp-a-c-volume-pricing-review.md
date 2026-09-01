# WP-A–C Volume / customer pricing — code review

**Date:** 2026-09-01
**Scope:** Full slice vs `architecture/wave-volume-pricing-addendum.md` (full), `.agents/reports/wp-a-volume-pricing-review.md`, `.claude/CLAUDE.md` (Decimal, isolation **404 not 403**, never SQLite, no schema without Alembic).
**Review only.** No features. No git commit.

## Verdict

**APPROVE_WITH_NITS**

No P0: Customer A never receives Customer B’s `CUSTOMER_SPECIFIC` row; convert / LPO→invoice keep frozen `unit_price`; money is `Decimal` + `money()` (no Python `float` on new schema fields); isolation is **404 not 403**; Alembic HEAD stays **`b8d5f0c3a216`** with no `price_source` on lines and no second price table.

Slice **may be committed when asked**.

This review did not re-run pytest or Playwright. File and test counts match the claim (`test_pricing.py` 13 `def test_`, Playwright `test(` = 24 including prior suites). No new Alembic file; no `models/product.py` edit; `ProductDetailPanel` not in the WP diff.

## P0s

None.

## Checklist

| # | Lock | Result |
|---|---|---|
| 1 | Isolation **404** never 403 (API + Playwright) | **Pass.** Product/client load is `id` + JWT `workspace_id` + `deleted_at IS NULL` → HTTP 404 `NOT_FOUND`. Handler preserves `exc.status_code` (no 403 remap). Cross-tenant client is 404, not a silent skip. Pytest: other-workspace product on invoice, preview client, workspace B `resolved-price`. Isolation suite: `?workspace_id=` spoof on `/resolved-price`. Playwright `volume-pricing-isolation.spec.ts`: B token + A product → 404, `not.toBe(403)`. |
| 2 | Decimal; explicit `unit_price` wins; convert / LPO→invoice frozen | **Pass.** `unit_price = money(_dec(row.price))`. `ResolvedPriceResponse` fields are `Decimal`, not `Float`. Explicit body price: `_line_unit_price` returns `_dec(...)` when not `None` (JSON null / omit still resolve). `frozen_invoice_items` / `slice_invoice_items` pass explicit `unit_price`. `copy_quote_item` copies quote line money (convert-to-lpo does not call `_resolve_line`). Send snapshots only. Pytest wipe DEFAULT_SALES to 1.00 then convert + LPO `/invoices` still 80. |
| 3 | A qty 10 → **80** not 90; B qty 10 → **90** not 80 | **Pass.** `_pick`: CUSTOMER_SPECIFIC for **this** `client_id` first (highest qualifying min), else TIER_1 `client_id IS NULL`, else DEFAULT_SALES. Invoice/quote/LPO create+PUT + preview. Playwright: A qty 1 and qty 10 → 80 Customer; switch header to B (not dirty) → 90 Volume. MEMBER invoice for B qty 10 → 90 not 80. |
| 4 | Preview one price + `price_type`; no other client ids | **Pass.** `GET /api/v1/products/{id}/resolved-price`. One `ResolvedPriceResponse`. A qty 10 blob must not contain client B’s id. B qty 10 → 90 / `TIER_1`. No `alternates`. `client_id` omitted → skip customer bucket (TIER_1 90). |
| 5 | UI does not scan `getProductPrices` for `DEFAULT_SALES` on sales lines | **Pass.** Invoice / quotation / LPO use `useCatalogLinePricing` → `getResolvedPrice` only. No `getProductPrices` / `prices.find(DEFAULT_SALES)` in those forms. Picker is `getProducts`. |
| 6 | Dirty override survives qty change | **Pass.** Typing `unit_price` sets `dirtyRef` + seq bump so in-flight preview cannot overwrite. Badge **Override**. Playwright: 12.50 stays after qty 5. Product pick clears dirty and re-resolves. Header client change skips dirty lines. `setValue` from preview does not go through the input `onChange` (RHF), so fill does not mark dirty. |
| 7 | `ProductDetailPanel` CRUD untouched | **Pass.** Not in the WP git set. Still POSTs `createProductPrice` / DELETE; still lists all dealer rows from GET product `prices[]`. Playwright still adds DEFAULT_SALES via that panel. |
| 8 | No Alembic; no `price_source` column | **Pass.** Versions: HEAD file is `b8d5f0c3a216`; nothing revises it. No `price_source` / `TIER_2` on models. `product_prices` unchanged (`d3e4c7fdb29f` ancestor). |
| 9 | CN / send / DN not re-priced | **Pass.** `PricingService` / `_resolve_line` only from invoice/quote/LPO **add**. CN `build_item` copies invoice line `unit_price`. `mark_as_sent` FTA snapshots only. Delivery notes have no unit price and no `PricingService` import. |
| 10 | Playwright 24 including prior suites | **Pass on count / claimed run.** 24 `test(` across `frontend/e2e` (volume happy + isolation + 22 prior: product, FTA, quotes, LPO, credit HOLD, DN, CN, AR, PDC). WP-C report: 24 passed, `npm run build` green. Not re-executed here. |

## Nits

Carry-forward (WP-A) plus WP-B/C:

1. **`backend/app/routers/products.py` is 532 lines** (addendum §8: files < 500). Preview GET is ~15 lines next to `/prices`. `invoice_service.py` (715) and `Invoices.tsx` (885) were already over; this WP only hooked them.
2. **Double product fetch.** Document add `_load_invoice_product` then `resolve` loads again. Preview loads once for inactive, then `resolve` loads again.
3. **Preview `quantity` is passed through `money()`.** Matching uses the raw Decimal; the response qty is fils-rounded. Spec example `"10.00"` matches; qty with >2 dp would display rounded.
4. **Missing `quantity` query** is FastAPI 422 `VALIDATION_ERROR` with `details[]`, not `field=quantity`. `quantity=0` is service 422 `field=quantity` (tested).
5. **Ad-hoc 422** asserts status only, not `field=unit_price`.
6. **No dedicated pytest** for deleted-product preview 404. Convert-to-lpo freeze after list-price change is covered by `copy_quote_item` (copies `unit_price`, never `_resolve_line`), not the wipe fixture.
7. **`ResolvedPriceResponse` money fields** omit `max_digits` / `decimal_places`. Values are already `money()` / Decimal.
8. **Tests still `SQLModel.metadata.create_all`** on Postgres `_test` (repo convention). Production HEAD asserted in `test_schema_not_float_and_alembic_head`.
9. **Playwright volume path is invoice-only.** Spec allows invoice **or** quote. Quote/LPO share the same hook and testids (`quotation-` / `lpo-` prefixes) but have no WP-C browser case. Quote/LPO **edit** disables the client `<select>` (pre-existing), so header-client re-preview is create-only there.
10. **Dirty is session-only.** Opening a saved DRAFT and changing qty re-previews (override is not persisted as a flag). Same-session Override is what WP-B/C lock.
11. **Frontend `Number()`** for preview display (`toFixed(2)`) and submit (`parseAmount`). Backend still Decimal. Same FTA form pattern. 80 / 90 / 12.50 are exact in IEEE.
12. **Axios interceptor toasts** preview 404 / `NO_LIST_PRICE` before the hook swallows 404. Isolation E2E is API-only so no toast. `NO_LIST_PRICE` toast is intended.

Not P0 / not blocking commit: no tenant 403, no float money on the engine, no Alembic, convert does not re-resolve, CUSTOMER_SPECIFIC is never “best dealer in the book,” sales lines do not scan `GET /prices`.

## Commit

**Yes — may be committed when asked.** Do not commit `.env`, caches, `frontend/dist`, `.pytest_cache`, or `.claude-flow` policy tmp files.

## Next UAE gap (do not implement)

**Bilingual PDF (gap 13).** Electrical spec columns (`amp` / mm²) and debit notes stay later. Not this slice: WhatsApp, Peppol, PDC changes, re-pricing SENT invoices, `TIER_2`, `price_source`.
