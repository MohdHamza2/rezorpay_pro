# Backend Agent Instructions

> You are the **Backend Agent** responsible for all FastAPI application code, business logic, and API development.

## Your Scope

You own these directories:
- `backend/app/main.py` — Application entrypoint and middleware
- `backend/app/config.py` — Configuration management
- `backend/app/database.py` — Database connection setup
- `backend/app/logging.py` — Structured logging
- `backend/app/auth/` — Authentication (JWT, password hashing, dependencies)
- `backend/app/routers/` — API endpoint handlers
- `backend/app/services/` — Business logic layer
- `backend/app/schemas/` — Pydantic request/response validation
- `backend/requirements.txt` — Python dependencies
- `backend/Dockerfile` — Container build

## Architecture Rules

### Layer Separation (STRICT)
```
Request → Router → Service → Model/DB → Response
```
- **Routers**: Parse HTTP requests, call services, format responses. NO business logic.
- **Services**: ALL business logic lives here. Validation, state transitions, calculations.
- **Models**: Pure data definitions. No business logic. SQLModel entities.
- **Schemas**: Pydantic models for API validation only.

### Response Format (ALL endpoints)
```json
{
  "success": true,
  "data": { ... },
  "pagination": { "total": 100, "page": 1, "per_page": 20, "pages": 5, "has_next": true, "has_prev": false }
}
```
Error format:
```json
{
  "success": false,
  "error": { "code": "ERROR_CODE", "message": "Human readable message" }
}
```

### Authentication
- JWT Bearer tokens via `Authorization: Bearer <token>`
- Access tokens expire in 30 minutes
- Refresh tokens expire in 7 days
- Every protected endpoint uses `get_current_user` and `get_current_workspace` dependencies
- ALWAYS filter by `workspace_id` — cross-tenant access is a security violation

### Financial Calculations
- ALL money uses `Decimal(12, 2)` — NEVER float
- `item.total_price = quantity × unit_price × (1 + tax_rate / 100)`
- `invoice.subtotal = Σ(quantity × unit_price)`
- `invoice.tax_amount = Σ(quantity × unit_price × tax_rate / 100)`
- `invoice.total_amount = subtotal + tax_amount`
- `balance_due = total_amount - Σ(payments WHERE status = SUCCESS)`

### State Machine
| From | To | Trigger | Validation |
|------|----|---------|------------|
| DRAFT | SENT | POST /send | Only from DRAFT |
| DRAFT | CANCELLED | POST /void | Requires reason |
| DRAFT | [deleted] | DELETE | Soft-delete only |
| SENT | PARTIALLY_PAID | Payment recorded | Automatic (0 < balance < total) |
| SENT | PAID | Payment recorded | Automatic (balance ≤ 0) |
| SENT/PARTIAL/PAID | CANCELLED | POST /void | Requires reason |
| CANCELLED | — | — | Terminal state, no transitions |

### Concurrency Safety
- Invoice numbering: `SELECT FOR UPDATE` on `InvoiceCounter`
- Payment recording: Row-level lock on `Invoice` via `with_for_update()`
- Idempotency: 48-hour TTL keys scoped to workspace

## Code Style
- Python 3.11 features allowed
- Format: `black --target-version py311`
- Lint: `ruff check`
- All imports at top of file (no E402)
- Docstrings for all public functions
- Type hints on all function signatures
- Structured logging: `logger.info("action", extra={"key": "value"})`
- Never `print()` — always `logger`

## Testing
- Integration tests: `test_step2_production.py` (requires running server)
- Unit tests: `tests/` directory using pytest
- Always test against real PostgreSQL — never SQLite

## Known Issues to Fix
1. `InvoiceStatus` enum has `CANCELLED` but service uses `VOIDED` — reconcile
2. `AuditService.log_event()` passes `context=` but model expects `metadata_log=`
3. Duplicate `Limiter` instances between `main.py` and `payments.py`
4. `auth_middleware` duplicates DB queries that `get_current_user` also performs
5. `CORS allow_origins=["*"]` with `allow_credentials=True` is invalid
