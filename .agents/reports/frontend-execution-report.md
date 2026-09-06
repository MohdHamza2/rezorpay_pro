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

---

# WP-B Tax Credit Notes UI + PDF — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/credit-notes`, Alembic `b8d5f0c3a216`). Isolation HTTP 404 (wrapper code may be `HTTP_ERROR`). Review: `.agents/reports/wp-a-credit-notes-review.md`.
**Spec:** `architecture/wave-credit-notes-addendum.md` WP-B, `.agents/frontend-agent.md`

## Goal

Sales UI + Tax Credit Note PDF for tax credit notes. Copy the delivery-note split: list / create-edit / detail / PDF. Do not display credits as cash paid (W2). Do not change Alembic, InvoicePDF title, or Playwright (WP-C).

## API client contract

- Base `/api/v1/credit-notes`. JWT via existing `apiClient`.
- List unwraps `PaginatedResponse`: `response.data.data` array + `pagination`. Query: `invoice_id`, `client_id`, `status`, `search`, `page`, `per_page`.
- Create/update bodies `extra="forbid"`-safe: only `invoice_id`, `reason`, optional `reason_notes` / `issue_date` / `items[]` with `invoice_item_id` + `quantity`. Never send money fields (backend copies frozen invoice lines). Issue POST `{}` only.
- Isolation: treat **HTTP 404**, not `error.code === "NOT_FOUND"` (W1).
- Do not call `GET /invoices/{id}/balance` (`total_paid` inflates by credits — W2).

## Files to change

| File | Change |
|---|---|
| `frontend/src/api/creditNotes.ts` | Types + list/get/create/update/delete/issue |
| `frontend/src/pages/creditNoteHelpers.ts` | Remaining qty from ISSUED CNs, form schema, payloads |
| `frontend/src/pages/CreditNotes.tsx` | Paginated list, filters, issue/edit/PDF |
| `frontend/src/pages/CreditNoteForm.tsx` | Pick SENT/PAID/PARTIAL/OVERDUE invoice, line picker |
| `frontend/src/pages/CreditNoteDetail.tsx` | Issue, DRAFT-only edit/delete, PDF preview |
| `frontend/src/pages/CreditNoteStatusBadge.tsx` | DRAFT / ISSUED |
| `frontend/src/components/pdf/CreditNotePDF.tsx` | Title **Tax Credit Note**; original INV; TRNs; Helvetica; English |
| `frontend/src/components/pdf/CreditNotePdfPreview.tsx` | HTML preview same title |
| `frontend/src/App.tsx` | `/credit-notes` under AuthGuard + Layout |
| `frontend/src/components/Layout.tsx` | Nav under Sales near Invoices |
| `frontend/src/api/invoices.ts` | Optional `amount_credited` |
| `frontend/src/api/clients.ts` | Optional `credit_balance` |
| `frontend/src/pages/Invoices.tsx` | AR panel: credited vs paid vs due; link to CNs; never label CN as payment |
| `frontend/src/pages/Clients.tsx` | Read-only `credit_balance` (no apply) |
| `InvoicePDF.tsx` | **Unchanged** (stays Tax Invoice) |

## UX

- Create from invoice: remaining qty = invoice line qty − Σ ISSUED CN qty. DRAFT does not reserve. Qty 0 omits the line. Amount-discount lines (W4): credit remaining as a block.
- Issue posts AR (no `/apply`). DRAFT-only PUT/DELETE.
- Invoice UI: `amount_credited` + adjusted `balance_due` if present. Amount paid stays cash. Client: unapplied `credit_balance`.
- `.toFixed` only with `?? 0`.

## Out of scope

Playwright WP-C, Alembic, debit notes, auto-apply credit_balance, Arabic PDF, git commit.

## Acceptance

1. `cd frontend && npm run build` succeeds
2. AuthGuard wraps `/credit-notes`
3. Extra keys never sent; paginated `data` array
4. Tax Invoice PDF title unchanged

---

# WP-B Tax Credit Notes UI + PDF — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Alembic:** not touched (`b8d5f0c3a216` remains WP-A).

## Result

