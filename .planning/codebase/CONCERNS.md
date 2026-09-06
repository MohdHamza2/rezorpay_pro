# Codebase Concerns

**Analysis Date:** 2026-08-31
**Last Audit:** 2026-09-06 (see `.agents/reports/full-project-audit-2026-09-06.md`)

## Tech Debt

**~~Product master API incomplete:~~ RESOLVED (2026-09-06 audit)**
- ~~Issue: Models include identifiers, UOM conversions, and prices (`backend/app/models/product.py`) but `backend/app/routers/products.py` only lists/creates Category, Brand, UOM, Product. No GET-by-id, PUT, DELETE, search, pagination, or nested resources. Frontend "Add Product" is `alert('Add Product UI coming soon')` (`frontend/src/pages/Products.tsx`). Hermes plan `.hermes/plans/2026-08-27_153000-wave3-product-master.md` still describes this gap.~~
- Resolved: full CRUD + search + pagination + nested resources landed; `test_products.py` covers the suite.

**~~Payment PUT vs immutability rule:~~ RESOLVED (2026-09-06 audit)**
- ~~Issue: `.claude/CLAUDE.md` says payments are immutable. `PUT /api/v1/invoices/{id}/payments/{id}` updates `status` and `pdc_status`.~~
- Resolved: PUT → **405**; PDC management moved to explicit lifecycle endpoints.

**~~Invoice OVERDUE never computed:~~ RESOLVED (2026-09-06 audit)**
- ~~Symptoms: Status enum includes `OVERDUE` but no job/query sets it when `due_date < today` and balance > 0.~~
- Resolved: computed on-read via `should_mark_overdue` (`backend/app/services/credit_control_service.py`).

**~~JWT secret defaults:~~ RESOLVED (2026-09-06)**
- ~~Risk: `SECRET_KEY` default `"change-me-in-production"` (`backend/app/config.py`)~~
- ~~Files: `backend/app/config.py`, `backend/.env.example`~~
- ~~Current mitigation: example file warns to change; no startup check refusing default in `ENVIRONMENT=production`~~
- Resolved: `Settings` model-validator raises `RuntimeError` when `ENVIRONMENT=production` and `SECRET_KEY` is the default. `.env.example` updated. `backend/app/routers/health.py` E402 import also cleaned.

**Tokens in localStorage:**
- Risk: XSS can steal access+refresh (`frontend/src/contexts/AuthContext.tsx`)
- Files: `frontend/src/api/client.ts`
- Current mitigation: none (no CSP documented)
- Recommendations: httpOnly cookies + CSRF, or strict CSP when hosting

**~~CORS localhost-only:~~ RESOLVED (2026-09-06)**
- ~~Risk: Production SPA origin rejected; temptation to `allow_origins=["*"]`~~
- ~~Files: `backend/app/main.py`~~
- ~~Current mitigation: explicit localhost list~~
- Resolved: `Settings.CORS_ORIGINS: list[str]` (JSON env var, default localhost dev list) wired into `main.py` CORS middleware; documented in `.env.example`.

**RBAC unused:**
- Risk: MEMBER equals OWNER for all writes
- Files: `backend/app/models/user.py`, no `require_role`
- Current mitigation: single-user workspaces from register
- Recommendations: Enforce ADMIN/OWNER for approve SPO, void invoice, workspace settings

**Rate limiter in-memory:**
- Risk: Per-process limits; multi-worker Gunicorn (`--workers 4` in `backend/Dockerfile`) multiplies allowed auth attempts
- Files: `backend/app/limiter.py`, `backend/Dockerfile`
- Current mitigation: slowapi on auth/payments
- Recommendations: Redis storage using existing `REDIS_URL`

**pip-audit non-blocking:**
- Risk: CI `continue-on-error: true` (`.github/workflows/ci.yml`)
- Recommendations: Fail on known exploited CVEs; `python-jose` is unmaintained — plan `PyJWT`

