# Architecture

**Analysis Date:** 2026-08-31

## Pattern Overview

**Overall:** Monolithic async FastAPI backend with a service-layer for financial/procurement domains, plus a separate Vite/React SPA. Multi-tenant SaaS via `workspace_id` on entities and JWT claims.

**Key Characteristics:**
- Routers parse HTTP; services own state machines, numbering, matching, and money math
- PostgreSQL is source of truth; Alembic owns schema; Redis is declared but unused by app code
- Tenant isolation: every business query must filter `workspace_id` from the authenticated user (`backend/app/auth/dependencies.py` `get_current_workspace_id`)
- Two products in one repo: AR invoicing (mature) and procurement/inventory (partial ERP), targeting UAE electrical B2B per `.agents/MASTER_PLAN_V3.md`

## Layers

**HTTP / Routers:**
- Purpose: Auth, validation, pagination wrappers, status codes
- Location: `backend/app/routers/`, `backend/app/auth/router.py`
- Contains: FastAPI `APIRouter` handlers
- Depends on: schemas, services or direct SQLModel queries, auth dependencies
- Used by: `backend/app/main.py` `include_router`

**Service layer (partial):**
- Purpose: Invoice lifecycle, payments + idempotency, gapless INV/SPO numbers, GRN receiving, supplier-invoice 3-way match, SPO workflow, invoice audit events
- Location: `backend/app/services/`
- Contains: `InvoiceService`, `InvoiceNumberService`, `PaymentService`, `AuditService`, `SPOService`, `SPONumberService`, `GRNService`, `SupplierInvoiceService`
- Depends on: models + AsyncSession
- Used by: matching routers
- Not used by: products, suppliers, clients, procurement, RFQ, inventory, dashboard, workspaces — those routers query SQLModel directly

**Models:**
- Purpose: SQLModel table definitions, ENUMs, constraints
- Location: `backend/app/models/`
- Contains: workspace/user/client/invoice/payment + product/supplier/inventory/PR/RFQ/SPO/GRN/supplier invoice
- Depends on: SQLAlchemy column types (`Numeric(12,2)`, PostgreSQL `ENUM`, JSONB)
- Used by: services, routers, Alembic (`import app.models` in `backend/alembic/env.py`)

**Schemas:**
- Purpose: Pydantic request/response; `{success, data}` wrapper
- Location: `backend/app/schemas/`
- Contains: per-domain Create/Response models; `common.py` wrappers
- Depends on: Pydantic v2
- Used by: routers `response_model=`

**Auth:**
- Purpose: JWT issue/verify, password hash, current user/workspace
- Location: `backend/app/auth/`
- Depends on: `python-jose`, passlib, `User`/`Workspace` models
- Used by: all `/api/v1` routers except `/health`

**Frontend SPA:**
- Purpose: Operator UI for the same workspace
- Location: `frontend/src/`
- Contains: pages, axios API modules, AuthContext, CSS modules, Invoice PDF
- Depends on: backend JSON API
- Used by: browser users

**Architecture specs (non-runtime):**
- Purpose: Target ERP rules for planners
- Location: `architecture/*.md`, `.agents/MASTER_PLAN_V3.md`
- Larger than implemented code. Treat as intent, not as current API.

## Data Flow

**Auth + tenant bind:**

1. `POST /auth/register` creates `Workspace` + `User` (role `OWNER`) (`backend/app/auth/router.py`)
2. Access JWT payload includes `sub` (user id) and `workspace_id`
3. `get_current_user` loads `User` by `sub`; `get_current_workspace_id` returns `user.workspace_id`
4. Routers filter queries with that UUID — never trust body/query `workspace_id` (SPO previously did; now JWT-only in `backend/app/routers/spo.py`)

**Invoice create → send → pay:**

