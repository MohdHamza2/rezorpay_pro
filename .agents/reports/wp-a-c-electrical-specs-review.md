# WP-A–C Electrical Catalogue Spec Columns — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full slice — WP-A API+Alembic+pytest, WP-B UI, WP-C Playwright. Review only. No git commit. No code changes (no P0).
**Spec:** `architecture/wave-electrical-specs-addendum.md` (full), `.agents/reports/wp-a-electrical-specs-review.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

No P0. The slice **may be committed when asked**.

Next remaining UAE gap after this (do **not** implement here): **debit notes**. That Alembic **must** set `down_revision = "1a30af047312"`, not `b8d5f0c3a216`. Peppol stays later.

---

## P0 gate (BLOCK if any fail)

| Gate | Result |
|---|---|
| Float spec columns | **PASS.** `amp_rating` / `cable_size_mm2` are `Optional[Decimal]` + `Numeric(8, 2)`. Cores/poles `Integer`. Voltage `String(32)`. No `float` / `Float` on the new fields. Not money; not `Numeric(12, 2)`. UI sends spec values as strings/ints; API persists Decimal. |
| Isolation 403 | **PASS.** Cross-workspace GET/PUT still 404 via `_get_live` (`!= 403` in pytest). Playwright `electrical-specs.spec.ts` workspace-B GET → **404** not 403. Unchanged `product-isolation.spec.ts` still asserts GET 404 not 403. List is JWT `workspace_id` only. |
| Rewritten Alembic history | **PASS.** Credit-notes blob hash matches `HEAD`: `8b63842449c06ec02a63591cda923d59bd34d8fc`. `git diff` on `b8d5f0c3a216_add_credit_notes.py` is empty. Only child of `b8d5f0c3a216` is `1a30af047312`. `d3e4c7fdb29f` not edited. |
| JSONB `specs` blob | **PASS.** No `specs` column on `products`. POST `specs: {}` still 422 (`extra="forbid"`). Migration has no JSONB. |
| Invoice / quote / LPO / CN / DN line snapshot columns | **PASS.** Line models unchanged (no amp/mm²/cores/poles/voltage). `_resolve_line` still copies `internal_sku` → `sku_snapshot` only; description from name; no spec append. `git diff` on `invoice_service.py` is empty. |

---

## Checklist (user + addendum)

| # | Item | Result |
|---|---|---|
| 1 | Linear Alembic; credit-notes unmodified | **PASS.** `1a30af047312_add_product_electrical_specs.py` `down_revision = "b8d5f0c3a216"`. Credit-notes file identical to `HEAD`. Reviewer `alembic heads` → `1a30af047312 (head)`. `alembic check` → `No new upgrade operations detected`. |
| 2 | Decimal Numeric(8,2) amp/mm2; voltage string; no float | **PASS.** Migration and model: `Numeric(8, 2)` / `Integer` / `String(32)`. Pydantic `gt=0`, `max_digits=8`, `decimal_places=2`; cores `ge=1, le=24`; poles `ge=1, le=4`. Voltage regex `^[0-9]+(/[0-9]+)?$` after strip; blank → null. Tests: `1.5` / `2.5` mm², `230/400`, `230V` / `11kV` / `230 / 400` → 422. No DB CHECK. |
| 3 | `extra=forbid`; hs_code / specs 422 | **PASS.** `ProductCreate` / `ProductUpdate` inherit `StrictModel` via `ProductElectricalSpecs`. POST/PUT `hs_code` and `specs: {}` 422; known `amp_rating` create 201. Frontend never posts `hs_code` / `name_ar` / `specs`. |
| 4 | Isolation 404 API + Playwright | **PASS.** Pytest: B GET/PUT A’s product 404 (not 403) with spoof `?workspace_id=`; B’s `?amp_rating=63` omits A’s breaker. Playwright new spec + unchanged `product-isolation.spec.ts`: 404 not 403. |
| 5 | `_resolve_line` / line models untouched | **PASS.** No git diff on `invoice_service.py`. Invoice / quote / LPO / CN / DN item models still `sku_snapshot` max 100 only. No spec columns on those tables. |
| 6 | ProductDetailPanel not rebuilt; invoice pickers unfiltered | **PASS.** `ProductDetailPanel.tsx` has no spec fields and no git diff. Identifiers / conversions / prices only. Invoice / quote / LPO pickers still `getProducts({ is_active: true, per_page: 100 })` with distinct query keys (`invoice-picker` / `quotation-picker` / `lpo-picker`). Category/brand/UOM tabs have no spec filters. |
| 7 | Playwright: 4C 10mm² vs 63A 3P; catalog spec still green | **PASS (spec + coder run).** New spec creates `CBL-4C10-{suffix}` cores 4 mm² 10 and `MCB-63-3P-{suffix}` amp 63 poles 3; filter mm²+cores shows cable not breaker; Clear; filter amp+poles shows breaker not cable. `product-catalog.spec.ts` and `product-isolation.spec.ts` have **zero** git diff (no spec fields required). Coder: `npm run test:e2e` **25 passed**; this review counted **25** `test(` calls under `frontend/e2e/` (matches). Catalog still creates without filling spec inputs (`pickSpecCreate` omits empties). |
| 8 | Search not parsing 10mm / 63A | **PASS.** `list_products` search remains ILIKE on `internal_sku` / `name` / `description` only. Pytest: `search=10mm` does not hit a row whose name/SKU/description lack `10mm` even with `cable_size_mm2=10`. Products UI has **no** search box and does not parse filter strings into specs. |

---

## WP-B UI (addendum §7)

| Item | Result |
|---|---|
| Optional form Amp / Cable mm² / Cores / Poles / Voltage | **PASS.** Testids match. Zod optional; voltage regex client-side. |
| Empty create omits; empty update JSON `null` | **PASS.** `pickSpecCreate` / `pickSpecUpdate`. |
| Filter toolbar Apply + Clear; query key refetch | **PASS.** `['products', { page, ...specQuery }]`. Clear resets to `EMPTY_PRODUCT_SPEC_FILTERS`. |
| One Specs column | **PASS.** `formatProductSpecs`: `4C 10mm²`, `63A 3P`, optional ` {voltage}V` display suffix, else `—`. Trailing zeros stripped. Compact CSS `specsCell`. |
| `listParams` omits unset so pickers unconstrained | **PASS.** `assignIfPresent` skips `undefined` / `''`. Axios encodes `/` in `230/400`. |
| `npm run build` | **PASS (coder).** `tsc -b && vite build` green. Not re-run in this review. |

---

## WP-C Playwright (addendum §8)

| Item | Result |
|---|---|
| New `frontend/e2e/electrical-specs.spec.ts` only | **PASS.** Does not rewrite catalog/isolation specs. |
| Helpers: `registerViaUi`, `createUom`, `E2E_PASSWORD` (`Passw0rd1`) | **PASS.** |
| Unique SKUs via `suffix` | **PASS.** |
| Optional isolation GET 404 in the new spec | **PASS.** |
| Runtime API 8000 / Vite 5173 | **PASS.** `playwright.config.ts` `VITE_API_URL` default `http://localhost:8000`, `baseURL` 5173. Never SQLite. |
| Full e2e 25/25 | **PASS (coder evidence).** 22 spec files, 25 tests. This review did **not** re-run Playwright (8+ min docker). Spec content matches §8. |

---

## Findings

### Critical (P0)

None.

### Warning

**W1 — Alembic pytest uses app `DATABASE_URL`, not `invoicesaas_test`** *(carried from WP-A)*

`test_alembic_new_revision_parent_and_check` runs `alembic heads` / `upgrade head` / `check` against `settings.DATABASE_URL`. The rest of the module uses `{DATABASE_URL}_test` + `create_all`. Same pattern as credit-notes WP-A. This review’s live `alembic check` on the app DB was clean. Do not treat a green pytest as “upgrade head on `_test`”.

**W2 — Non-digit cores/poles filters are silently dropped**

`parseFilterInt` requires `/^\d+$/`; `"abc"` becomes `undefined` and is omitted from the query. Amp/mm² invalid values still go to the API and 422. Staff can think cores/poles applied when only the other filters ran. UX only; typed 4C / 63A 3P path is correct.

### Info / nits (do not block commit)

**I1 — List `?voltage=` has no dedicated pytest** *(carried from WP-A)*

Service equality is implemented. §6.5 tests mm²+cores and amp+poles AND, not `?voltage=230/400`. UI can send the encoded query param. Filter voltage testid exists; WP-C leaves it optional/unfilled.

**I2 — New isolation tests do not DELETE**

Addendum §6.9 / WP-C optional ask GET (and WP-A PUT). DELETE remains 404 via `_require_live_product`; covered by existing product isolation tests. Isolation spec file correctly left unchanged.

**I3 — Invalid list `voltage` 422 body is a string `detail`**

Write-body voltage failures go through Pydantic. List uses `Depends(_list_voltage)` → `HTTPException(422, detail=str(exc))`. WP-B `errors.ts` now reads string `detail` for toasts (HTTP 422, not a specific `error.code`). Small global interceptor change; fallback still `'An error occurred'` when `detail` is a Pydantic list.

**I4 — File length**

`routers/products.py` 556 lines; `Products.tsx` 533 lines (addendum “files < 500”). No new routes. Spec helpers live in `productUi.tsx` (380). Not a behaviour bug.

**I5 — `1.6` A and `search=63A` are untested** *(carried from WP-A)*

`gt=0` + `Numeric(8, 2)` accept `1.6`. Search does not parse `63A` (same ILIKE path as `10mm`). Playwright names the cable `4-core 10mm XLPE` — findability under test is still the typed filters, not search.

**I6 — Playwright does not assert Specs cell text**

WP-C required row visibility under filters, not `4C 10mm²` / `63A 3P` in the Specs column. Formatter matches §7. Optional later.

**I7 — Pytest schema is `create_all`, not Alembic, on `_test`**

Matches `test_products.py`. Linear history is the new revision file + this review’s `alembic check` on the app DB.

---

## Diff surface (this slice)

Touched (commit-when-asked set):

- `backend/app/models/product.py`
- `backend/app/schemas/products.py`
- `backend/app/routers/products.py`
- `backend/app/services/product_service.py`
- `backend/alembic/versions/1a30af047312_add_product_electrical_specs.py` *(new)*
- `backend/tests/test_product_electrical_specs.py` *(new)*
- `frontend/src/api/products.ts`
- `frontend/src/api/errors.ts` *(string `detail` toast only)*
- `frontend/src/pages/Products.tsx`
- `frontend/src/pages/productUi.tsx`
- `frontend/src/pages/Products.module.css`
- `frontend/e2e/electrical-specs.spec.ts` *(new)*

Confirmed **untouched**: credit-notes Alembic, `invoice_service._resolve_line`, invoice/quote/LPO/CN/DN line models, `ProductDetailPanel.tsx`, `product-catalog.spec.ts`, `product-isolation.spec.ts`, invoice/quote/LPO picker `getProducts` calls.

---

## Alembic for later WPs

| | |
|---|---|
| New HEAD | **`1a30af047312`** |
| Parent | **`b8d5f0c3a216`** (credit notes; unmodified) |
| Debit notes | `down_revision = "1a30af047312"` |
| Peppol | later, not next |

---

## Test evidence (this review)

```
pytest tests/test_product_electrical_specs.py tests/test_products.py tests/test_multi_tenant_isolation.py
45 passed, 1 warning in 53.09s
```

```
alembic heads  →  1a30af047312 (head)
alembic check  →  No new upgrade operations detected
credit-notes hash == HEAD  →  8b63842449c06ec02a63591cda923d59bd34d8fc
```

Playwright: coder `npm run test:e2e` **25 passed** (8.1m). This review verified spec files and the 25-test count; did not re-run the browser suite.

---

## Commit-when-asked

**Yes.** Include the files in “Diff surface” plus the execution/review reports if the commit convention requires them. Do **not** include `.pytest_cache`, `.ruff_cache`, `frontend/dist`, or `.claude-flow` policy tmp files.