**No object-level auth beyond workspace:**
- Risk: Any workspace member can approve SPO (`backend/app/routers/spo.py` `approve`) and AP invoices
- Recommendations: Maker-checker (architecture RFQ/SPO docs) before production money movement

## Performance Bottlenecks

**~~PR/RFQ numbering full-table load:~~ RESOLVED (2026-09-06)**
- ~~Problem: `select(ProcurementRequest).where(workspace)` then `len(all())`~~
- ~~Files: `backend/app/routers/procurement.py`, `rfq.py`~~
- ~~Cause: Count via load~~
- Resolved: gapless `pr_counters` / `rfq_counters` / `grn_counters` tables + `FOR UPDATE` services (`PRNumberService`, `RFQNumberService`, `GRNNumberService`), Alembic `9f3a2c1e5d84`. Concurrent-create coverage added in `test_concurrent_numbering.py`.

**~~GRN number same pattern:~~ RESOLVED (2026-09-06)**
- ~~Files: `backend/app/services/grn_service.py`~~
- Resolved: `GRNCounter` + `FOR UPDATE` via `GRNNumberService` (see above).

**Dashboard AR sum in process:**
- Files: `backend/app/routers/dashboard.py`
- Improvement path: SQL sum

**Unpaginated master lists:**
- Files: products/suppliers/inventory routers
- Improvement path: pagination + indexes already on `workspace_id`

**Frontend bundle:**
- Problem: Vite advisory >500KB; Hermes plan notes ~1.7MB historically
- Files: `frontend/vite.config.ts` (no `manualChunks`)
- Improvement path: route-level `React.lazy` for SPO/GRN/PDF

## Fragile Areas

**Invoice financial path:**
- Files: `backend/app/services/invoice_service.py`, `payment_service.py`, `invoice_number.py`
- Why fragile: row locks, idempotency, status cache vs payment sums
- Safe modification: only through services; add concurrent tests for any balance change
- Test coverage: numbering + isolation; no dedicated overpayment/idempotency/state-machine files

**3-way match:**
- Files: `backend/app/services/supplier_invoice_service.py`
- Why fragile: tolerance math, match enums
- Safe modification: table-driven tests per `MatchResult`
- Test coverage: one e2e `test_3way_match_engine`

**GRN quantity constraint:**
- Files: `backend/app/models/grn.py` `chk_grnitem_quantity_received_match`
- Why fragile: DB rejects rows if accepted+damaged+rejected ≠ received
- Safe modification: validate in service before flush (already UI-validated in `GRNDetail.tsx`)
- Test coverage: `test_grn.py`, `test_e2e_grn.py`

**Alembic ENUM chain:**
- Files: `backend/alembic/versions/`
- Why fragile: PostgreSQL ENUM alters are painful; tests `create_all` hide drift
- Safe modification: always `alembic revision --autogenerate` + `alembic check`
- Test coverage: CI `alembic check` only

## Scaling Limits

**Postgres + single API process:**
- Current capacity: Compose `pool_size=10`, `max_overflow=20` (`backend/app/database.py`); Gunicorn 4 workers
- Limit: in-memory rate limit; unpaginated lists; dashboard full scan
- Scaling path: Redis limiter, pagination, SQL aggregates, read replicas later

**Multi-tenant:**
- Current: one DB, `workspace_id` filters (no RLS)
- Limit: app-bug = cross-tenant leak
- Scaling path: keep isolation tests on every new router; consider RLS later

**Gapless counters:**
- Current: one locked row per workspace/year for INV and SPO
- Limit: serialize creates per tenant/year
- Scaling path: acceptable for SME volume; do not switch to UUID invoice numbers (UAE/FTA expectation of sequences)

## Dependencies at Risk

**python-jose 3.3.0:**
- Risk: unmaintained JWT lib
- Impact: auth tokens
- Migration plan: PyJWT + cryptography, keep HS256 claims (`sub`, `workspace_id`, `type`, `exp`)

