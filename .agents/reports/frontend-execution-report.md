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

---

# WP-B Quotations UI + PDF — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/quotations`, Alembic `cb01b6bef962`). Do not touch Alembic. Do not retitle invoice PDF.
**Spec:** `architecture/wave-quotations-addendum.md` WP-B; `.agents/reports/architect-quotations-note.md`

## Goal

Add Quotations to the existing Vite + React app: list + filters, DRAFT create/edit, detail actions, convert to DRAFT invoice, client-side PDF titled **Quotation**. Invoice PDF stays **Tax Invoice**. No Next.js, no Playwright (WP-C), no Arabic, no LPO.

## API client

`frontend/src/api/quotations.ts`: list/get/create/update/delete, send, accept, reject, convert.

- List unwraps `PaginatedResponse.data` array (`response.data.data`) with `page` / `per_page`.
- Write bodies only allow WP-A keys (`extra="forbid"`): never `hs_code`, `from_uom_id`, `line_net`, `total_price` on writes.
- Convert returns `Invoice` (201 first / 200 idempotent). Navigate to `/invoices` (DRAFT invoice list).

## Files

| File | Change |
|---|---|
| `frontend/src/api/quotations.ts` | CRUD + send/accept/reject/convert |
| `frontend/src/pages/Quotations.tsx` | List + status/client/search filters |
| `frontend/src/pages/QuotationForm.tsx` | Create / DRAFT-only edit (catalog + ad-hoc, XOR discount, inherit tax, AED, valid_until +14) |
| `frontend/src/pages/QuotationDetail.tsx` | Status badges, send/accept/reject, convert on ACCEPTED only |
| `frontend/src/pages/quotationHelpers.ts` | Form payloads, dates, AED `?? 0` |
| `frontend/src/pages/Quotations.module.css` | Filters, badges, detail |
| `frontend/src/components/pdf/QuotationPDF.tsx` | Title **Quotation**; quote number; valid until; line net/VAT; EXPIRED/REJECTED watermark |
| `frontend/src/components/Layout.tsx` | Sales nav: Clients, **Quotations**, Invoices |
| `frontend/src/App.tsx` | AuthGuard routes `/quotations`, `/quotations/new`, `/quotations/:id`, `/quotations/:id/edit` |

## Out of scope

Playwright WP-C, Alembic, InvoicePDF title, LPO, public accept, git commit.

## Acceptance

`cd frontend && npm run build` succeeds. Convert only when ACCEPTED, lands on invoices. PDF says Quotation not Tax Invoice. `?? 0` before `toFixed`. Toasts on errors (existing interceptor).

---

# WP-B Quotations UI + PDF — Implementation (completed)

**Date:** 2026-09-01
**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

1. **API client** — `frontend/src/api/quotations.ts` unwraps `PaginatedResponse.data` for list. Write payloads omit extra keys (`hs_code`, `from_uom_id`, line totals). Send `{}`; reject sends `{ reason }` only when provided; convert returns `Invoice`.
2. **Nav / routes** — Sales: Clients → Quotations → Invoices. AuthGuard routes: `/quotations`, `/quotations/new`, `/quotations/:id/edit`, `/quotations/:id`.
3. **List** — status / client / search filters, badges, send (DRAFT), convert (ACCEPTED only).
4. **Form** — catalog + ad-hoc lines, XOR discount, blank VAT inherits 5%, AED, `valid_until` default +14, DRAFT-only edit.
5. **Detail** — send / accept / reject (optional reason) / convert. Convert toasts invoice number and navigates to `/invoices` (DRAFT).
6. **PDF** — new `QuotationPDF` title **Quotation**, quote number, valid until, line net/VAT/gross, EXPIRED/REJECTED watermark, English Helvetica. `InvoicePDF` still **Tax Invoice**.

Alembic, InvoicePDF title, Playwright WP-C, LPO, git commit: not touched.

## Files

- `frontend/src/api/quotations.ts` (new)
- `frontend/src/pages/Quotations.tsx` (new)
- `frontend/src/pages/QuotationForm.tsx` (new)
- `frontend/src/pages/QuotationDetail.tsx` (new)
- `frontend/src/pages/quotationHelpers.ts` (new)
- `frontend/src/pages/QuotationStatusBadge.tsx` (new)
- `frontend/src/pages/Quotations.module.css` (new)
- `frontend/src/components/pdf/QuotationPDF.tsx` (new)
- `frontend/src/components/pdf/QuotationPdfPreview.tsx` (new)
- `frontend/src/components/Layout.tsx`
- `frontend/src/App.tsx`
- `.agents/reports/frontend-execution-report.md`

---

# WP-C Quotations Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/quotations`) + WP-B UI + PDF
**Spec:** `architecture/wave-quotations-addendum.md` WP-C; user brief (client + one AED line; convert → DRAFT invoice; PDF title **Quotation**; cross-tenant GET 404 not 403)

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`, FTA + product specs). Prove quote create → send → accept → convert lands on a DRAFT invoice, HTML preview title is **Quotation** (not Tax Invoice), and workspace B cannot GET workspace A's quote. Do not break product/FTA tests. No LPO. Never SQLite.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` from `frontend/` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |

