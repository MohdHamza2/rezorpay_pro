# InvoiceSaaS (rezorpay_pro) — Full Project Audit

**Audit Date:** 2026-09-06
**Technique:** System inventory + targeted re-verification of every documented concern + live test/build runs.
**Verdict:** Architecture and feature coverage are strong — all Waves 1–7 plus the AR/electrical B2B addenda shipped. But **the repo is not green at HEAD**: the backend suite fails 4 tests and the frontend production build is broken (12 TS errors). CI has no frontend job, so the regression is invisible to CI. Fixable, but not "everything is perfect."

---

## 1. What is Actually Shipping (verified)

| Area | Status |
|---|---|
| Auth + Workspace tenant (JWT, bcrypt, slug) | Working; slug race unguarded (see M-9) |
| Clients + AR invoices + payments | Working; payments immutable (PUT → 405), idempotency keys 48h, overpayment 400 |
| FTA tax invoices (STANDARD/SIMPLIFIED, TRN snapshots) | Working + E2E |
| Credit control | Working: `OVERDUE` computed on-read, `HOLD` engine, block flags (fabricated — not enforced end-to-end) |
| Quotations | Working + E2E (customers) |
| Customer Purchase Orders (LPO) | Working + E2E |
| Delivery Notes | Working + E2E |
| Credit Notes (tax CN + AR posting) | Working + E2E |
| Tax Debit Notes (sales) | Backend + UI + PDF shipped; **frontend build broken on this code (F-1)** |
| AR Statements (aging JSON + PDF) | Working + E2E |
| PDC (post-dated cheques) state machine | Working + E2E |
| Volume + customer pricing | Working + E2E |
| Bilingual EN/AR PDF (Noto Naskh Arabic) | Working |
| Electrical spec columns + filters | Backend + UI shipped |
| Enquiry Management (Wave 7) | Working + E2E + **unused-import TS errors (F-1)** |
| Product master (categories/brands/UOM/product, specs, search) | Full CRUD + pagination (concern RESOLVED) |
| Supplier master | root list/create only (M-6, M-7) |
| Inventory (warehouse/bin/level/adjust) | Working; no transfers/counts/reservations |
| Procurement (PR/RFQ/SPO/GRN/supplier-invoice 3-way match) | Working; numbering unsafe (M-5); purchase-return hook is `pass` (M-11) |
| Backend tests | 25 files, **224 pass / 4 fail** |
| Frontend | 48 pages, 13 Playwright specs, **`npm run build` FAILS** |

Migrated schema: 29 Alembic revisions, single head `c624e2ac4f47` (enquiry).

---

## 2. Findings — Blocking (fix before next wave)

> **Remediation status (2026-09-06):** F-1, F-2, F-3, M-1, M-2, M-5, M-10 fixed and verified. See `.agents/reports/frontend-execution-report.md` (F-1), `backend-execution-report.md` (F-2, M-1, M-2, M-5, M-10), and `.github/workflows/ci.yml` (F-3).

### F-1 Frontend production build is broken (12 TS errors) `STATUS: FIXED`
`npm run build` (`tsc -b && vite build`) fails on `master`. All errors trace to the debit-notes + enquiry frontend work (`fc7989d`, `f03713a`):

| File | Error | Fix |
|---|---|---|
| `src/components/pdf/TaxDebitNotePDF.tsx:193` | `PDF_LABELS.taxDebitNoteNo` doesn't exist | Use `PDF_LABELS.debitNoteNo` |
| `TaxDebitNotePDF.tsx:194,273` | `cn.tax_debit_note_number` doesn't exist on `TaxDebitNote` | Use `cn.debit_note_number` |
| `src/pages/InvoiceArPanel.tsx:36` | `invoice.amount_debited` not on frontend `Invoice` type (backend schema has it) | Add field to frontend type |
| `InvoiceArPanel.tsx:99` | `row.tax_debit_note_number` | Use `row.debit_note_number` (field is `debit_note_number` per `api/debitNotes.ts:42`) |
| `src/pages/enquiries/Enquiries.tsx:4` | unused `Plus` | remove |
| `src/pages/enquiries/EnquiryDetail.tsx:1,5` | unused `useState, Check, Edit2, Play, RefreshCw, X` | remove |

There is **no `typecheck` script** in `frontend/package.json` — `tsc -b` only runs as part of `build`.

### F-2 Backend test suite is red — 4 failures `STATUS: FIXED`
Run: `pytest` → **now 228 passed, 0 failed** (was 224 passed, 4 failed).

