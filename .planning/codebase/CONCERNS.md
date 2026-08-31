# Codebase Concerns

**Analysis Date:** 2026-08-31

## Tech Debt

**Product master API incomplete:**
- Issue: Models include identifiers, UOM conversions, and prices (`backend/app/models/product.py`) but `backend/app/routers/products.py` only lists/creates Category, Brand, UOM, Product. No GET-by-id, PUT, DELETE, search, pagination, or nested resources. Frontend "Add Product" is `alert('Add Product UI coming soon')` (`frontend/src/pages/Products.tsx`). Hermes plan `.hermes/plans/2026-08-27_153000-wave3-product-master.md` still describes this gap.
- Files: `backend/app/routers/products.py`, `backend/app/schemas/products.py`, `frontend/src/pages/Products.tsx`, `frontend/src/api/products.ts`
- Impact: Electrical catalog (SKU, conversions, customer prices) cannot be maintained in production UI; invoices still use free-text lines with no `product_id` (`backend/app/models/invoice_item.py`).
- Fix approach: Complete schemas + nested routes as in the Hermes plan; add `test_products.py`; replace alert with create/edit modals; link invoice items to products when sales docs need SKU/VAT.

**Supplier child tables unused:**
- Issue: `SupplierContact`, `SupplierBankAccount`, `SupplierDocument`, `SupplierProduct` exist (`backend/app/models/supplier.py`) with no router endpoints. `backend/app/routers/suppliers.py` is list/create on the root row only.
- Files: `backend/app/routers/suppliers.py`, `frontend/src/pages/Suppliers.tsx`
- Impact: Cannot store IBAN, trade license, VAT certificate, or supplier SKU mapping — required for UAE vendor onboarding.
- Fix approach: Nested CRUD under `/suppliers/{id}/…` with workspace checks; UI tabs.

**Unsafe document numbering (PR, RFQ, GRN):**
- Issue: `len(select all)+1` without `FOR UPDATE` (`backend/app/routers/procurement.py`, `backend/app/routers/rfq.py`, `backend/app/services/grn_service.py` `_generate_grn_number`). Concurrent creates collide on unique `(workspace_id, number)`.
- Files: those three; contrast working `backend/app/services/invoice_number.py` and `spo_number.py`
- Impact: Duplicate-key 500s under concurrent warehouse receiving or buyer PR creation.
- Fix approach: Counter tables like `InvoiceCounter`/`SPOCounter`; never load all rows to count.

**Payment PUT vs immutability rule:**
- Issue: `.claude/CLAUDE.md` says payments are immutable. `PUT /api/v1/invoices/{id}/payments/{id}` updates `status` and `pdc_status` (`backend/app/routers/payments.py`). V3 test plan requires 405 on PUT.
- Files: `backend/app/routers/payments.py`, `backend/app/schemas/payments.py` `PaymentUpdate`
- Impact: Amount is not editable (good) but status mutation can change AR without a new event type for PDC clear/bounce.
- Fix approach: Keep PDC as an explicit lifecycle endpoint that writes an audit event and recalculates invoice status; do not allow arbitrary status writes; add tests.

**Service layer inconsistency:**
- Issue: Clients/products/suppliers/PR/RFQ/inventory/dashboard/workspaces skip services and query in routers. Mid-file `import time` in PR/RFQ routers.
- Files: `backend/app/routers/procurement.py`, `rfq.py`, `products.py`, `suppliers.py`
- Impact: Duplicated numbering bugs; harder to test; E402 violations.
- Fix approach: Extract numbering + create into services; hoist imports.

**List pagination incomplete:**
- Issue: CLAUDE.md requires pagination on all lists. Only clients, invoices, payments paginate. Products/suppliers/inventory/PR/RFQ/SPO/GRN/AP return full arrays.
- Files: `backend/app/routers/products.py` and siblings; frontend has no `pagination` types (`frontend/src/types/api.ts`)
- Impact: Unbounded payloads as catalogs grow.
- Fix approach: `PaginatedResponse` + `page`/`per_page` on every list; update axios wrappers.

**Frontend invoice list contract:**
- Issue: `getInvoices` types `SuccessResponse<Invoice[]>` (`frontend/src/api/invoices.ts`) but backend `GET /invoices` returns `PaginatedResponse` with `data` + `pagination`. It works only because `data` is still the array. No page controls in `frontend/src/pages/Invoices.tsx`.
- Files: `frontend/src/api/invoices.ts`, `backend/app/routers/invoices.py`
- Impact: Silent truncation at `per_page` default 20.
- Fix approach: Type pagination; add page UI; same for clients.

**Tests use `create_all`, not Alembic:**
- Issue: Fixtures `SQLModel.metadata.drop_all` / `create_all` (`backend/tests/test_auth.py` et al.). CI separately runs `alembic upgrade head` on empty DB then pytest which drops and recreates from models.
- Files: every `setup_database` fixture
- Impact: Tests can pass with model-only schema while production Alembic differs (ENUM names, server defaults).
- Fix approach: Session fixture that migrates once; stop `create_all` in tests.

