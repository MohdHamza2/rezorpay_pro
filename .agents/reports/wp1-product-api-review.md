# WP-1 Product Master API — Code Review

**Date:** 2026-08-31
**Reviewer:** reviewer subagent
**Scope:** shipped Product Master API only (no WP-2, no payment/PDC PUT, no Alembic).
**Specs:** `architecture/wave-3-product-master-addendum.md`, mvp-sequence §5 WP-1 AC, `.claude/CLAUDE.md`, `.agents/backend-agent.md`.
**Mode:** review only. No product-code patches (no P0 security/money bug found).

**Verdict:** `APPROVE_WITH_NITS`

WP-2 (frontend catalog UI) **may start**. Address nits below in a follow-up coder pass; none are tenant-leak or float-money P0.

---

## Verdict rationale (short)

Isolation is JWT `workspace_id` with 404 (never 403) on cross-tenant GET/PUT/DELETE of products and children. Money/tax/conversion fields are Pydantic `Decimal`, never `float`. Soft vs hard delete matches the addendum. Lists use live `PaginatedResponse` (`data` = array). Extra keys / `from_uom_id` / non-AED / bad identifier types → 422. Uniqueness 409 and UOM-in-use 400 are in the service. Router is HTTP-only. No Alembic, `models/product.py` untouched, payment PUT untouched. E2E payload edits drop keys that `extra="forbid"` now correctly rejects.

Known `selectinload` deviation is **acceptable** (no `Relationship` on `Product`; model locked).

---

## Findings (severity first)

### Critical

_None._ No cross-workspace leak in reviewed query paths. No `float` money/tax/conversion schema fields. Payments/PDC PUT not modified.

---

### Warning

#### W1 — Soft-deleted product orphans identifiers; unique `(workspace_id, type, value)` can never be freed

- **File:line:** `backend/app/services/product_service.py:683-692` (soft-delete product only); `:742-760` (child DELETE requires live parent); `:718-728` (identifier uniqueness is workspace-wide, all rows)
- **Why it fails the addendum:** §2.5 requires parent `deleted_at IS NULL` else 404. §4 unique is `(workspace_id, type, value)` with 409. §8 identifiers are hard-delete only. Implemented separately, those rules compose into a trap: DELETE product → nested identifier DELETE 404s → MPN/barcode/EAN remains forever → new product cannot reuse the value (409 / IntegrityError). Addendum §13.6 locks SKU non-reuse on purpose; it does **not** lock identifier non-reuse, but the live unique constraint plus “live parent required” makes reuse impossible without a cascade the coder did not add.
- **Required fix:** On product soft-delete, hard-delete that product’s identifier, conversion, and price rows in the same service call (still no Alembic). Nested child routes stay 404 for already-deleted parents. Add a test: create MPN → soft-delete product → new product can attach the same MPN.

#### W2 — Category parent walk 404s if an *ancestor* is soft-deleted

- **File:line:** `backend/app/services/product_service.py:205-226` (`_assert_acyclic_parent` uses `_get_live` on every hop)
- **Why it fails the addendum:** §2.1: immediate `parent_id` must be same workspace, not self, not deleted; circular → 400. Immediate parent is correctly 404 if missing/deleted. After a mid-tree soft-delete, live child C still has `parent_id` of deleted B. Creating D with `parent_id=C` walks C→B and 404s `"Category not found"` even though C is a valid live parent.
- **Required fix:** Validate only the immediate parent with `_get_live`. Further ancestors: load without 404 on deleted/missing and treat that as end-of-chain (still detect cycles among live nodes). Test: A←B←C, delete B, POST category with `parent_id=C` → 201.

#### W3 — Isolation tests do not prove query `workspace_id` cannot override JWT