1. `POST /api/v1/invoices` (`backend/app/routers/invoices.py`) → `InvoiceService.create_invoice`
2. `InvoiceNumberService.generate_invoice_number` locks `invoice_counters` `FOR UPDATE` (`backend/app/services/invoice_number.py`) → `INV-YYYY-XXXX`
3. Line totals: `qty * unit_price * (1 + tax_rate/100)` as `Decimal` (`backend/app/services/invoice_service.py`)
4. `POST …/send` sets status `SENT` (no email)
5. `POST …/payments` requires `Idempotency-Key`; `PaymentService.record_payment` locks invoice row, rejects overpayment, stores key 48h (`backend/app/models/idempotency_key.py`)
6. Status cached from successful payments: `SENT` / `PARTIALLY_PAID` / `PAID`
7. Void: `POST …/void` → `CANCELLED`; DELETE is soft-delete on `DRAFT` only

**Procurement (partial):**

1. `POST /api/v1/procurement/requests` creates PR with count-based `PR-YYYY-NNNNNN` (no counter table, no `FOR UPDATE`) — `backend/app/routers/procurement.py`
2. `POST /api/v1/rfq/requests` same pattern for `RFQ-YYYY-NNNNNN` — `backend/app/routers/rfq.py`
3. `POST /api/v1/spos/` → `SPOService.create_draft` + gapless `SPO-YYYY-NNNNNN` (`backend/app/services/spo_number.py`)
4. Transitions: submit-approval → approve → send → acknowledge items → cancel
5. GRN: `POST /api/v1/grns` → receive → inspect/disposition → stock post (`backend/app/services/grn_service.py`)
6. Supplier invoice: create → submit-matching (3-way) → resolve-discrepancy → approve (`backend/app/services/supplier_invoice_service.py`)

**Frontend request cycle:**

1. `apiClient` axios (`frontend/src/api/client.ts`) attaches Bearer from `localStorage`
2. 401 triggers `/auth/refresh` then retry; failure dispatches `auth_unauthorized`
3. TanStack Query caches per page (`queryKey: ['invoices']`, etc.)
4. Toasts via `react-hot-toast`

**State Management:**
- Backend: PostgreSQL rows; invoice status is a cache of payment sums (`backend/app/services/invoice_service.py` docstring)
- Frontend: React local state + TanStack Query; auth user in `AuthContext`; no Redux/Zustand
- JWT not stored in httpOnly cookies — XSS-sensitive `localStorage`

## Key Abstractions

**Workspace tenant:**
- Purpose: isolation boundary
- Examples: `backend/app/models/workspace.py`
- Pattern: UUID FK `workspace_id` on almost every table; unique constraints are `(workspace_id, number)` for documents

**Gapless document numbers:**
- Purpose: legal/audit sequences
- Examples: `backend/app/models/invoice_counter.py`, `backend/app/models/spo_counter.py`
- Pattern: composite PK `(workspace_id, year)`, `SELECT FOR UPDATE`, increment in same transaction as insert
- Implemented for: Invoice, SPO
- Missing / unsafe count-then-format: PR (`backend/app/routers/procurement.py`), RFQ (`backend/app/routers/rfq.py`), GRN (`backend/app/services/grn_service.py` `_generate_grn_number`)

**Response wrapper:**
- Purpose: uniform client contract
- Examples: `backend/app/schemas/common.py` `SuccessResponse`, `PaginatedResponse`, `ErrorResponse`
- Pattern: `{"success": true, "data": …}` / `{"success": false, "error": {code, message}}`
- List invoices/clients/payments use `PaginatedResponse` with `pagination` meta. Many later routers return unpaginated `SuccessResponse[List[…]]`.

**Invoice state machine:**
- Purpose: AR lifecycle
- Examples: `InvoiceStatus` in `backend/app/models/invoice.py`; transitions in `InvoiceService`
- Pattern: DRAFT → SENT (send) / CANCELLED (void) / soft-delete; SENT → PARTIALLY_PAID / PAID via payments; CANCELLED terminal
- `OVERDUE` enum member exists; no scheduler/job sets it

**3-way match:**
- Purpose: AP invoice vs SPO vs GRN
- Examples: `MatchResult` in `backend/app/models/supplier_invoice.py`; `supplier_invoice_service.py`
- Pattern: qty/price/tax/supplier/currency/product/UOM checks; workspace `price_tolerance_percent`