## Specs to add

1. `frontend/e2e/quotations.spec.ts` — register → client → DRAFT quote (one AED ad-hoc line) → preview **Quotation** (not Tax Invoice) → send → accept → convert → `/invoices` row is **DRAFT**. Cheap extra: after SENT, edit URL redirects and PUT cannot save. After convert, invoice send without Settings TRN/address still shows `FTA_SEND_BLOCKED`.
2. `frontend/e2e/quotation-isolation.spec.ts` — workspace A creates quote via API; workspace B `GET /api/v1/quotations/{id}` → **404** not 403 (request context).

## UI `data-testid` (keep CSS modules)

Fill gaps on list/form/detail: `quotation-edit`, `quotation-number`, `quotation-notes`, `quotation-add-item`. Preview already uses `quotation-pdf-title` / `quotation-pdf-preview`. Reuse `nav-quotations`, `quotation-create`, send/accept/convert, invoice-status/send, `fta-send-blocked`.

## Out of scope

LPO / convert-to-CPO, expired-quote UI, second-convert UI, Arabic PDF, GitHub Actions, git commit.

## Acceptance

- `npm run test:e2e` green (product + FTA + quotations)
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → log only (pytest already covers WP-A)

---

# WP-C Quotations Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 7 tests using 1 worker
  ok 1 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (669ms)
  ok 2 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.5s)
  ok 3 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.0s)
  ok 4 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.6s)
  ok 5 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (1.1m)
  ok 6 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (490ms)
  ok 7 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.3s)
  7 passed (1.3m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

No UI or API bugs found in the run. Product + FTA specs still pass. Isolation 404 (not 403) confirmed in request context.

Product-isolation 1.1m is register `5/minute` retry (helpers wait 16s on 429). Quotation specs themselves were ~2.3s (UI) and 490ms (isolation).

## Specs shipped

1. **Happy path** — unique register (password 8+) → client → DRAFT quote (one AED ad-hoc line) → HTML preview title **Quotation** (invoice `pdf-title` absent) → send → SENT PUT 403 `INVALID_STATE` + `/edit` redirects → accept → convert → `/invoices` DRAFT → send without Settings TRN/address still `FTA_SEND_BLOCKED`.
2. **Isolation** — workspace B `GET /api/v1/quotations/{id}` → **404** not 403.

## UI / harness

- `data-testid`: `quotation-edit`, `quotation-number`, `quotation-notes`, `quotation-add-item`, `quotation-open-{number}` (list/form/detail). Existing send/accept/convert/preview ids reused.
- Helpers: `createAdhocQuotationViaUi`, `pageAccessToken`. Register still retries 429.

## Files

- `frontend/e2e/quotations.spec.ts` (new)
- `frontend/e2e/quotation-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/src/pages/Quotations.tsx`
- `frontend/src/pages/QuotationForm.tsx`
- `frontend/src/pages/QuotationDetail.tsx`
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- Expired-quote cannot convert (browser); API pytest covers it
- Second convert same invoice (browser); API pytest covers it
- Catalog `product_id` line in this E2E (ad-hoc AED line per WP-C brief)
- LPO / convert-to-CPO
- Playwright not wired into GitHub Actions
- Auth register 5/minute (retries; product-isolation can wait ~1m)

---

# WP-B Customer LPO UI + PDF — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/customer-purchase-orders`, Alembic `59084165d346`). Do not touch Alembic. Do not retitle Tax Invoice or Quotation PDFs. Do not change supplier `/spo` “Purchase Orders” nav.
**Spec:** `architecture/wave-customer-lpo-addendum.md` WP-B; `.agents/reports/architect-customer-lpo-note.md`

## Goal

Add Customer LPO to the existing Vite + React app: list + filters, DRAFT create/edit, detail (receive / cancel / partial invoice), convert ACCEPTED quote → DRAFT LPO, client-side PDF titled **LPO**. Invoice PDF stays **Tax Invoice**. Quotation PDF stays **Quotation**. SPO nav stays “Purchase Orders”. No Next.js, no Playwright (WP-C), no OCR, no Arabic.

## API client

`frontend/src/api/lpos.ts`: list/get/create/update/delete, receive, cancel, POST invoices (partial).

- List unwraps `PaginatedResponse.data` array (`response.data.data`) with `page` / `per_page`.
- Write bodies only allow WP-A keys (`extra="forbid"`): never `hs_code`, `from_uom_id`, `line_net`, `total_price`, `quantity_invoiced`, `quotation_id` on manual create.
- Partial invoice body: `{ items?: [{ customer_purchase_order_item_id, quantity }], notes? }` only.
- Convert-from-quote lives on quotations client: `POST /quotations/{id}/convert-to-lpo`.

## Files

| File | Change |
|---|---|
| `frontend/src/api/lpos.ts` | CRUD + receive/cancel/invoices |
| `frontend/src/api/quotations.ts` | `convertQuotationToLpo` + `converted_lpo_id` |
| `frontend/src/pages/Lpos.tsx` | List + status/client/search filters |
| `frontend/src/pages/LpoForm.tsx` | Create / DRAFT-only edit (catalog + ad-hoc, XOR discount, inherit tax, AED) |
| `frontend/src/pages/LpoDetail.tsx` | Receive, cancel, remaining qty → DRAFT invoice |
| `frontend/src/pages/lpoHelpers.ts` | Form payloads, dates, AED `?? 0` |
| `frontend/src/pages/LpoStatusBadge.tsx` | DRAFT/RECEIVED/PARTIAL/INVOICED/CANCELLED |
| `frontend/src/pages/Lpos.module.css` | LPO badges + invoice-remaining inputs |
| `frontend/src/components/pdf/LpoPDF.tsx` | Title **LPO**; internal + customer PO; invoiced/remaining |
| `frontend/src/components/pdf/LpoPdfPreview.tsx` | HTML preview title **LPO** |
| `frontend/src/components/Layout.tsx` | Sales nav: Clients, Quotations, **LPO**, Invoices (`/lpos`) |
| `frontend/src/App.tsx` | AuthGuard routes `/lpos`, `/lpos/new`, `/lpos/:id`, `/lpos/:id/edit` |
| `frontend/src/pages/Quotations.tsx` | Convert to LPO next to convert-to-invoice; disable invoice convert if LPO |
| `frontend/src/pages/QuotationDetail.tsx` | Same convert-to-LPO + open LPO when `converted_lpo_id` |

## Out of scope

Playwright WP-C, Alembic, InvoicePDF title, QuotationPDF title, SPO/GRN, OCR, git commit.

## Acceptance

`cd frontend && npm run build` succeeds. Extra keys never sent. `?? 0` before `toFixed`. PDF title **LPO** not Tax Invoice. `/spo` still “Purchase Orders”.

---

# WP-B Customer LPO UI + PDF — Implementation (completed)

**Date:** 2026-09-01
**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

1. **API client** — `frontend/src/api/lpos.ts` unwraps paginated `data` for list. Write payloads omit extra keys (`hs_code`, `from_uom_id`, line totals, `quotation_id` on manual create). Receive sends `{}`. Partial invoice sends `{ items: [{ customer_purchase_order_item_id, quantity }], notes? }` only.
2. **Nav / routes** — Sales: Clients → Quotations → **LPO** (`/lpos`) → Invoices. AuthGuard routes: `/lpos`, `/lpos/new`, `/lpos/:id/edit`, `/lpos/:id`. Purchasing **Purchase Orders** still `/spo`.
3. **List** — status / client / search (LPO # or customer PO), badges, receive (DRAFT), both internal `LPO-YYYY-XXXX` and `customer_po_number`.
4. **Form** — catalog + ad-hoc lines, XOR discount, blank VAT inherits 5%, AED, optional customer PO + expected delivery, DRAFT-only edit.
5. **Detail** — Receive, Cancel (RECEIVED), Delete (DRAFT), remaining qty inputs → DRAFT invoice (navigates to `/invoices`). Status PARTIAL/INVOICED from API. Linked invoices listed.
6. **Quote convert** — ACCEPTED quote: Convert to LPO next to Convert to invoice (`quotation-convert` unchanged). Invoice convert disabled if `converted_lpo_id`. Lands on DRAFT LPO.
7. **PDF** — new `LpoPDF` title **LPO**, internal number, customer PO, quote ref, ordered/invoiced/remaining, CANCELLED watermark, English Helvetica. `InvoicePDF` still **Tax Invoice**. `QuotationPDF` still **Quotation**.

Alembic, InvoicePDF title, QuotationPDF title, SPO nav, Playwright WP-C, OCR, git commit: not touched.

## Files

- `frontend/src/api/lpos.ts` (new)
- `frontend/src/pages/Lpos.tsx` (new)
- `frontend/src/pages/LpoForm.tsx` (new)
- `frontend/src/pages/LpoDetail.tsx` (new)
- `frontend/src/pages/lpoHelpers.ts` (new)
- `frontend/src/pages/LpoStatusBadge.tsx` (new)
- `frontend/src/pages/Lpos.module.css` (new)
- `frontend/src/components/pdf/LpoPDF.tsx` (new)
- `frontend/src/components/pdf/LpoPdfPreview.tsx` (new)
- `frontend/src/api/quotations.ts`
- `frontend/src/api/invoices.ts` (`customer_purchase_order_id` on GET type)
- `frontend/src/pages/Quotations.tsx`
- `frontend/src/pages/QuotationDetail.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/App.tsx`
- `.agents/reports/frontend-execution-report.md`

---

# WP-C Customer LPO Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/customer-purchase-orders`) + WP-B UI + PDF
**Spec:** `architecture/wave-customer-lpo-addendum.md` WP-C; user brief (manual LPO receive + remaining qty → DRAFT invoice; PDF title **LPO**; quote ACCEPTED convert; cross-tenant GET 404 not 403)

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`, product + FTA + quotation specs). Prove manual LPO create → receive → partial remaining-qty invoice lands DRAFT, HTML preview title is **LPO** (not Tax Invoice), ACCEPTED quote converts to DRAFT LPO, and workspace B cannot GET workspace A's LPO. Do not break product/FTA/quotation tests. Do not rename supplier SPO nav. Never SQLite. No OCR.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` from `frontend/` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |

## Specs to add

1. `frontend/e2e/lpos.spec.ts` — register → client → DRAFT LPO (one AED ad-hoc line) → preview **LPO** (not Tax Invoice) → receive → invoice remaining qty (partial) → `/invoices` row is **DRAFT**. Cheap extra: after SENT/ACCEPTED quote, Convert to LPO lands DRAFT LPO; convert-to-invoice after LPO is 409. Invoice send without Settings TRN/address still `FTA_SEND_BLOCKED`.
2. `frontend/e2e/lpo-isolation.spec.ts` — workspace A creates LPO via API; workspace B `GET /api/v1/customer-purchase-orders/{id}` → **404** not 403 (request context).

## UI `data-testid` (keep CSS modules)

Fill gaps: `lpo-invoice-qty-0` (index, not UUID), `lpo-remaining-0`. Reuse `nav-lpos`, `lpo-create`, `lpo-form`, `lpo-form-submit`, `lpo-receive`, `lpo-invoice`, `lpo-pdf-title` / `lpo-pdf-preview`, `quotation-convert-lpo`, invoice-status/send, `fta-send-blocked`.

## Out of scope

OCR, WhatsApp, delivery notes, credit HOLD, Arabic PDF, GitHub Actions, git commit, supplier SPO/GRN nav rename.

## Acceptance

- `npm run test:e2e` green (product + FTA + quotations + LPO)
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → log only (pytest already covers WP-A)

---

# WP-C Customer LPO Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 9 tests using 1 worker
  ok 1 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (682ms)
  ok 2 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.6s)
  ok 3 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.1s)
  ok 4 [chromium] › e2e\lpo-isolation.spec.ts:4:1 › cross-tenant LPO GET returns 404 (1.1m)
  ok 5 [chromium] › e2e\lpos.spec.ts:12:1 › manual LPO receive partial invoice lands draft invoice (4.5s)
  ok 6 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.5s)
  ok 7 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (445ms)
  ok 8 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (1.1m)
  ok 9 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.1s)
  9 passed (2.4m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

No UI or API bugs found in the run. Product + FTA + quotation specs still pass. Isolation 404 (not 403) confirmed in request context. Supplier `/spo` nav still **Purchase Orders**.

LPO isolation 1.1m and quotation-isolation 1.1m are register `5/minute` retry (helpers wait 16s on 429). LPO UI spec itself was 4.5s.

## Specs shipped

1. **Happy path** — unique register (password 8+) → client → DRAFT LPO (qty 2 ad-hoc AED line) → HTML preview title **LPO** (invoice `pdf-title` absent) → receive → invoice remaining qty 1 → `/invoices` DRAFT → send without Settings TRN/address still `FTA_SEND_BLOCKED`. Cheap: ACCEPTED quote Convert to LPO lands DRAFT LPO; convert-to-invoice after LPO is 409 `CONFLICT`.
2. **Isolation** — workspace B `GET /api/v1/customer-purchase-orders/{id}` → **404** not 403.

## UI / harness

- `data-testid`: `lpo-invoice-qty-0` (index, not UUID), `lpo-remaining-0`. Existing create/receive/preview/convert-lpo ids reused.
- Helper: `createAdhocLpoViaUi`. Register still retries 429.

## Files

- `frontend/e2e/lpos.spec.ts` (new)
- `frontend/e2e/lpo-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/src/pages/LpoDetail.tsx`
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- Invoice rest of remaining qty in the browser (second `/invoices`); this slice invoices 50% then lands DRAFT
- Over-invoice UI toast; API pytest covers 400
- OCR, WhatsApp, delivery notes, credit HOLD
- Playwright not wired into GitHub Actions
- Auth register 5/minute (retries; isolation specs can wait ~1m)

---

# WP-B Credit HOLD UI — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`GET /clients/{id}/credit`, Client `credit_limit` / `payment_terms_days`, SEND/receive `400 CREDIT_HOLD`). Do not touch Alembic. Do not change payment PUT.
**Spec:** `architecture/wave-credit-control-addendum.md` WP-B; `.agents/reports/architect-credit-control-note.md`

## Goal

Surface credit HOLD in the existing Vite + React app: client terms + limit, WARNING/HOLD badge, exposure vs limit, invoice SEND toast/banner, LPO receive toast/banner, due date from client terms. Keep existing Settings credit flags; add warning days + `block_po_on_hold`. No Next.js, no Playwright (WP-C), no AR PDF.

## FTA toast pattern (match)

Interceptor skips `FTA_SEND_BLOCKED` so the send handler toasts + shows `data-testid="fta-send-blocked"`. Duplicate skip for `CREDIT_HOLD`; handlers toast + banner `data-testid="credit-hold"`. LPO receive uses the same skip so the interceptor does not double-toast.

## Files

| File | Change |
|---|---|
| `frontend/src/api/errors.ts` | Shared skip-toast codes (`FTA_SEND_BLOCKED`, `CREDIT_HOLD`) |
| `frontend/src/api/client.ts` | Skip interceptor toast for those codes |
| `frontend/src/api/clients.ts` | Credit fields; write payload (no extra keys); `GET /credit` |
| `frontend/src/api/workspaces.ts` | `credit_warning_days`, `block_po_on_hold` (keep existing flags) |
| `frontend/src/api/invoices.ts` | `OVERDUE` on status union (WP-A on-read) |
| `frontend/src/pages/clientHelpers.ts` | Terms allow-list, inherit/COD parse, extra-key-safe body |
| `frontend/src/pages/CreditStatusBadge.tsx` | ACTIVE / WARNING / HOLD |
| `frontend/src/pages/Clients.tsx` | Form + list badge + exposure vs limit; optional aging from GET credit |
| `frontend/src/pages/Clients.module.css` | Badge, select, aging |
| `frontend/src/pages/Invoices.tsx` | Due date from terms; CREDIT_HOLD banner; collectable OVERDUE |
| `frontend/src/pages/LpoDetail.tsx` / `Lpos.tsx` | CREDIT_HOLD on receive |
| `frontend/src/pages/Settings.tsx` | Keep limit/hold days; add warning days + block LPO on HOLD |

## Client write body (extra="forbid")

Send only `name`, `email`, `phone`, `address`, `tax_id`, `credit_limit`, `payment_terms_days`. Never `credit_status`, `exposure`, `effective_credit_limit`, `id`. Empty credit limit → omit on create / `null` on update (inherit). `0` → COD.

## Out of scope

Playwright WP-C, Alembic, payment PUT, AR PDF, `block_do_on_hold` as a working control, git commit.

## Acceptance

`cd frontend && npm run build` succeeds. Extra keys never sent. `?? 0` before `toFixed`. HOLD send/receive shows `CREDIT_HOLD` without duplicate toast.

---

# WP-B Credit HOLD UI — Implementation (completed)

**Date:** 2026-09-01
**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

1. **Clients** — `credit_limit` blank = inherit, `0` = COD; `payment_terms_days` 0/30/45/60. Write bodies omit `credit_status` / exposure / ids. List WARNING/HOLD badge + exposure vs effective limit. Edit modal optional GET `/clients/{id}/credit` aging panel.
2. **Invoice send** — interceptor skips `CREDIT_HOLD` like `FTA_SEND_BLOCKED`; handler toasts + banner (`data-testid="credit-hold"`; FTA banner id unchanged). Due date defaults from client terms, not +30. OVERDUE badge; payment still allowed on SENT / PARTIALLY_PAID / OVERDUE (collections).
3. **LPO receive** — same CREDIT_HOLD banner + toast on list and detail when blocked.
4. **Settings** — kept `credit_limit_default` and `credit_hold_days`; added `credit_warning_days` and `block_po_on_hold`. `block_do_on_hold` not on the form.

Alembic, payment PUT, Playwright WP-C, AR PDF, git commit: not touched.

## Files

- `frontend/src/api/errors.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/clients.ts`
- `frontend/src/api/workspaces.ts`
- `frontend/src/api/invoices.ts`
- `frontend/src/pages/clientHelpers.ts` (new)
- `frontend/src/pages/CreditStatusBadge.tsx` (new)
- `frontend/src/pages/Clients.tsx`
- `frontend/src/pages/Clients.module.css`
- `frontend/src/pages/Invoices.tsx`
- `frontend/src/pages/Invoices.module.css`
- `frontend/src/pages/LpoDetail.tsx`
- `frontend/src/pages/Lpos.tsx`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/Settings.module.css`
- `.agents/reports/frontend-execution-report.md`

---

# WP-C Credit HOLD Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`CREDIT_HOLD` 400 on send/receive) + WP-B UI (`data-testid="credit-hold"`, client COD 0, Settings `block_po_on_hold`)
**Spec:** `architecture/wave-credit-control-addendum.md` WP-C

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`, product + FTA + quotation + LPO specs). Prove COD client (`credit_limit` 0) first invoice SEND with valid FTA TRN+address succeeds, unpaid SENT puts the client on HOLD, and a second SEND is blocked with banner `credit-hold` while the invoice stays DRAFT. Do not break product/FTA/quote/LPO specs. Never SQLite.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` from `frontend/` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |

## Specs to add

1. `frontend/e2e/credit-hold.spec.ts` — register → Settings FTA TRN+address, credit_limit_default 0, hold days, block LPO on HOLD → client COD 0 + address → invoice 1 send **SENT** → clients badge HOLD → invoice 2 send **blocked** (`credit-hold` banner, stays DRAFT, not FTA). Cheap extra: LPO receive on HOLD stays DRAFT with the same banner.
2. `frontend/e2e/credit-isolation.spec.ts` — workspace A `GET /api/v1/clients/{id}/credit` 200; workspace B → **404** not 403 (request context).

## UI `data-testid`

Reuse `credit-hold`, `client-credit-limit`, `client-credit-status`, `settings-block-po-on-hold`, invoice send/status, `lpo-receive`. Add missing Settings ids: `settings-credit-limit-default`, `settings-credit-hold-days`. Helpers: optional client `creditLimit`; `createAdhocInvoiceViaUi` must tolerate more than one invoice row.

## Out of scope

OVERDUE backdate UI, AR PDF, DN/`block_do_on_hold`, PDC bounce, GitHub Actions, git commit.

## Acceptance

- `npm run test:e2e` green (product + FTA + quotations + LPO + credit HOLD)
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → log only (pytest already covers WP-A)

---

# WP-C Credit HOLD Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 11 tests using 1 worker
  ok  1 [chromium] › e2e\credit-hold.spec.ts:12:1 › COD client second invoice send is credit HOLD (6.3s)
  ok  2 [chromium] › e2e\credit-isolation.spec.ts:4:1 › cross-tenant client credit GET returns 404 (32.5s)
  ok  3 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (428ms)
  ok  4 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.4s)
  ok  5 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.1s)
  ok  6 [chromium] › e2e\lpo-isolation.spec.ts:4:1 › cross-tenant LPO GET returns 404 (1.1m)
  ok  7 [chromium] › e2e\lpos.spec.ts:12:1 › manual LPO receive partial invoice lands draft invoice (4.7s)
  ok  8 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.4s)
  ok  9 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (1.1m)
  ok 10 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (416ms)
  ok 11 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.0s)
  11 passed (3.1m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

Product + FTA + quotation + LPO specs still pass. Isolation 404 (not 403) confirmed for `GET /clients/{id}/credit`.

LPO isolation 1.1m and product-isolation 1.1m are register `5/minute` retry (helpers wait 16s on 429). Credit HOLD UI spec itself was 6.3s.

## Specs shipped

1. **COD / HOLD** — unique register (password 8+) → Settings FTA TRN+address, credit_limit_default 0, hold days 90, block LPO on HOLD → client `credit_limit` 0 → invoice 1 send **SENT** (FTA ok) → clients badge **HOLD** → invoice 2 send shows `credit-hold` banner (not `fta-send-blocked`) and stays **DRAFT**. Cheap: LPO receive on HOLD stays DRAFT with the same banner.
2. **Isolation** — workspace B `GET /api/v1/clients/{id}/credit` → **404** not 403.

## UI / harness

- Settings `data-testid`: `settings-credit-limit-default`, `settings-credit-hold-days` (existing `settings-block-po-on-hold` reused).
- Helpers: optional `creditLimit` on `createClientViaUi`; `saveWorkspaceFta` can set credit defaults; `createAdhocInvoiceViaUi` waits on `.first()` invoice row and fills due date so COD 0 is valid.
- **UI fix hit in the run:** `addDaysToIso` used `toISOString()` after local midnight, so terms 0 produced due_date = yesterday in IST and blocked FTA invoice create. Now uses local calendar Y-M-D.

## Files

- `frontend/e2e/credit-hold.spec.ts` (new)
- `frontend/e2e/credit-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/Invoices.tsx`
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- OVERDUE backdate / aging HOLD in the browser; API pytest covers it
- AR PDF, DN / `block_do_on_hold`, PDC bounce
- Playwright not wired into GitHub Actions
- Auth register 5/minute (retries; isolation specs can wait ~1m)

---

# WP-B Delivery Notes UI + PDF — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/delivery-notes`, Alembic `a7c4e9d2b105`). Do not touch Alembic.
**Spec:** `architecture/wave-delivery-notes-addendum.md` WP-B; `.agents/reports/wp-a-delivery-notes-review.md` W1 (isolation 404 may be `HTTP_ERROR` — key off status).