`cd frontend && npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

## Shipped

- API client unwraps paginated `data` array. Create/update send only allowed keys (`invoice_item_id` + `quantity` on lines). Issue POST `{}`. Isolation toasts/pages use HTTP 404 (`isHttpNotFound`), not `NOT_FOUND`.
- Routes `/credit-notes`, `/new`, `/:id/edit`, `/:id` under `AuthGuard` + `Layout`. Nav **Credit Notes** under Sales & Customers, after Invoices (`nav-credit-notes`).
- Create DRAFT from SENT / PAID / PARTIALLY_PAID / OVERDUE invoice. Line picker caps qty at remaining (invoice qty − Σ ISSUED CN qty). Amount-discount lines must credit remaining in full (W4). Issue posts AR. DRAFT-only edit/delete.
- `CreditNotePDF` / preview title **Tax Credit Note**; original INV number + issue date; seller/buyer TRN snapshots (live fallback on DRAFT). English, Helvetica. `InvoicePDF` still **Tax Invoice**.
- Invoice AR panel: amount paid (cash) vs amount credited (credit notes) vs balance due. Never labels a CN as a payment. Does not call `GET /invoices/{id}/balance`.
- Client list + credit panel: read-only unapplied `credit_balance`. No apply UI.
- `.toFixed` on new money/qty helpers uses `?? 0`.

## Files

**New:** `frontend/src/api/creditNotes.ts`, `frontend/src/pages/creditNoteHelpers.ts`, `frontend/src/pages/CreditNotes.tsx`, `frontend/src/pages/CreditNoteForm.tsx`, `frontend/src/pages/CreditNoteDetail.tsx`, `frontend/src/pages/CreditNoteStatusBadge.tsx`, `frontend/src/pages/CreditNotes.module.css`, `frontend/src/pages/InvoiceArPanel.tsx`, `frontend/src/components/pdf/CreditNotePDF.tsx`, `frontend/src/components/pdf/CreditNotePdfPreview.tsx`

**Edited:** `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/api/invoices.ts`, `frontend/src/api/clients.ts`, `frontend/src/pages/Invoices.tsx`, `frontend/src/pages/Clients.tsx`, `.agents/reports/frontend-execution-report.md`

## Out of scope (unchanged)

Playwright WP-C, Alembic, debit notes, auto-apply `credit_balance`, Arabic PDF, git commit.

---

# WP-C Tax Credit Notes Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A API (`/api/v1/credit-notes`, Alembic `b8d5f0c3a216`) + WP-B UI (`/credit-notes`, PDF title **Tax Credit Note**, AR panel cash vs credited)
**Spec:** `architecture/wave-credit-notes-addendum.md` WP-C; W1 isolation HTTP 404 (wrapper may be `HTTP_ERROR`); W2 do not use `GET /invoices/{id}/balance` `total_paid`

## Goal

Extend the existing Vite Playwright harness (`frontend/playwright.config.ts`, `frontend/e2e/helpers.ts`, product + FTA + quotation + LPO + credit HOLD + DN specs). Prove FTA-valid SIMPLIFIED invoice send → create CN from SENT invoice → issue posts AR (`amount_credited` up, `balance_due` down, `amount_paid` still cash 0) → HTML preview title **Tax Credit Note**. Workspace B GET CN is **404** not 403. Optional cheap: qty above remaining is blocked in the form. Do not break product/FTA/quote/LPO/credit-hold/DN specs. Never SQLite. No debit notes.

## Harness (reuse)

| Item | Choice |
|---|---|
| Config | existing `frontend/playwright.config.ts` — `testDir: e2e`, Chromium, workers 1 |
| Helpers | `frontend/e2e/helpers.ts`, `global-setup.ts` (`GET /health/ready`) |
| Script | `npm run test:e2e` from `frontend/` |
| API | docker postgres **5434**, API **8000**, Vite **5173** |
| Auth | unique emails, password `Passw0rd1` (8+); retry register on 429 (5/minute) |

## Specs to add

1. `frontend/e2e/credit-notes.spec.ts` — register → Settings FTA TRN+address → client with address (SIMPLIFIED, no buyer TRN) → ad-hoc AED invoice send **SENT** → create CN from that invoice → optional qty > remaining form error → issue **ISSUED** → preview **Tax Credit Note** (not Tax Invoice) → invoice AR panel: credited up, balance down, paid (cash) still 0.
2. `frontend/e2e/credit-note-isolation.spec.ts` — workspace A FTA send + create CN via API; workspace B `GET /api/v1/credit-notes/{id}` → **404** not 403 (request context). Key off HTTP status (W1).

## UI `data-testid`

Reuse `nav-credit-notes`, `cn-create`, `cn-form`, `cn-invoice-select`, `cn-qty-0`, `cn-remaining-0`, `cn-form-submit`, `cn-detail`, `cn-status`, `cn-issue`, `cn-preview-pdf`, `cn-pdf-title`, `invoice-create-cn`, `invoice-ar-panel`, `invoice-amount-paid`, `invoice-amount-credited`, `invoice-balance-due`. Isolation keys off HTTP 404.

## Out of scope

Debit notes, PAID+CN `credit_balance` browser path (API pytest covers it), auto-apply credit, Arabic PDF, GitHub Actions, git commit.

## Acceptance

- `npm run test:e2e` green (product + FTA + quotations + LPO + credit HOLD + DN + CN)
- `npm run build` still succeeds
- Fix UI bugs hit in the run; API bugs → log only (pytest already covers WP-A)

---

# WP-C Tax Credit Notes Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 16 tests using 1 worker
  ok  1 [chromium] › e2e\credit-hold.spec.ts:12:1 › COD client second invoice send is credit HOLD (7.6s)
  ok  2 [chromium] › e2e\credit-isolation.spec.ts:4:1 › cross-tenant client credit GET returns 404 (438ms)
  ok  3 [chromium] › e2e\credit-note-isolation.spec.ts:10:1 › cross-tenant credit note GET returns 404 (537ms)
  ok  4 [chromium] › e2e\credit-notes.spec.ts:11:1 › simplified tax invoice credit note issue posts AR (1.2m)
  ok  5 [chromium] › e2e\delivery-note-isolation.spec.ts:11:1 › cross-tenant delivery note GET returns 404 (575ms)
  ok  6 [chromium] › e2e\delivery-notes.spec.ts:21:1 › catalog LPO delivery note confirm issues stock (4.0s)
  ok  7 [chromium] › e2e\delivery-notes.spec.ts:77:1 › HOLD blocks DN confirm when block_do_on_hold (359ms)
  ok  8 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (1.1m)
  ok  9 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.3s)
  ok 10 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (1.9s)
  ok 11 [chromium] › e2e\lpo-isolation.spec.ts:4:1 › cross-tenant LPO GET returns 404 (1.1m)
  ok 12 [chromium] › e2e\lpos.spec.ts:12:1 › manual LPO receive partial invoice lands draft invoice (4.6s)
  ok 13 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.5s)
  ok 14 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (420ms)
  ok 15 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (1.1m)
  ok 16 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.0s)
  16 passed (5.0m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

Product + FTA + quotation + LPO + credit HOLD + DN specs still pass. Isolation 404 (not 403) confirmed for `GET /credit-notes/{id}`. Issue posted AR: invoice total AED 210.00 → credited AED 105.00, cash paid still AED 0.00, balance due AED 105.00, status stayed SENT.

FTA isolation 1.1m, LPO isolation 1.1m, quotation-isolation 1.1m, and CN happy path 1.2m are register `5/minute` retry (helpers wait 16s on 429). CN isolation itself was 537ms.

## Specs shipped

1. **Happy path** — unique register (password 8+) → Settings FTA TRN+address → SIMPLIFIED client (address, no buyer TRN) → ad-hoc invoice qty 2 @ 100 send **SENT** (preview still **Tax Invoice**) → Create CN → qty 99 blocked (`Cannot exceed remaining`) → qty 1 create DRAFT `CN-YYYY-XXXX` → issue **ISSUED** → HTML preview title **Tax Credit Note** (invoice `pdf-title` absent, seller TRN present) → invoice AR panel: credited AED 105.00, paid (cash) AED 0.00, balance AED 105.00, copy “not cash payments”.
2. **Isolation** — workspace B `GET /api/v1/credit-notes/{id}` → **404** not 403.

## UI / harness

- List Amount Due `data-testid="invoice-balance-due"` (AR panel already had it; list GET omits `amount_credited` so credited vs cash is asserted in the AR panel GET).
- Form `cn-qty-error-0` for remaining-qty overflow (UI stand-in for `CREDIT_EXCEEDS_REMAINING`; API 400 still pytest-only).
- Helpers: `putWorkspaceFtaApi`, `createFtaSentInvoiceApi`. Register still retries 429.

## Files

- `frontend/e2e/credit-notes.spec.ts` (new)
- `frontend/e2e/credit-note-isolation.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/src/pages/Invoices.tsx`
- `frontend/src/pages/CreditNoteForm.tsx`
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- PAID invoice + CN → `credit_balance` in the browser; API pytest covers it
- Header `CREDIT_EXCEEDS_REMAINING` 400 on issue (two DRAFTs); form caps qty instead
- Debit notes, auto-apply credit, Arabic PDF
- Playwright not wired into GitHub Actions
- Auth register 5/minute (retries; isolation specs can wait ~1m)
- Next after A–C: AR statement / PDC / volume pricing (not debit notes)

---

# WP-B AR Account Statement UI + PDF — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A APPROVE_WITH_NITS (`.agents/reports/wp-a-ar-statement-review.md`). Pytest green. No Alembic. No backend edits unless P0 blocks UI.
**Spec:** `architecture/wave-ar-statement-addendum.md` WP-B + §7.1 JSON + §8 PDF; `.agents/reports/architect-ar-statement-note.md`

## Goal

Per-client Account Statement page + client-side `@react-pdf/renderer` PDF from `GET /api/v1/clients/{id}/ar-statement`. Not a tax invoice. Not a Tax Credit Note. Credits ≠ cash. Unapplied credit in footer, not an aging bucket. Outstanding amounts are current; aging days vs as-of.

## API client (do not invent fields)

`GET /api/v1/clients/{id}/ar-statement?from=&to=&as_of=`
- `from` and `to` required. `as_of` optional on API; page always sends explicit query params.
- Wrapper `{success, data, error}`. `data` is **one object**, not a list.
- Isolation HTTP 404 (code may be `HTTP_ERROR` or `NOT_FOUND` — UI keys off status via `isHttpNotFound`).
- Types match WP-A schema: `doc_type` OPENING | TAX_INVOICE | PAYMENT | PAYMENT_PENDING | TAX_CREDIT_NOTE; labels from JSON; `totals.paid` vs `totals.credited`; `credit_balance`; aging buckets `current` / `days_1_30` / `days_31_60` / `days_61_90` / `days_90_plus`.

Add `getArStatement(clientId, { from, to, as_of? })` on the clients API module.

## UI

1. Route `/clients/:id/statement` under existing AuthGuard layout. **No** top-level Statements nav.
2. Clients table: Statement action per row. Keep edit/delete/credit badge.
3. Date range + as-of. Defaults: `to`/`as_of` = UTC today, `from` = first of that month. Always send `from`, `to`, `as_of`.
4. Lines: Date | Type | Number | Debit | Credit | Balance. Use `doc_type_label`. Paid vs credited vs pending visually distinct. Never label Tax Credit Note as Payment or cash.
5. Footer: billed, paid (SUCCESS only), credited (CN), amount due now, **Unapplied credit** (`credit_balance`) — not an aging bucket.
6. Aging: Current / 1–30 / 31–60 / 61–90 / 90+.
7. Copy: outstanding amounts are current; aging days vs as-of.
8. `DATE_RANGE_TOO_LONG` / `STATEMENT_TOO_LARGE` / 422 from>to: toast from `error.code` / message. Cross-tenant 404: existing not-found pattern.
9. MEMBER can view (same as GET client — no extra RBAC).

## PDF

- `frontend/src/components/pdf/StatementPDF.tsx` + preview like CN/Invoice.
- Exact title **Account Statement**. `data-testid="statement-pdf-title"` on on-screen title and PDF title text.
- Must NOT be Tax Invoice / Tax Credit Note / INVOICE / Arabic كشف حساب.
- Helvetica, English, copy Invoice/CN padding/header/table chrome.
- Header: workspace name, address, TRN if present; client name, address, TRN (`tax_id`).
- Meta: period from–to, as of, AED.
- Columns: Date | Type | Number | Debit | Credit | Balance. Payment method on second line. PENDING: type Payment (pending); debit/credit 0; pending not in Credit.
- Footer totals + Unapplied credit + aging + PDC SUCCESS note from addendum §6.
- Download/preview from the statement page. Rebuild from GET JSON. No server PDF.

## Out

Invoice list `amount_credited` column. Alembic. Backend. Playwright (WP-C). PDC bounce. Bilingual. Debit notes. Email. Dashboard overdue pack.

## Files to change

| File | Change |
|---|---|
| `frontend/src/api/clients.ts` | Types + `getArStatement` |
| `frontend/src/api/errors.ts` | Toast text includes `DATE_RANGE_TOO_LONG` / `STATEMENT_TOO_LARGE` codes |
| `frontend/src/api/client.ts` | Use that toast formatter |
| `frontend/src/pages/statementHelpers.ts` | Date defaults, zod range, aging labels, line tone |
| `frontend/src/pages/ArStatement.tsx` | Page |
| `frontend/src/pages/ArStatement.module.css` | Line tones, money cols, aging |
| `frontend/src/components/pdf/StatementPDF.tsx` | PDF + download |
| `frontend/src/components/pdf/StatementPdfPreview.tsx` | HTML preview |
| `frontend/src/App.tsx` | Route `/clients/:id/statement` |
| `frontend/src/pages/Clients.tsx` | Statement action |
| `frontend/src/pages/Clients.module.css` | Statement link |

## Acceptance

1. `cd frontend && npm run build` green
2. PDF title **Account Statement**
3. Credits not shown as cash; unapplied credit not an aging bucket
4. No backend / Alembic / pytest / Playwright / git commit

---

# WP-B AR Account Statement UI + PDF — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No backend / Alembic / pytest / Playwright.**

## Result

`npm run build` (`tsc -b && vite build`) **green**. Vite 8.2.1. Pre-existing chunk-size warning only.

PDF title locked to **Account Statement** on:
- On-screen page `h2` (`data-testid="statement-pdf-title"`)
- HTML preview `h3` (`data-testid="statement-pdf-title"`)
- `@react-pdf/renderer` title text + `Document title="Account Statement"` + `id` / `data-testid` on the PDF title `Text`

Not Tax Invoice, Tax Credit Note, INVOICE, or Arabic كشف حساب.

## Behaviour

- Route `/clients/:id/statement` behind AuthGuard + Layout. No top-level Statements nav.
- Clients table **Statement** link per row; edit / delete / credit badge unchanged.
- Date defaults: `to` / `as_of` = UTC today, `from` = first of that month. Apply always sends `from`, `to`, `as_of`.
- Lines use `doc_type_label`. SUCCESS payments green; tax credit notes purple (never labelled Payment/cash); pending muted with credit column 0.
- Footer: billed, paid (SUCCESS), credited (CN), amount due now, Unapplied credit (`credit_balance`) — not in the aging table.
- Aging: Current / 1–30 / 31–60 / 61–90 / 90+.
- Copy: outstanding amounts are current; aging days vs as-of. PDC SUCCESS footnote from addendum §6.
- `DATE_RANGE_TOO_LONG` / `STATEMENT_TOO_LARGE` toasts as `CODE: message`. from>to blocked by zod + toast. Cross-tenant 404 → `statement-not-found` (HTTP status, not error.code).
- MEMBER: no extra RBAC (same as GET client).
- PDF rebuilds from GET JSON. No server PDF route.

## Files

- `frontend/src/api/clients.ts` — types + `getArStatement`
- `frontend/src/api/errors.ts` / `frontend/src/api/client.ts` — statement error toast formatter
- `frontend/src/pages/statementHelpers.ts` (new)
- `frontend/src/pages/ArStatement.tsx` (new)
- `frontend/src/pages/ArStatement.module.css` (new)
- `frontend/src/components/pdf/StatementPDF.tsx` (new)
- `frontend/src/components/pdf/StatementPdfPreview.tsx` (new)
- `frontend/src/App.tsx`
- `frontend/src/pages/Clients.tsx`
- `frontend/src/pages/Clients.module.css`
- `.agents/reports/frontend-execution-report.md`

## Out (unchanged)

Invoice list `amount_credited` column. Backend. Alembic. Playwright (WP-C). PDC bounce. Bilingual. Debit notes. Email. Dashboard overdue pack.

---

# WP-C AR Account Statement Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**API:** docker postgres host **5434**, API **8000**, Vite **5173**. `/health/ready` 200 (`database: connected`). Not SQLite.

## Result

```
Running 18 tests using 1 worker
  ok  1 [chromium] › e2e\ar-statement-isolation.spec.ts:10:1 › cross-tenant AR statement GET returns 404 (501ms)
  ok  2 [chromium] › e2e\ar-statement.spec.ts:39:1 › account statement shows invoice payment and credit note (4.6s)
  ok  3 [chromium] › e2e\credit-hold.spec.ts:12:1 › COD client second invoice send is credit HOLD (6.4s)
  ok  4 [chromium] › e2e\credit-isolation.spec.ts:4:1 › cross-tenant client credit GET returns 404 (32.5s)
  ok  5 [chromium] › e2e\credit-note-isolation.spec.ts:10:1 › cross-tenant credit note GET returns 404 (513ms)
  ok  6 [chromium] › e2e\credit-notes.spec.ts:11:1 › simplified tax invoice credit note issue posts AR (2.3s)
  ok  7 [chromium] › e2e\delivery-note-isolation.spec.ts:11:1 › cross-tenant delivery note GET returns 404 (1.1m)
  ok  8 [chromium] › e2e\delivery-notes.spec.ts:21:1 › catalog LPO delivery note confirm issues stock (2.4s)
  ok  9 [chromium] › e2e\delivery-notes.spec.ts:77:1 › HOLD blocks DN confirm when block_do_on_hold (350ms)
  ok 10 [chromium] › e2e\fta-isolation.spec.ts:4:1 › cross-tenant invoice GET returns 404 (1.1m)
  ok 11 [chromium] › e2e\fta-send-blocked.spec.ts:4:1 › send invoice without workspace TRN is blocked (1.3s)
  ok 12 [chromium] › e2e\fta-tax-invoice.spec.ts:11:1 › simplified tax invoice send and preview (2.0s)
  ok 13 [chromium] › e2e\lpo-isolation.spec.ts:4:1 › cross-tenant LPO GET returns 404 (482ms)
  ok 14 [chromium] › e2e\lpos.spec.ts:12:1 › manual LPO receive partial invoice lands draft invoice (1.3m)
  ok 15 [chromium] › e2e\product-catalog.spec.ts:12:1 › product master catalog happy path (2.4s)
  ok 16 [chromium] › e2e\product-isolation.spec.ts:4:1 › cross-tenant product GET returns 404 (441ms)
  ok 17 [chromium] › e2e\quotation-isolation.spec.ts:4:1 › cross-tenant quotation GET returns 404 (1.1m)
  ok 18 [chromium] › e2e\quotations.spec.ts:12:1 › quotation send accept convert to draft invoice (2.0s)
  18 passed (5.5m)
