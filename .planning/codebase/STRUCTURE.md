# Codebase Structure

**Analysis Date:** 2026-08-31

## Directory Layout

```
rezorpay_pro/
├── .agents/                    # Agent roster, MASTER_PLAN_V3, execution reports
├── .claude/                    # CLAUDE.md project rules
├── .github/workflows/          # ci.yml
├── .hermes/plans/              # Wave 3 product-master completion plan
├── .planning/codebase/         # GSD map (this folder)
├── architecture/               # Wave 0 ERP specs (target, not runtime)
├── backend/                    # FastAPI application
│   ├── alembic/                # Migrations + env.py
│   ├── app/                    # Runtime Python package
│   ├── tests/                  # pytest (in-process TestClient)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── alembic.ini
│   └── .env.example
├── frontend/                   # Vite + React + TypeScript SPA
│   ├── src/pages/              # Route screens
│   ├── src/api/                # Axios wrappers
│   ├── src/components/         # Layout, AuthGuard, Skeleton, pdf/
│   ├── src/contexts/           # AuthContext
│   └── src/types/              # api.ts, auth.ts
├── docker-compose.yml          # postgres + redis + api
├── .pre-commit-config.yaml
├── IDEA.md                     # One-line product note
└── .gitignore
```

## Directory Purposes

**backend/app/:**
- Purpose: Runtime API
- Contains: `main.py`, `config.py`, `database.py`, `logging.py`, `limiter.py`
- Key files: `backend/app/main.py`

**backend/app/auth/:**
- Purpose: JWT + password + dependencies
- Key files: `router.py`, `utils.py`, `dependencies.py`, `__init__.py`

**backend/app/models/:**
- Purpose: SQLModel tables
- Key files: `__init__.py` (Alembic discovery), `workspace.py`, `invoice.py`, `payment.py`, `product.py`, `supplier.py`, `inventory.py`, `procurement.py`, `rfq.py`, `spo.py`, `grn.py`, `supplier_invoice.py`

**backend/app/schemas/:**
- Purpose: Pydantic API contracts
- Key files: `common.py` (wrappers), domain files matching routers

**backend/app/routers/:**
- Purpose: HTTP endpoints
- Key files: `invoices.py`, `payments.py`, `clients.py`, `products.py`, `suppliers.py`, `inventory.py`, `procurement.py`, `rfq.py`, `spo.py`, `grn.py`, `supplier_invoices.py`, `workspaces.py`, `dashboard.py`, `health.py`
- `__init__.py` exports only health/clients/invoices/payments; remaining routers imported in `main.py` directly

**backend/app/services/:**
- Purpose: Business logic for invoice/payment/SPO/GRN/AP match
- Key files: listed in `backend/app/services/__init__.py`

**backend/alembic/versions/:**
- Purpose: Linear migration chain (initial `001_initial_schema.py` through `b7e2f4a9c1d3_add_spo_counters.py` plus GRN/supplier-invoice revisions)
- Generated: Yes (autogenerate + hand edits)
- Committed: Yes

**backend/tests/:**
- Purpose: Integration tests against real PostgreSQL
- Key files: `conftest.py`, `test_auth.py`, `test_multi_tenant_isolation.py`, `test_concurrent_numbering.py`, `test_spo.py`, `test_grn.py`, `test_e2e_spo.py`, `test_e2e_grn.py`, `test_e2e_3way_match.py`

**frontend/src/:**
- Purpose: Operator UI
- Contains: pages for dashboard, clients, invoices, products, suppliers, inventory, procurement, RFQ, SPO, GRN, supplier invoices, settings, login/register

**architecture/:**
- Purpose: Domain rules for future waves
- Key files: `domain-model.md`, `business-rules.md`, `state-machines.md`, `api-contracts.md`, `entity-relationship.md`, plus per-module architecture docs
- Generated: No (hand-written specs)
- Committed: Yes

**.agents/:**
- Purpose: Multi-agent instructions and wave reports
- Key files: `AGENTS.md`, `backend-agent.md`, `frontend-agent.md`, `database-agent.md`, `MASTER_PLAN_V3.md`, `reports/`

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI app
- `frontend/src/main.tsx`: React mount
- `frontend/src/App.tsx`: routes
- `backend/alembic/env.py`: migrations

**Configuration:**
- `backend/app/config.py`: Settings
- `backend/.env.example`: backend env names
- `frontend/.env.example`: `VITE_API_URL`
- `docker-compose.yml`: local stack
- `.github/workflows/ci.yml`: CI
- `.claude/CLAUDE.md`: project rules (must follow)
- `.pre-commit-config.yaml`: black + ruff

**Core Logic:**
- `backend/app/services/invoice_service.py`
- `backend/app/services/payment_service.py`
- `backend/app/services/invoice_number.py`
- `backend/app/services/spo_service.py`
- `backend/app/services/grn_service.py`
- `backend/app/services/supplier_invoice_service.py`

