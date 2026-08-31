# Frontend Execution Report - GRN Module (Task 5L)

## Implemented Features
1. **GRN List View**:
   - Updated `frontend/src/pages/GRN.tsx` to include navigation to the new detailed reconciliation view.
2. **GRN API Client**:
   - Refactored `frontend/src/api/grn.ts` to include complete types and backend API hooks (e.g. `startReceiving`, `stageForInspection`, `recordDisposition`, `addGRNItem`).
3. **GRN Detail & Reconciliation View (`frontend/src/pages/GRNDetail.tsx`)**:
   - **Receiving Screen**: Allows the warehouse staff to transition the GRN from `DRAFT` to `RECEIVING`.
   - **Raw Quantity Entry**: Added a form section available in `RECEIVING` state to pull SPO items and accept raw `quantity_received` input, making an atomic call to the backend.
   - **Stage for Inspection**: Enables moving the GRN from `RECEIVING` to `PENDING_INSPECTION`.
   - **Disposition UI**: A complete form leveraging `react-hook-form` to split the received quantity into `quantity_accepted`, `quantity_damaged`, and `quantity_rejected`.
   - **Validation**: Added client-side checks ensuring `qty_accepted + qty_damaged + qty_rejected === quantity_received` and mandatory reasons for damaged or rejected goods. Validation feedback is provided via `react-hot-toast`.
4. **App Routing**:
   - Added `GRNDetail` as a route in `frontend/src/App.tsx`.

## Architecture Compliance
- The UI handles the invariants correctly per `INV-5.1` by enforcing validations on the frontend prior to triggering API calls.
- Connects directly to the backend schemas provided by the Backend Agent.

---

# WP-2 Product Master UI — Plan (before edits)

**Date:** 2026-08-31
**Owner:** frontend / coder
**Depends on:** WP-1 Product Master API as shipped (`backend/app/routers/products.py`, `schemas/products.py`, addendum `architecture/wave-3-product-master-addendum.md`)

## Goal

Replace `alert('Add Product UI coming soon')` in the existing Vite + React app with a full electrical catalog UI: Products | Categories | Brands | UOMs, plus product detail for identifiers, UOM conversions, and AED prices. No Next.js, no Tailwind, no second app.

## API client contract (critical)

WP-1 list endpoints return `PaginatedResponse`: `{ success, data: T[], pagination }`.

- Add `PaginationMeta` + `PaginatedResponse<T>` to `frontend/src/types/api.ts` if missing.
- `getProducts` / `getCategories` / `getBrands` / `getUOMs` must read `response.data.data` (the array) and pass `page` / `per_page` (default 100, API max).
- Bodies must `extra='forbid'`-safe: never send `hs_code`, `type: GOODS`, `from_uom_id`, `amp`, electrical spec fields, or nested PUT on children.

## Files to change

| File | Change |
|---|---|
| `frontend/src/types/api.ts` | Add pagination types |
| `frontend/src/api/products.ts` | Full CRUD matching WP-1 paths |
| `frontend/src/pages/Products.tsx` | Tabs, product list, create/edit modal, soft-delete, row → detail |
| `frontend/src/pages/ProductDetailPanel.tsx` | Identifiers / conversions / prices (new) |
| `frontend/src/pages/ProductCatalogTabs.tsx` | Categories / Brands / UOMs CRUD (new) |
| `frontend/src/pages/productUi.tsx` | Shared modal, skeleton, pagination, AED format helpers (new) |
| `frontend/src/pages/Products.module.css` | Tabs, modal, detail, actions — keep existing module |
| `frontend/src/App.tsx` | No route change; AuthGuard already wraps `/products` |

## UX copy from Clients.tsx

Modal overlay, react-hook-form + zod, react-hot-toast, TanStack Query invalidate-on-success, lucide `Plus`/`Edit2`/`Trash2`, Skeleton rows, `window.confirm` soft-delete.

## Product form (create/edit)

Required: `internal_sku`, `name`, `base_uom_id`.
Optional: description, category, brand, is_active, tax_rate, reorder_level.
Empty UUID selects omitted or sent `null` on update to clear.

## Detail children

No PUT — delete + recreate.
Conversions UI copy: `1 [to UOM] = [factor] [base UOM]`.
Prices: DEFAULT_SALES, TIER_1 + min_quantity, CUSTOMER_SPECIFIC + client_id; currency AED only.
`.toFixed` only with `?? 0` on nullable amounts.

## Out of scope

Playwright (WP-3), backend, Alembic, invoice `product_id`, FTA PDF, git commit.

