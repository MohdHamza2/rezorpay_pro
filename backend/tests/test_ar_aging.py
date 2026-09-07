"""Wave 29 AR — aging report tests.

Covers: bucket placement, totals/outstanding invariants, detail rows,
by-customer aggregation, per-client filter, as_of guards, status/balance/
deleted exclusion, multi-workspace isolation, no-clamping past as_of.
Mirrors `test_ap_aging.py` (Wave 22).
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403

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

    asyncio.run(_setup())
    yield

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_teardown())


def register_and_token():
    email = f"ar_age_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AR Aging Tester",
            "workspace_name": "AR Aging Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["data"]["workspace_id"]


def create_client(token, name):
    r = client.post(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.json()
    return r.json()["data"]["id"]


def seed_invoice(
    workspace_id,
    client_id,
    number,
    total,
    due_shift_days,
    status="SENT",
    credited=None,
    deleted_at=None,
):
    wrt = datetime.now(timezone.utc).date()
    due = wrt + timedelta(days=due_shift_days)

    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.invoice import Invoice

            invoice = Invoice(
                workspace_id=workspace_id,
                client_id=client_id,
                invoice_number=number,
                currency="AED",
                subtotal=Decimal(str(total)),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal(str(total)),
                amount_credited=credited if credited is not None else Decimal("0.00"),
                status=status,
                issue_date=wrt,
                supply_date=wrt,
                due_date=due,
                deleted_at=deleted_at,
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def test_aging_summary_buckets():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Age Corp")
    # due today+5 (current), today-5, today-40, today-70, today-120
    for i, shift in enumerate((5, -5, -40, -70, -120)):
        seed_invoice(workspace_id, client_id, f"AR-INV-{i}", 1000, shift)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["client_count"] == 1
    assert data["invoice_count"] == 5
    assert float(data["total_outstanding"]) == 5000.00
    assert float(data["buckets"]["current"]) == 1000.00
    assert float(data["buckets"]["days_1_30"]) == 1000.00
    assert float(data["buckets"]["days_31_60"]) == 1000.00
    assert float(data["buckets"]["days_61_90"]) == 1000.00
    assert float(data["buckets"]["days_90_plus"]) == 1000.00


def test_aging_detail_rows():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Detail Corp")
    late_id = seed_invoice(workspace_id, client_id, "DET-INV-1", 2000, -40)

    r = client.get(
        "/api/v1/ar-aging/detail", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    row = next(x for x in data["invoices"] if x["invoice_id"] == str(late_id))
    assert row["bucket"] == "days_31_60"
    assert row["days_overdue"] == 40
    assert float(row["balance_due"]) == 2000.0
    assert row["client_name"] == "Detail Corp"


def test_aging_by_customer():
    token, workspace_id = register_and_token()
    c_a = create_client(token, "Alpha Ltd")
    c_b = create_client(token, "Beta Ltd")
    seed_invoice(workspace_id, c_a, "ALP-INV-1", 1500, -10)
    seed_invoice(workspace_id, c_a, "ALP-INV-2", 500, -10)
    seed_invoice(workspace_id, c_b, "BET-INV-1", 800, 0)

    r = client.get(
        "/api/v1/ar-aging/by-customer", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert float(data["total_outstanding"]) == 2800.0
    rows = data["customers"]
    assert len(rows) == 2
    by_name = {row["client"]["name"]: row for row in rows}
    assert float(by_name["Alpha Ltd"]["total_outstanding"]) == 2000.0
    assert float(by_name["Beta Ltd"]["total_outstanding"]) == 800.0
    assert float(by_name["Alpha Ltd"]["buckets"]["days_1_30"]) == 2000.0


def test_aging_client_filter():
    token, workspace_id = register_and_token()
    c_a = create_client(token, "Filter A")
    c_b = create_client(token, "Filter B")
    seed_invoice(workspace_id, c_a, "FIL-A-INV", 1000, -5)
    seed_invoice(workspace_id, c_b, "FIL-B-INV", 4000, -5)

    r = client.get(
        f"/api/v1/ar-aging?client_id={c_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 1000.0


def test_aging_as_of_future_rejected():
    token, _ = register_and_token()
    future = (date.today() + timedelta(days=2)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?as_of={future}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def test_aging_by_customer_rejects_client_id():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Conf Co")
    seed_invoice(workspace_id, client_id, "CON-INV-1", 1000, -5)

    r = client.get(
        f"/api/v1/ar-aging/by-customer?client_id={client_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def test_aging_status_exclusion():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Status Co")
    seed_invoice(workspace_id, client_id, "EX-DRAFT", 1000, -5, status="DRAFT")
    seed_invoice(workspace_id, client_id, "EX-PAID", 1000, -5, status="PAID")
    seed_invoice(workspace_id, client_id, "EX-CANCEL", 1000, -5, status="CANCELLED")
    seed_invoice(workspace_id, client_id, "EX-OPEN", 5000, -5)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 5000.0


def test_aging_deleted_excluded():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Del Co")
    seed_invoice(
        workspace_id,
        client_id,
        "DEL-INV-1",
        1000,
        -5,
        deleted_at=datetime.now(timezone.utc),
    )

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0


def test_aging_multi_workspace_isolation():
    token_a, workspace_a = register_and_token()
    token_b, workspace_b = register_and_token()
    client_b = create_client(token_b, "Other WS Customer")
    seed_invoice(workspace_b, client_b, "OTHER-1", 9000, -5)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token_b}"})
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 9000.0


def test_aging_zero_balance_excluded():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Zero Co")
    seed_invoice(
        workspace_id,
        client_id,
        "ZERO-INV-1",
        1000,
        -5,
        status="SENT",
        credited=Decimal("1000.00"),
    )

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0


def test_aging_past_as_of_honored_no_clamping():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "NoClamp Co")
    seed_invoice(workspace_id, client_id, "NOCLAMP-1", 1000, -35)

    today = date.today()
    past_as_of = (today - timedelta(days=20)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging/detail?as_of={past_as_of}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["as_of"] == past_as_of
    row = data["invoices"][0]
    assert row["days_overdue"] == 15
    assert row["bucket"] == "days_1_30"

    future = (today + timedelta(days=2)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?as_of={future}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()
