"""Wave 22 AP — aging report tests.

Covers: bucket placement, totals/outstanding invariants, detail rows,
by-supplier aggregation, per-supplier filter, as_of guards.
"""

import asyncio
import sys
import uuid
from datetime import date, timedelta

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
    email = f"ap_age_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AP Aging Tester",
            "workspace_name": "AP Aging Workspace",
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


def create_supplier(token, name, code):
    r = client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "supplier_code": code,
            "email": f"{code.lower()}@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.json()
    return r.json()["data"]["id"]


def seed_invoice(workspace_id, supplier_id, number, total, due_shift_days):
    from datetime import datetime, timezone

    due = date.today() + timedelta(days=due_shift_days)

    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.supplier_invoice import SupplierInvoice
            from decimal import Decimal

            invoice = SupplierInvoice(
                workspace_id=workspace_id,
                supplier_id=supplier_id,
                supplier_invoice_number=number,
                invoice_date=datetime.combine(
                    date.today(), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
                due_date=datetime.combine(due, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ),
                currency="AED",
                total_amount=Decimal(str(total)),
                amount_paid=Decimal("0.00"),
                balance_due=Decimal(str(total)),
                status="APPROVED",
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def test_aging_summary_buckets():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Age Co", "AGE-001")
    # due today+5 (current), today-5, today-40, today-70, today-120
    for i, shift in enumerate((5, -5, -40, -70, -120)):
        seed_invoice(workspace_id, supplier_id, f"AGE-INV-{i}", 1000, shift)

    r = client.get("/api/v1/ap-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["supplier_count"] == 1
    assert data["invoice_count"] == 5
    assert float(data["total_outstanding"]) == 5000.00
    assert float(data["buckets"]["current"]) == 1000.00
    assert float(data["buckets"]["days_1_30"]) == 1000.00
    assert float(data["buckets"]["days_31_60"]) == 1000.00
    assert float(data["buckets"]["days_61_90"]) == 1000.00
    assert float(data["buckets"]["days_90_plus"]) == 1000.00


def test_aging_detail_rows():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Detail Co", "DET-001")
    late_id = seed_invoice(workspace_id, supplier_id, "DET-INV-1", 2000, -40)

    r = client.get(
        "/api/v1/ap-aging/detail", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    row = next(x for x in data["invoices"] if x["supplier_invoice_id"] == str(late_id))
    assert row["bucket"] == "days_31_60"
    assert row["days_overdue"] == 40
    assert float(row["balance_due"]) == 2000.0
    assert row["supplier_name"] == "Detail Co"


def test_aging_by_supplier():
    token, workspace_id = register_and_token()
    sup_a = create_supplier(token, "Alpha Supply", "ALP-001")
    sup_b = create_supplier(token, "Beta Supply", "BET-001")
    seed_invoice(workspace_id, sup_a, "ALP-INV-1", 1500, -10)
    seed_invoice(workspace_id, sup_a, "ALP-INV-2", 500, -10)
    seed_invoice(workspace_id, sup_b, "BET-INV-1", 800, 0)

    r = client.get(
        "/api/v1/ap-aging/by-supplier", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert float(data["total_outstanding"]) == 2800.0
    rows = data["suppliers"]
    assert len(rows) == 2
    by_name = {row["supplier"]["name"]: row for row in rows}
    assert float(by_name["Alpha Supply"]["total_outstanding"]) == 2000.0
    assert float(by_name["Beta Supply"]["total_outstanding"]) == 800.0
    assert float(by_name["Alpha Supply"]["buckets"]["days_1_30"]) == 2000.0


def test_aging_supplier_filter():
    token, workspace_id = register_and_token()
    sup_a = create_supplier(token, "Filter A", "FIL-A1")
    sup_b = create_supplier(token, "Filter B", "FIL-B1")
    seed_invoice(workspace_id, sup_a, "FIL-A-INV", 1000, -5)
    seed_invoice(workspace_id, sup_b, "FIL-B-INV", 4000, -5)

    r = client.get(
        f"/api/v1/ap-aging?supplier_id={sup_a}",
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
        f"/api/v1/ap-aging?as_of={future}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def test_aging_by_supplier_rejects_supplier_id():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Conf Co", "CON-001")
    seed_invoice(workspace_id, supplier_id, "CON-INV-1", 1000, -5)

    r = client.get(
        f"/api/v1/ap-aging/by-supplier?supplier_id={supplier_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()