```

`npm run build` — `tsc -b && vite build` succeeded (Vite 8.2.1). Pre-existing chunk-size warning only.

Product + FTA + quotation + LPO + credit HOLD + DN + CN specs still pass. Isolation **404** (not 403) confirmed for `GET /api/v1/clients/{id}/ar-statement?from=&to=`. PDF title **Account Statement** asserted on page `h2` and preview; invoice `pdf-title` / CN `cn-pdf-title` absent. Credits ≠ cash: paid AED 50.00 vs credited AED 105.00.

## Specs shipped

1. **Happy path** — unique register (password 8+) → Settings FTA → SIMPLIFIED client → ad-hoc invoice qty 2 @ 100 send **SENT** → UI CASH payment AED 50.00 (Idempotency-Key via `recordPayment`) → CN qty 1 **ISSUED** → Clients table `client-statement` → range today → three line types Tax Invoice / Payment / Tax Credit Note; `statement-credited` ≠ `statement-paid`; aging visible; preview title **Account Statement** (not Tax Invoice / Tax Credit Note).
2. **Isolation** — workspace A `createFtaSentInvoiceApi`; workspace B `GET /api/v1/clients/{A}/ar-statement?from=&to=` (today) → **404** not 403. Own GET 200.

## Helpers / product

- `authJson` **unchanged** (no Idempotency-Key); payment recorded through the Invoices UI modal so CN isolation callers stay intact.
- No backend, Alembic, Invoices.tsx, or WP-B testid changes. Existing statement testids used.

## Files

- `frontend/e2e/ar-statement.spec.ts` (new)
- `frontend/e2e/ar-statement-isolation.spec.ts` (new)
- `.agents/reports/frontend-execution-report.md`

## Not covered (leftovers)

- PENDING payment line / SUCCESS PDC label in the browser
- MEMBER-role statement GET
- Debit notes, bilingual PDF, email statement
- Playwright not wired into GitHub Actions
- Next after A–C: PDC truth (gap 11), then volume pricing (not debit notes)


---

# WP-C AR Account Statement Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-B UI+PDF shipped (`/clients/:id/statement`, StatementPDF title **Account Statement**). WP-A GET `/clients/{id}/ar-statement` 404 isolation.
**Spec:** `architecture/wave-ar-statement-addendum.md` WP-C + §8 PDF title.

## Goal

Playwright covers the collections statement: three activity line types on one page, credits ≠ cash, aging visible, PDF title **Account Statement** (not Tax Invoice / Tax Credit Note), and cross-workspace GET **404** not 403.

## Runtime

Docker API **8000**, Postgres host **5434**. Never SQLite. Password **Passw0rd1**. Unique emails. Register 429 retry already in helpers.

## Specs

1. **Happy path** `frontend/e2e/ar-statement.spec.ts`
   - registerViaUi → saveWorkspaceFta → createClientViaUi → SIMPLIFIED SENT tax invoice (same as fta-tax-invoice / credit-notes)
   - SUCCESS payment CASH/BANK (UI modal; recordPayment already sends Idempotency-Key)
   - ISSUED CN partial qty 1 (same as credit-notes.spec)
   - Clients table `client-statement` → `/clients/:id/statement` for a range covering invoice + payment + CN
   - Assert `statement-line-TAX_INVOICE`, `statement-line-PAYMENT`, `statement-line-TAX_CREDIT_NOTE`
   - `statement-credited` ≠ `statement-paid`
   - `statement-aging` visible
   - `statement-pdf-title` **Account Statement** on page and preview; not Tax Invoice / Tax Credit Note

2. **Isolation** `frontend/e2e/ar-statement-isolation.spec.ts`
   - Workspace A: putWorkspaceFtaApi + createFtaSentInvoiceApi
   - Workspace B: `GET /api/v1/clients/{A}/ar-statement?from=&to=` (today range) → **404** not 403

## Helpers

- Reuse `registerViaUi`, `registerWorkspace`, `createFtaSentInvoiceApi`, `authJson`, `uniqueEmail`, `E2E_PASSWORD`, FTA helpers.
- Do **not** add Idempotency-Key to `authJson` unless POSTing payments via API. CN isolation callers stay unchanged.
- No backend / Alembic / PDC bounce / debit notes. Prefer existing WP-B testids.

## Acceptance

- `npm run test:e2e` all existing + new green
- `npm run build` green
- Isolation 404 confirmed; PDF title Account Statement asserted
- No git commit

---

# WP-B PDC truth UI — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A APPROVE_WITH_NITS (`.agents/reports/wp-a-pdc-review.md`). Historical SUCCESS PDC is cash. No Alembic. No Playwright (WP-C). No git commit.
**Spec:** `architecture/wave-pdc-addendum.md` WP-B + §3 transitions + §6 historical SUCCESS + §7 statement note; `.agents/reports/architect-pdc-note.md`

## Goal

Record-payment modal + AR payment list treat **PDC as pending until CLEARED**. CHEQUE stays one-step SUCCESS. OWNER/ADMIN get Deposit / Clear / Bounce / Return for legal transitions only. MEMBER hides those buttons. Statement footer uses addendum §7 copy. Existing Vite + React app only.

## API client

- Keep `recordPayment` + `Idempotency-Key`. PDC body: `pdc_date` required; **never send `pdc_status`**. No extra keys.
- `GET /api/v1/invoices/{id}/payments` — unwrap paginated `data` array (`listPayments`).
- Four POSTs, empty `{}`, **no** Idempotency-Key:
  `POST /api/v1/invoices/{invoiceId}/payments/{paymentId}/pdc/deposit|clear|bounce|return`
- Isolation: key off HTTP **404** (`isHttpNotFound`), not `error.code`.

## UI

1. Payment modal: PDC requires cheque date; after submit toast **pending**, not PAID. CHEQUE = SUCCESS cash.
2. AR panel payment list: method, amount, `status`, `pdc_status`. SUCCESS-only `amount_paid` (existing GET). PENDING must not look like paid.
3. OWNER/ADMIN actions (hide illegal): RECEIVED+PENDING → Deposit, Return; DEPOSITED+PENDING → Clear, Bounce; CLEARED or `status=SUCCESS` (historical) → none (cash); BOUNCED/RETURNED → none. Deposit before `pdc_date` still calls API (400 toast).
4. MEMBER: hide action buttons. Type `role` on `User` from `/auth/me` + login/register. API 403 if called.
5. Testids: `payment-method`, `payment-pdc-date`, `payment-submit`, `payment-row-*`, `pdc-deposit`, `pdc-clear`, `pdc-bounce`, `pdc-return`; reuse `invoice-status`, `invoice-amount-paid`.
6. `PDC_SUCCESS_NOTE` exact: `Uncleared PDC is Payment (pending) and is not cash. Cleared PDC is Payment.` (ArStatement + StatementPDF + preview).

## Out

Dashboard `pdc_outstanding`, Statements nav, volume pricing, bilingual, debit notes, Playwright, backend/Alembic, git commit.

## Acceptance

`cd frontend && npm run build` green.

---

# WP-B PDC truth UI — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No backend / Alembic / Playwright.**

## Result

`npm run build` (`tsc -b && vite build`) **green**. Vite 8.2.1. Pre-existing chunk-size warning only.

## SUCCESS vs PENDING

- New PDC: modal requires cheque date; body sends `pdc_date` only (no `pdc_status`). Toast: **pending, not cash**. Invoice `amount_paid` / status stay SUCCESS-only from GET.
- PENDING PDC rows: muted, status shown as `PENDING (not cash)`. Deposit/Return (RECEIVED) or Clear/Bounce (DEPOSITED) for OWNER/ADMIN.
- Historical `status=SUCCESS` PDC (or CLEARED): treated as cash. No Deposit / Bounce / Return / Clear buttons.
- CHEQUE / CASH / BANK / CARD: one-step SUCCESS. Toast “Payment recorded”, not “invoice PAID”.
- MEMBER: action buttons hidden. `User.role` from `/auth/me` + login/register. API still 403 if called.

## Files

- `frontend/src/api/invoices.ts` — `listPayments`, `postPdcAction` (`{}`, no Idempotency-Key), `paymentCreateBody` omits `pdc_status`
- `frontend/src/types/auth.ts` — `User.role` (`OWNER` | `ADMIN` | `MEMBER`)
- `frontend/src/contexts/AuthContext.tsx` — persist `role` from me/login/register
- `frontend/src/pages/paymentHelpers.ts` (new) — legal transitions, toasts, RBAC hide
- `frontend/src/pages/InvoicePayments.tsx` (new) — AR payment list + PDC actions
- `frontend/src/pages/InvoiceArPanel.tsx` — embed payment list; isolation retry on HTTP 404
- `frontend/src/pages/Invoices.tsx` — PDC date required; pending toast; testids
- `frontend/src/pages/Invoices.module.css` — pending row + PDC buttons
- `frontend/src/pages/statementHelpers.ts` — §7 `PDC_SUCCESS_NOTE` (ArStatement + StatementPDF + preview)

## Out (unchanged)

Dashboard `pdc_outstanding`, Statements nav, volume pricing, bilingual, debit notes, Playwright WP-C, backend, Alembic, git commit.

---

# WP-C PDC truth Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-B UI shipped (`invoice-record-payment`, `payment-pdc-date`, `pdc-deposit`/`clear`/`bounce`/`return`, AR `payment-list`). WP-A four POSTs + PUT 405.
**Spec:** `architecture/wave-pdc-addendum.md` WP-C.

## Goal

Playwright covers PDC as a promise until CLEARED: future cheque does not PAID, same-day deposit+clear posts cash, bounce leaves AR open and re-evaluates credit (no forced HOLD). Cross-workspace PDC actions and PUT are **404**; own-workspace PUT is **405**.

## Runtime

Docker API **8000**, Postgres host **5434**. Never SQLite. Password **Passw0rd1**. Unique emails. Register 429 retry already in helpers.

## Specs

1. **Happy** `frontend/e2e/pdc.spec.ts`
   - registerViaUi → saveWorkspaceFta → createClientViaUi → SIMPLIFIED SENT tax invoice (same as fta-tax-invoice / credit-notes)
   - Future PDC (`pdc_date` = utc today+7) full balance via testids → invoice **SENT**, `invoice-amount-paid` AED 0.00, payment row PENDING not cash
   - Separate SENT invoice: PDC `pdc_date=utc today` → Deposit → Clear → amount_paid increases; status PARTIAL or PAID
   - Bounce: SENT + PDC today → Deposit → Bounce → not PAID; balance_due still full; GET `/clients/{id}/credit` or badge (do not force HOLD)

2. **Isolation** `frontend/e2e/pdc-isolation.spec.ts`
   - Workspace A: putWorkspaceFtaApi + createFtaSentInvoiceApi + POST PDC (`Idempotency-Key`)
   - Workspace B: POST `/pdc/deposit|clear|bounce|return` on A’s ids → **404** not 403
   - Workspace B: PUT `/invoices/{A}/payments/{id}` → **404**
   - Workspace A: PUT same payment (`{"status":"SUCCESS"}`) → **405** (if 422, assert not 200 and document)

## Helpers

- Reuse `registerViaUi`, `registerWorkspace`, `createFtaSentInvoiceApi`, `authJson`, `uniqueEmail`, `E2E_PASSWORD`, `isoDate`, FTA helpers.
- Add **optional** extra headers on `authJson` for Idempotency-Key. Existing CN/AR/credit isolation callers stay unchanged (no 5th-header required).
- AR statement still records **CASH** via payment modal (`getByTitle('Record Payment')` + amount/select). Do not change that spec. Keep `invoice-record-payment`, `payment-amount`, `payment-method`, `payment-submit`.
- No backend / Alembic. Prefer existing WP-B testids.

## Acceptance

- `npm run test:e2e` all existing + new green
- `npm run build` green
- Isolation 404/405 confirmed; future PDC did not PAID
- No git commit

---

# WP-C PDC truth Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No backend / Alembic.**

## Result

- `npm run test:e2e` — **22 passed** (8.1m), chromium, workers 1. Product/FTA/quote/LPO/credit-hold/DN/CN/AR statement unchanged (statement still records **CASH** via the payment modal).
- `npm run build` — **green** (`tsc -b && vite build`, Vite 8.2.1).
- Future PDC: invoice stayed **SENT**, `invoice-amount-paid` AED 0.00, payment row PENDING not cash.
- Same-day PDC: Deposit → Clear → amount_paid AED 210.00, status PAID.
- Bounce: invoice not PAID; balance_due AED 210.00; credit GET/badge evaluated (not forced HOLD).
- Isolation: workspace B `POST .../pdc/{deposit,clear,bounce,return}` and `PUT .../payments/{id}` → **404** not 403. Workspace A PUT `{status:SUCCESS}` → **405** (not 200).

## Files

- `frontend/e2e/helpers.ts` — optional `extraHeaders` on `authJson` (Idempotency-Key for PDC create). CN/AR isolation callers unchanged.
- `frontend/e2e/pdc.spec.ts` — happy path (future / clear / bounce)
- `frontend/e2e/pdc-isolation.spec.ts` — 404/405

## Out (unchanged)

Volume pricing, bilingual, debit notes, WhatsApp, Peppol, refunds, Alembic, git commit.

---

# WP-B Volume / customer pricing UI — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A APPROVE_WITH_NITS (`.agents/reports/wp-a-volume-pricing-review.md`). Preview GET is live. **WP-B may start.**
**Spec:** `architecture/wave-volume-pricing-addendum.md` WP-B + §3.4 + §7; `.agents/reports/architect-volume-pricing-note.md`
**No backend. No Alembic. No git commit. No Playwright (WP-C).**

## Goal

Invoice / quotation / LPO catalog lines fill `unit_price` from **preview GET** (`client_id` + qty), not `getProductPrices` → `DEFAULT_SALES`. Dirty override stays until product re-pick. Show List / Volume / Customer / Override. Do not rebuild `ProductDetailPanel` price CRUD.

## API client

`getResolvedPrice(productId, { client_id?, quantity })` in `frontend/src/api/products.ts`
- `GET /api/v1/products/{id}/resolved-price?quantity=&client_id=`
- Unwrap `{success, data}`
- Isolation **404** keyed off HTTP status (`isHttpNotFound`)
- Extra keys never POSTed (GET query only: `quantity` required, `client_id` omitted when empty)

Do **not** scan `getProductPrices` / `prices[]` for list or dealer rows on sales lines.

## Shared helper (one place)

Dirty/preview logic lives in one hook used by `Invoices.tsx`, `QuotationForm.tsx`, `LpoForm.tsx`:

1. Product pick → preview GET (header client + line qty) → fill price, reset dirty, show matched rule.
2. Qty or header client change → re-preview and fill **until** that line is dirty.
3. Typing `unit_price` → **Override**. Qty must not overwrite a dirty price (12.50 stays).
4. Product pick resets dirty and re-resolves.
5. Ad-hoc (no product): no preview; price required as today.
6. `NO_LIST_PRICE` / 400 inactive: toast from `error.code`; clear price (do not keep stale list).

Labels: `DEFAULT_SALES` → List, `TIER_1` → Volume, `CUSTOMER_SPECIFIC` → Customer, dirty → Override.

## Testids (reuse existing prefixes)

- Client: `invoice-client-select` / `quotation-client-select` / `lpo-client-select`
- Product / qty / price: `invoice-item-0-product`, `invoice-item-0-quantity`, `invoice-item-0-price` (same pattern for quotation/lpo)
- New: `invoice-item-0-price-source` (text `List` | `Volume` | `Customer` | `Override`)

## Out

ProductDetailPanel prices. Electrical specs. Bilingual. Debit notes. Playwright. SPO/purchase prices.

## Acceptance

`cd frontend && npm run build` green.

---

# WP-B Volume / customer pricing UI — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No backend / Alembic / Playwright.**

## Result

`npm run build` (`tsc -b && vite build`) **green**. Vite 8.2.1. Pre-existing chunk-size warning only.

## Dirty vs resolve

Shared hook `useCatalogLinePricing` (`frontend/src/pages/catalogLinePricing.tsx`) is the only dirty/preview owner. Invoice, quotation, and LPO forms call it.

- **Clean catalog line:** product pick, qty change, and header client change call `GET /api/v1/products/{id}/resolved-price?quantity=&client_id=` and fill `unit_price`. Source badge: List (`DEFAULT_SALES`) / Volume (`TIER_1`) / Customer (`CUSTOMER_SPECIFIC`).
- **Dirty line:** typing in `unit_price` sets Override and bumps a per-line seq so an in-flight preview cannot overwrite. Qty / client changes skip preview. Typed 12.50 stays.
- **Product pick** clears dirty for that line (keyed by field-array id) and re-resolves.
- **Ad-hoc** (empty product): no GET; price still required by existing zod.
- **Preview error** (`NO_LIST_PRICE`, inactive 400, isolation HTTP 404): toast from `error.code` (`NO_LIST_PRICE: …` / `VALIDATION_ERROR: …` when `field=product_id`); `unit_price` is cleared so a stale list price is not kept.
- **§3.4:** client A qty 10 → 80 Customer; switch client to B without dirty → 90 Volume.

`getProductPrices` is not used on sales lines. `ProductDetailPanel` price CRUD unchanged.

## Files

- `frontend/src/api/products.ts` — `getResolvedPrice` (GET query only)
- `frontend/src/api/errors.ts` — code-prefixed toasts for `NO_LIST_PRICE` and inactive `VALIDATION_ERROR`
- `frontend/src/pages/catalogLinePricing.tsx` — shared dirty/preview hook + `LinePriceSource`
- `frontend/src/pages/Invoices.tsx` / `QuotationForm.tsx` / `LpoForm.tsx`
- `frontend/src/pages/Invoices.module.css` — `.priceSource`
- `.agents/reports/frontend-execution-report.md`

Testids reused: `invoice-item-0-product|quantity|price`, `invoice-client-select` (same prefixes for quotation/lpo). New: `*-item-0-price-source`.

## Out (unchanged)

ProductDetailPanel rebuild, electrical specs, bilingual, debit notes, Playwright WP-C, SPO/purchase prices, backend, Alembic, git commit.

---

# WP-C Volume / customer pricing Playwright E2E — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-B UI (preview GET + dirty/override + `invoice-item-0-price-source`).
**Spec:** `architecture/wave-volume-pricing-addendum.md` WP-C + §3.4 fixture.
**No git commit. No Alembic. No backend** unless a missing product-price testid is required (prefer API seed).

## Goal

Playwright covers §3.4 on a new invoice line: client A qty 1 → **80 Customer**; qty 10 still **80 Customer**; switch header to client B (not dirty) → **90 Volume**; type **12.50** → **Override** and qty change keeps 12.50. Second workspace GET resolved-price → **404** not 403.

Ad-hoc invoice helpers still fill explicit `unit_price`. Do not change product/FTA/quote/LPO/credit-hold/DN/CN/AR/PDC specs.

## Files

| File | Change |
|---|---|
| `frontend/e2e/volume-pricing.spec.ts` | **New.** Register → clients A/B → catalog product (UOM/category/brand like product-catalog) → DEFAULT_SALES 100 via UI → TIER_1 / CUSTOMER_SPECIFIC via `POST /api/v1/products/{id}/prices` + `pageAccessToken` → invoice form assertions |
| `frontend/e2e/volume-pricing-isolation.spec.ts` | **New.** Workspace A API catalog+prices; workspace B `GET /api/v1/products/{A}/resolved-price?quantity=1` → 404 not 403 |

## Helpers (reuse, do not break)

`registerViaUi`, `createClientViaUi`, `createUom` / `createCategory` / `createBrand`, `uniqueEmail`, `pageAccessToken`, `authJson`, `registerWorkspace`, `expectApiData`, `selectOptionContaining`. Password `Passw0rd1`. Unique emails. 429 retry already in register helpers.

UI testids: `invoice-client-select`, `invoice-item-0-product`, `invoice-item-0-quantity`, `invoice-item-0-price`, `invoice-item-0-price-source` (List \| Volume \| Customer \| Override). Product prices: `price-type`, `price-amount`, `price-add`, `price-row-DEFAULT_SALES`. Min qty / client `<select>` may lack testids — seed TIER_1 / CUSTOMER_SPECIFIC via API.

## Runtime

`API_URL` `http://localhost:8000`. Postgres **5434**. Never SQLite.