## Acceptance

1. `cd frontend && npm run build` succeeds
2. User can create category → brand → UOM → product → identifier → conversion → price without API docs
3. Edit + soft-delete; lists refresh via Query
4. No new `.toFixed` on nullable amounts without `?? 0`
5. AuthGuard still wraps; no second Next.js app

## WP-2 implementation (completed)

Shipped against live WP-1 contracts. List clients unwrap `response.data.data` and send `page`/`per_page` (default 100). Create/update bodies omit unknown keys (`hs_code`, `from_uom_id`, electrical specs). Children are POST + DELETE only.

**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

**Route:** `/products` still nested under `AuthGuard` + `Layout` in `App.tsx`. No Next.js, no Tailwind.

**AED:** `formatAed` uses `Number(amount ?? 0).toFixed(2)`. Tax display uses the same null-safe pattern.

**Playwright / backend / Alembic:** not touched (WP-3 / out of scope).

---

# WP-3 Browser E2E — Plan (before edits)

**Date:** 2026-08-31
**Owner:** frontend / coder
**Depends on:** WP-1 API + WP-2 catalog UI
**Spec:** `.agents/reports/mvp-execution-sequence-2026-08-31.md` §5 WP-3

## Goal

Add Playwright to the existing Vite app (`frontend/` only). Prove the electrical catalog path in a real browser against docker PostgreSQL + API (`localhost:8000`, postgres host port **5434**). Never SQLite. No second frontend, no Next.js, no CI product.

## Harness

| Item | Choice |
|---|---|
| Package | `@playwright/test` in `frontend/package.json` |
| Config | `frontend/playwright.config.ts` — `testDir: e2e`, `baseURL: http://localhost:5173`, `webServer: npm run dev`, `reuseExistingServer: !process.env.CI` |
| Browser | Chromium only |
| API | `VITE_API_URL=http://localhost:8000` |
| Script | `"test:e2e": "playwright test"` |
| Workers | 1 (auth rate limit `5/minute` on `/auth/register`) |

If `GET http://localhost:8000/health` fails, start `docker compose up -d postgres api` from repo root before the run.

## Specs

1. **`frontend/e2e/product-catalog.spec.ts` (happy path)**
   Register unique user (`#name`, `#email`, `#password`, `#workspace_name`) → AuthGuard app shell → Settings: default tax shows **5**, TRN field exists → Products → UOM `MTR`/`Metre` → category `Cables` → brand `Ducab` → product SKU `CBL-4MM-001` / NYA 4mm² cable / base MTR → detail: MPN identifier, DRUM conversion factor 500 (`1 … = …`), DEFAULT_SALES AED 12.50 → reload: row + identifier + price persist.

   Password in the test is **8+ characters** (backend `UserRegister` validator). Frontend zod still says min 6.

2. **`frontend/e2e/product-isolation.spec.ts` (negative)**
   Register workspace A via API, create a product, register workspace B, `GET /api/v1/products/{id}` with B's token → **404** (not 403). Does not depend on the UI spec.

## `data-testid` (keep existing CSS modules)

Tabs, add buttons, table rows (`product-row-{sku}`, `uom-row-{code}`, …), product detail sections, identifier/conversion/price controls, Settings tax/TRN, nav Products/Settings.

## Not covered (document after run)

Invoice send/pay, GRN receiving/disposition, supplier invoice 3-way match, FTA PDF, quotations, edit/soft-delete UI, volume/customer prices. Those stay on API pytest (`test_e2e_*.py`). Child-resource isolation already lives in `test_multi_tenant_isolation.py` — do not rewrite unless E2E finds an API bug.

## Acceptance

- Playwright catalog flow passes against local docker API (not SQLite).
- Cross-tenant product GET 404.
- `npm run build` still succeeds.
- Git commit out of scope.

---

# WP-3 implementation (completed)

**Date:** 2026-08-31
**API:** docker `invoicesaas-api` + `invoicesaas-db` (postgres **5434**, API **8000**, `/health/ready` connected). Not SQLite.

## Result

