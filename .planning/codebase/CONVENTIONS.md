# Coding Conventions

**Analysis Date:** 2026-08-31

## Naming Patterns

**Files:**
- Backend: `snake_case.py` (`invoice_service.py`, `supplier_invoices.py`)
- Frontend pages/components: `PascalCase.tsx` (`AuthGuard.tsx`, `GRNDetail.tsx`)
- Frontend API modules: lowercase/kebab (`supplier-invoices.ts`, `client.ts`)
- CSS: `{Component}.module.css` next to the TSX file
- Tests: `test_{area}.py` under `backend/tests/`
- Migrations: `{revision}_{description}.py` in `backend/alembic/versions/`

**Functions:**
- Python: `snake_case` (`get_current_workspace_id`, `record_payment`)
- TypeScript: `camelCase` (`getInvoices`, `recordPayment`)
- FastAPI handlers: `snake_case` verb + resource (`list_invoices`, `create_payment`)

**Variables:**
- Python: `snake_case`; money as `Decimal` never `float`
- TypeScript: `camelCase`; API IDs are UUID strings
- Env vars: `UPPER_SNAKE` (`DATABASE_URL`, `SECRET_KEY`)

**Types:**
- SQLModel tables: PascalCase singular (`Invoice`, `GoodsReceiptNote`)
- Pydantic: `{Entity}Create` / `{Entity}Update` / `{Entity}Response`
- Enums: `class Foo(str, Enum)` with `UPPER_SNAKE` values matching PostgreSQL ENUM labels
- Frontend interfaces: PascalCase (`Invoice`, `SPOItem`)

## Code Style

**Formatting:**
- Black, Python 3.11 (`--target-version py311` in `.pre-commit-config.yaml`)
- No project `pyproject.toml` line-length override — Black default 88
- Frontend: no Prettier config detected; Oxlint via `npm run lint`

**Linting:**
- Ruff 0.2.2 on `backend/app/` in CI (`.github/workflows/ci.yml`)
- Mandatory: all imports at top of file (E402) — `.claude/CLAUDE.md`
- Exceptions still present: mid-function `import time` in `backend/app/routers/procurement.py` and `backend/app/routers/rfq.py`; mid-handler `from fastapi import HTTPException` in `backend/app/routers/health.py`
- Do not add mid-file imports in new code

## Import Organization

**Order (Python):**
1. stdlib (`uuid`, `datetime`, `decimal`, `enum`, `typing`)
2. third-party (`fastapi`, `sqlalchemy`, `sqlmodel`, `pydantic`)
3. `app.*` absolute imports (`from app.models.invoice import Invoice`)
4. `TYPE_CHECKING` blocks for relationship type hints to avoid cycles (`backend/app/models/invoice.py`)

**Path Aliases:**
- Backend: package `app` (run from `backend/` with `PYTHONPATH` implicit via uvicorn)
- Frontend: relative imports only (`../api/client`) — no `@/` alias in `frontend/vite.config.ts` or `tsconfig`

**Do not** use `from app.routers import *` in new modules. `backend/app/routers/__init__.py` is a partial barrel.

## Error Handling

**Patterns:**
- Raise `HTTPException` from routers; let `http_exception_handler` wrap `{success: false, error}`
- Business rules that need machine codes: pass `ErrorDetail` (`backend/app/schemas/common.py` `ErrorCode`)
- Cross-tenant: return **404** with `"… not found"`, not 403 (`backend/app/services/spo_service.py` scoped get; isolation tests)
- Validation: rely on Pydantic 422 handler
- Services raise `HTTPException` today (SPO/GRN/supplier invoice). Keep that pattern unless introducing a shared domain-error type — do not mix bare `Exception` for expected 400s
- Never leak stack traces in JSON (global handler already generic)

## Logging

**Framework:** stdlib `logging` + `JSONFormatter` (`backend/app/logging.py`)

**Patterns:**
- `logger = logging.getLogger(__name__)` or named loggers
- `logger.info("msg", extra={...})` — never `print()`
- Redact tokens, passwords, user objects (`.claude/CLAUDE.md`)
- Request id is in contextvar `request_id_ctx`; do not pass it manually unless adding extra fields
- Frontend: `react-hot-toast` for user errors; axios interceptor already toasts API `error.message`

## Comments

