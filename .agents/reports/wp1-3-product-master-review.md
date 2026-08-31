# WP-1–3 Product Master — Code Review

**Date:** 2026-08-31
**Reviewer:** reviewer subagent
**Scope:** Wave 3 Product Master slice — WP-1 API + claimed W1–W5 nits, WP-2 catalog UI, WP-3 Playwright.
**Mode:** review only. No product-code patches (no P0 tenant-leak or money-float bug found).
**No git commit.**

**Specs:** `architecture/wave-3-product-master-addendum.md`, `.agents/reports/mvp-execution-sequence-2026-08-31.md` §5 WP-1–3, `.claude/CLAUDE.md`, `.agents/reports/wp1-product-api-review.md`.

**Verdict:** `APPROVE_WITH_NITS`

WP-1–3 source may be committed **when the user asks**. Next V3 work (FTA tax invoice / quotes / LPO) is **not** this reviewer’s job.

---

## Verdict rationale (short)

Isolation stays JWT `workspace_id` with **404** (never 403) on cross-tenant product and child GET/PUT/DELETE/POST. Money/tax/conversion fields are Pydantic `Decimal` / SQLAlchemy `Numeric`; UI formats with `?? 0` before `toFixed`. Product soft-delete now **hard-deletes** identifier, conversion, and price rows (prior W1). List JSON is live `PaginatedResponse` (`data` = array); the UI unwraps that array, not `data.items`. Extra keys / `from_uom_id` / `hs_code` → 422; UI payloads omit those keys. Router is HTTP-only. No Alembic rewrite, `models/product.py` untouched, payment PUT untouched.

Prior WP-1 nits **W1–W5 are fixed in code and tests**. Remaining items are UX contract (register min 6 vs API 8), Playwright coverage holes (conversion after reload; auth rate-limit on re-run), and accepted W6 uniqueness race. None are tenant-leak or float-money P0.

---

## Findings (severity first)

### Critical

_None._ No cross-workspace leak in reviewed query paths. No `float` / `Float` on product money, tax, reorder, conversion, or price schema/model fields. Payments/PDC PUT not modified. Alembic `d3e4c7fdb29f` still revises `96b45ccabfb7`; no new revision.

---

### Warning

#### W1 — Frontend register/login zod min 6 vs API password min 8

- **File:line:** `frontend/src/pages/Register.tsx:14`; `frontend/src/pages/Login.tsx:13`; `backend/app/auth/router.py:39-43`
- **Severity:** **Warning** (not P0). Users with 6–7 character passwords pass client validation, then get API 422. Not a tenant leak, not a money bug, not a WP-3 false green (E2E uses `Passw0rd1`, 9 chars). Login has the same min-6 schema (pre-existing). WP-3 only added `data-testid="register-submit"` on Register.
- **Required fix:** Align zod to `min(8)` (and copy) so the UI matches `UserRegister`. Do not treat this as a security incident. Do not block the WP-1–3 commit.

#### W2 — Playwright happy path does not re-assert conversion after reload

- **File:line:** `frontend/e2e/product-catalog.spec.ts:50-67`
- **Why:** WP-3 AC is SKU → identifier → conversion → AED price → **reload still shows it**. After reload the spec asserts product row, MPN row, and `AED 12.50`. Conversion is asserted **before** reload only (`conversion-label` contains `500`). Persistence of the DRUM conversion is unproven in E2E (API tests cover CRUD).
- **Required fix:** After reload + row click, `expect(page.getByTestId('conversion-label')).toContainText('500')`. Nit; catalog run was reported green (3.3s).

#### W3 — Auth `5/minute` register limit can flake a second local Playwright run

- **File:line:** `backend/app/config.py:21` (`RATE_LIMIT_AUTH = "5/minute"`); `frontend/playwright.config.ts:10` (`workers: 1`); `frontend/e2e/product-catalog.spec.ts` + `product-isolation.spec.ts` (3 registers per suite: catalog 1 + isolation A/B)
- **Why:** One suite stay under 5. A re-run from the same IP inside 60s can 429 `/auth/register`. Workers=1 is the right in-suite mitigation. Not a product bug.
- **Required fix:** Unique-enough already; optional `test.setTimeout` / retry-on-429 in helpers, or document “wait 60s before re-run”. Do not raise production auth limits for E2E.

