# Project Audit — Master Reference

> This file is the single reference for all pending work, gaps, errors, and execution
> state. Whenever a session gets lost, read this file first. Every fix must be logged
> here in the Change Log before being marked done.
>
> Audit date: **2026-09-08** · Audited HEAD: **87fbe53** · Source: 4 parallel codebase
> audits (frontend↔backend contracts, backend wiring, frontend routing/types,
> planning/gaps docs) + manual verification of every critical claim.
>
> Scope: everything EXCEPT the production/deployment phase (as instructed by user).

---

## 1. Current Health Status

| Check | Result |
|---|---|
| Backend full suite | **408 passed** (verified during Wave 29, ~9–11 min, ≥900s timeout) |
| `ruff check` | Clean |
| `black` | Clean except pre-existing drift in `tests/test_enquiries.py`, `tests/test_ar_statement.py` (unrelated) |
| `alembic check` | Clean ("No new upgrade operations") |
| Frontend `npm run build` | Clean (tsc + vite) |
| Frontend `npx oxlint` | Clean (0 new warnings; 35 pre-existing in untouched files) |
| Alembic chain | 38 revisions, single linear chain, one head + one root, no branches |
| `tsc --noEmit` (frontend) | Exit 0, zero diagnostics |

**Known test-runtime quirks:** full suite needs ≥900s timeout (not a hang). Windows
venv `python.exe` is a stub that spawns `C:\Program Files\Python311\python.exe`
(same-looking processes). Port 8000 has docker + wslrelay listeners on `::1`/`::`;
always use `127.0.0.1:8000` (frontend `.env` already set). CORS only allows
localhost/127.0.0.1 ports 5173/5174/5175.

---

## 2. Master Pending List (planned but not implemented)

### 2.1 Reporting / BI (candidate "Wave 30" — Phase 6 continuation)
| # | Item | Status |
|---|---|---|
| 1.1 | Sales-by-customer / sales-by-product / revenue / cashflow aggregations | not started |
| 1.2 | Historical point-in-time aging engine (`as_of` reconstructed from payment history) | not started |
| 1.3 | Reports-page statement export (PDF/CSV) — today only per-client/per-supplier pages | partial |
| 1.4 | Playwright E2E for Reports/Dashboard | not started |
| 1.5 | `pdc_outstanding` + workspace-wide AR aging dashboard field pack | not started |

### 2.2 Purchasing / GRN (candidate "Wave 31")
| # | Item | Status |
|---|---|---|
| 2.1 | **D-22 Landed cost allocation** into inventory valuation (deferred "post-Wave-29") | not started |
| 2.2 | SPO amendments persistence (`SPOAmendmentCreate` is dead code; partial-confirmation branch is `pass`) | not started |
| 2.3 | RFQ award flow | not started |
| 2.4 | Supplier child-table CRUD (product identifiers / UOM conversions / prices) | partial (models only) |
| 2.5 | Inventory `/adjust` tightening (OWNER/ADMIN only + reason + ledger) | partial |
| 2.6 | Supplier-invoice event/history table | not started |
| 2.7 | Purchase-return VAT treatment (supplier-credit tax wave) | not started |
| 2.8 | Warehouse returns receiving workflow | not started |
| 2.9 | UOM conversion multi-hop resolution | not started |