## Goal

Add Delivery Notes to the existing Vite + React app: list + filters, XOR create from LPO remaining **or** invoice remaining, DRAFT edit/delete, confirm / cancel, client-side PDF titled **Delivery Note**. Settings exposes `block_do_on_hold`. Invoice PDF stays **Tax Invoice**. Quotation stays **Quotation**. LPO stays **LPO**. GRN inbound nav unchanged. No Next.js, no Playwright (WP-C), no adjust UI, no Arabic.

## API client

`frontend/src/api/deliveryNotes.ts`: list/get/create/update/delete, confirm (`{}`), cancel (`{ reason? }`).

- List unwraps `PaginatedResponse.data` array (`response.data.data`) with `page` / `per_page`.
- Write bodies only allow WP-A keys (`extra="forbid"`): never `hs_code`, `from_uom_id`, prices, `client_id`, both parents.
- Isolation: treat **HTTP 404** (W1), not only `error.code === "NOT_FOUND"`.
- Confirm CREDIT_HOLD: interceptor already skips that code; handler toasts + banner (no duplicate).

## Files

| File | Change |
|---|---|
| `frontend/src/api/deliveryNotes.ts` | CRUD + confirm/cancel |
| `frontend/src/api/errors.ts` | `isHttpNotFound` (status 404) |
| `frontend/src/api/inventory.ts` | `getWarehouseBins` |
| `frontend/src/api/lpos.ts` | `quantity_delivered` / `quantity_undelivered` on items |
| `frontend/src/api/workspaces.ts` | `block_do_on_hold` |
| `frontend/src/pages/DeliveryNotes.tsx` | List + filters + confirm |
| `frontend/src/pages/DeliveryNoteForm.tsx` | XOR parent, remaining qty, warehouse/bin |
| `frontend/src/pages/DeliveryNoteDetail.tsx` | Confirm / cancel / PDF |
| `frontend/src/pages/deliveryNoteHelpers.ts` | Payloads, remaining, `?? 0` qty |
| `frontend/src/pages/DeliveryNoteStatusBadge.tsx` | DRAFT / CONFIRMED / CANCELLED |
| `frontend/src/pages/DeliveryNotes.module.css` | Badges |
| `frontend/src/components/pdf/DeliveryNotePDF.tsx` | Title **Delivery Note**; SKU/qty; CANCELLED watermark |
| `frontend/src/components/pdf/DeliveryNotePdfPreview.tsx` | HTML title **Delivery Note** |
| `frontend/src/components/Layout.tsx` | Sales nav after LPO (`/delivery-notes`) |
| `frontend/src/App.tsx` | AuthGuard routes |
| `frontend/src/pages/Settings.tsx` | `block_do_on_hold` checkbox |