```
Running 2 tests using 1 worker
  ok 1 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (3.3s)
  ok 2 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (502ms)
  2 passed (6.6s)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Same pre-existing chunk-size warning.

No API bug found. Did **not** rewrite pytest; child-resource isolation already in `backend/tests/test_multi_tenant_isolation.py`.

## UI changes (E2E harness, existing CSS modules kept)

- Stable `data-testid` on nav, catalog tabs/add/rows, product form, detail identifier/conversion/price, Settings TRN + tax.
- Settings: `htmlFor` on TRN/tax; `Number()` coerce so UAE VAT default **5** displays when the API sends Decimal JSON.
- Register submit `data-testid="register-submit"`. Password in E2E is 8+ chars (backend validator). Frontend zod still min 6.

No selector/pagination/label failures during the run. First Playwright pass was green.

## Not covered (WP-3 leftovers)

- Invoice send / pay (browser)
- GRN receiving / inspection / disposition (browser)
- Supplier invoice 3-way match (browser)
- FTA tax invoice PDF, quotations, LPO
- Product edit / soft-delete UI, TIER_1 / CUSTOMER_SPECIFIC prices
- Frontend register min-6 vs API min-8 mismatch (tests use 8+)
- Playwright not wired into GitHub Actions (explicitly out of scope)

Those procurement/AR paths already have API e2e: `test_e2e_spo.py`, `test_e2e_grn.py`, `test_e2e_3way_match.py`.

---

# WP-B FTA Tax Invoice UI — Plan (before edits)

**Date:** 2026-08-31
**Owner:** frontend / coder
**Depends on:** WP-A API (`c8e1a4f2b6d0`). Do not touch Alembic. Do not rewrite payment PUT.
**Spec:** `architecture/wave-fta-tax-invoice-addendum.md` WP-B; `.agents/reports/wp-a-fta-tax-invoice-review.md` W2 snapshot fallback.

## Goal

Settings address + invoice form (optional `product_id`, line discount, optional tax inherit, `supply_date`, AED) + client-side PDF titled **Tax Invoice**. Existing Vite + React app only. No Next.js, no Playwright (WP-C), no Arabic font, no IBAN, no Net terms.

## Files

| File | Change |
|---|---|
| `frontend/src/api/errors.ts` | Extract `error.code` / `message` / `field` (incl. `FTA_SEND_BLOCKED`) |
| `frontend/src/api/client.ts` | Toast extracted API message (not generic `detail`) |
| `frontend/src/types/api.ts` | `ErrorResponse.error.field` |
| `frontend/src/api/workspaces.ts` | `address` |
| `frontend/src/api/clients.ts` | `tax_id` (buyer TRN) |
| `frontend/src/api/invoices.ts` | Snapshots, `supply_date`, line net/VAT/discount/`product_id`; write payloads forbid extra keys |
| `frontend/src/pages/Settings.tsx` | Address field; surface API field errors |
| `frontend/src/pages/Clients.tsx` | Label `tax_id` as TRN; B2B address hint |
| `frontend/src/pages/Invoices.tsx` | Catalog + ad-hoc lines; DRAFT-only edit; send surfaces FTA message |
| `frontend/src/components/pdf/InvoicePDF.tsx` | Title Tax Invoice; seller/buyer TRN+address; supply date; line net/VAT/gross; snapshot-or-live fallback |
| CSS modules | Address textarea, line-item grid, hints |

## PDF fallback (W2)

Prefer snapshots when `status !== DRAFT` **and** the snapshot string is non-null/non-empty; otherwise live `/workspaces/me` + client. GET `/invoices/{id}` before download (list rows have no items).

## Out of scope

Playwright WP-C, quotes/LPO, Arabic, IBAN, Net 30/45/60, Alembic, payment PUT, git commit.

## Acceptance

`cd frontend && npm run build` succeeds. Extra keys `hs_code` / `from_uom_id` never sent. `?? 0` before `toFixed` on amounts.

---

# WP-B FTA Tax Invoice UI — Implementation (completed)

**Date:** 2026-08-31
**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

1. **Settings** — workspace `address` textarea (`data-testid="settings-address"`). TRN + default tax 5% kept. API `error.field` mapped onto the form (`workspace.address` → `address`). Address is not required to *save* (drafts allowed); hint states it is required to *send*.
2. **Invoice form** — optional catalog `product_id` (GET products, DEFAULT_SALES fill) + ad-hoc name/qty/price; line discount % XOR amount; blank VAT inherits; `supply_date`; currency locked AED. Create/update bodies omit `hs_code`, `from_uom_id`, `total_price`, `client_id` on PUT. Edit still DRAFT-only; loads GET `/invoices/{id}` because list rows have no items.
3. **PDF** — title **Tax Invoice**. Seller/buyer name, address, TRN; supply date; line net / VAT% / VAT AED / gross; AED totals. Snapshots when `status !== DRAFT` and non-empty; else live workspace + client (W2 old SENT rows). CANCELLED watermark. English only. Download fetches full invoice then `@react-pdf/renderer` `pdf().toBlob()`.
4. **Send** — `FTA_SEND_BLOCKED` toasted from `error.message` on the send action (interceptor skips that code so the button handler is the surface).
5. **Clients** — `tax_id` labeled TRN; address B2B send hint.

Alembic, payment PUT, Playwright WP-C, Arabic, IBAN, Net terms: not touched.

---

# WP-C FTA Tax Invoice Playwright E2E — Plan (before edits)

**Date:** 2026-08-31
**Owner:** frontend / coder
**Depends on:** WP-A API + WP-B UI
**Spec:** `architecture/wave-fta-tax-invoice-addendum.md` WP-C; `.agents/reports/wp-a-fta-tax-invoice-review.md`

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/`). Prove FTA send-block, SIMPLIFIED send + Tax Invoice preview, and cross-workspace invoice GET 404. No second frontend, no Next.js, no CI product, never SQLite.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |

