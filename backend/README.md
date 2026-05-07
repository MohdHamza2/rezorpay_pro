# InvoiceSaaS Backend

AI-powered SaaS platform for invoice automation and cashflow intelligence for micro-SMEs.

## Tech Stack

- **Framework**: FastAPI
- **ORM**: SQLModel (SQLAlchemy 2.0 + Pydantic v2)
- **Database**: PostgreSQL + asyncpg
- **Auth**: JWT (python-jose) + bcrypt
- **Rate Limiting**: slowapi

## Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Setup Environment

```bash
cp .env.example .env
# Edit .env with your database URL and secret keys
```

### 3. Run Database

Ensure PostgreSQL is running and the database is created:

```bash
createdb invoicesaas
```

### 3.5 Run Migrations (CRITICAL)

Apply the initial schema to the database:

```bash
alembic upgrade head
```

### 4. Start Server

```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create workspace + owner user |
| POST | `/auth/login` | Get JWT access + refresh tokens |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Get current user info |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Project Structure

```
backend/
├── alembic/                 # Database migrations
│   ├── __init__.py
│   ├── env.py              # Async Alembic config
│   ├── script.py.mako      # Migration template
│   └── versions/
│       ├── __init__.py
│       └── 001_initial_schema.py
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # SQLModel engine + session
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── dependencies.py    # JWT deps, get_current_user
│   │   ├── router.py          # /auth/login, /auth/register
│   │   └── utils.py           # hash_password, create_token
│   ├── models/
│   │   ├── __init__.py
│   │   ├── workspace.py
│   │   ├── user.py
│   │   ├── client.py
│   │   ├── invoice.py
│   │   ├── invoice_item.py
│   │   ├── payment.py
│   │   └── invoice_event.py
│   └── routers/
│       ├── __init__.py
│       └── health.py
├── tests/
│   ├── __init__.py
│   └── test_auth.py
├── alembic.ini             # Alembic configuration
├── pytest.ini              # Test configuration
├── requirements.txt
└── .env.example
```

## Database Models

### Multi-Tenancy
- Workspace-based multi-tenancy
- All queries filtered by workspace_id
- Future: workspace_memberships for multi-workspace users

### Key Features
- **UUIDs**: All IDs use UUID (secure, scalable)
- **Timezone-aware**: All timestamps use UTC
- **Financial precision**: DECIMAL(12,2) for all money fields
- **Soft deletes**: deleted_at on Workspace, Client, Invoice
- **Immutable payments**: No soft delete (financial records)
- **CHECK constraints**: Non-negative amounts, quantities
- **State machine**: Enforced invoice status transitions
- **Partial payments**: Status auto-calculated from payment sums

## Development

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Rate Limiting

Auth endpoints are rate-limited to prevent brute-force attacks.
Default: 5 requests per minute.

### Security

- bcrypt password hashing
- JWT tokens with expiration
- Refresh token rotation
- Workspace-scoped authorization

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string (postgresql+asyncpg://...) |
| `SECRET_KEY` | Yes | - | JWT signing key (change in production!) |
| `ALGORITHM` | No | HS256 | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | 30 | Access token lifetime (minutes) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | 7 | Refresh token lifetime (days) |
| `RATE_LIMIT_AUTH` | No | 5/minute | Auth endpoint rate limit |
| `APP_NAME` | No | InvoiceSaaS | Application name |
| `DEBUG` | No | false | Debug mode (logs SQL queries) |