**FastAPI 0.109 / Starlette 0.36 / SQLModel 0.0.14:**
- Risk: behind current releases
- Impact: security patches, Pydantic compatibility
- Migration plan: staged upgrade with existing pytest suite

**React 19 vs plan React 18:**
- Risk: docs/plan mismatch; ecosystem churn
- Impact: low if staying on 19
- Migration plan: update MASTER_PLAN lock to React 19

**redis package unused:**
- Risk: dependency without benefit
- Impact: audit surface
- Migration plan: wire slowapi Redis backend or drop until queues exist

## Missing Critical Features

**UAE electrical B2B sales cycle:**
- Problem: No Enquiry, Quotation (with revisions), Customer LPO/CPO, Delivery Note/DO, Credit Note, Debit Note, BOQ, Arabic/English docs, Emirate/address structure
- Blocks: Quote-to-cash for contractors; FTA-ready tax invoices with buyer TRN on PDF (client `tax_id` exists but PDF bill-to omits TRN — `frontend/src/components/pdf/InvoicePDF.tsx` shows name/email only)
- Spec: `architecture/domain-model.md`, `.agents/MASTER_PLAN_V3.md` Waves 7–11, 23–25

**Email / WhatsApp send:**
- Problem: Send endpoints are state flags
- Blocks: Actually delivering invoices/SPOs to customers/suppliers

**Payment gateway (Razorpay or UAE acquirer):**
- Problem: No integration; CREDIT_CARD is a manual method enum
- Blocks: Automated card collection (may be out of scope for cheque/PDC-heavy electrical trade)

**VAT compliance pack:**
- Problem: Workspace `default_tax_rate` default 5.00; no FTA VAT return, no per-line VAT ID, no reverse charge, no designated zone
- Blocks: Wave 12/27 VAT report in plans

**i18n / RTL:**
- Problem: English-only UI (`frontend/src/components/Layout.tsx` labels)
- Blocks: Arabic invoices and operator UI

**Inventory completeness:**
- Problem: No reservations, transfers, stock count, negative-stock policy beyond adjust endpoint
- Blocks: Sell-from-stock + customer-driven procurement scenarios in V3 Section 2

**RFQ engine:**
- Problem: Models for responses/awards exist (`backend/app/models/rfq.py`); API is create/list RFQ only (`backend/app/routers/rfq.py`)
- Blocks: Landed-cost comparison (architecture `rfq-architecture.md`)

**SPO amendments:**
- Problem: `SPOAmendment` tables in `backend/app/models/spo.py`; no router
- Blocks: Price/qty changes after send

**Production DevOps:**
- Problem: No frontend Docker, no CD, no TLS, no APM, CORS not prod-ready
- Blocks: Wave 29 go-live

**GSD planning files:**
- Problem: `.planning/STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md` absent before this map
- Blocks: `/gsd-plan-phase` context

## Test Coverage Gaps

**Invoice lifecycle:**
- What's not tested: send/void/edit-draft-only, overpayment 400, idempotent double-pay, OVERDUE
- Files: `backend/app/routers/invoices.py`, `payments.py`
- Risk: AR regressions
- Priority: High

**Product/supplier/inventory/PR/RFQ CRUD:**
- What's not tested: beyond product/supplier isolation GETs
- Files: corresponding routers
- Risk: silent 500s, missing workspace filters on new endpoints
- Priority: High for any new CRUD

**Frontend:**
- What's not tested: all pages
- Files: `frontend/src/`
- Risk: pagination bug, PDF TRN omission, auth refresh
- Priority: High for MVP UI

**Browser E2E:**
- What's not tested: login → invoice → payment → PDF download
- Priority: Medium (Playwright not in stack)

**RBAC / CORS / production secret:**
- Priority: Medium until multi-user workspaces

---

*Concerns audit: 2026-08-31*
