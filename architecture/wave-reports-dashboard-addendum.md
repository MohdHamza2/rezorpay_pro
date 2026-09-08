# Wave 29 — Reports & Dashboard (AR aging aggregate + Reports UI)

**Status: LOCKED (rev 2 — coordinator approval)**
**Phase:** Phase 6: Reporting & Dashboard (first wave after Phase 5 completion)

## 0. Scope (locked)

Two deliverables in one wave:

1. **Backend** — workspace-wide **AR aging** report endpoints that mirror the
   existing AP aging endpoints 1:1 (symmetric counterpart, no new business
   rules).
2. **Frontend** — a new **Reports page** (`/reports`) consuming the AR aging,
   AP aging, statement, and VAT-compliance exports that already exist, plus
   targeted Dashboard improvements that only surface currently-existing data.

No new business rules are introduced. AR aging uses the same aging-bucket
definitions, open-status set, date guards, and role model already locked for
AR credit control and statement features. Anything not backed by a live
endpoint is explicitly **deferred** (§8).

## 1. Why AR aging (not a new invention)

AP aging summary/detail/by-supplier already ships (Wave 22). The AR side is
currently only available **per client** via `GET /clients/{id}/credit`. A
workspace-wide AR aging view is the symmetric gap: every aggregation, bucket
boundary, and naming rule is copied from `services/supplier_payment_service.ap_aging`
+ `schemas/ap_aging.py`, adapted only where AR field names differ.

## 2. Backend — AR aging endpoints (locked)

### 2.1 Endpoints (new router `routers/ar_aging.py`, mounted at `/api/v1`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/v1/ar-aging` | any workspace member | summary |
| GET | `/api/v1/ar-aging/detail` | any workspace member | invoice-level rows |
| GET | `/api/v1/ar-aging/by-customer` | any workspace member | per-client rollup |

- **Auth:** `get_current_workspace_id` (any authenticated member) — identical
  to AP aging. No rate limiter (identical to AP aging).
- **Query params:** `as_of: date?`, `client_id: UUID?`.
- **Guards (mirror AP aging exactly):**
  - `as_of` in the future → 422 `VALIDATION_ERROR` field=`as_of` ("as_of cannot be after today").
  - `GET /api/v1/ar-aging/by-customer?client_id=<uuid>` → 422
    `VALIDATION_ERROR` field=`client_id` — the by-customer endpoint is an
    aggregation over customers and cannot be narrowed to one. (Internally the
    service uses `view="by-customer"`; the **HTTP contract** is expressed on
    the `/by-customer` endpoint, not as a `?view=` query parameter — no such
    HTTP parameter exists.)

### 2.2 Response schemas (new `schemas/ar_aging.py`)

Mirrors `schemas/ap_aging.py`; reuses `CreditBuckets` from `schemas/clients.py`.

```text
ArAgingSummaryResponse  { as_of: date, client_count: int, invoice_count: int,
                          total_outstanding: Decimal, buckets: CreditBuckets }
ArAgingDetailRow        { client_id: UUID, client_name: str, invoice_id: UUID,
                          invoice_number: str, issue_date: date, due_date: date,
                          days_overdue: int, balance_due: Decimal, bucket: str }
ArAgingDetailResponse   { as_of: date, total_outstanding: Decimal,
                          buckets: CreditBuckets, invoices: list[ArAgingDetailRow] }
ArAgingCustomerRow      { client: {id, name}, total_outstanding: Decimal,
                          buckets: CreditBuckets }
ArAgingByCustomerResponse { as_of: date, total_outstanding: Decimal,
                            buckets: CreditBuckets, customers: list[ArAgingCustomerRow] }
```

**Naming deltas vs AP (locked):** `supplier_*` → `client_*` / `customer`
(AR has no customer-facing code column; `Client` has `id` + `name` —
AP's `by-supplier` includes `supplier_code`, AR's `by-customer` deliberately
omits any code. Flagged, not invented).

### 2.3 Data rules (locked, verified against live AP implementation)

- **Row set (mirror AP exactly):** `Invoice` where `workspace_id == ws`,
  `deleted_at IS NULL`, `status IN AR_STATUSES(SENT, PARTIALLY_PAID, OVERDUE)`
  **and** `balance_due > 0`. Verified: the live AP implementation
  (`supplier_payment_service.open_ap_invoices`, `supplier_payment_service.py:286-290`)
  filters `status.in_(OPEN_AP_STATUSES)` **and** `balance_due > ZERO` — the AR
  mirror uses the AR open set plus the same `balance_due > 0` guard, so paid-in-full
  rows within the open set are excluded exactly as they are on the AP side.