## Specs to add

1. `frontend/e2e/fta-send-blocked.spec.ts` — register → client + DRAFT invoice → send without Settings TRN/address → user sees `FTA_SEND_BLOCKED` (toast or `data-testid="fta-send-blocked"`). Stays DRAFT.
2. `frontend/e2e/fta-tax-invoice.spec.ts` — Settings TRN `100123456789003` + address; client with address (SIMPLIFIED, no buyer TRN); one AED line + supply_date; send → SENT; PDF preview **Tax Invoice** + seller TRN; reload still SENT.
3. `frontend/e2e/fta-isolation.spec.ts` — workspace B GET `/api/v1/invoices/{id}` of A → **404** not 403 (request context, other token).

## UI `data-testid` (keep CSS modules)

Settings save; Clients add/TRN/address; invoice create/send/line/supply_date; FTA banner; PDF preview title + seller TRN. Preview modal (HTML, same snapshot-or-live as `InvoicePDF`) so E2E does not parse binary PDF.

## Out of scope

Arabic PDF, quotes/LPO, payments browser E2E, git commit, GitHub Actions.

## Acceptance

- `npm run test:e2e` green against docker API (not SQLite)
- Existing product catalog + isolation still pass
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → pytest on PostgreSQL after logging `backend-execution-report.md`

---

# WP-C FTA Tax Invoice Playwright E2E — Implementation (completed)

**Date:** 2026-08-31
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200. Not SQLite.

## Result

```
Running 5 tests using 1 worker
  ok 1 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (733ms)
  ok 2 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.6s)
  ok 3 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.0s)
  ok 4 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.4s)
  ok 5 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (1.1m)
  5 passed (1.2m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

No API bug found. No backend/pytest changes. Isolation 404 (not 403) confirmed in browser request-context.

Product-isolation 1.1m is register `5/minute` retry (helpers wait 16s on 429). FTA specs themselves were ~2s each.

## UI / harness

- `data-testid` on Settings save, Clients add/TRN/address, invoice create/send/line/supply_date, FTA banner, PDF preview.
- HTML **Tax Invoice** preview (snapshot-or-live, same `snapOrLive` as `InvoicePDF`) so E2E asserts title + seller TRN without parsing binary PDF. Download still works.
- Persistent `fta-send-blocked` alert for `FTA_SEND_BLOCKED` (toast still fires).
- Register helpers retry on 429. Password still 8+.
- Happy path is **SIMPLIFIED** (seller TRN `100123456789003` + address; client address; no buyer TRN; one ad-hoc AED line).

## Files

- `frontend/e2e/fta-send-blocked.spec.ts` (new)
- `frontend/e2e/fta-tax-invoice.spec.ts` (new)
- `frontend/e2e/fta-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/src/pages/Invoices.tsx`, `Invoices.module.css`
- `frontend/src/pages/Clients.tsx`, `Settings.tsx`
- `frontend/src/components/pdf/invoicePdfFields.ts` (new)
- `frontend/src/components/pdf/InvoicePdfPreview.tsx` (new)
- `frontend/src/components/pdf/InvoicePDF.tsx` (shared `snapOrLive`)

## Not covered (leftovers)

- STANDARD send in the browser (B2B buyer TRN); API covers it
- Catalog `product_id` line in this E2E (addendum WP-C listed it; this slice used ad-hoc per the WP-C brief)
- Arabic PDF, quotes/LPO, payments browser E2E
- Playwright not wired into GitHub Actions
- Frontend register zod min-6 vs API min-8
- Auth register 5/minute (retries; product-isolation can wait ~1m when the window is full)