### 2.3 Tax / Compliance
| # | Item | Status |
|---|---|---|
| 3.1 | India GST market (Category 11) | not started |
| 3.2 | e-Invoice / PINT-AE / Peppol / FTA XML submission (readiness fields `einvoice_*`, `hs_code`, `vat_category` don't exist in models) | not started |
| 3.3 | VAT filing (returns, FTA certification, netting engine) — Wave 28 export is read-only | not started |
| 3.4 | Certified translator / Arabic PDF workflow | not started |
| 3.5 | VAT period-consistency divergence (GST business date vs driver-UTC bucket dates) | documented, unfixed |
| 3.6 | Tax-invoice header `discount_amount` override | not started |
| 3.7 | **Credit-note server-side PDF** (`pdf_service.py:35` `SUPPORTED_DOCUMENTS` excludes CREDIT_NOTE; WhatsApp `DOCUMENT_TYPES` excludes it) | **real gap** |

### 2.4 Pricing / PDM
| # | Item | Status |
|---|---|---|
| 4.1 | Tiered pricing V3 (TIER_2+, DEALER, valid_from/to, max_quantity, customer groups, invoice-time resolution engine) | partial (subset ships) |
| 4.2 | Re-pricing of SENT invoices | not started |
| 4.3 | Electrical specs + e-invoice pack columns (`hs_code`, `vat_category`) | not started |
| 4.4 | Volume-pricing changes on master after SENT | not started |

### 2.5 Credit / AR
| # | Item | Status |
|---|---|---|
| 5.1 | Admin HOLD override endpoint (`POST /clients/{id}/credit-status` + override) | not started |
| 5.2 | `block_do_on_hold` enforcement on DN dispatch (flag ships; override path missing) | partial |
| 5.3 | PDC bounce → credit re-evaluation integration | partial |
| 5.4 | Auto-apply `credit_balance` FIFO to next invoice | not started |
| 5.5 | Refunds as negative payments | not started (locked design) |
| 5.6 | Over-credit / negative `balance_due` | not started (by design) |
| 5.7 | `invoice_list.amount_credited` in invoice list response | not started |
| 5.8 | AR credit-note auto-generation from sales returns | not started |

### 2.6 Platform / Hardening (non-production)
| # | Item | Status |
|---|---|---|
| 6.1 | Redis wired (installed + `REDIS_URL` set, but limiter is in-memory; no queues) | not started |
| 6.2 | Scheduler / nightly overdue job (OVERDUE set only on request paths; no `jobs/` module) | partial |
| 6.3 | Email attachments / templates / bulk-send (Wave 26 deferred pack) | not started |
| 6.4 | WhatsApp deferred pack (LLM, reply automation, media, bulk/queues, per-workspace creds) | not started |
| 6.5 | Bilingual server rendering / client+server PDF unification | partial (server EN-only) |
| 6.6 | Multi-currency tax invoices | not started (by design, AED-only) |

---

## 3. Frontend ↔ Backend API Disconnects (verified)

| # | Area | Disconnect | Ref |
|---|---|---|---|
| A1 | Debit notes | Frontend `TaxDebitNoteItem` expects `uom_id`, `sku_snapshot`, `discount_amount`, `line_net`, `created_at`, `updated_at`; backend `TaxDebitNoteItemResponse` returns `internal_sku` and none of those (list view) | `frontend/src/api/debitNotes.ts` vs `backend/app/schemas/tax_debit_notes.py` |
| A2 | Enquiries | Frontend expects envelope `{items,total,skip,limit}`; backend returns `{items,total,page,size}` → `skip`/`limit` are `undefined` in UI | `frontend/src/api/enquiries.ts:65-70` vs `backend/app/routers/enquiries.py:57-62` |
| A3 | Enquiries | Frontend sends `search`; backend `get_enquiries` has no `search` param → silently ignored | `frontend/src/api/enquiries.ts:80-89` vs `backend/app/routers/enquiries.py:29-35` |
| A4 | Invoices | `InvoiceListItem` frontend declares `amount_credited`/`amount_debited`; backend omits them | `frontend/src/api/invoices.ts:42-55` vs `backend/app/schemas/invoices.py:193-207` |
| A5 | UOM | `getUOMs` may send `search`; `list_uom` has no search param → silently ignored | `frontend/src/api/products.ts` vs `backend/app/routers/products.py:218-231` |
| A6 | Clients | `getClients` types `PaginatedResponse` as `SuccessResponse<Client[]>` (drops pagination; works by luck) | `frontend/src/api/clients.ts:53-56` vs `backend/app/routers/clients.py:118-166` |
| A7 | VAT manifest | Backend `warnings = dict[str, List[str]]`; frontend types `string[]` (loose typing) | `frontend/src/api/reports.ts:172-195` vs `backend/app/schemas/vat_compliance.py:89-101` |
| A8 | Dashboard | `DashboardMetricsResponse` (dead type) does NOT match real `/dashboard/stats` → `DashboardStats` | `frontend/src/types/api.ts:42-48` |

**Confirmed OK:** auth, payments+PDC, credit notes, quotations, LPOs, delivery notes,
GRN, procurement, RFQ, SPO, suppliers, supplier invoices, AR/AP aging, workspaces.

---

## 4. Backend Wiring & Logic Gaps (verified)

| # | Gap | Ref |
|---|---|---|
| B1 | **SPO amendment flow is a stub** — `price_amendment_pending=True` set but `SPOAmendmentCreate` never persisted; partial-confirmation branch is `pass` (no backorder handling) | `spo_service.py:206-219` |
| B2 | **Credit-note PDF unreachable** server-side (only INVOICE/QUOTATION/AR_STATEMENT renderable) | `pdf_service.py:35`, `schemas/whatsapp_comms.py:26` |
| B3 | **No scheduled OVERDUE job** — overdue only flips opportunistically on request paths | `invoices.py:113,190`, `credit_control_service.py:204,358` |
| B4 | **Duplicated aging logic** — `supplier_payment_service._bucket_of` re-implements `credit_control_service._bucket_key` (identical thresholds, 2 sources); duplicate status tuples `PAYABLE_STATUSES`==`OPEN_AP_STATUSES`; duplicate open-AR query; double invoice load in `CreditControlService.aging`; overdue condition triple-implemented | `supplier_payment_service.py:37-44,409-419` vs `credit_control_service.py:117-126,157-169,296-298` |
| B5 | **Dead schemas** — `ClientListResponse`, `PaymentListResponse`, `APIResponse`, `ErrorResponse`, `SPOAmendmentCreate`, `SPODeliveryScheduleCreate` never used | `schemas/clients.py:122`, `schemas/payments.py:77`, `schemas/common.py:38,70`, `schemas/spo.py:100,114` |
| B6 | **Enquiries is the only unwrapped contract** — no `SuccessResponse` wrapper; inconsistent with every other router | `routers/enquiries.py:28,57` |
| B7 | Untyped nested payloads `ArAgingCustomerRow.client` / `ApAgingSupplierRow.supplier` as `dict`; AP row includes `supplier_code`, AR row doesn't (asymmetry) | `schemas/ar_aging.py:40`, `schemas/ap_aging.py:40` |
| B8 | `delete_client` has no response_model, returns untyped dict | `routers/clients.py:253` |
| B9 | Stale misleading comment on rate-limit decorator (`payments.py:113-114` says "would be a decorator" though it already is) | `routers/payments.py:113-114` |
| B10 | AR aging + AP aging endpoints carry no rate limit (payments/reports/comms do) | `routers/ar_aging.py`, `routers/supplier_payments.py` |

---

## 5. Frontend Routing / Nav / Type Issues (verified)

| # | Issue | Ref |
|---|---|---|
| F1 | **3 dead in-page links** fall through catch-all redirect to `/`: `/invoices/new`, `/supplier-invoices/new`, `/clients/:id` | `Dashboard.tsx:180`, `SupplierInvoices.tsx:26`, `enquiries/EnquiryDetail.tsx:203` |
| F2 | **5 "coming soon" alert stubs** (create flows): Suppliers, Inventory, Procurement, RFQ, GRN | `Suppliers.tsx:25`, `Inventory.tsx:25`, `Procurement.tsx:25`, `RFQ.tsx:25`, `GRN.tsx:27` |
| F3 | **4 dead types** never imported: `ApiResponse`, `RevenueData`, `InvoiceStatusData`, `DashboardMetricsResponse` | `frontend/src/types/api.ts:30-48` |
| F4 | SPOBuilder uses `data: any`, raw UUID inputs for supplier/warehouse, no error surface | `SPOBuilder.tsx` |
| F5 | Unused client-side API exports (e.g. `cancelSPO`, some product getters) — no build impact | `api/spo.ts`, `api/products.ts` |

**Confirmed OK:** all 26 routes resolve to real pages; left-nav 100% valid; single shared
axios client with consistent token/refresh/`auth_unauthorized` handling; zero raw
`fetch`; no dangling imports (tsc exit 0).

---

## 6. Errors & Inconsistencies (verified)

| # | Issue | Severity | Ref |
|---|---|---|---|
| E1 | **`check_amount_debited_nonneg` declared in model but NO migration creates it** — DB constraint never applied (only app logic enforces) | HIGH | `models/invoice.py:48` (grep of all 38 migrations: absent) |
| E2 | **Doc numbering sync** — 3 parallel wave definitions disagree (ROADMAP frozen at Phase 5; committed sequence Waves 21–29; MASTER_PLAN_V3 superseded numbering where Wave 26=WhatsApp, 28=India) | MED | `.planning/ROADMAP.md`, `.agents/MASTER_PLAN_V3.md` |
| E3 | STATE.md says Wave 29 "ready to commit" though committed at `87fbe53`; Wave 27 slot shows "implementation begins next" though implemented+committed | MED | `.planning/STATE.md:4,39` |
| E4 | Doc drift: `MASTER_PLAN_V3`/`STACK.md` "Wave 29 = production hardening" vs project numbering "Wave 29 = Reporting & Dashboard" | MED | `.agents/MASTER_PLAN_V3.md`, `.planning/codebase/STACK.md:110` |
| E5 | Two different "Wave 28" (India vs UAE VAT pack) across docs | LOW | `business-rules.md:670`, `phase-5-comms-integrations-planning.md:27-30` |
| E6 | Bilingual↔volume-pricing↔electrical-specs↔debit-notes dependency ordering circular in addenda (§7 "After this WP") | LOW | addenda `:7` lines |
| E7 | `credit_control_service.py:1` docstring predates implemented HOLD evaluation | LOW | `credit_control_service.py:1` |
| E8 | `phase-5-comms-integrations-planning.md:30` describes now-implemented Reports/Dashboard as "future" | LOW | planning doc |

---

## 7. Git Hygiene (as of audit)

- **97 untracked stray files**: 88 `backend/hang-probe-test_*.log(+.err)` + `backend/pytest-full.log`, `backend/pytest-wave29.log`, `backend/backend-uvicorn.log`, `backend/uvicorn-err.log`, `backend/uvicorn-out.log` (my Wave-29 verification artifacts — safe to delete).
- 9 files show `M` in `git status` but `git diff --stat` is **empty** → pure CRLF noise (autocrlf), no real uncommitted content.
- `frontend/.env` properly gitignored (`.gitignore:23` `.env`); holds `VITE_API_URL=http://127.0.0.1:8000`.
- `.gitignore` does NOT cover `backend/*.log*` — must be added so logs never get committed.

---

## 8. Execution Plan (sequential; each item: plan → implement → test → verify → docs → commit)

Ordering rationale: correctness fixes first (cheap, low-risk, unblock everything), then
pending feature waves in roadmap order (Reports/BI → GRN/purchasing), keeping style
consistency fixes bundled with the surface they touch.

1. **Cleanup**: delete the 97 stray log files; add `backend/*.log*` to `.gitignore`.
2. **Fix A2/A3** — enquiries envelope `{page,size}` + `search` support (backend + frontend contract match). Backend agent.
3. **Fix A1** — debit note list item schema parity (align `TaxDebitNoteItemResponse` with frontend expectations). Backend + frontend.
4. **Fix A8 + F3** — delete dead types, ensure `DashboardStats` canonical. Frontend only.
5. **Fix F1** — repair 3 dead links. Frontend only.
6. **Fix E1** — add `check_amount_debited_nonneg` migration (Database agent → alembic). Verify `alembic check` clean + round-trip.
7. **Fix E2/E3/E4/E5** — reconcile ROADMAP/STATE/master-plan numbering (docs-only wave).
8. **Wave 30** — Phase 6 continuation BI/analytics (per §2.1 + `wave-reports-dashboard-addendum.md` §5 deferrals), incl. Playwright E2E for Reports/Dashboard (1.4). Report-first.
9. **Wave 31** — D-22 landed cost into inventory valuation (per §2.2 + `grn-architecture.md`), plus SPO amendments (B1) as bundled scope. Report-first.
10. **Backend consolidation** — dedupe aging logic (B4), kill dead schemas (B5), wrap enquiries contract (B6), rate-limit aging endpoints (B10). Style-only, no behavior change.
11. **Ongoing**: any newly discovered gap gets added to this file's Change Log and worked in order.

---

## 9. Change Log

| Date | Item | Status |
|---|---|---|
| 2026-09-08 | Audit created (4 parallel agents + manual verification) | done |
| 2026-09-08 | Cleanup: deleted 88 hang-probe log artifacts; `.gitignore` `backend/*.log*` | done |
| 2026-09-08 | A2/A3: enquiries envelope `{items,total,page,size}` + `search` (or_/ilike) + test | done |
| 2026-09-08 | A1: TDN item schema parity — `uom_id`, `sku_snapshot`, `discount_amount`, `line_net`, timestamps; discount-aware `apply_line_money`; migration `a1b2c3d4e5f6` | done |
| | | |

---

## 10. Rules To Respect While Working From This File

- Read `.claude/CLAUDE.md` + `.agents/AGENTS.md` before edits (already done).
- Report every action in `.agents/reports/{role}-execution-report.md` before/while editing.
- One commit per completed wave/phase, after: tests green, ruff/black clean, `alembic check` clean (when schema involved), docs updated (execution report + STATE.md + THIS FILE).
- Backend list APIs paginate (`page`/`per_page` + `PaginationMeta`); responses wrapped in `SuccessResponse`.
- Database change → Database Agent (model + alembic) → Backend Agent (router/service/schema).
- Money: `Decimal(12,2)`, never float. Payments immutable. Soft deletes only. Never SQLite.
- Never commit secrets. `frontend/.env`, `backend/.env` stay untracked.
- Windows PowerShell; backend venv at `backend\.venv\Scripts\`.