## Acceptance

- `npm run test:e2e` **all** green (existing + new)
- `npm run build` green
- A→80 / B→90 / override 12.50; isolation 404
- No git commit

---

# WP-C Volume / customer pricing Playwright E2E — Implementation (completed)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No backend / Alembic.**

## Result

- `npm run test:e2e` — **24 passed** (7.8m), chromium, workers 1. Product/FTA/quote/LPO/credit-hold/DN/CN/AR/PDC specs unchanged. Ad-hoc invoice helpers still fill explicit `unit_price`.
- `npm run build` — **green** (`tsc -b && vite build`, Vite 8.2.1).
- Happy path §3.4: client A qty 1 → **80.00 Customer**; qty 10 still **80.00 Customer**; switch header to B (not dirty) → **90.00 Volume**; type **12.50** → **Override**; qty change keeps 12.50.
- Isolation: workspace B `GET /api/v1/products/{A}/resolved-price?quantity=1` → **404** not 403.

## Files

- `frontend/e2e/volume-pricing.spec.ts` — UI catalog + DEFAULT_SALES via UI; TIER_1 / CUSTOMER_SPECIFIC via `POST /prices` + `pageAccessToken`
- `frontend/e2e/volume-pricing-isolation.spec.ts` — API catalog+prices; cross-tenant resolved-price 404
- `.agents/reports/frontend-execution-report.md`