- **File:line:** `backend/tests/test_multi_tenant_isolation.py:331-333` (token B + `workspace_id=ws_b`); same pattern in `backend/tests/test_products.py:681-720`
- **Why it fails the addendum:** §1.2 / §2: “never body/query `workspace_id`”; “Ignore query `workspace_id` (tests still append it; JWT wins).” Tests append the *caller’s* workspace id, so they would still 404 even if a future router bound `Query(workspace_id)` and preferred it. Cross-tenant POST of children as B, and category/brand/UOM GET/PUT/DELETE as B, are also untested (§13.10 asks for children; mvp-sequence AC4 is product *and* children — categories are sibling resources).
- **Required fix:** One case: token B + `?workspace_id=<A’s uuid>` on GET/PUT/DELETE product (and one child) still 404. Add category/brand/UOM cross-tenant 404. Add POST identifier/conversion/price as B on A’s `product_id` → 404.

#### W4 — UOM delete vs conversions on *deleted* products; conversion-ref path untested

- **File:line:** `backend/app/services/product_service.py:473-484` (conversion block joins `Product.deleted_at IS NULL`); `backend/tests/test_products.py:541-547` (only `Product.base_uom_id`)
- **Why it fails the addendum:** §2.3: block soft-delete if any non-deleted `Product.base_uom_id` **or** `ProductUOMConversion.to_uom_id` references the UOM. Grammar applies “non-deleted” to Product; conversion rows have no `deleted_at`. Implementation ignores conversions whose parent product is already soft-deleted (FK still points at the UOM row, which is OK because UOM is soft-deleted not removed). The conversion-as-`to_uom` block for a *live* product is implemented but has no test (§13.12 only names product reference).
- **Required fix:** Keep live-product conversion block. Add test: product + conversion `to_uom=BOX`, BOX not base → DELETE BOX → 400. Optional: also block if *any* conversion row references the UOM (stricter reading).

#### W5 — Missing addendum tests (false-green risk, not a current code fail)

| Gap | Spec | Notes |
|---|---|---|
| Circular / self `parent_id` → 400 | addendum §2.1 | Implemented at `:211-226`; untested |
| Brand duplicate name 409 | §2.2 | Implemented at `:353-354`; only category name tested (`test_products.py:228-238`) |
| `is_active` default = no filter | §2.4 lock | Implemented at `:549-550`; list never asserts inactive rows still appear |
| Duplicate `TIER_1` same `min_quantity` 409 | §5 | Implemented at `:875-887`; untested |
| Same MPN on two live products 409 | §4 | Unique is workspace-wide; test only duplicates on the same product (`:434-446`) |
| `INTERNAL_SKU` identifier type 422 | §4 | Enum omit → 422; only `FOO` tested |
| PUT extra keys 422 | §2.4 | POST `hs_code` tested (`:296-310`); PUT not |
| tax_rate null not defaulted to 5.00 | §6 | Create omits `tax_rate`; GET null unasserted |

- **Required fix:** Add the rows above to `test_products.py`. Do not treat current greens as coverage of those rules.

#### W6 — `DEFAULT_SALES` / price uniqueness is service-only (race → two list prices)

- **File:line:** `backend/app/services/product_service.py:859-874`, `:910-933` (`create_price` flushes without `_flush_or_conflict`)
- **Why it fails the addendum:** §5: at most one `DEFAULT_SALES` per product (409). Pre-check then insert has no DB unique (addendum forbids WP-1 Alembic). Concurrent POSTs can both pass the SELECT.
- **Required fix:** Catch `IntegrityError` is a no-op until a unique exists. Accept race for WP-1 or document. Prefer catching flush errors and mapping to 409 if a later migration adds a unique. Not P0.

---

### Info

#### I1 — GET product children via extra queries, not `selectinload` (accepted deviation)

- **File:line:** `backend/app/services/product_service.py:555-617`; `backend/app/models/product.py` (no `Relationship` on `Product`)
- **Why:** Addendum §2.4 asks to eager-load children. Coder cannot add relationships (model locked, no Alembic). Three scoped `select`s filter `product_id` **and** `workspace_id`. Response still embeds `identifiers` / `conversions` / `prices`; no stock.
- **Required fix:** None for WP-1. Optional later: add relationships + `selectinload` in a model/Alembic WP.

#### I2 — Error wrapper `code` is always `HTTP_ERROR`, not `CONFLICT` / `NOT_FOUND`