#### W4 — Customer-specific price client dropdown uses unpaginated `getClients` (default 20)

- **File:line:** `frontend/src/pages/ProductDetailPanel.tsx:327`; `frontend/src/api/clients.ts:13-16`
- **Why:** `GET /api/v1/clients` is `PaginatedResponse` (default `per_page=20`). `getClients` types `SuccessResponse<Client[]>` but runtime `data` is still the array, so the first page works. CUSTOMER_SPECIFIC cannot pick client 21+. WP-3 happy path only uses `DEFAULT_SALES`. Pre-existing clients client; WP-2 newly depends on it.
- **Required fix:** Pass `per_page=100` (or paginate) when loading clients for the price form. Out of WP-3 AC.

#### W5 — Commit set must not include caches, `node_modules`, or `dist`

- **Evidence:** git status at review time lists `frontend/node_modules/**`, `frontend/dist/**`, `backend/.pytest_cache/**`, `backend/.ruff_cache/**`, `__pycache__`.
- **Why:** Not a product defect. Committing those would bloat the tree and can leak install artifacts.
- **Required fix:** When the user asks to commit, stage only WP-1–3 source, tests, Playwright harness, and `.agents/reports/*` / addendum. Keep `frontend/.gitignore` (`node_modules`, `dist`, `/test-results/`, `/playwright-report/`).

---

### Info

#### I1 — Prior WP-1 nits W1–W5: verified fixed

| Prior | Claim | Evidence |
|---|---|---|
| W1 orphan identifiers | Product soft-delete hard-deletes children | `product_service.py:714-731` `_hard_delete_children`; `test_mpn_reusable_after_product_soft_delete` |
| W2 deleted ancestor 404 | Walk stops on deleted/missing ancestor | `_load_category_maybe` + `_walk_live_ancestors`; `test_category_parent_walk_ignores_deleted_ancestor` |
| W3 JWT vs query `workspace_id` | Token B + `?workspace_id=<A>` still 404 | `test_multi_tenant_isolation.py:327-427`; `test_workspace_b_cannot_access_workspace_a_product_or_children` (product + children POST/GET/DELETE + category/brand/UOM) |
| W4 UOM vs conversion `to_uom` | Live conversion blocks UOM delete | `test_uom_delete_blocked_when_live_conversion_references_it` |
| W5 missing tests | Circular parent, brand 409, inactive list, TIER_1 dup, shared MPN, `INTERNAL_SKU`, PUT `hs_code`, tax_rate null | `test_products.py` functions listed in checklist below |

#### I2 — W6 price uniqueness race (accepted)

- **File:line:** `product_service.py:899-973` (`create_price` flushes without `_flush_or_conflict`)
- **Why:** Addendum forbids WP-1 Alembic unique indexes. Concurrent `DEFAULT_SALES` POSTs can both pass the SELECT. Documented in backend report; not P0.

#### I3 — GET product children via extra queries, not `selectinload` (accepted)

- No `Relationship` on `Product` (model locked). Three scoped selects filter `product_id` **and** `workspace_id`. No stock embed.

#### I4 — Error wrapper `code` is still generic `HTTP_ERROR`

- Same as invoices/SPO. HTTP status 400/404/409 is correct. Machine `CONFLICT` not used.

#### I5 — Playwright coverage leftovers (documented by frontend report)

Not covered in browser: invoice send/pay, GRN, 3-way match, FTA PDF, quotations, product **edit/soft-delete UI**, TIER_1 / CUSTOMER_SPECIFIC, Playwright in GitHub Actions. Isolation E2E is API GET only (no `/products/:id` route in the SPA). Child isolation lives in pytest.