1. **`tests/test_ar_statement_tdn.py::test_stmt_with_tdn`** — `relation "users" does not exist`.
   Root cause: this test module has **no schema setup of its own** (`setup_database` in `test_ar_statement.py` is a module-scoped autouse fixture, so it only runs for that module). Standalone run: no tables. Full suite: `test_ar_statement.py` alphabetically runs first and its teardown does `drop_all`, so when `test_ar_statement_tdn.py` runs there are no tables. Test must set up its own schema fixture.

2–4. **Stale "alembic head" guard assertions** in three files:
   - `test_pdc.py::test_fta_cn_hold_overpay_alembic` (line 751)
   - `test_pricing.py::test_schema_not_float_and_alembic_head` (line 497)
   - `test_product_electrical_specs.py::test_alembic_new_revision_parent_and_check` (line 479)

   All assert a specific revision (`b8d5f0c3a216` credit-notes, or its child `1a30af047312`) appears in `alembic heads`. The head has since advanced (electrical specs → tax debit notes → debit-note-issued → **`c624e2ac4f47` enquiry**), so `alembic heads` no longer lists those old revisions. These tests passed when written (Sep 1) and have been red since the electrical-specs/tax-debit-note/enquiry migrations landed. **They are guard tests, not product bugs, but they keep CI red.** Fix: pin to `c624e2ac4f47` (and update the parent/child check to the new chain), or make the guard assert chain ancestry rather than a literal head.

> Implication: **CI is currently red on `master`** (these are deterministic, DB-independent failures), and the "fix CI" commits (d5ad13d, b8499a3) did not address them.

### F-3 CI has no frontend job `STATUS: FIXED`
`.github/workflows/ci.yml` contained only backend ruff/black lint, backend pytest, and pip-audit. The frontend is **never built, type-checked, or EA-tested in CI**. That is why F-1 shipped unnoticed. **Fixed:** added a `frontend` job (Node 22, `npm ci`, `npm run lint` (oxlint), `npm run build`), triggered on push/PR to main/master.

---

## 3. Findings — Medium (pre-production hardening)

