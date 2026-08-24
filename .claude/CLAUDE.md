# InvoiceSaaS — Project Intelligence

> This file is the single source of truth for all AI agents working on this project.
> Read this FIRST before making any changes.

## Project Identity

- **Name**: InvoiceSaaS (rezorpay_pro)
- **Type**: Multi-tenant SaaS backend for invoice automation and cashflow intelligence
- **Stack**: FastAPI + SQLModel + PostgreSQL 16 + asyncpg + Alembic + Redis (planned)
- **Architecture**: Monolithic backend with service-layer abstraction, async-first
- **Python**: 3.11
- **Auth**: JWT (access + refresh tokens) via python-jose + passlib/bcrypt
- **Multi-tenancy**: Workspace-scoped via `workspace_id` on every entity

## Critical Rules (MUST FOLLOW)

### Database Rules
1. **NEVER use SQLite** for testing — PostgreSQL ENUM types, row locks, and async behavior REQUIRE real PostgreSQL
2. **NEVER modify schema without Alembic** — run `alembic revision --autogenerate -m "description"` then `alembic upgrade head`
3. **NEVER use `SQLModel.metadata.create_all` in production** — Alembic manages all schema changes
4. **All financial fields use `Decimal(12,2)`** — NEVER use float for money
5. **Invoice numbers are gapless** — `INV-YYYY-XXXX` format, enforced via `SELECT FOR UPDATE` row locks
6. **Payments are immutable** — never update or delete payment records (financial audit trail)
7. **Soft deletes only** — use `deleted_at` timestamp, never hard-delete business entities

### API Rules
1. **All responses follow the wrapper pattern**: `{"success": true/false, "data": ..., "error": ...}`
2. **All list endpoints use pagination**: `page`, `per_page`, with `PaginationMeta`
3. **All payment endpoints require `Idempotency-Key` header** — 48-hour TTL
4. **Invoice edits blocked unless status is `DRAFT`** — enforced at service layer
5. **Overpayments rejected** — `amount > balance_due` returns 400

### Code Quality & Tracking Rules
1. **MANDATORY REPORTING**: Every agent MUST document every single action, code edit, and implementation detail in a dedicated report file (e.g., `backend-execution-report.md`) within the `.agents/reports/` directory. No changes are to be made without tracking them in the report first.
2. **All imports at top of file** — no mid-file imports (E402)
3. **Format with `black`** — target Python 3.11
4. **Lint with `ruff`** — fix violations before committing
5. **Pre-commit hooks are installed** — they run automatically on `git commit`
6. **Structured JSON logging only** — use `logger.info("msg", extra={...})`, never `print()`
7. **No sensitive data in logs** — redact JWT tokens, passwords, user objects

### State Machine Rules
```
DRAFT → SENT (via /send endpoint)
DRAFT → CANCELLED (via /void endpoint)
DRAFT → [soft-deleted] (via DELETE)
SENT → PARTIALLY_PAID (automatic on partial payment)
SENT → PAID (automatic on full payment)
SENT → CANCELLED (via /void)
PARTIALLY_PAID → PAID (automatic on final payment)
PARTIALLY_PAID → CANCELLED (via /void)
PAID → CANCELLED (via /void)
CANCELLED → [terminal, no transitions]
```

## Architecture Patterns

### Service Layer
- **Routers** handle HTTP concerns only (parse request, return response)
- **Services** contain all business logic (validation, state transitions, calculations)
- **Models** are pure data definitions (no business logic)
- **Schemas** handle API validation (Pydantic models)

### Concurrency Safety
- Invoice number generation uses `SELECT FOR UPDATE` row locks
- Payment recording uses row-level locks on the invoice
- Idempotency keys prevent duplicate payment processing

### Multi-Tenancy
- Every query MUST filter by `workspace_id`
- Cross-workspace data access is a security violation
- `workspace_id` comes from the authenticated JWT token

## Directory Structure
```
rezorpay_pro/
├── .github/workflows/ci.yml    # GitHub Actions (lint → test → security)
├── .pre-commit-config.yaml     # black + ruff + hygiene hooks
├── .gitignore
├── docker-compose.yml          # api + postgres + redis
├── .claude/                    # Claude Code configuration
│   ├── CLAUDE.md              # THIS FILE
│   ├── settings.json          # Local settings
│   └── commands/              # Custom slash commands
├── .agents/                    # Multi-agent instructions
│   ├── backend-agent.md       # Backend development rules
│   ├── frontend-agent.md      # Frontend development rules
│   └── database-agent.md      # Database & migration rules
└── backend/
    ├── Dockerfile
    ├── .env / .env.example
    ├── requirements.txt
    ├── alembic.ini
    ├── alembic/                # Migration scripts
    ├── app/
    │   ├── main.py            # FastAPI entrypoint
    │   ├── config.py          # Pydantic Settings
    │   ├── database.py        # Async engine + sessions
    │   ├── logging.py         # Structured JSON logging
    │   ├── auth/              # JWT authentication
    │   ├── models/            # SQLModel ORM entities
    │   ├── schemas/           # Pydantic request/response
    │   ├── routers/           # API endpoint handlers
    │   └── services/          # Business logic layer
    └── tests/                 # Test suites
```

## Known Issues

*All issues from the original Aug 2026 audit were resolved during the
`stabilization/wave-sync` effort (P0–P4). See
`.agents/reports/stabilization-execution-report.md` for the full trail.*

Resolved:
1. ~~`InvoiceStatus.VOIDED` referenced but not defined~~ — no such reference
   exists; the void path uses `InvoiceEventType.INVOICE_VOIDED` and the enum's
   `CANCELLED` state. Verified (P3/P4).
2. ~~Audit metadata silently dropped (`context=` vs `metadata_log=`)~~ —
   `AuditService.log_event` accepts `metadata=` and persists it as
   `InvoiceEvent.metadata_log` (`audit_service.py`). Verified (P4).
3. ~~CI pipeline broken (no server before integration tests)~~ — the live-server
   step was removed; CI runs in-process `TestClient` tests. `pytest.ini` header
   and test-DB name bugs fixed. Green (P3).
4. ~~`tax_id` in schema but not in Client model~~ — `Client.tax_id` exists
   (`models/client.py:24`) and matches the schema. Verified (P4).
5. ~~`Client.email` nullability mismatch~~ — model and schema both make `email`
   optional; migration `4ec511b03a6f_make_client_email_nullable` aligns the DB.
   Verified (P4).

ENUM case reconciliation: no model↔migration drift — `alembic check` reports
"No new upgrade operations detected" against a clean-room `upgrade head` (P3).