Happy-path waits are web-first (`toBeVisible`, `toHaveCount(0)`, `toPass`, `selectOptionContaining` waits for option). No `waitForTimeout`. SKU `CBL-4MM-001` is hardcoded but each run **registers a new workspace**, so uniqueness is per-tenant — not a cross-run collision. MPN uses `uniqueSuffix()`.

#### I6 — Style / CLAUDE.md hygiene

- No `print()` in product service/router/schemas. Logs: `workspace_id` / `product_id` only.
- Imports at top of app files. Tests keep the suite’s post-`win32` import pattern.
- `product_service.py` ~995 lines (style cap 500). Split later; not an addendum fail.
- Zod `Number(...)` is client-side validation only; create/update bodies send **strings** for tax, factor, and price (`optionalAmount`, `.trim()`).

#### I7 — `get_current_workspace_id` is JWT-only

- `backend/app/auth/dependencies.py:86-89` returns `current_user.workspace_id`. Product router never binds query/body `workspace_id`.

#### I8 — Alembic / payments / model lock

- `d3e4c7fdb29f` `down_revision = '96b45ccabfb7'` (ancestor of HEAD `06c9b4b1dcda`). No new versions file in `backend/alembic/versions/` (19 files, same chain as mvp-sequence).
- `backend/app/models/product.py` — money columns remain `Numeric`; no diff required for WP-1–3.
- `backend/app/routers/payments.py:236` `PUT /invoices/{invoice_id}/payments/{payment_id}` still present (addendum §14).

---

## Checklist (review prompt)

| # | Item | Result |
|---|---|---|
| 1 | Tenant isolation still 404 (API + e2e isolation spec) | **Pass.** Service `_get_live` / `_require_live_product` filter `workspace_id` + `deleted_at IS NULL`. Child writes load the parent in JWT workspace first. Pytest: product + identifier/conversion/price GET/PUT/DELETE/POST as B with `?workspace_id=A` → 404; category/brand/UOM GET/PUT/DELETE → 404. Playwright `product-isolation.spec.ts`: B GET A’s product → 404, not 403. Own GET 200. |
| 2 | Decimal money; no float in models/schemas; UI `?? 0` before toFixed | **Pass.** Schemas: `tax_rate` / `reorder_level` / `price` / `min_quantity` / `conversion_factor` are `Decimal` with digit constraints. Model: `Numeric(5,2)` / `(12,2)` / `(14,6)`. `test_schema_fields_are_not_float`. UI: `formatAed` / tax label use `Number(amount ?? 0).toFixed(2)`. Settings tax coerce is `Number(workspace.default_tax_rate ?? 5)` for display (Wave 2 workspace field; not product money storage). |
| 3 | Soft-delete product still hard-deletes children (W1) | **Pass.** `_hard_delete_children` then `deleted_at`. Nested child DELETE on deleted parent still 404. MPN reusable on a new product. SKU of soft-deleted product still 409 (`uq_workspace_internal_sku`). |
| 4 | PaginatedResponse vs UI list unwrap | **Pass.** Router lists return `PaginatedResponse` with `data=[...]` and sibling `pagination`. `frontend/src/types/api.ts` matches. `unwrapList` uses `Array.isArray(payload.data)` — not `data.items`. Child GETs are unpaginated `SuccessResponse[list]`. Tests forbid nested `items`. |
| 5 | Extra keys 422; no `hs_code` / `from_uom_id` in UI payloads | **Pass.** `StrictModel` `extra="forbid"`. POST/PUT `hs_code` and conversion `from_uom_id` tested 422. UI `ProductWrite` / `ConversionWrite` / `PriceWrite` only live fields; `currency: 'AED'` on price create. Grep: no `hs_code` / `from_uom_id` / `vat_category` under `frontend/`. |
| 6 | Playwright covers WP-3 AC; flaky waits; hardcoded data | **Pass with nits (W2, W3).** Flow: register UI → Settings TRN + tax `Number()===5` → UOM MTR/DRUM → category Cables → brand Ducab → SKU `CBL-4MM-001` → MPN → conversion 500 → AED 12.50 → reload row/identifier/price. Isolation spec is API 404. Waits are Playwright assertions, not sleeps. Hardcoded SKU is safe per new workspace. Conversion after reload unasserted (W2). Auth 5/min re-run flake (W3). Frontend report: 2 passed locally vs docker API, not SQLite. |
| 7 | Password mismatch 6 vs 8 | **Warning (W1).** Not P0. E2E uses 8+. Align zod later. |
| 8 | Secrets in e2e, CI, `.env` | **Pass.** `E2E_PASSWORD = 'Passw0rd1'` is a fixture, not a production secret. CI `SECRET_KEY: ci-test-secret-key-not-for-production`. No live credentials in Playwright helpers. Do not commit `.env`. |
| 9 | Router still HTTP-only | **Pass.** `routers/products.py`: parse, `Depends`, `commit`/`refresh`, wrap. Uniqueness, isolation, conversion/price/UOM/VAT rules live in `ProductService`. |
| 10 | No Alembic rewrite, payment PUT untouched | **Pass.** I8. |