**Inventory ledger:**
- Purpose: stock snapshot + immutable movements
- Examples: `InventoryLevel`, `InventoryTransaction` in `backend/app/models/inventory.py`
- Pattern: `available = on_hand - reserved - damaged`; adjustments `FOR UPDATE` (`backend/app/routers/inventory.py`); GRN posts on accept

## Entry Points

**FastAPI app:**
- Location: `backend/app/main.py`
- Triggers: Uvicorn/Gunicorn `app.main:app`
- Responsibilities: lifespan (logging + engine dispose), CORS, rate limiter, exception handlers, router mount, `GET /` status

**React app:**
- Location: `frontend/src/main.tsx` → `frontend/src/App.tsx`
- Triggers: Vite `npm run dev` / static `dist/`
- Responsibilities: QueryClient, AuthProvider, routes, Toaster

**Alembic:**
- Location: `backend/alembic/env.py`
- Triggers: `alembic upgrade head` (Compose API command and Dockerfile CMD)
- Responsibilities: apply SQLModel metadata migrations asynchronously

**Compose:**
- Location: `docker-compose.yml`
- Triggers: `docker compose up`
- Responsibilities: postgres + redis + api with bind-mount hot reload

## Error Handling

**Strategy:** HTTPException → wrapper JSON; validation 422 with `details`; unhandled Exception → 500 generic message.

**Patterns:**
- Router `HTTPException(status_code, detail=str)` — FastAPI handler wraps as `{success: false, error: {code: "HTTP_ERROR", message}}` (`backend/app/main.py`)
- Some payment errors pass `ErrorDetail.model_dump()` as `detail` (nested structure)
- Cross-tenant access: 404 not 403 (`backend/tests/test_multi_tenant_isolation.py` contract) to avoid existence leaks
- Overpayment: 400 (`PAYMENT_EXCEEDS_BALANCE` in `ErrorCode`)
- Invoice edit/delete only when `DRAFT`

## Cross-Cutting Concerns

**Logging:** JSON stdout + request id contextvar (`backend/app/logging.py`). Use `logger.info("msg", extra={...})`; never `print()`. `procurement.py` / `rfq.py` still `import time` mid-function for numbering.

**Validation:** Pydantic schemas on request bodies. Money: `Decimal` + `Numeric(12,2)` (qty sometimes `Numeric(12,4)` on SPO/GRN). Invoice due_date ≥ issue_date (`backend/app/schemas/invoices.py`).

**Authentication:** HTTP Bearer JWT. Health and `/` are public. Rate limit auth `RATE_LIMIT_AUTH` (default 5/minute) and payments `10/minute`. Tests disable limiter in `backend/tests/conftest.py`.

**Multi-tenancy:** JWT workspace, not a header. Soft deletes: `deleted_at` on Workspace, Client, Invoice, Product masters, Supplier. Payments have no `deleted_at` (immutable records; PDC status PUT exists — see CONCERNS).

**CORS:** Hardcoded localhost origins in `backend/app/main.py`. Production frontend origin not configurable via settings.

## Implemented vs Target Domains

| Domain | Runtime status |
|--------|----------------|
| Auth + Workspace | Working (settings partial) |
| Clients + AR Invoices + Payments | Working (PDF client-side; email stub) |
| Product master | Models complete; API list/create only |
| Supplier master | Models complete; API list/create root only |
| Inventory warehouse/bin/level/adjust | Working (no transfers/counts/reservations) |
| Procurement Request | List/create only; numbering unsafe |
| RFQ | List/create header/items only; no quotes/awards API |
| SPO | Lifecycle + gapless numbers; amendments unused |
| GRN | Lifecycle + stock post; numbering unsafe; purchase-return hook is `pass` |
| Supplier invoice + 3-way match | Working; no AP payment / aging |
| Enquiry, Quotation, Customer PO, Delivery Order, Credit/Debit notes | Spec only (`architecture/domain-model.md`) |
| WhatsApp, Email, OCR, FTA VAT report | Spec / stub fields only |

---

*Architecture analysis: 2026-08-31*