## Out of scope

Playwright WP-C, Alembic, inventory adjust UI, InvoicePDF / QuotationPDF / LpoPDF titles, GRN inbound nav, git commit.

## Acceptance

`cd frontend && npm run build` succeeds. Extra keys never sent. Qty `?? 0` before `toFixed`. PDF title **Delivery Note**. Isolation 404 keyed off HTTP status. Confirm CREDIT_HOLD toast without interceptor duplicate.

---

# WP-B Delivery Notes UI + PDF — Implementation (completed)

**Date:** 2026-09-01
**Build:** `cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

1. **API client** — `frontend/src/api/deliveryNotes.ts` unwraps paginated `data` for list. Create/update bodies omit extra keys (no prices, `client_id`, both parents). Confirm sends `{}`. Cancel sends `{ reason }` only when provided.
2. **Nav / routes** — Sales: Clients → Quotations → LPO → **Delivery Notes** (`/delivery-notes`) → Invoices. AuthGuard routes: `/delivery-notes`, `/delivery-notes/new`, `/delivery-notes/:id/edit`, `/delivery-notes/:id`. GRN stays **Inbound Shipments** (`/grn`).
3. **Create** — XOR LPO remaining **or** invoice remaining. Warehouse/bin picker. Ordered / delivered / remaining columns. Confirm / cancel. DRAFT edit/delete.
4. **CREDIT_HOLD** — interceptor already skips that code; confirm handler toasts + banner (`data-testid="credit-hold"`). Isolation 404 keyed off HTTP status (`isHttpNotFound`), not `NOT_FOUND`.
5. **Settings** — `block_do_on_hold` checkbox (`settings-block-do-on-hold`).
6. **PDF** — new `DeliveryNotePDF` title **Delivery Note**, DN number, LPO or invoice ref, SKU/description/qty, CANCELLED watermark, English Helvetica. `InvoicePDF` still **Tax Invoice**. `QuotationPDF` still **Quotation**. `LpoPDF` still **LPO**. Qty uses `?? 0` before `toFixed`.

Alembic, inventory adjust UI, Playwright WP-C, git commit: not touched.

## Files

- `frontend/src/api/deliveryNotes.ts` (new)
- `frontend/src/pages/DeliveryNotes.tsx` (new)
- `frontend/src/pages/DeliveryNoteForm.tsx` (new)
- `frontend/src/pages/DeliveryNoteDetail.tsx` (new)
- `frontend/src/pages/deliveryNoteHelpers.ts` (new)
- `frontend/src/pages/DeliveryNoteStatusBadge.tsx` (new)
- `frontend/src/pages/DeliveryNotes.module.css` (new)
- `frontend/src/components/pdf/DeliveryNotePDF.tsx` (new)
- `frontend/src/components/pdf/DeliveryNotePdfPreview.tsx` (new)
- `frontend/src/api/errors.ts`
- `frontend/src/api/inventory.ts`
- `frontend/src/api/lpos.ts`
- `frontend/src/api/workspaces.ts`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/App.tsx`
- `.agents/reports/frontend-execution-report.md`