## Out (unchanged)

Helpers (`createAdhocInvoiceViaUi` still explicit price), electrical specs, bilingual, debit notes, WhatsApp, Peppol, PDC, SENT re-price, backend, Alembic, git commit.

---

# WP-A Bilingual PDF — font + shared labels (planned BEFORE code)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Spec:** `architecture/wave-bilingual-pdf-addendum.md` WP-A + §3 font + §5 strings + §7 tests. Architect note: `.agents/reports/architect-bilingual-pdf-note.md`.
**No git commit. No Alembic. No Playwright. No `*PDF.tsx` / preview retitling.**

## Goal

Vendor Noto Naskh Arabic Regular (OFL) and land the shared title/label/font-register contract so WP-B can wire dual titles without hard-coding AR in six PDF files.

## Locked

- Alembic **NO**. HEAD stays **`b8d5f0c3a216`**. No `name_ar` / `address_ar`. Do not edit models.
- Font: official notofonts OFL hinted Regular TTF → `frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf` + `OFL.txt`. Regular only. 50 KiB ≤ size ≤ 2 MiB. Download once at implement time; no CDN in source; no runtime fetch.
- `pdfFonts.ts`: `Font.register` family `NotoNaskhArabic`, Vite `?url` import, hyphenation callback `[word]`, `PDF_FONT_AR` / `PDF_FONT_EN='Helvetica'`, idempotent `registerPdfFonts()`. No `fonts.googleapis` / `fonts.gstatic` / `http://`.
- `pdfTitles.ts`: six EN + six AR exact UTF-8 from addendum §5.1. LPO AR **أمر شراء محلي**. EN byte-identical: Tax Invoice, Tax Credit Note, Quotation, LPO, Delivery Note, Account Statement.
- `pdfLabels.ts`: all §5.2 chrome keys + watermarks + footer disclaimer.
- Do **not** change InvoicePDF / CreditNotePDF / QuotationPDF / LpoPDF / DeliveryNotePDF / StatementPDF or their previews (Playwright EN titles stay green).