**Testing:**
- `backend/tests/`
- Leftover live-server scripts (not in `testpaths`): `backend/test_e2e.py`, `backend/test_step2_api.py`, `backend/test_step2_production.py`

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` matching entity (`invoice_service.py`, `supplier_invoices.py`)
- React pages: `PascalCase.tsx` (`Invoices.tsx`, `SPODetail.tsx`)
- CSS: `Component.module.css` colocated
- API clients: `kebab-or-plural.ts` (`supplier-invoices.ts`, `invoices.ts`)
- Alembic: `{rev}_{slug}.py`

**Directories:**
- Plural domain folders under `app/`: `models/`, `routers/`, `schemas/`, `services/`
- Frontend: `pages/`, `components/`, `api/`, `contexts/`, `types/`

**Python symbols:**
- Classes: PascalCase (`InvoiceService`, `PaymentMethod`)
- Functions: snake_case (`get_current_workspace_id`)
- ENUMs: UPPER_SNAKE members (`DRAFT`, `BANK_TRANSFER`)

**TypeScript symbols:**
- Components: PascalCase exported functions
- API functions: camelCase (`getInvoices`, `recordPayment`)

## Where to Add New Code

**New AR/API feature (invoice-like):**
- Model: `backend/app/models/{entity}.py` + export in `backend/app/models/__init__.py`
- Migration: `cd backend && alembic revision --autogenerate -m "description"` then `alembic upgrade head`
- Schema: `backend/app/schemas/{entity}.py`
- Service: `backend/app/services/{entity}_service.py` if state machine, numbering, or money
- Router: `backend/app/routers/{entity}.py` with `prefix="/…"`, mount in `backend/app/main.py` under `/api/v1`
- Tests: `backend/tests/test_{entity}.py` using existing TestClient + Postgres `_test` harness
- Report: append `.agents/reports/backend-execution-report.md` and database report if schema changed

**New frontend page:**
- Page: `frontend/src/pages/{Name}.tsx` + CSS module if needed
- API: `frontend/src/api/{name}.ts` using `apiClient` and `SuccessResponse<T>`
- Route: `frontend/src/App.tsx` inside `AuthGuard`/`Layout`
- Nav: `frontend/src/components/Layout.tsx` `navGroups`
- Tests: none exist — if adding, colocate `*.test.tsx` or add Playwright under `frontend/` (not established)

**New master-data CRUD (products/suppliers style):**
- Prefer extending existing router (`backend/app/routers/products.py`) with GET-by-id, PUT, DELETE, pagination
- Do not add a second service unless logic exceeds simple SQLModel CRUD

**Utilities:**
- Auth helpers: `backend/app/auth/`
- Shared API types: `frontend/src/types/api.ts`
- Shared response wrappers: `backend/app/schemas/common.py` — reuse; do not invent a new envelope

**UAE sales documents (quotation, LPO/CPO, delivery note, credit note):**
- No folders exist. Follow Database Agent → model + Alembic, then router/service/schema, then `frontend/src/pages/` + `frontend/src/api/`
- Specs live in `architecture/domain-model.md` (Quotation, CustomerPurchaseOrder, DeliveryOrder, CreditNote)

## Special Directories

**.agents/reports/:**
- Purpose: mandatory append-only execution logs
- Generated: No
- Committed: Yes

**.claude-flow/:**
- Purpose: plugin stats (`backend/.claude-flow/`, `frontend/.claude-flow/`)
- Generated: Yes
- Committed: appears modified in git status; treat as tool noise unless asked

**frontend/dist/:**
- Purpose: Vite build output
- Generated: Yes
- Committed: No (gitignore `dist/`)

**.venv/ / node_modules/:**
- Generated: Yes
- Committed: No

**architecture/:**
- Purpose: target ERP specification
- Generated: No
- Committed: Yes
- Incomplete vs Wave 0 report: `api-contracts.md` and `entity-relationship.md` exist on disk even though `wave0-execution-report.md` still lists them PENDING

## Router prefix cheat sheet

Mount all of these from `backend/app/main.py` with `/api/v1` except auth and health:

| Prefix | File |
|--------|------|
| `/auth` | `backend/app/auth/router.py` |
| `/health` | `backend/app/routers/health.py` |
| `/api/v1/clients` | `backend/app/routers/clients.py` |
| `/api/v1/invoices` | `backend/app/routers/invoices.py` |
| `/api/v1` payments under invoices | `backend/app/routers/payments.py` (no extra prefix) |
| `/api/v1/dashboard` | `backend/app/routers/dashboard.py` |
| `/api/v1/workspaces` | `backend/app/routers/workspaces.py` |
| `/api/v1/products` | `backend/app/routers/products.py` |
| `/api/v1/suppliers` | `backend/app/routers/suppliers.py` |
| `/api/v1/inventory` | `backend/app/routers/inventory.py` |
| `/api/v1/procurement` | `backend/app/routers/procurement.py` |
| `/api/v1/rfq` | `backend/app/routers/rfq.py` |
| `/api/v1/spos` | `backend/app/routers/spo.py` |
| `/api/v1/grns` | `backend/app/routers/grn.py` (router prefix `""`) |
| `/api/v1/supplier-invoices` | `backend/app/routers/supplier_invoices.py` |

---

*Structure analysis: 2026-08-31*