---

# WP-C Delivery Notes Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/delivery-notes`, ISSUE on confirm) + WP-B UI (`/delivery-notes`, PDF title **Delivery Note**, Settings `block_do_on_hold`)
**Spec:** `architecture/wave-delivery-notes-addendum.md` WP-C

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`, product + FTA + quotation + LPO + credit specs). Prove catalog LPO remaining → DRAFT DN → confirm ISSUEs stock (levels drop), HTML preview title is **Delivery Note** (not Tax Invoice), and workspace B cannot GET workspace A's DN (404 not 403). Optional cheap HOLD: confirm 400 `CREDIT_HOLD` when `block_do_on_hold`. Do not break product/FTA/quote/LPO/credit specs. Never SQLite.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` from `frontend/` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |
| Stock seed | Playwright `request` + JWT: warehouse+bin, product, ADMIN `OPENING` adjust (not GRN UI) |

## Specs to add

1. `frontend/e2e/delivery-notes.spec.ts` — register → Settings `block_do_on_hold` checked → client → API warehouse/bin/product/opening stock → UI LPO catalog line + receive → DN from remaining → preview **Delivery Note** → confirm CONFIRMED → GET inventory `on_hand` decreased. Cheap extra: request-only HOLD confirm blocked then allowed when flag is off.
2. `frontend/e2e/delivery-note-isolation.spec.ts` — workspace A creates DN via API; workspace B `GET /api/v1/delivery-notes/{id}` → **404** not 403.