## Files (planned)

| File | Change |
|---|---|
| `frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf` | Vendor hinted Regular TTF |
| `frontend/src/assets/fonts/OFL.txt` | SIL OFL 1.1 from the same Noto package |
| `frontend/src/components/pdf/pdfFonts.ts` | Font.register + hyphenation + family constants |
| `frontend/src/components/pdf/pdfTitles.ts` | `PDF_TITLES` EN+AR |
| `frontend/src/components/pdf/pdfLabels.ts` | chrome + watermarks + footer |

## Out

WP-B layout, WP-C Playwright, electrical specs, debit notes, server PDF, Alembic, git commit.

---

# WP-A Bilingual PDF — font + shared labels (implemented)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Alembic. No Playwright. No PDF layout.**

## Done

- Vendored Noto Naskh Arabic Regular (OFL hinted TTF) + `OFL.txt` from notofonts/arabic (hinted Regular). **247336** bytes. TTF magic `\x00\x01\x00\x00`.
- Shared modules: `pdfFonts.ts` (`Font.register` family `NotoNaskhArabic`, Vite `?url`, hyphenation `[word]`, idempotent), `pdfTitles.ts` (six EN+AR), `pdfLabels.ts` (§5.2 chrome + watermarks + footer).
- `*PDF.tsx` and previews **untouched**. Pytest `test_bilingual_pdf_assets.py` **6 passed**. Alembic HEAD **`b8d5f0c3a216`**.

## Files

- `frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf`
- `frontend/src/assets/fonts/OFL.txt`
- `frontend/src/components/pdf/pdfFonts.ts`
- `frontend/src/components/pdf/pdfTitles.ts`
- `frontend/src/components/pdf/pdfLabels.ts`
- `.agents/reports/frontend-execution-report.md`

---

# WP-B Bilingual PDF — UI / PDF / preview (planned BEFORE code)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Spec:** `architecture/wave-bilingual-pdf-addendum.md` WP-B + §4 layout + §5 labels. Architect note: `.agents/reports/architect-bilingual-pdf-note.md`. WP-A review: **APPROVE_WITH_NITS** (`.agents/reports/wp-a-bilingual-pdf-review.md`).
**No git commit. No Alembic. No Playwright. No backend money/snapshots/send gates.**

## Goal

Wire all six client PDFs, six HTML previews, invoice download (`pdf().toBlob()`), and the Account Statement page `h2` to WP-A titles/labels/font. Dual title EN left / AR right. Stacked chrome. Same repo TTF via `Font.register` and CSS `@font-face`.

## Locked

- Import `PDF_TITLES` / `PDF_LABELS`; do not hard-code AR in six PDF files.
- `registerPdfFonts()` from every `*PDF.tsx` and every download path (invoice download lives in `Invoices.tsx`).
- Page default Helvetica. AR `Text` uses `PDF_FONT_AR`. No `fontWeight: 'bold'` on AR. No CDN.
- Existing EN `data-testid` on an EN-only node with exact live EN string. AR sibling `*-ar` testids with `lang="ar"` `dir="rtl"`.
- LPO EN title stays **LPO**. LPO live column `VAT` (not `VAT AED`); AR from `vatAed`.
- Do not `direction: rtl` on Page. Western digits / AED `toFixed(2)`.
- Do not translate line descriptions, notes, SKU, TRN digits, status badges.
- Watermarks keep EN; AR second line ملغى / منتهي / مرفوض / مسودة.
- Footer disclaimer §4.5; “Generated by InvoiceSaaS” EN.
- Shared `PdfDualTitle.tsx` + HTML dual title + `pdfBilingual.module.css`.

## Files (planned)

| File | Change |
|---|---|
| `frontend/src/components/pdf/PdfDualTitle.tsx` | react-pdf dual title row |
| `frontend/src/components/pdf/HtmlDualTitle.tsx` | preview / statement `h2` sibling titles |
| `frontend/src/components/pdf/pdfBilingual.module.css` | `@font-face` same TTF + dual-title CSS |
| `frontend/src/components/pdf/pdfChrome.tsx` | stacked labels, headers, watermark, footer |
| `frontend/src/components/pdf/InvoicePDF.tsx` + preview | bilingual chrome |
| `frontend/src/pages/Invoices.tsx` | `registerPdfFonts()` before `pdf().toBlob()` |
| `frontend/src/components/pdf/CreditNotePDF.tsx` + preview + download | bilingual chrome |
| `frontend/src/components/pdf/QuotationPDF.tsx` + preview + download | bilingual chrome |
| `frontend/src/components/pdf/LpoPDF.tsx` + preview + download | bilingual chrome; EN LPO / VAT |
| `frontend/src/components/pdf/DeliveryNotePDF.tsx` + preview + download | bilingual chrome |
| `frontend/src/components/pdf/StatementPDF.tsx` + preview + download | bilingual chrome; type AR by `doc_type` |
| `frontend/src/pages/ArStatement.tsx` | dual title on page `h2` |

