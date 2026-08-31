# Technology Stack

**Analysis Date:** 2026-08-31

## Languages

**Primary:**
- Python 3.11 — FastAPI backend in `backend/app/`, Alembic in `backend/alembic/`, pytest in `backend/tests/`
- TypeScript ~6.0.2 (`frontend/package.json`, `frontend/tsconfig.json`) — Vite React SPA in `frontend/src/`

**Secondary:**
- SQL (PostgreSQL 16 dialect) — Alembic migrations in `backend/alembic/versions/`
- CSS Modules + vanilla CSS — `frontend/src/**/*.module.css`, `frontend/src/index.css`, `frontend/src/App.css`
- YAML — CI in `.github/workflows/ci.yml`, pre-commit in `.pre-commit-config.yaml`, Compose in `docker-compose.yml`
- Markdown — architecture specs in `architecture/`, agent plans in `.agents/`

## Runtime

**Environment:**
- CPython 3.11 (CI pins `PYTHON_VERSION: "3.11"` in `.github/workflows/ci.yml`; Docker `python:3.11-slim` in `backend/Dockerfile`)
- Node.js (Vite 8 / React 19 SPA; no `.nvmrc` present)
- Browser: client-side React 19 SPA; invoice PDF via `@react-pdf/renderer`

**Package Manager:**
- pip — `backend/requirements.txt` (pinned versions; no `poetry.lock` / `pyproject.toml`)
- npm — `frontend/package.json` + `frontend/package-lock.json` present
- Lockfile: backend lockfile missing (pip-tools / uv lock not detected); frontend lockfile present

## Frameworks

**Core:**
- FastAPI 0.109.0 + Starlette 0.36.0 + Uvicorn 0.27.0 — HTTP API (`backend/app/main.py`)
- SQLModel 0.0.14 + SQLAlchemy 2.0.25 (asyncio) + asyncpg 0.29.0 — ORM and async PostgreSQL
- Alembic 1.13.1 — schema migrations only (`backend/alembic/`)
- Pydantic Settings 2.1.0 — env config (`backend/app/config.py`)
- React 19.2.8 + React Router DOM 7.18.2 — SPA (`frontend/src/App.tsx`)
- Vite 8.2.0 + `@vitejs/plugin-react` 6.0.4 — frontend build (`frontend/vite.config.ts`)
- TanStack Query 5.101.4 — server state (`frontend/src/pages/*`)
- React Hook Form 7.85.0 + Zod 4.4.3 + `@hookform/resolvers` — forms (`frontend/src/pages/Invoices.tsx`, `Settings.tsx`)

**Testing:**
- pytest 7.4.4 + pytest-asyncio 0.23.2 + httpx 0.26.0 + FastAPI `TestClient` — backend (`backend/pytest.ini`, `backend/tests/`)
- Frontend unit/e2e/browser tests: Not detected (no Vitest/Jest/Playwright/Cypress)

**Build/Dev:**
- Black 24.2.0 — Python format (`backend/`, `.pre-commit-config.yaml`)
- Ruff 0.2.2 — Python lint (`ruff check app/` in CI)
- Oxlint 1.75.0 — frontend lint (`frontend/package.json` script `"lint": "oxlint"`, `frontend/.oxlintrc.json`)
- pre-commit 3.6.0 — black + ruff + hygiene (`.pre-commit-config.yaml`)
- pip-audit 2.7.0 — dependency CVE scan (CI job `security`, `continue-on-error: true`)
- Gunicorn 21.2.0 + Uvicorn workers — production process manager (`backend/Dockerfile` CMD)
- Docker Compose — `postgres:16-alpine` + `redis:7-alpine` + API (`docker-compose.yml`)

## Key Dependencies