## UI `data-testid`

Reuse `nav-delivery-notes`, `dn-create`, `dn-form`, `dn-parent-type-lpo`, `dn-parent-select`, `dn-warehouse`, `dn-qty-0`, `dn-remaining-0`, `dn-form-submit`, `dn-detail`, `dn-number`, `dn-status`, `dn-confirm`, `dn-preview-pdf`, `dn-pdf-title`, `settings-block-do-on-hold`, `lpo-item-0-product`. Isolation keys off HTTP 404.

## Out of scope

GRN receiving UI, inventory adjust UI, transfers, counts, WhatsApp, tax credit notes, Arabic PDF, GitHub Actions, git commit.

## Acceptance

- `npm run test:e2e` green (product + FTA + quotations + LPO + credit + DN)
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → log only (pytest already covers WP-A)

---

# WP-C Delivery Notes Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 14 tests using 1 worker
  ok  1 [chromium] › e2e\credit-hold.spec.ts:12:1 › COD client second invoice send is credit HOLD (7.0s)
  ok  2 [chromium] › e2e\credit-isolation.spec.ts:4:1 › cross-tenant client credit GET returns 404 (32.5s)
  ok  3 [chromium] › e2e\delivery-note-isolation.spec.ts:11:1 › cross-tenant delivery note GET returns 404 (519ms)
  ok  4 [chromium] › e2e\delivery-notes.spec.ts:21:1 › catalog LPO delivery note confirm issues stock (4.3s)
  ok  5 [chromium] › e2e\delivery-notes.spec.ts:77:1 › HOLD blocks DN confirm when block_do_on_hold (1.1m)
  ok  6 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (458ms)
  ok  7 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.4s)
  ok  8 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.0s)
  ok  9 [chromium] › e2e\lpo-isolation.spec.ts:4:1 › cross-tenant LPO GET returns 404 (1.1m)
  ok 10 [chromium] › e2e\lpos.spec.ts:12:1 › manual LPO receive partial invoice lands draft invoice (4.6s)
  ok 11 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.4s)
  ok 12 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (1.1m)
  ok 13 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (475ms)
  ok 14 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.1s)
  14 passed (4.2m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

Product + FTA + quotation + LPO + credit specs still pass. Isolation 404 (not 403) confirmed for `GET /delivery-notes/{id}`. Confirm ISSUEd stock: opening 10 → after ship qty 2, `on_hand` 8.

HOLD 1.1m, LPO isolation 1.1m, and product-isolation 1.1m are register `5/minute` retry (helpers wait 16s on 429). DN UI spec itself was 4.3s; isolation 519ms.

## Specs shipped

1. **Happy path** — unique register (password 8+) → Settings `block_do_on_hold` checked → client → API warehouse+bin+catalog product + ADMIN `OPENING` adjust 10 → UI LPO catalog line qty 2 + receive → DN from remaining → HTML preview title **Delivery Note** (invoice `pdf-title` absent) → confirm **CONFIRMED** → GET inventory `on_hand` 8.
2. **HOLD (cheap)** — request-only: COD send → HOLD; `block_do_on_hold` true → confirm 400 `CREDIT_HOLD`; flag false → confirm 200.
3. **Isolation** — workspace B `GET /api/v1/delivery-notes/{id}` → **404** not 403.

## UI / harness

- Reused existing WP-B `data-testid`s (no new UI ids needed).
- Helpers: `expectApiData`, `createWarehouseBinViaApi`, `seedCatalogOpeningStock`, `inventoryOnHand`, `createCatalogLpoViaUi`. Register still retries 429.

## Files

- `frontend/e2e/delivery-notes.spec.ts` (new)
- `frontend/e2e/delivery-note-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- Invoice-parent DN in the browser (this slice used LPO remaining)
- GRN receiving UI to seed stock (ADMIN opening adjust via request)
- Cancel CONFIRMED / stock reverse in the browser; API pytest covers it
- Over-deliver remaining qty toast in the browser
- Playwright not wired into GitHub Actions
- Auth register 5/minute (retries; isolation specs can wait ~1m)
- Next after A–C: tax credit notes (gap 10)