## Out

Playwright (WP-C), Alembic, `*_ar` columns, electrical specs, debit notes, server PDF, Eastern Arabic numerals.

---

# WP-B Bilingual PDF — UI / PDF / preview (implemented)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Alembic. No Playwright. No backend money/snapshots/send gates.**

## Done

- Shared `PdfDualTitle` (react-pdf) + `HtmlDualTitle` (EN testid on EN-only `h2`/`h3`, AR sibling `lang="ar"` `dir="rtl"`).
- `pdfBilingual.module.css` `@font-face` loads the same in-repo Noto TTF (Vite emitted `NotoNaskhArabic-Regular-*.ttf`; no CDN).
- All six PDFs: `registerPdfFonts()`, Helvetica page default, stacked chrome from `PDF_LABELS`, watermarks EN + AR second line, §4.5 footer + “Generated by InvoiceSaaS” EN.
- Invoice download in `Invoices.tsx` calls `registerPdfFonts()` before `pdf().toBlob()`. Other docs call it in their `download*Pdf` paths.
- LPO EN title remains **LPO**. LPO VAT column EN stays **VAT**; AR from `vatAed`.
- Statement Type column: EN from JSON `doc_type_label`; AR mapped by `doc_type`.
- `npm run build` (**green**): `tsc -b && vite build` succeeded.

## EN testids (exact live strings, EN-only nodes)

| Testid | Node | Text |
|---|---|---|
| `pdf-title` | preview `h3` | Tax Invoice |
| `cn-pdf-title` | preview `h3` | Tax Credit Note |
| `quotation-pdf-title` | preview `h3` | Quotation |
| `lpo-pdf-title` | preview `h3` | LPO |
| `dn-pdf-title` | preview `h3` | Delivery Note |
| `statement-pdf-title` | page `h2` **and** preview `h3` | Account Statement |

AR siblings: `pdf-title-ar`, `cn-pdf-title-ar`, `quotation-pdf-title-ar`, `lpo-pdf-title-ar`, `dn-pdf-title-ar`, `statement-pdf-title-ar`.

## Files

- `frontend/src/components/pdf/PdfDualTitle.tsx`
- `frontend/src/components/pdf/HtmlDualTitle.tsx`
- `frontend/src/components/pdf/pdfBilingual.module.css`
- `frontend/src/components/pdf/pdfChrome.tsx`
- `frontend/src/components/pdf/InvoicePDF.tsx`
- `frontend/src/components/pdf/InvoicePdfPreview.tsx`
- `frontend/src/pages/Invoices.tsx`
- `frontend/src/components/pdf/CreditNotePDF.tsx`
- `frontend/src/components/pdf/CreditNotePdfPreview.tsx`
- `frontend/src/components/pdf/QuotationPDF.tsx`
- `frontend/src/components/pdf/QuotationPdfPreview.tsx`
- `frontend/src/components/pdf/LpoPDF.tsx`
- `frontend/src/components/pdf/LpoPdfPreview.tsx`
- `frontend/src/components/pdf/DeliveryNotePDF.tsx`
- `frontend/src/components/pdf/DeliveryNotePdfPreview.tsx`
- `frontend/src/components/pdf/StatementPDF.tsx`
- `frontend/src/components/pdf/StatementPdfPreview.tsx`
- `frontend/src/pages/ArStatement.tsx`
- `.agents/reports/frontend-execution-report.md`

---

# WP-C Bilingual PDF — Playwright (planned BEFORE code)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Spec:** `architecture/wave-bilingual-pdf-addendum.md` WP-C + §8 Playwright.
**No git commit. No Alembic. No backend. Isolation specs unchanged.**

## Goal

Keep every existing EN `toHaveText` exact match. Add AR `toHaveText` on WP-B sibling testids. FTA preview: fail if any request URL includes `fonts.googleapis.com` or `fonts.gstatic.com`. Do not parse PDF binaries.

## Locked

- EN titles stay exact: Tax Invoice / Tax Credit Note / Quotation / LPO / Delivery Note / Account Statement.
- AR exact: فاتورة ضريبية / إشعار دائن ضريبي / عرض سعر / أمر شراء محلي / إذن تسليم / كشف حساب.
- Isolation specs title-free (404, not titles). No new isolation file.
- Statement page `h2[data-testid="statement-pdf-title"]`; preview `h3`. Scope AR so page vs preview do not collide.
- Password 8+ (`Passw0rd1`). Unique emails. Docker API 8000, Postgres 5434, Vite 5173. Never SQLite.

## Files (planned)

| File | Change |
|---|---|
| `frontend/e2e/fta-tax-invoice.spec.ts` | `pdf-title-ar` + no Google font requests while preview open |
| `frontend/e2e/credit-notes.spec.ts` | `cn-pdf-title-ar` |
| `frontend/e2e/quotations.spec.ts` | `quotation-pdf-title-ar` |
| `frontend/e2e/lpos.spec.ts` | `lpo-pdf-title-ar` |
| `frontend/e2e/delivery-notes.spec.ts` | `dn-pdf-title-ar` |
| `frontend/e2e/ar-statement.spec.ts` | `statement-pdf-title-ar` on page (h2 sibling) and preview (scoped) |

## Out

Isolation files, Alembic, backend, PDF binary parse, switching EN `toHaveText` to `toContainText`.

## Acceptance

`npm run test:e2e` all green. `npm run build` green. EN exact. AR asserted. No Google font CDN on FTA preview.

---

# WP-C Bilingual PDF — Playwright (implemented)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Alembic. No backend. Isolation specs unchanged.**

## Done

- Kept every existing EN `toHaveText` exact match (did not switch to `toContainText`).
- Added AR `toHaveText` on sibling testids: `pdf-title-ar`, `cn-pdf-title-ar`, `quotation-pdf-title-ar`, `lpo-pdf-title-ar`, `dn-pdf-title-ar`, `statement-pdf-title-ar`.
- Statement AR: page uses `h2[data-testid="statement-pdf-title"] + [data-testid="statement-pdf-title-ar"]`; preview uses `statement-pdf-preview` scoped locator. Both re-asserted while preview is open so page vs preview do not collide.
- FTA: while preview is open, fail if any request URL includes `fonts.googleapis.com` or `fonts.gstatic.com`. Optional `font-family` includes `NotoNaskhArabic`. No PDF binary parse.
- Isolation specs untouched (still title-free).

## Results

- `npm run test:e2e`: **24 passed** (7.6m). Docker API 8000 healthy, Postgres 5434, Vite 5173.
- `npm run build`: **green** (`tsc -b && vite build`).

## EN titles still exact

| Testid | `toHaveText` |
|---|---|
| `pdf-title` | Tax Invoice |
| `cn-pdf-title` | Tax Credit Note |
| `quotation-pdf-title` | Quotation |
| `lpo-pdf-title` | LPO |
| `dn-pdf-title` | Delivery Note |
| `statement-pdf-title` | Account Statement |

## AR titles asserted

| Testid | `toHaveText` |
|---|---|
| `pdf-title-ar` | فاتورة ضريبية |
| `cn-pdf-title-ar` | إشعار دائن ضريبي |
| `quotation-pdf-title-ar` | عرض سعر |
| `lpo-pdf-title-ar` | أمر شراء محلي |
| `dn-pdf-title-ar` | إذن تسليم |
| `statement-pdf-title-ar` | كشف حساب (page + preview) |

## Files

- `frontend/e2e/fta-tax-invoice.spec.ts`
- `frontend/e2e/credit-notes.spec.ts`
- `frontend/e2e/quotations.spec.ts`
- `frontend/e2e/lpos.spec.ts`
- `frontend/e2e/delivery-notes.spec.ts`
- `frontend/e2e/ar-statement.spec.ts`
- `.agents/reports/frontend-execution-report.md`

---

# WP-B Electrical Catalogue Spec Columns — Plan (before edits)

**Date:** 2026-09-01
**Owner:** frontend / coder
**Depends on:** WP-A **APPROVE_WITH_NITS** (`.agents/reports/wp-a-electrical-specs-review.md`). Alembic HEAD **`1a30af047312`**.
**Spec:** `architecture/wave-electrical-specs-addendum.md` §7; `.agents/reports/architect-electrical-specs-note.md`.

## Goal

Staff save **4C 10mm²** and **63A 3P** on the Products tab and filter the list. Frontend only. No Playwright (WP-C). No git commit. No backend unless a testid is impossible otherwise (it is not). Do not rebuild `ProductDetailPanel` identifiers/conversions/prices. Do not add spec filters to invoice/quote/LPO pickers.

