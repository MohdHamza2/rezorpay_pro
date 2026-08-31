# Testing Patterns

**Analysis Date:** 2026-08-31

## Test Framework

**Runner:**
- pytest 7.4.4 + pytest-asyncio 0.23.2 (`asyncio_mode = auto`)
- Config: `backend/pytest.ini`
```
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```
- Assertion Library: pytest `assert` (no unittest.TestCase in suite)
- HTTP: `fastapi.testclient.TestClient` (sync) against the real ASGI app

**Run Commands:**
```bash
cd backend
pytest                    # all tests under tests/
pytest tests/test_auth.py -v
pytest tests/test_e2e_3way_match.py -v
# Coverage: not configured (no pytest-cov in requirements.txt)
```

CI (`.github/workflows/ci.yml`): `alembic upgrade head` then `alembic check` then `pytest` on Postgres 16 service `invoicesaas_test`.

## Test File Organization

**Location:**
- Separate tree: `backend/tests/` (not colocated with `app/`)
- Do not put new tests in `backend/test_*.py` at package root — those files (`test_e2e.py`, `test_step2_api.py`, `test_step2_production.py`) are live-server leftovers and are excluded by `testpaths = tests`

**Naming:**
- `test_{domain}.py` for focused suites
- `test_e2e_{flow}.py` for multi-step HTTP journeys

**Structure:**
```
backend/tests/
├── conftest.py                      # disables slowapi limiter
├── test_auth.py                     # health, root, register/login
├── test_multi_tenant_isolation.py   # clients, invoices, payments, products, suppliers
├── test_concurrent_numbering.py     # INV + SPO gapless + year reset + rollback
├── test_spo.py                      # SPO isolation + gapless
├── test_grn.py                      # GRN lifecycle + cancel
├── test_e2e_spo.py                  # SPO happy path
├── test_e2e_grn.py                  # GRN complex flow
└── test_e2e_3way_match.py           # supplier invoice matching
```

**Missing test modules (do not assume they exist):**
- `test_invoices.py`, `test_payments.py`, `test_products.py`, `test_clients.py`, `test_inventory.py`, `test_procurement.py`, `test_rfq.py`, `test_workspaces.py`, `test_dashboard.py`
- Invoice CRUD/send/void covered only indirectly via isolation + numbering
- Frontend: zero `*.test.ts(x)` / Playwright / Cypress

## Test Structure

**Suite Organization:**
```python
# Pattern from backend/tests/test_auth.py and test_spo.py
import sys
import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app
from app.database import get_session
from app.config import get_settings
from app.models import *  # noqa: F401 — populate metadata

settings = get_settings()
TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def override_get_session():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())
```

**Patterns:**
- Setup: module-scoped `drop_all` / `create_all` on `{DATABASE_URL}_test` (idempotent suffix — required for CI where URL already ends `_test`)
- Teardown: `drop_all`
- Assertion: `assert r.status_code == 200` then `r.json()["success"]` and `r.json()["data"]`
- Auth helper: POST `/auth/register` with unique email, extract `data.access_token`, send `Authorization: Bearer …`

**Use this harness for new tests.** Copy `TEST_DATABASE_URL` derivation exactly. Import all models. Do not use SQLite.

## Mocking

**Framework:** Not used. Tests hit a real PostgreSQL database and the real FastAPI app.

**Patterns:**
- Override only `get_session` to the test engine
- `backend/tests/conftest.py` sets `limiter.enabled = False` so many registrations do not 429

**What to Mock:**
- Nothing in current suite. When Email/WhatsApp/OCR exist, mock those HTTP clients — do not mock SQLModel.

**What NOT to Mock:**
- PostgreSQL, Alembic types, row locks, ENUM behavior, `FOR UPDATE` — these are why SQLite is forbidden

## Fixtures and Factories

**Test Data:**
```python
def _register(prefix: str, workspace_name: str) -> tuple[str, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email,
        "password": "securepassword123",
        "name": "Tester",
        "workspace_name": workspace_name,
    })
    data = r.json()["data"]
    return data["access_token"], data["user"]["workspace_id"]
```
See `backend/tests/test_multi_tenant_isolation.py`.

E2E files build a graph: workspace → supplier → warehouse/bin → category/brand/UOM → product → SPO → GRN → supplier invoice (`backend/tests/test_e2e_3way_match.py`).

**Location:**
- Inline helpers in each test module (duplicated). No `tests/factories.py` / `conftest` user fixtures yet.
- Prefer extracting shared `_register` / product-seed helpers into `backend/tests/conftest.py` if adding many files — keep emails unique with `uuid4`.

## Coverage

**Requirements:** None enforced (no `--cov` in CI, no codecov)

**View Coverage:**
```bash
# Not wired. If adding: pip install pytest-cov
cd backend && pytest --cov=app --cov-report=term-missing
```

**Documented test counts:** 19 collected functions across 8 files (auth 3, isolation 5, numbering 4, spo 2, grn 2, e2e spo 1, e2e grn 1, 3way 1).

## Test Types

**Unit Tests:**
- Not separated. Numbering/isolation tests are HTTP-level, not isolated function tests of services.

**Integration Tests:**
- Primary style: `TestClient` + PostgreSQL `_test` DB
- Multi-tenant: Workspace B must get 404 on A's ids (`test_multi_tenant_isolation.py`, `test_spo.py`)
- Concurrency: parallel invoice/SPO creates (`test_concurrent_numbering.py`)
- CI also runs `alembic check` for model↔migration drift

**E2E Tests:**
- Backend HTTP journeys named `test_e2e_*` (not browser)
- Browser E2E: Not used
- Frontend: Not used

## Common Patterns

**Async Testing:**
```python
# Services are async; tests stay sync via TestClient which runs the event loop.
# Module fixtures use asyncio.run() for drop/create.
# Windows: WindowsSelectorEventLoopPolicy at top of every DB test file.
```

**Error Testing:**
```python
# Isolation pattern
r = client.get(f"/api/v1/invoices/{a_invoice_id}", headers=headers_b)
assert r.status_code == 404
```

**Payments:**
```python
client.post(
    f"/api/v1/invoices/{invoice_id}/payments",
    json={"amount": "10.00", "payment_method": "BANK_TRANSFER"},
    headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
)
```
Always send `Idempotency-Key` or the API returns 400.

**Currency:**
- Seed payloads use `"currency": "AED"` (see `backend/tests/test_e2e_spo.py`).

## How to add tests for a new endpoint

1. Put file in `backend/tests/test_{feature}.py`
2. Copy the engine/override/`create_all` harness (or import shared fixtures once they exist)
3. Register two workspaces for isolation
4. Assert wrapper `success` and HTTP codes
5. For numbering: assert unique sequential `PREFIX-YEAR-…` and uniqueness under concurrency
6. Run `pytest tests/test_{feature}.py -v` against real Postgres
7. Do not add SQLite fallbacks

## Gaps vs MASTER_PLAN_V3 Section 14

Required by plan, not present as dedicated tests:
- Stock reservation race
- Credit-limit concurrent CPO block
- Payment idempotency duplicate-key (logic exists; no named test)
- Payment PUT/DELETE immutability (PUT exists for PDC — plan says 405)
- N+1 SQL logging assertions
- Role-based VIEWER cannot write
- Decimal rounding `0.005 → 0.01`
- Invoice state-machine invalid transitions suite
- Product identifier/price/UOM conversion CRUD
- Frontend build is not in CI

---

*Testing analysis: 2026-08-31*