- **File:line:** `backend/app/main.py:106-114`; service raises `HTTPException(detail=str)` at `product_service.py:73-86`
- **Why:** Addendum §1.2: errors `{ success: false, error: { code, message } }`. Handler supplies that shape; `code` is generic. HTTP status is still 404/409/400. Same pattern as invoices/SPO. Status + message meet CLAUDE.md wrapper; machine `CONFLICT` is not used.
- **Required fix:** Out of WP-1 unless product wants `ErrorCode.CONFLICT` in `detail` dict. Do not block.

#### I3 — E2E payload alignment did **not** hide API regressions

- **File:line:** `backend/tests/test_e2e_spo.py:119-131` (`type: GOODS` removed; 200 **or** 201); `backend/tests/test_e2e_grn.py:120-126` (`type: GOODS` removed); `backend/tests/test_e2e_3way_match.py:103-111` (`base_currency` removed)
- **Why:** Those keys are not live columns. Addendum §2.4 / §12: extra body keys → 422; POST create **201**; existing `{name, internal_sku, base_uom_id}` and `{name, code}` must keep working. Dropping extras is required by `extra="forbid"`. Relaxing 200→`in (200, 201)` matches §12 (“tests already allow 200 or 201”). Assertions on SPO/GRN/3-way business outcomes are unchanged.
- **Required fix:** None. Optional: assert product/UOM POST **201** exactly now that WP-1 locked it.

#### I4 — Alembic / history / payments / model lock

- `backend/alembic/versions/d3e4c7fdb29f_add_wave_3_product_master.py:17` still `down_revision = '96b45ccabfb7'`
- HEAD file `06c9b4b1dcda` untouched; no new revision
- `backend/app/models/product.py` — no diff vs HEAD
- `backend/app/routers/payments.py:236` PUT still present (addendum §14)
- **Required fix:** None.

#### I5 — Style / CLAUDE.md hygiene (non-blocking)

- No `print()` in service/router/schemas. Logs are `logger.info(..., extra={workspace_id|product_id})` — no tokens/passwords (`product_service.py:285, 635, 692`).
- Imports at top of app files (no E402). Tests use the suite’s post-`win32` import pattern (`test_products.py:19-31`).
- `product_service.py` is ~955 lines (reviewer style cap 500). Split later; not an addendum fail.
- Router owns commit/refresh/wrapper only (`routers/products.py`). Uniqueness, 404 isolation, conversion/price/UOM rules live in the service.
- `_flush_or_conflict` (`:149-154`) `rollback()` on IntegrityError is correct; router does not commit on 409.

#### I6 — `jsonable_encoder` may emit JSON numbers for `Decimal`

- Project-wide FastAPI encoding; addendum allows “JSON number or string”. Schemas are `Decimal`. Tests coerce with `Decimal(str(value))` (`test_products.py:93-94, 471, 570`).
- **Required fix:** None for WP-1.

---

## Checklist (review prompt)