## API types (`frontend/src/api/products.ts`)

`Product`, `ProductWrite`, `ProductListQuery` gain optional: `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage`.

`listParams` / `getProducts` pass them **when set**. Extra keys never POSTed (`extra="forbid"`). Empty create → omit spec keys. Empty update → JSON `null` so staff can clear. Encode `voltage` query values (slash in `230/400`).

## Form (create/edit)

Optional Amp, Cable mm², Cores, Poles, Voltage. Zod optional (voltage regex `^[0-9]+(/[0-9]+)?$` so `230V` fails client-side; else interceptor 422 toast — I3: key off HTTP 422, not `error.code`; list invalid voltage is string `detail` wrapped as `error.message`).

Testids: `product-amp-input`, `product-mm2-input`, `product-cores-input`, `product-poles-input`, `product-voltage-input`.

## List filters

Toolbar on Products tab only. Same five fields + Apply + Clear. Apply writes spec params into `getProducts` query key (refetch). Clear omits spec params.

Testids: `product-filter-amp`, `product-filter-mm2`, `product-filter-cores`, `product-filter-poles`, `product-filter-voltage`, `product-filter-apply`, `product-filter-clear`.

## Specs column

One compact cell, not five empty columns:

- cores + mm² → `{cores}C {mm2}mm²` (strip trailing zeros; `mm²` in UI)
- amp + poles → `{amp}A {poles}P`
- voltage if set → append ` {voltage}V` **display only**
- else `—`

## Out

Debit notes, Peppol, hs_code, ProductDetailPanel rebuild, Playwright, invoice/quote/LPO pickers, category/brand/UOM tabs.

## Files (planned)

| File | Change |
|---|---|
| `frontend/src/api/products.ts` | Types + `listParams` |
| `frontend/src/pages/productUi.tsx` | Spec format, payload helpers, filter bar |
| `frontend/src/pages/Products.tsx` | Form fields, query key, Specs column |
| `frontend/src/pages/Products.module.css` | Filter toolbar + compact specs cell |

## Acceptance

`cd frontend && npm run build` green. Staff can save 4C 10mm² and 63A 3P and filter the list.

---

# WP-B Electrical Catalogue Spec Columns — Implemented

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Playwright. No backend. ProductDetailPanel identifiers/conversions/prices untouched. Invoice/quote/LPO pickers unchanged.**

## Done

- Types: `Product` / `ProductWrite` / `ProductListQuery` optional `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage`.
- `listParams` passes spec query params only when set (pickers omit them). Axios encodes `voltage` slashes (`230/400`).
- Create omits empty spec keys. Update sends JSON `null` so staff can clear.
- Form: optional Amp / Cable mm² / Cores / Poles / Voltage. Zod optional. `230V` fails client-side (`^[0-9]+(/[0-9]+)?$`). List filter invalid voltage toasts client-side; interceptor still toasts HTTP 422 (`error.message` or string `detail`, not a specific `error.code`).
- Products-tab toolbar: five filters + Apply + Clear. Apply updates `['products', { page, ...specQuery }]` so `getProducts` refetches. Clear omits spec params.
- One Specs column: `4C 10mm²`, `63A 3P`, optional ` 230/400V` display suffix; else `—`. Trailing zeros stripped.

## Testids

Form: `product-amp-input`, `product-mm2-input`, `product-cores-input`, `product-poles-input`, `product-voltage-input`

Filters: `product-filter-amp`, `product-filter-mm2`, `product-filter-cores`, `product-filter-poles`, `product-filter-voltage`, `product-filter-apply`, `product-filter-clear`

## Files

- `frontend/src/api/products.ts`
- `frontend/src/api/errors.ts` (422 string `detail` toast)
- `frontend/src/pages/productUi.tsx`
- `frontend/src/pages/Products.tsx`
- `frontend/src/pages/Products.module.css`
- `.agents/reports/frontend-execution-report.md`

## Build

`npm run build` in `frontend/`: **green** (`tsc -b && vite build`).

---

# WP-C Electrical Catalogue Spec Columns — Playwright (planned)

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Alembic. No backend. Do not rewrite `product-catalog.spec.ts` or `product-isolation.spec.ts`.**

## Spec (architecture/wave-electrical-specs-addendum.md WP-C §8)

New `frontend/e2e/electrical-specs.spec.ts`:

1. Register via UI (`registerViaUi`, password `Passw0rd1`) → UOM PCS → Products tab.
2. Create cable SKU `CBL-4C10-{suffix}`: cores `4`, mm² `10`.
3. Create breaker SKU `MCB-63-3P-{suffix}`: amp `63`, poles `3`. Voltage optional (omit).
4. Filter mm² `10` + cores `4` → Apply → cable row visible; breaker **not**.
5. Clear; filter amp `63` + poles `3` → breaker visible; cable **not**.
6. Optional: second workspace GET A’s product id → **404** (not 403). Isolation spec file left unchanged.

Reuse helpers: `registerViaUi`, `createUom`, `uniqueSuffix` (via register), `selectOptionContaining`, `waitForModalClosed`, `pageAccessToken`, `registerWorkspace`, `authJson`.

Testids: `product-amp-input`, `product-mm2-input`, `product-cores-input`, `product-poles-input`, `product-voltage-input`, `product-filter-amp`, `product-filter-mm2`, `product-filter-cores`, `product-filter-poles`, `product-filter-apply`, `product-filter-clear`, `product-row-{sku}`.

Runtime: Docker API **8000**, Postgres **5434**, Vite **5173**. Never SQLite.

Acceptance: `npm run test:e2e` **all** green; `npm run build` green; catalog + isolation specs still green (no spec fields required; isolation still 404).

---

# WP-C Electrical Catalogue Spec Columns — Implemented

**Date:** 2026-09-01
**Owner:** frontend / coder
**No git commit. No Alembic. No backend. `product-catalog.spec.ts` and `product-isolation.spec.ts` unchanged.**

## File

`frontend/e2e/electrical-specs.spec.ts`

Flow:

1. `registerViaUi` (`Passw0rd1`) → UOM PCS → Products tab.
2. Cable `CBL-4C10-{suffix}`: cores `4`, mm² `10`.
3. Breaker `MCB-63-3P-{suffix}`: amp `63`, poles `3` (voltage omitted).
4. Filter mm² `10` + cores `4` → Apply → cable row visible; breaker **not**.
5. Clear; filter amp `63` + poles `3` → breaker visible; cable **not**.
6. Optional: workspace B GET A’s cable id → **404** (not 403). Isolation spec file not rewritten.

## Results

- `npm run test:e2e` (all): **25 passed** (8.1m)
- `electrical-specs.spec.ts`: pass (cable vs breaker filters confirmed)
- `product-catalog.spec.ts`: pass (no spec fields required)
- `product-isolation.spec.ts`: pass (cross-tenant GET still **404**, not 403)
- `npm run build`: **green** (`tsc -b && vite build`)

---

## 2026-09-06 — F-1: frontend production build fixed (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` finding F-1. `npm run build` was failing with 12 TS errors that shipped silently because CI had no frontend job.

### Files changed

- `src/components/pdf/TaxDebitNotePDF.tsx`:
  - `PDF_LABELS.taxDebitNoteNo` → `PDF_LABELS.debitNoteNo` (label key never existed).
  - `cn.tax_debit_note_number` → `cn.debit_note_number` (field name per `api/debitNotes.ts`).
  - Download filename `TaxTaxDebitNote_...` → `TaxDebitNote_...` (double-prefix typo).
- `src/pages/InvoiceArPanel.tsx`:
  - `row.tax_debit_note_number` → `row.debit_note_number`.
  - `amount_debited` coerced to `number` (was `number | string | null`, failed `> 0` type math).
- `src/api/invoices.ts` — added `amount_debited?: number | string | null` to `InvoiceListItem` to match backend `InvoiceResponse`.
- `src/pages/enquiries/Enquiries.tsx` — removed unused `Plus` import.
- `src/pages/enquiries/EnquiryDetail.tsx` — removed unused `useState`, `Check`, `Edit2`, `Play`, `RefreshCw`, `X` imports.

### Verification

- `npm run build`: **green** (`tsc -b && vite build`, 2226 modules, 1.15s).
- `npm run lint` (oxlint): warnings only (pre-existing fast-refresh / unused catch-param pattern across other files; none new).

Note: the audit also found the 3 other blocking fixes — F-2 (backend tests, see backend report) and F-3 (add frontend job to CI, see `.github/workflows/ci.yml`). Chunk-size warning (2 MB main bundle) remains as a known non-blocking item.