**When to Comment:**
- Financial invariants and lock reasons (`FOR UPDATE`) — see `backend/app/services/invoice_number.py`
- State-machine rules at service module docstring
- Do not narrate what the next line does
- Architecture docs in `architecture/` are specs, not code comments

**JSDoc/TSDoc:**
- Sparse. Frontend types live in `frontend/src/api/*.ts` interfaces. Add JSDoc only for non-obvious contracts (idempotency headers).

## Function Design

**Size:**
- Routers: HTTP only — parse, call service or query, return wrapper
- Services: one class per aggregate with `@staticmethod` / `@classmethod` (existing style in `InvoiceService`, `PaymentService`, `GRNService`)
- Keep money math in services, not routers

**Parameters:**
- Session first: `session: AsyncSession`
- Then `workspace_id: uuid.UUID` (always from JWT, never from client)
- Then resource ids and payload
- Prefer `Decimal` for amounts; coerce with `Decimal(str(value))` if input is not Decimal

**Return Values:**
- Services return ORM instances; routers wrap with `SuccessResponse(data=Schema.model_validate(obj))`
- List endpoints that must paginate: `PaginatedResponse` + `PaginationMeta` (`page`, `per_page`) — required by `.claude/CLAUDE.md` for list endpoints. New list APIs must paginate even if older product/supplier lists do not.

## Module Design

**Exports:**
- Models: add to `backend/app/models/__init__.py` `__all__` so Alembic and tests `from app.models import *` see the table
- Services: add to `backend/app/services/__init__.py` when introducing a new service
- Frontend: named exports for pages/hooks; default export only `App` (`frontend/src/App.tsx`)

**Barrel Files:**
- `app.models.__init__` — required for metadata
- `app.routers.__init__` — incomplete; mount new routers in `main.py` explicitly (current pattern for products through supplier invoices)

## API Contract Rules (mandatory)

1. Success body: `{"success": true, "data": ...}`
2. Error body: `{"success": false, "error": {"code", "message"}}`
3. Payment writes: require `Idempotency-Key` header (48h TTL)
4. Invoice mutations: only `DRAFT` for PUT/DELETE
5. Overpayment: reject when `amount > balance_due`
6. Money: `Decimal(12,2)` columns; never float in Python
7. Soft delete business entities via `deleted_at`
8. Payments: do not add DELETE; treat records as audit trail (PDC lifecycle currently uses PUT — do not extend PUT to amount/date edits)

## Frontend Conventions

- Wrap authenticated routes in `AuthGuard` + `Layout` (`frontend/src/App.tsx`)
- Call backend with `apiClient` from `frontend/src/api/client.ts` so tokens and toasts stay consistent
- Use TanStack Query `queryKey` arrays (`['products']`, `['dashboard_stats']`)
- Forms: react-hook-form + zod (`frontend/src/pages/Settings.tsx` pattern)
- Display money as `AED {n.toFixed(2)}` (`frontend/src/pages/Invoices.tsx`)
- Empty/loading: `Skeleton` component (`frontend/src/components/Skeleton.tsx`)
- Do not introduce a CSS-in-JS library; Vanilla CSS modules match `.agents/frontend-agent.md` and existing pages
- Invoice PDF: extend `frontend/src/components/pdf/InvoicePDF.tsx`; include workspace TRN

## Database Conventions

- Never SQLite for tests (`.claude/CLAUDE.md`) — ignore the sqlite branch in `backend/app/database.py` when adding code
- Never `SQLModel.metadata.create_all` in production; tests currently use `create_all` in fixtures (do not copy that into app startup)
- Unique document numbers: `UniqueConstraint("workspace_id", "{number}")`
- Gapless sequences: counter table + `with_for_update()` like `InvoiceNumberService` — do not copy PR/RFQ/GRN `len(all())+1` numbering
- ENUMs: Python `str, Enum` + SQLAlchemy `Enum`; keep labels uppercase to match migrations

## Agent / process conventions

- Read `.claude/CLAUDE.md` before edits
- Schema change: Database Agent model + Alembic, then Backend Agent router/service
- Append `.agents/reports/{role}-execution-report.md` for implementation work
- Do not invent business rules — flag in the report (`.agents/MASTER_PLAN_V3.md` governance)

---

*Convention analysis: 2026-08-31*