- **Bucketing:** reuse `aging_buckets(invoices, resolved)` + `_bucket_key`
  directly from `credit_control_service` (AR `Invoice.due_date` is already a
  plain `date` — **no** `_AgingRow` adapter needed). Bucket keys:
  `current / days_1_30 / days_31_60 / days_61_90 / days_90_plus`.
- **Row bucketing (detail view):** `bucket = _bucket_key((resolved - due_date).days)`;
  `days_overdue = max(0, (resolved - due_date).days)`.
- **Totals:** `total_outstanding = SUM(balance_due)` over the row set,
  normalized via `money(...)`; per-customer / per-invoice rows use the same.
- **Client names:** batch `SELECT Client WHERE workspace_id == ws AND id IN (...)`
  → map; unresolved ids render `""` (mirror AP `_supplier_names`).

**as_of resolution (locked):** `resolved = as_of` if provided, else `utc_today()`.
Reject `as_of > utc_today()` with 422 (already in §2.1). **No clamping / no
"lower-bounded to today" behavior** — a past `as_of` is honored verbatim
(e.g. `as_of=2026-09-01` on 2026-09-07 resolves to 2026-09-01). This mirrors
`supplier_payment_service.ap_aging` (`supplier_payment_service.py:318`).

**Historical semantics (verified against live AP — locked):** `as_of` **does
not reconstruct** historical outstanding balances or historical lifecycle/
payment status. Verified: `ap_aging` reads the **current** open row set and the
**current** stored `balance_due`, and uses `resolved` only to (a) place rows in
buckets by `due_date` and (b) compute `days_overdue`. Consequences, mirrored by AR:

- An invoice that is PAID today is **excluded** even for a past `as_of` before
  its payment date.
- Outstanding is the **current** `balance_due` of currently-open invoices,
  bucket-shifted by the requested `as_of` — not a point-in-time ledger rebuild.

This is intentional symmetry, not an omission. No historical-payment or
historical-status reconstruction is introduced in Wave 29 (future BI wave
scope, out of boundary).

**Wave 30 item 1.2 addendum (historical mode):** the historical engine that
Wave 29 deferred is implemented as an **opt-in** mode on the same AR endpoints:
`GET /ar-aging?historical=true&as_of=<past>` (also `/detail`, `/by-customer`).
- Scope guard: `as_of` is resolved/rejected exactly as in the live mode
  (future → 422); the default `historical=false` behavior is **unchanged** and
  keeps all locked Wave 29 semantics above.
- Row set (reconstructed, not live): invoices `issue_date <= as_of`, status in
  `HISTORICAL_STATUSES` (SENT / PARTIALLY_PAID / PAID / OVERDUE — DRAFT and
  CANCELLED excluded, since no cancellation timestamp exists to date the
  snapshot), and not deleted before `as_of`.
- `balance_as_of = max(0, total_amount − Σ ISSUED credit notes (issue_date ≤
  as_of) + Σ ISSUED tax debit notes (issue_date ≤ as_of) − Σ SUCCESS payments
  (payment_date ≤ as_of))`, floored at 0 and kept only when `> 0` — mirroring
  the live `balance_due > 0` open-set guard. This naturally includes invoices
  paid today that were outstanding at the past `as_of`, and excludes invoices
  created after `as_of`.
- Bucketing / totals / client names reuse the exact same helpers as live mode;
  the same response schemas are returned (no new wiring).

### 2.4 Code layout (locked)

- `services/ar_aging.py` — one `ar_aging(session, workspace_id, as_of=None, client_id=None, view="summary")` function mirroring `supplier_payment_service.ap_aging` (imports `aging_buckets`, `_bucket_key`, `utc_today`, `AR_STATUSES` from `credit_control_service`). Keeps `credit_control_service.py` under the 500-line valve and mirrors `schemas/ar_aging.py` / `routers/ar_aging.py` 1:1 with AP.
- `routers/ar_aging.py` — three handlers (no internal prefix) + wiring in `main.py` (`include_router(ar_aging_router)`).
- **No Alembic.** No new columns/tables/enums — pure read aggregation over existing state (same as Wave 28).
- **Scalability / cardinality (locked):** AR aging response cardinality and
  pagination behavior **exactly match the existing AP aging endpoints** — which
  are intentionally unpaginated (`ap-aging` summary is bounded by row count;
  `detail`/`by-customer` return full lists). **No new pagination semantics are
  introduced in this wave.** The frontend is responsible for the light-weight
  consumption pattern: initial load fetches only summary + by-customer; detail
  is fetched on demand (§3.2). This mirrors AP's existing UI-facing contract.

