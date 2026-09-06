"""Wave 22 AP — supplier statement (AP ledger) tests.

Covers: date guards (from>to, as_of future), 404 for foreign suppliers,
opening balance reconstruction, activity lines with running balances,
totals, amount_due_now + aging footer, workspace isolation.
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

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
    email = f"ap_stmt_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AP Stmt Tester",
            "workspace_name": "AP Stmt Workspace",
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


def seed_invoice(
    workspace_id, supplier_id, number, total, invoice_days_ago, due_days=15
):
    def _dt(d):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    invoice_date = date.today() - timedelta(days=invoice_days_ago)
    due = date.today() + timedelta(days=due_days)

    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.supplier_invoice import SupplierInvoice
            from decimal import Decimal

            invoice = SupplierInvoice(
                workspace_id=workspace_id,
                supplier_id=supplier_id,
                supplier_invoice_number=number,
                invoice_date=_dt(invoice_date),
                due_date=_dt(due),
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


def post_payment(token, invoice_id, amount, idem_key, payment_date=None):
    body = {"supplier_invoice_id": str(invoice_id), "amount": amount}
    if payment_date:
        body["payment_date"] = payment_date
    return client.post(
        "/api/v1/supplier-payments",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idem_key,
        },
        json=body,
    )


def get_statement(token, supplier_id, from_iso, to_iso, as_of=None):
    qs = f"from={from_iso}&to={to_iso}"
    if as_of:
        qs += f"&as_of={as_of}"
    return client.get(
        f"/api/v1/suppliers/{supplier_id}/statement?{qs}",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_statement_opening_activity_totals_and_footer():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Ledger Co", "LDG-001")

    # INV-A issued 30d ago, partially paid 10d ago (both before window)
    inv_a = seed_invoice(workspace_id, supplier_id, "LDG-INV-A", 1500, 30)
    post_payment(
        token,
        inv_a,
        1000,
        "idem-stmt-a",
        payment_date=(date.today() - timedelta(days=10)).isoformat(),
    )
    # INV-B issued within the window
    seed_invoice(workspace_id, supplier_id, "LDG-INV-B", 500, 5)

    today = date.today()
    from_iso = (today - timedelta(days=7)).isoformat()
    to_iso = (today + timedelta(days=7)).isoformat()

    r = get_statement(token, supplier_id, from_iso, to_iso)
    assert r.status_code == 200, r.json()
    data = r.json()["data"]

    assert data["currency"] == "AED"
    assert data["supplier"]["name"] == "Ledger Co"
    assert data["from"] == from_iso
    assert data["to"] == to_iso

    # opening = 1500 billed before window - 1000 paid before window
    assert float(data["opening_balance"]) == 500.0

    # lines: OPENING + INV-B (payment is before the window, no activity row)
    assert len(data["lines"]) == 2
    opening_line = data["lines"][0]
    assert opening_line["doc_type"] == "OPENING"
    assert float(opening_line["running_balance"]) == 500.0
    inv_b_line = data["lines"][1]
    assert inv_b_line["doc_type"] == "SUPPLIER_INVOICE"
    assert inv_b_line["number"] == "LDG-INV-B"
    assert float(inv_b_line["debit"]) == 500.0
    assert float(inv_b_line["running_balance"]) == 1000.0

    assert float(data["totals"]["billed"]) == 500.0
    assert float(data["totals"]["paid"]) == 0.0
    assert float(data["totals"]["pending"]) == 0.0
    assert float(data["totals"]["closing_running"]) == 1000.0

    # amount_due_now = INV-A remaining 500 + INV-B 500
    assert float(data["amount_due_now"]) == 1000.0
    # both invoices due +15d -> current bucket
    assert float(data["aging"]["buckets"]["current"]) == 1000.0


def test_statement_in_window_payment_shows_line():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Win Co", "WIN-001")
    inv = seed_invoice(workspace_id, supplier_id, "WIN-INV-1", 2000, 3)
    post_payment(token, inv, 800, "idem-win")

    today = date.today()
    r = get_statement(
        token,
        supplier_id,
        (today - timedelta(days=5)).isoformat(),
        today.isoformat(),
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    lines = data["lines"]
    payment_line = next(x for x in lines if x["doc_type"] == "SUPPLIER_PAYMENT")
    assert float(payment_line["credit"]) == 800.0
    assert payment_line["payment_method"] == "BANK_TRANSFER"
    assert payment_line["cleared_cash"] is True
    assert float(payment_line["running_balance"]) == 1200.0


def test_statement_from_after_to_rejected():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Guard Co", "GRD-001")
    today = date.today()
    r = get_statement(
        token,
        supplier_id,
        (today + timedelta(days=2)).isoformat(),
        today.isoformat(),
    )
    assert r.status_code == 422, r.json()


def test_statement_as_of_future_rejected():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Future Co", "FUT-001")
    today = date.today()
    r = get_statement(
        token,
        supplier_id,
        (today - timedelta(days=1)).isoformat(),
        today.isoformat(),
        as_of=(today + timedelta(days=3)).isoformat(),
    )
    assert r.status_code == 422, r.json()


def test_statement_range_too_long_rejected():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Long Co", "LNG-001")
    today = date.today()
    r = get_statement(
        token,
        supplier_id,
        (today - timedelta(days=400)).isoformat(),
        today.isoformat(),
    )
    assert r.status_code == 422, r.json()
    assert r.json()["error"]["code"] == "DATE_RANGE_TOO_LONG"


def test_statement_foreign_supplier_404():
    token_a, workspace_a = register_and_token()
    token_b, _workspace_b = register_and_token()
    supplier_a = create_supplier(token_a, "For Co", "FOR-001")
    seed_invoice(workspace_a, supplier_a, "FOR-INV-1", 1000, 3)

    today = date.today()
    r = get_statement(
        token_b,
        supplier_a,
        (today - timedelta(days=5)).isoformat(),
        today.isoformat(),
    )
    assert r.status_code == 404, r.json()
    assert r.json()["error"]["code"] == "NOT_FOUND"
