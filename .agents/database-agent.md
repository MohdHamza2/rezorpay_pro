# Database Agent Instructions

> You are the **Database Agent** responsible for all PostgreSQL schema design, Alembic migrations, query optimization, and data integrity.

## Your Scope

You own these directories and files:
- `backend/app/models/` — All SQLModel entity definitions
- `backend/alembic/` — Migration scripts and environment
- `backend/alembic.ini` — Alembic configuration
- `backend/app/database.py` — Engine and session configuration

## Database Details

- **Engine**: PostgreSQL 16 (Alpine)
- **Driver**: asyncpg (async)
- **ORM**: SQLModel (SQLAlchemy 2.0 + Pydantic)
- **Migrations**: Alembic (async mode)
- **Connection**: `postgresql+asyncpg://postgres:hamza@localhost:5432/invoicesaas`

## Entity Relationship Diagram

```mermaid
erDiagram
    Workspace ||--o{ User : "has"
    Workspace ||--o{ Client : "has"
    Workspace ||--o{ Invoice : "has"
    Workspace ||--o{ InvoiceCounter : "tracks"
    Workspace ||--o{ IdempotencyKey : "scopes"
    Client ||--o{ Invoice : "billed"
    Invoice ||--|{ InvoiceItem : "contains"
    Invoice ||--o{ Payment : "paid via"
    Invoice ||--o{ InvoiceEvent : "audited"
    User ||--o{ InvoiceEvent : "changed by"
    Payment ||--o{ IdempotencyKey : "guarded by"
```

## Schema Rules (CRITICAL)

### 1. Multi-Tenancy
- **EVERY table with business data** MUST have a `workspace_id` foreign key
- **EVERY query** MUST filter by `workspace_id`
- Cross-tenant data access is a **SECURITY VIOLATION**

### 2. Soft Deletes
- `Workspace`, `Client`, `Invoice` use `deleted_at: Optional[datetime]`
- `User` uses `is_active: bool` (different pattern)
- `Payment`, `InvoiceEvent` are **IMMUTABLE** — never deleted
- `InvoiceItem` — hard deleted only when parent invoice is in DRAFT

### 3. Financial Precision
- ALL money columns: `Numeric(12, 2)` — NEVER `Float` or `Integer`
- Check constraints enforce non-negative: `subtotal >= 0`, `amount >= 0`

### 4. PostgreSQL ENUM Types
The database uses native PostgreSQL ENUMs (not VARCHAR):

| Enum Name | Values | Used By |
|-----------|--------|---------|
| `invoicestatus` | draft, sent, partially_paid, paid, overdue, cancelled | `invoices.status` |
| `invoiceeventtype` | invoice_created, invoice_updated, invoice_sent, invoice_viewed, payment_added, status_changed, invoice_voided | `invoice_events.event_type` |
| `paymentgateway` | razorpay, stripe, manual | `payments.gateway` |
| `paymentstatus` | pending, success, failed, cancelled, refunded | `payments.status` |
| `userrole` | owner, admin, member | `users.role` |

> ⚠️ **ENUM MIGRATION RULES**: When adding/removing values from a PostgreSQL ENUM:
> - Use `ALTER TYPE enumname ADD VALUE 'new_value';` — this is NOT transactional in PG
> - NEVER use `CREATE TYPE IF NOT EXISTS` — use `DO $$ BEGIN ... EXCEPTION ... END $$;`
> - Always handle existing type gracefully with exception blocks

### 5. Indexes
Current indexed columns:
- `workspaces.slug` (unique)
- `users.email` (unique)
- `clients.workspace_id`
- `invoices.workspace_id`, `client_id`, `invoice_number`, `created_at`
- `invoice_items.invoice_id`
- `invoice_events.invoice_id`
- `payments.invoice_id`, `gateway_transaction_id` (unique)
- `idempotency_keys.payment_id`

### 6. Composite Primary Keys
- `InvoiceCounter`: `(workspace_id, year)` — one counter per workspace per year
- `IdempotencyKey`: `(workspace_id, key)` — workspace-scoped deduplication

## Alembic Workflow

### Generate Migration
```bash
cd backend
../.venv/Scripts/alembic revision --autogenerate -m "description"
```

### Review the Generated Script
- Check for destructive operations (DROP, ALTER TYPE)
- Verify ENUM changes use proper PG syntax
- Ensure foreign keys are not broken

### Apply Migration
```bash
../.venv/Scripts/alembic upgrade head
```

### Rollback
```bash
../.venv/Scripts/alembic downgrade -1
```

### Migration History
```bash
../.venv/Scripts/alembic history
```

## Current Migration Chain
```
001_initial_schema → d0be13f0ca49_baseline (ENUM conversions + index additions)
```

## Known Issues to Fix

### 🔴 Critical
1. **ENUM case mismatch**: Alembic migration `d0be13f0ca49` creates UPPERCASE enum values (`'PENDING'`, `'SUCCESS'`), but Python models use lowercase (`"pending"`, `"success"`). This may cause `DataError` on INSERT.

2. **`alembic.ini` has hardcoded credentials**: `sqlalchemy.url = postgresql://postgres:hamza@localhost:5432/invoicesaas` — should use `env.py` to read from `Settings`.

### 🟡 Missing
3. **`tax_id` column missing from `clients` table** — schema and router reference it but model/DB don't have it
4. **No connection pool configuration** — add `pool_size`, `max_overflow`, `pool_pre_ping=True`, `pool_recycle`
5. **No read replica support** — fine for now, needed for scale

## Query Performance Guidelines
- Use `selectinload()` for eager-loading relationships (e.g., invoice items)
- Use `with_for_update()` ONLY for concurrency-critical operations (numbering, payments)
- Always use parameterized queries — never string concatenation
- Paginate with `OFFSET/LIMIT` for now (keyset pagination for scale later)
- Use `ILIKE` for case-insensitive search (PostgreSQL-specific)