| # | Item | Result |
|---|---|---|
| 1 | Cross-workspace leak; 404 not 403; JWT only | **Pass (code).** Router never binds query/body `workspace_id` (`get_current_workspace_id` only). `_get_live` filters `workspace_id` + `deleted_at IS NULL`. Child writes load product in JWT workspace first. Isolation tests cover product + identifier/conversion/price GET/DELETE (+ product PUT/DELETE). See W3 for test holes (category/brand/UOM, POST-as-B, query spoof). |
| 2 | Float money / tax / conversion_factor | **Pass.** `tax_rate` / `reorder_level` / `price` / `min_quantity` / `conversion_factor` are `Decimal` with digit constraints (`schemas/products.py:131-134, 145-148, 204, 224-226`). Grep: no `float`/`Float` types in new schema fields. Model `product.py` already `Numeric`. |
| 3 | Soft vs hard delete | **Pass.** Category/Brand/UOM/Product set `deleted_at` (`:316, 384, 487, 689`). Identifier/conversion/price `session.delete` (`:759, 840, 953`). Lists filter `deleted_at IS NULL`. GET deleted → 404. See W1 for orphan children. |
| 4 | Wrapper + `PaginatedResponse` | **Pass.** Lists return `PaginatedResponse` with `data=[...]` and sibling `pagination` (`routers/products.py:49-63, 129-143, 203-216, 276-300`). Tests forbid nested `items` (`test_products.py:97-103`). Item POST 201; DELETE `{success: true, data: null}`. Child GETs unpaginated `SuccessResponse[list]`. |
| 5 | Identifier allow-list, price types, UOM conversion (no `from_uom_id`) | **Pass.** `IdentifierType` / `PriceType` enums; `Literal["AED"]`; conversion body `to_uom_id` + `conversion_factor` only; `extra="forbid"`; semantic in module docstring + `_CONVERSION_BASE_MSG`; `to_uom_id == base` → 400; optional `base_uom_id` echo on conversion response. |
| 6 | Duplicate SKU/name 409 | **Pass.** Category/brand name among non-deleted (`:276-277, 353-354`). SKU/UOM code include deleted rows (`:494-506, 411-423`) matching live uniques. Product **name** is not unique in the addendum (only SKU). |
| 7 | UOM delete blocked when referenced | **Pass (code)** for live `base_uom_id` and live-product conversions (`:458-486`). Test covers base UOM only (W4). |
| 8 | PUT `base_uom_id` with conversions 400 | **Pass.** `:662-667`; tested `test_products.py:519-538`. Same `base_uom_id` is allowed. |
| 9 | Extra body keys 422 | **Pass.** `StrictModel` `extra="forbid"` (`schemas/products.py:36-39`). POST `hs_code` and conversion `from_uom_id` tested. |
| 10 | Router owning business rules | **Pass.** Service has uniqueness, isolation, conversion/price/UOM/VAT bounds. Router: parse, `Depends`, commit, wrap. |
| 11 | E402, `print()`, secrets in logs | **Pass** on app files (I5). |
| 12 | Tests: missing cases / false greens / child isolation | **Nits** — W3, W5. Core §13 cases exist and are not false greens. Isolation of children is present for GET/DELETE. |
| 13 | E2E payload changes hiding regressions | **Pass** — I3. Tightening, not loosening business asserts. |
| 14 | Alembic/history rewritten | **Pass** — I4. |

---

## What shipped vs spec (confirmation)

- Endpoints: category / brand / UOM / product CRUD + nested identifier/conversion/price. Static paths before `/{product_id}`.
- `is_active` list filter optional; default both.
- `tax_rate` optional 0–100; not copied from workspace 5.00.
- Currency AED only; `DEFAULT_SALES` / `TIER_1` / `CUSTOMER_SPECIFIC` rules in schema validator + service unique checks.
- PostgreSQL test harness (`invoicesaas_test` derivation, `create_all` like existing suite — not production `create_all`).
- Coder report exists: `.agents/reports/backend-execution-report.md` (2026-08-31 WP-1 section).

---

## Coder follow-up (nits only — do not block WP-2)

Not a BLOCK list. Do these in a small follow-up if WP-2 will delete/recreate catalog rows:

1. **W1:** `delete_product` hard-deletes child identifier/conversion/price rows; test MPN reuse after product soft-delete.
2. **W2:** Category cycle walk must not 404 on deleted ancestors.
3. **W3 / W5:** Isolation + missing §13-adjacent tests listed above.
4. **W4:** Test UOM delete blocked by conversion `to_uom_id`.

---

## APPROVE_WITH_NITS

WP-2 (frontend catalog UI) may start against these contracts:

- `PaginatedResponse`: `data` is an array; `pagination` sibling.
- POST create **201**; DELETE `{ success: true, data: null }`.
- Extra keys (`hs_code`, `from_uom_id`, `type` on product, `base_currency`, electrical specs) → **422**.
- Cross-tenant resource access → **404**.
- Conversion: 1 `to_uom` = `conversion_factor` × base UOM; no `from_uom_id`.
- Prices: `DEFAULT_SALES` | `TIER_1` | `CUSTOMER_SPECIFIC`, currency `AED`.
- Identifiers: `MPN` | `BARCODE` | `SUPPLIER_CODE` | `EAN` | `UPC` | `CUSTOMER_CODE`.

Do **not** start WP-2 expecting `selectinload` or identifier reuse after product delete until W1 is fixed.