- **M-1 JWT secret default `STATUS: FIXED`** — `config.py` now raises `RuntimeError` in `ENVIRONMENT=production` when `SECRET_KEY` is the default `"change-me-in-production"`. `.env.example` updated. Also fixed `health.py` E402 import.
- **M-2 CORS hardcoded localhost `STATUS: FIXED`** — `Settings.CORS_ORIGINS: list[str]` (JSON env var, default `["http://localhost:5173", "http://localhost:3000"]`) wired into CORS middleware; documented in `.env.example`.
- **M-3 Dashboard AR sum in Python** — `dashboard.py:37/45` still loads every non-cancelled invoice and sums `balance_due` client-side. Use a SQL aggregate (subtotal of payments).
- **M-4 Payments rate limiter in-memory** — slowapi memory backend; Gunicorn `--workers 4` multiplies allowed auth/payment attempts. Redis is declared (`REDIS_URL`) but **unused by app code**. Wire Redis storage or drop the dep.
- **M-5 Unsafe document numbering (PR/RFQ/GRN) `STATUS: FIXED`** — replaced count-based (`count(all rows)+1`) with gapless `FOR UPDATE` counter tables `pr_counters`/`rfq_counters`/`grn_counters` (Alembic `9f3a2c1e5d84`), mirroring `InvoiceCounter`/`SPOCounter`. New `PRNumberService`/`RFQNumberService`/`GRNNumberService`. Concurrency test coverage added.
- **M-6 Supplier child tables unused** — `SupplierContact/BankAccount/Document/Product` exist in models; `suppliers.py` is still `GET ""` + `POST ""` only. No IBAN/trade-license/VAT-cert/SKU endpoints.
- **M-7 Unpaginated masters + E402** — suppliers/products/inventory/PR/RFQ/SPO/GRN/AP list endpoints return full arrays (`PaginatedResponse` only on clients/invoices/payments/products). The `import time` mid-function E402s in `procurement.py`/`rfq.py` were resolved as part of M-5; pagination for the remaining masters is still open.
- **M-8 Tests use `create_all`, not Alembic** — every suite does `SQLModel.metadata.drop_all/create_all` from the ORM, so tests can pass on a schema that differs from migration history (ENUM names, server defaults). CI's `alembic check` is separate and won't catch test-DB drift. (Also the direct cause of F-2 #1.)
- **M-9 Register slug race** — `auth/router.py:97–107` uniqueness loop has no lock / no `UniqueViolation` retry; parallel registers with the same workspace name can collide.
- **M-10 Leftover scripts `STATUS: FIXED`** — deleted `backend/test_e2e.py`, `backend/test_step2_api.py`, `backend/test_step2_production.py` (outside `tests/`; `pytest.ini` `testpaths=tests` already excluded them).
- **M-11 GRN purchase-return stub** — `grn_service.py:300–303` is still `# Hook logic placeholder ... pass`; rejected qty doesn't create a PRN/debit note.
- **M-12 pip-audit non-blocking** — CI `continue-on-error: true`; `python-jose` unmaintained.
- **M-13 localStorage JWT** — XSS-sensitive token storage; no CSP documented.

---

## 4. Findings — Low / Process / Docs

- **L-1 ROADMAP vs STATE contradiction `STATUS: FIXED`:** `.planning/STATE.md` said *"Phase 3: Sales Quotation Builder (Wave 8 — Pending)"* but `.planning/ROADMAP.md` says *"Phase 3: Advanced Inventory (Waves 18-19)".* These disagree on what Phase 3 is. (Note: quotations already shipped, so "Quotation Builder" as a phase id is stale.) **Fixed:** STATE.md realigned to Advanced Inventory + audit remediation recorded in Recent Actions.
- **L-2 `.agents/reports/README.md` is stale `STATUS: FIXED`** — was timestamped 2026-08-31; Wave Status still said Wave 3 "Next DoD to finish", Waves 6–11 "Not started", Wave 0 drift "remains". **Fixed:** refreshed to 2026-09-06 audit state, added remediation status table, listed the audit report in the index.
- **L-3 `.planning/codebase/CONCERNS.md` partially stale** — product-master and payment-immutability concerns are resolved; GRN/numbering/dashboard/supplier/secret/CORS/redis concerns are still live. Re-run the audit to mark which remain.
- **L-4 No root `README.md`, no root `AGENTS.md`, no `TODOS.md`** — only `.agents/` has AGENTS.md. Non-blocking for code, but onboarding/`/health` surface is thin.
- **L-5 Repo noise** — `fix.py` script and `graphifyy/cache/ast/*.json` (hundreds of AST cache files) are committed. Consider gitignoring the cache.
- **L-6 React 19 vs docs** — MASTER_PLAN locked React 18; enablements use React 19.2.8. Align the plan.

---

## 5. "What already exists" (don't re-plan these)

Already implemented and tested: FTA tax invoices (standard/simplified + TRN), quotations, customer LPOs, delivery notes, tax credit + debit notes, AR statements/aging, PDC lifecycle, volume + customer pricing, bilingual EN/AR PDFs, electrical specs, enquiry (Wave 7), product master full CRUD, credit control engine (HOLD + OVERDUE-on-read), SPO/GRN/supplier-invoice 3-way match.

---

## 6. Upcoming Implementations & Left Architectures (integrate next)

From `.planning/ROADMAP.md` + `architecture/*` intended domains (ordered):

1. **Phase 3 — Advanced Inventory (ROADMAP; Waves 18-19)**
   - Stock Reservations based on Customer POs (link to `reserved_qty` already on inventory models; enforce `available = on_hand - reserved - damaged` at reservation time).
   - Multi-warehouse Stock Transfers.
   - Stock Counting / Reconciliation.
2. **Phase 4 — AP Payments & Aging**
   - Supplier payment recording (mirror AR idempotency/immutability patterns).
   - AP aging reports integrated with the supplier-invoice 3-way match engine.
3. **Phase 5 — Communications & Integrations**
   - Email engine via Resend API (send endpoints are currently state flags only).
   - WhatsApp Business API (Meta) for automated PDF delivery.
   - UAE VAT Compliance Pack export (FTA return; workspace already has `default_tax_rate`).
4. **Architecture left-overs to close the CFO cycle**
   - GRN auto-Purchase Return / debit note (currently `pass`).
   - SPO amendments (models exist; no router).
   - RFQ quote-response + award engine (models exist; API is create/list only).
   - Supplier child tables (contact, bank, documents, SKU mapping).
   - Production-grade: frontend Dockerfile + CD + TLS + CORS via env, harden secret default, Redis-backed limiter, pagination everywhere, RLS or stronger tenant tests per new router.

---

## 7. Recommended order (dependencies)

1. Fix F-1 (frontend build) — 5 small edits, unblocks deploy.
2. Fix F-2 (4 tests) — add schema fixture to `test_ar_statement_tdn.py`; bump alembic-head guards to `c624e2ac4f47`.
3. Add F-3 CI frontend job — prevents recurrence.
4. Documentation hygiene L-1/L-2 (ROADMAP vs STATE; reports index) before the next phase claims a slot.
5. Then Phase 3 Advanced Inventory; keep M-5 (numbering) fixed first since reservations add concurrent writes.

---

*Report generated 2026-09-06 from live verification (git history + pytest + `npm run build`).*