**Critical:**
- `python-jose[cryptography]==3.3.0` — JWT access/refresh (`backend/app/auth/utils.py`)
- `passlib[bcrypt]==1.7.4` + `bcrypt==4.2.0` — password hashing (`backend/app/auth/utils.py`)
- `slowapi==0.1.9` — IP rate limits on auth and payment create (`backend/app/limiter.py`, `backend/app/auth/router.py`, `backend/app/routers/payments.py`)
- `email-validator==2.1.0.post1` — Pydantic `EmailStr`
- `python-multipart==0.0.6` — form parsing (present; file-upload endpoints not detected)
- `axios==1.19.0` — frontend HTTP (`frontend/src/api/client.ts`)
- `@react-pdf/renderer==4.6.1` — client-side invoice PDF (`frontend/src/components/pdf/InvoicePDF.tsx`)
- `recharts==3.10.1` — listed in `frontend/package.json`; Dashboard currently uses lucide + CSS cards, not charts
- `lucide-react` — icons (`frontend/src/components/Layout.tsx`)
- `react-hot-toast` — toasts (`frontend/src/App.tsx`)

**Infrastructure:**
- `redis==5.0.1` — package present; `REDIS_URL` in `backend/app/config.py`; slowapi uses in-memory default (`backend/app/limiter.py` has no Redis storage). Redis service exists in `docker-compose.yml` but is not wired into rate limiting or queues.
- PostgreSQL 16 — required. `backend/app/database.py` still branches on `sqlite` `connect_args`; project rule forbids SQLite for tests.

## Configuration

**Environment:**
- Backend: Pydantic `Settings` in `backend/app/config.py` loaded from `backend/.env` (file present; do not commit). Template: `backend/.env.example`
- Frontend: `VITE_API_URL` via `frontend/.env.example`; runtime read in `frontend/src/api/client.ts`
- Compose: interpolates `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `ENVIRONMENT`; API uses `env_file: ./backend/.env`

**Key configs required (names only):**
- `DATABASE_URL` — `postgresql+asyncpg://…`
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`
- `APP_NAME`, `DEBUG`, `ENVIRONMENT`
- `RATE_LIMIT_AUTH`
- `REDIS_URL` (declared; unused by limiter)
- `VITE_API_URL` (frontend)

**Build:**
- `backend/Dockerfile` — multi-stage (builder + runtime non-root `appuser`)
- `backend/.dockerignore`
- `frontend/vite.config.ts` — default Vite + React plugin; no path aliases, no code-splitting config
- `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`
- No frontend Dockerfile
- No `pyproject.toml` / `ruff.toml` — ruff/black invoked with CLI defaults

## Platform Requirements

**Development:**
- Python 3.11 venv, `pip install -r backend/requirements.txt`
- PostgreSQL 16 (Compose maps host `5434` → container `5432`)
- Redis 7 optional (Compose maps host `6380` → `6379`)
- Node + npm for `frontend/` (`npm run dev` Vite; default port 5173)
- Alembic: `cd backend && alembic upgrade head`
- CORS allowlist in `backend/app/main.py` is localhost-only (`3000`, `5173`–`5175`)

**Production:**
- Target: Docker image of FastAPI + Gunicorn/Uvicorn (`backend/Dockerfile` CMD) against PostgreSQL 16
- Hosting platform: Not detected (no Terraform, Fly, Railway, ECS, k8s manifests)
- SSL/domain/monitoring: Not detected
- Frontend production hosting: Not detected (`npm run build` emits `frontend/dist/` only)
- Wave 29 in `.agents/MASTER_PLAN_V3.md` is the planned production-hardening wave; not implemented

## Locked vs Actual Divergence

`.agents/MASTER_PLAN_V3.md` Section 1 locks:
- Frontend React 18 — actual is React 19 (`frontend/package.json`)
- Email Resend — not in `backend/requirements.txt`
- OCR Gemini Flash Vision — `ocr_job_id` / `ocr_extracted` columns only (`backend/app/models/supplier_invoice.py`)
- WhatsApp Meta Cloud API — `whatsapp_number` field only (`backend/app/models/workspace.py`)
- Redis for rate limiting + queues — Redis runs in Compose; app limiter is in-memory

---

*Stack analysis: 2026-08-31*