---

## WP-1–W5 nits vs this tree

| Nit | Status |
|---|---|
| W1 hard-delete children + MPN reuse | **Fixed** |
| W2 category ancestor walk | **Fixed** |
| W3 query spoof + catalog isolation + child POST | **Fixed** |
| W4 UOM delete vs conversion `to_uom` | **Fixed** (live product only; after W1, conversions on deleted products are gone) |
| W5 missing tests | **Fixed** (circular, brand 409, inactive list, TIER_1 dup min_qty, shared MPN, INTERNAL_SKU, PUT hs_code, tax_rate null) |
| W6 DEFAULT_SALES race | **Accepted** (no Alembic unique) |

---

## WP-2 AC (code review)

| AC | Result |
|---|---|
| Replace `alert('Add Product UI coming soon')` | **Pass.** Tabs + modals + detail panel. |
| Create category → brand → UOM → product → identifier → conversion → price | **Pass** (UI + Playwright happy path). |
| Edit and soft-delete; Query invalidate | **Pass in code** (edit/delete buttons, `invalidateQueries`). Not exercised in Playwright (documented leftover). |
| No new `.toFixed` without `?? 0` | **Pass** on product UI helpers. |
| AuthGuard wraps `/products`; 401 → login | **Pass.** `App.tsx` nested route under `AuthGuard` + `Layout`. Guard `Navigate`s to `/login`. Axios interceptor toasts API errors (catalog mutations rely on that, no local `onError`). |
| `npm run build` | Reported green in frontend execution report (not re-run this review). |

Lookups use `per_page=100` (API max). Workspaces with >100 UOMs/categories will truncate dropdowns — acceptable for this slice.

---

## WP-3 AC

| AC | Result |
|---|---|
| Browser flow vs local docker API, not SQLite | **Pass** (reported 2/2; global-setup hits `/health/ready` which runs `SELECT 1`). |
| Cross-tenant product access 404 | **Pass** (pytest + Playwright request spec). |
| Failures not silently skipped | **Pass.** No `test.skip` in e2e specs. |
| Document not-covered | **Pass.** Frontend report lists invoice/GRN/3-way/FTA/quotes/edit UI. |

---

## What must not be in the commit (when the user asks)

Include: backend product service/schemas/router/tests, e2e payload tweaks, frontend catalog + Playwright + testids, `.agents/reports/*`, `architecture/wave-3-product-master-addendum.md`.

Exclude: `frontend/node_modules`, `frontend/dist`, pytest/ruff/`__pycache__`, `.env`, Playwright report folders (already gitignored).

---

## APPROVE_WITH_NITS

WP-1–3 may be committed when the user asks. Follow-ups (not blockers, not this reviewer’s job to implement):

1. Zod password min 8 on Register/Login.
2. Assert conversion label after Playwright reload.
3. `getClients({ per_page: 100 })` for customer prices (later).
4. Unique index for `DEFAULT_SALES` when a later Alembic WP exists.

**Do not start FTA tax invoice / quotations / LPO in this review.** Those remain later V3 work per the addendum and mvp-sequence.
