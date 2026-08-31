# External Integrations

**Analysis Date:** 2026-08-31

## APIs & External Services

**Payment gateways:**
- Razorpay — Not detected (no SDK, no env vars, no webhook router). Repo name `rezorpay_pro` is historical; payments are manual B2B methods in `backend/app/models/payment.py` (`CASH`, `BANK_TRANSFER`, `CHEQUE`, `PDC`, `CREDIT_CARD`) recorded via `POST /api/v1/invoices/{id}/payments`.
- Stripe / PayPal / Network International / PayTabs — Not detected.
- `Payment.gateway_transaction_id` in `backend/app/models/payment.py` is an optional unique string for future gateway IDs.

**Email:**
- Resend — Specified in `.agents/MASTER_PLAN_V3.md`; not implemented. No `resend` package, no SMTP settings in `backend/app/config.py`.
- `POST /api/v1/invoices/{id}/send` in `backend/app/routers/invoices.py` only transitions `DRAFT → SENT` and logs `sent_method="email"`. No message is sent.

**WhatsApp:**
- Meta WhatsApp Business Cloud API — Specified in `.agents/MASTER_PLAN.md` / V3. Not implemented. No webhook route. Workspace stores `whatsapp_number` (`backend/app/models/workspace.py`); Settings UI collects it (`frontend/src/pages/Settings.tsx`).

**OCR:**
- Gemini Flash Vision — Specified in V3. Not implemented. `SupplierInvoice.ocr_job_id` / `ocr_extracted` in `backend/app/models/supplier_invoice.py` are unused stubs.

**PDF:**
- Client-side only: `@react-pdf/renderer` in `frontend/src/components/pdf/InvoicePDF.tsx`. No server PDF, no WeasyPrint/ReportLab. Templates for Quotation, DO, SPO, GRN, Statement: missing.

## Data Storage

**Databases:**
- PostgreSQL 16 (`postgres:16-alpine` in `docker-compose.yml`; CI `postgres:16-alpine`)
  - Connection: env `DATABASE_URL` (`postgresql+asyncpg://…`) via `backend/app/config.py` → `backend/app/database.py`
  - Client: SQLModel / SQLAlchemy async + asyncpg
  - Migrations: Alembic (`backend/alembic/env.py` reads `settings.DATABASE_URL`)
  - Compose host port: `5434` → container `5432`

**File Storage:**
- Local filesystem only. `Workspace.logo_url` and `SupplierDocument.document_url` / `SupplierInvoice.document_url` are URL strings; no S3/GCS/upload endpoint detected.

**Caching:**
- Redis 7 container in `docker-compose.yml` (`REDIS_URL` in config). Application code does not use Redis as cache, broker, or slowapi storage (`backend/app/limiter.py` is default in-memory).

## Authentication & Identity

**Auth Provider:**
- Custom JWT
  - Implementation: `backend/app/auth/utils.py` (python-jose HS256), `backend/app/auth/router.py`, `backend/app/auth/dependencies.py`
  - Access token 30 min; refresh 7 days (`backend/app/config.py`)
  - Password: passlib bcrypt
  - Register creates a `Workspace` + `User` with `UserRole.OWNER`
  - Endpoints: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`
  - Frontend: tokens in `localStorage` key `auth_tokens` (`frontend/src/contexts/AuthContext.tsx`); axios interceptor refresh (`frontend/src/api/client.ts`)
- OAuth / SSO / Magic link: Not detected
- RBAC: `UserRole` enum (`OWNER`, `ADMIN`, `MEMBER`) on `backend/app/models/user.py`; no `require_role` dependency. All authenticated workspace members share the same write access.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, OpenTelemetry)

**Logs:**
- Structured JSON to stdout (`backend/app/logging.py` `JSONFormatter`)
- Request ID middleware sets `X-Request-ID` and `X-Process-Time` (`backend/app/main.py`)
- Health: `GET /health`, `GET /health/live`, `GET /health/ready` (`backend/app/routers/health.py`) — ready pings `SELECT 1`
- Global 500 handler returns generic `"Something went wrong"` (`backend/app/main.py`)

## CI/CD & Deployment

**Hosting:**
- Not detected. `backend/Dockerfile` + `docker-compose.yml` for local/dev. No frontend container. No deploy workflow beyond CI.

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` on `push`/`pull_request` to `main`/`master`
  1. Lint: `ruff check app/` + `black --check app/` (backend only; tests not linted in CI job though P3 formatted them)
  2. Test: ephemeral Postgres 16, `alembic upgrade head`, `alembic check`, `pytest` (working-directory `backend`)
  3. Security: `pip-audit --strict` with `continue-on-error: true`
- Frontend lint/build/test: not in CI
- CD / deploy job: None

## Environment Configuration

**Required env vars (names only):**
- `DATABASE_URL`
- `SECRET_KEY`
- `ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `APP_NAME`
- `DEBUG`
- `ENVIRONMENT`
- `RATE_LIMIT_AUTH`
- `REDIS_URL`
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` (Compose)
- `VITE_API_URL` (frontend)

**Secrets location:**
- `backend/.env` (gitignored; `.env.example` committed)
- `frontend/.env` if used (gitignored via `.gitignore` `.env` rule)
- Compose `env_file: ./backend/.env`
- Never commit real secrets. `.env.example` contains local-dev placeholders.

## Webhooks & Callbacks

**Incoming:**
- None. Planned: `POST /api/v1/whatsapp/webhook` (`.agents/MASTER_PLAN.md`). No Razorpay/payment webhooks.

**Outgoing:**
- None. Invoice “send” does not call email/WhatsApp APIs. SPO “send” (`backend/app/routers/spo.py` `POST /spos/{id}/send`) is a state transition only (`SPOService.send`).

## UAE / Domain Integrations (planned, not wired)

- FTA VAT return filing API — Not detected
- UAE Trade License / TRN validation service — Not detected (TRN is a free-text workspace field)
- IBAN/SWIFT validation — Supplier bank fields exist (`backend/app/models/supplier.py`); no validator service
- Arabic translation / RTL CDN — Not detected

---

*Integration audit: 2026-08-31*