**Wave numbering mismatch:**
- Issue: `.agents/MASTER_PLAN_V3.md` Wave 7 = Enquiry, Wave 8 = Quotation. Implemented migrations named Wave 7 inventory, Wave 8 PR, Wave 9 RFQ, Wave 10 SPO, Wave 11 GRN. `.agents/reports/README.md` still shows Wave 0 IN PROGRESS / later waves PENDING.
- Files: `.agents/MASTER_PLAN_V3.md`, `backend/alembic/versions/*`, `.agents/reports/README.md`
- Impact: Planners implement the wrong next wave.
- Fix approach: Publish a single current-state roadmap (GSD `ROADMAP.md`) mapping implemented modules vs V3 wave ids. `.planning/STATE.md` / `ROADMAP.md` / `REQUIREMENTS.md` are missing.

**Invoice items are free-text:**
- Issue: `InvoiceItem` has description/qty/price/tax only (`backend/app/models/invoice_item.py`). No `product_id`, UOM, SKU, or electrical spec snapshot.
- Impact: Cannot reprint from catalog; no BOQ/LPO line traceability.
- Fix approach: Optional `product_id` + snapshot fields; tax default from product or workspace `default_tax_rate`.

**Credit control stored, not enforced:**
- Issue: Workspace `credit_limit_default`, `credit_warning_days`, `credit_hold_days`, `block_po_on_hold`, `block_do_on_hold` (`backend/app/models/workspace.py`) have no engine. Client has no per-customer limit or aging.
- Files: `backend/app/models/workspace.py`, `backend/app/models/client.py`, `frontend/src/pages/Settings.tsx`
- Impact: Settings UI implies blocking that does not happen. DO/CPO modules do not exist to block.
- Fix approach: Implement aging + HOLD after CPO/DO exist; until then do not expose block flags as if live.

**GRN purchase-return stub:**
- Issue: `pass` after rejected qty (`backend/app/services/grn_service.py` around auto-PurchaseReturn).
- Impact: Rejected goods do not create PRN/debit note.
- Fix approach: Implement PurchaseReturn when Wave 25 entities exist; until then persist a discrepancy record.

**Duplicate GRN migrations:**
- Issue: `2a98d90a2f79_add_wave_11_grn.py` and `5f24e4eb1428_add_grn_models.py` both add GRN-related schema.
- Files: `backend/alembic/versions/`
- Impact: Fragile history; `alembic check` currently clean — do not squash without a freeze.
- Fix approach: Leave chain; document head revision in ROADMAP.

**Workspace schema vs API:**
- Issue: Model has `over_receipt_tolerance_percent`, `spo_amendment_approval_threshold` (`backend/app/models/workspace.py`) omitted from `WorkspaceResponse` (`backend/app/schemas/workspaces.py`).
- Impact: Operators cannot configure SPO/GRN tolerances from Settings.
- Fix approach: Add fields to schema + Settings form.

**Leftover scripts:**
- Issue: `backend/test_e2e.py`, `test_step2_api.py`, `test_step2_production.py` outside `tests/`.
- Impact: Confusion; accidental `pytest` from wrong directory.
- Fix approach: Delete or move to `scripts/` gitignored.

## Known Bugs

**Invoice OVERDUE never computed:**
- Symptoms: Status enum includes `OVERDUE` (`backend/app/models/invoice.py`) but no job/query sets it when `due_date < today` and balance > 0.
- Files: `backend/app/models/invoice.py`, `backend/app/services/invoice_service.py`
- Trigger: Aging invoices stay `SENT` / `PARTIALLY_PAID`
- Workaround: Filter due dates in UI (not implemented)

**Health ready mid-file import:**
- Symptoms: E402 in `backend/app/routers/health.py` (`from fastapi import HTTPException` inside except)
- Files: `backend/app/routers/health.py`
- Trigger: ruff on that file if CI expands to all routers (CI currently `ruff check app/` — this is a violation)
- Workaround: Hoist import

**Dashboard outstanding loads all invoices:**
- Symptoms: `get_dashboard_stats` selectinloads every non-cancelled invoice to sum `balance_due` in Python (`backend/app/routers/dashboard.py`)
- Files: `backend/app/routers/dashboard.py`
- Trigger: Large AR books
- Workaround: SQL aggregate of totals minus successful payments

**Register slug races:**
- Symptoms: Slug uniqueness loop without lock (`backend/app/auth/router.py`)
- Trigger: Parallel registers with same workspace name
- Workaround: UniqueViolation retry

## Security Considerations

**JWT secret defaults:**
- Risk: `SECRET_KEY` default `"change-me-in-production"` (`backend/app/config.py`)
- Files: `backend/app/config.py`, `backend/.env.example`
- Current mitigation: example file warns to change; no startup check refusing default in `ENVIRONMENT=production`
- Recommendations: Fail boot if production and secret is default/short; rotate; consider RS256 later

**Tokens in localStorage:**
- Risk: XSS can steal access+refresh (`frontend/src/contexts/AuthContext.tsx`)
- Files: `frontend/src/api/client.ts`
- Current mitigation: none (no CSP documented)
- Recommendations: httpOnly cookies + CSRF, or strict CSP when hosting

**CORS localhost-only:**
- Risk: Production SPA origin rejected; temptation to `allow_origins=["*"]`
- Files: `backend/app/main.py`
- Current mitigation: explicit localhost list
- Recommendations: `CORS_ORIGINS` env list

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

**PR/RFQ numbering full-table load:**
- Problem: `select(ProcurementRequest).where(workspace)` then `len(all())`
- Files: `backend/app/routers/procurement.py`, `rfq.py`
- Cause: Count via load
- Improvement path: `func.count` or counter row

**GRN number same pattern:**
- Files: `backend/app/services/grn_service.py`
- Improvement path: `GRNCounter` + `FOR UPDATE`

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