## 3. Frontend — Reports page (locked)

### 3.1 New `api/reports.ts`

Types + fetchers for:
- AR aging summary / detail / by-customer (`GET /api/v1/ar-aging[...]`).
- AP aging summary / detail / by-supplier (`GET /api/v1/ap-aging[...]`).
- VAT compliance: **ZIP download** (`GET /api/v1/reports/vat-compliance?format=csv&from&to` via `responseType: 'blob'`, trigger anchor download with the server's `Content-Disposition` filename) and **JSON view** (`format=json`).

### 3.2 New page `pages/Reports.tsx` (+ `Reports.module.css`), route `/reports`

Three tabs, driven by `@tanstack/react-query`:

1. **AR Aging** — `as_of` date input (default today; blocked > today client-side),
   summary cards (total outstanding, invoice count, client count), recharts
   bucket bar chart, and a **by-customer table** (customer, total, per-bucket
   cells). **Lazy detail loading (no full-fetch on mount):** initial load
   fetches only summary + by-customer; selecting a customer fetches
   `detail?client_id=...`; an explicit "All Detail" action fetches the full
   `detail`. Mirrors AP's consumption pattern, not a duplicate grid.
2. **AP Aging** — same layout against suppliers, lazy detail same as AR.
3. **VAT Compliance** — `from`/`to` date inputs (enforce `from ≤ to`, both ≤ today,
   `to-from ≤ 366`), **Download CSV ZIP** button (blob), **Download JSON** button,
   and an inline JSON preview panel.

**VAT permission boundary (locked UX):** backend is OWNER/ADMIN-only
(`get_current_user` + workspace + role gate). The frontend **does not rely on
the 403 alone**. The VAT tab is visible to all roles, and the JSON preview and
all download actions are gated **before any request is fired**:

```text
MEMBER:
  VAT tab visible
    → "OWNER/ADMIN only" notice shown
    → NO JSON preview fetch (no format=json request ever fired)
    → NO JSON preview rendered
    → Download ZIP / Download JSON buttons unavailable (disabled/hidden)

OWNER/ADMIN:
  VAT tab
    → JSON preview available (fetch format=json on demand / on demand + on action)
    → Download JSON
    → Download ZIP
```

Preview is fetched **on demand only** (when the user opens the preview panel),
never automatically on tab mount for any role. This reuses the existing
permission convention in `frontend/src/pages/paymentHelpers.ts:11`
(`canManagePdc` → `role === 'OWNER' || role === 'ADMIN'`); Wave 29 adds a
parallel `canManageVat(role)` / shared helper. Wording everywhere is
**"OWNER/ADMIN only"** — never "owners only".

Charts: `recharts` (already in `package.json`, currently unused) — bar chart for
bucket distributions on AR/AP tabs.

### 3.3 Dashboard enhancements (only existing data)

- **Quick Actions** — wire the three dead buttons to real existing pages:
  Create Customer Invoice → `/invoices`, Log Procurement Request →
  `/procurement`, Record Goods Receipt → `/grn`.
- **Replace the empty "Recent Activities" widget** — heading is **renamed to
  "Recent Invoices"** (not reused under the old misleading title). Contents:
  latest N invoices from `GET /api/v1/invoices` using **server-side
  pagination `?page=1&per_page=5`** — verified the endpoint orders by
  `Invoice.created_at.desc()` (`invoices.py:152`) and supports
  `page`/`per_page` (`invoices.py:104-105`), so the widget never fetches the
  full invoice table; `InvoiceResponse` includes `created_at`
  (`schemas/invoices.py:88`). Empty state when none.
- **Add an "Open AR / AP" snapshot widget** — two mini bucket summaries fed by
  `ar-aging` + `ap-aging` summaries (today), reusing the same recharts bar or a
  compact table. No new endpoints.

### 3.4 Navigation

- Sidebar (`components/Layout.tsx`): new **Overview → Reports** item
  (`BarChart3` icon), path `/reports`.
- `App.tsx`: register `<Route path="reports" element={<Reports />} />`.

### 3.5 Frontend conventions

Mirror existing pages: CSS Modules, `lucide-react` icons, `react-hot-toast`
via `extractApiError`, react-query keys namespaced (`reports.ar_aging.*`,
`reports.ap_aging.*`, `reports.vat_*`), `Skeleton` during loading.

## 4. Tests (locked)

### 4.1 Backend — `tests/test_ar_aging.py` (mirror `test_ap_aging.py`)

Module-scoped `drop_all/create_all`; fresh workspace per test; AR invoices
seeded directly via async session (`Invoice` with `issue_date`/`supply_date`/
`due_date` today-guarded, `status=SENT|PARTIALLY_PAID|OVERDUE`, non-deleted).
Cases:

1. Summary buckets — invoices due at +5/-5/-40/-70/-120 → correct
   `client_count`/`invoice_count`/`total_outstanding` and each bucket.
2. Detail rows — a -40-day invoice → `bucket=days_31_60`, `days_overdue=40`,
   `client_name` resolves.
3. By-customer — two clients, rollup totals + per-customer buckets; sorted by name.
4. `client_id` filter on summary — only that client's invoices counted.
5. `as_of` future → 422.
6. `client_id` + by-customer → 422.
7. Status exclusion — DRAFT and PAID and CANCELLED invoices excluded.
8. Deleted invoice excluded.
9. Multi-workspace isolation — other workspace's invoices never counted.
10. Zero-balance row within the open set excluded (`balance_due = 0` even while
    status stays SENT — mirrors AP's `balance_due > ZERO` guard).
11. Past `as_of` honored verbatim (no clamping), using a **genuinely past**
    `as_of` (a future one would 422 and the test must not use it): seed an
    invoice with `due_date = today - 35`, request `as_of = today - 20`
    → `days_overdue = 15`, `bucket = days_1_30` (proves `resolved = today - 20`,
    not clamped to today). Separately, a future `as_of` still 422s.

### 4.2 Frontend verification

- `npm run build` (`tsc -b && vite build`) and `npx oxlint` must pass.
- No Playwright E2E in this wave (deferred, §8). Manual/browser eyeball of
  the three tabs + downloads.

## 5. NOT in this slice (deferred, flagged not silent)

- Sales-by-customer / sales-by-product / revenue / cashflow aggregations
  (would require **new** backend queries/invented report definitions — out of
  scope; candidate for a later BI wave).
- **Historical point-in-time aging** (reconstructing balances/status from
  payment history for a past `as_of`) — shipped as **Wave 30 item 1.2** on the
  AR endpoints as the opt-in `historical=true` mode (§2.3 addendum). The AP
  side intentionally keeps the live bucket-shift behavior; an AP historical
  mirror remains future scope paired with the B4 aging-logic dedup.
- Aligning `frontend/src/types/api.ts` `DashboardMetricsResponse`
  (`revenue_overview`, `invoice_status_distribution`) — **aspirational only**;
  `/dashboard/stats` does not return them and this wave does not touch
  `/dashboard/stats`. Noted (drift, not fixed here).
- Statement export (PDF/CSV) on the Reports page — existing statements stay on
  their per-client / per-supplier pages.
- Playwright E2E for reports/dashboard.

## 6. Coder checklist

- Backend: new files `schemas/ar_aging.py`, `services/ar_aging.py`,
  `routers/ar_aging.py`; wire in `main.py`; no model/migration changes;
  `alembic check` stays clean (no head move). **One shared bucket/boundary
  implementation (`credit_control_service` helpers) — no second copy of aging
  rules.**
- Backend tests: `tests/test_ar_aging.py` (11 cases above); full suite green;
  `ruff` + `black` clean.
- Frontend: `api/reports.ts`, `pages/Reports.tsx` + CSS, `Layout.tsx` nav,
  `App.tsx` route, `Dashboard.tsx` enhancements; `npm run build` + `oxlint` clean.
- Docs: `.planning/STATE.md` (+ checkbox `[x]` for Wave 28, phase header) and
  `.agents/reports/backend-execution-report.md`; commit per wave with hooks passing.
