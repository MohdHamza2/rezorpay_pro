"""Wave 23 — supplier statement integration with applied debit notes.

Covers: DN activity line (correct envelope + credit), line ordering within the
same day (invoice before DN before payment), totals.credited + closing_running,
opening balance reconstruction subtracting DNs applied before the window,
and amount_due_now reflecting the reduced balance.
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.supplier_debit_note import SupplierDebitNote  # noqa: E402
from app.models.supplier_invoice import SupplierInvoice  # noqa: E402

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
    email = f"sdstmt_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "Stmt Tester",
            "workspace_name": "Stmt Workspace",
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


def create_supplier(token, name="StmtCo"):
    r = client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "supplier_code": f"ST{uuid.uuid4().hex[:4]}",
            "email": "st@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def seed_invoice(workspace_id, supplier_id, number, total, days_ago=3):
    def _dt(d):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    total = Decimal(str(total))

    async def insert():
        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=uuid.UUID(supplier_id),
                supplier_invoice_number=number,
                invoice_date=_dt(
                    datetime.now(timezone.utc).date() - timedelta(days=days_ago)
                ),
                due_date=_dt(date.today() + timedelta(days=15)),
                currency="AED",
                total_amount=total,
                amount_paid=Decimal("0.00"),
                balance_due=total,
                status="APPROVED",
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return str(invoice.id)

    return asyncio.run(insert())


def create_issue_apply(token, supplier_id, invoice_id, amount):
    r = client.post(
        "/api/v1/supplier-debit-notes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier_id,
            "amount": str(amount),
            "reason": "Supplier credit for return",
            "issue_date": date.today().isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    note = r.json()["data"]
    client.post(
        f"/api/v1/supplier-debit-notes/{note['id']}/issue",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    applied = client.post(
        f"/api/v1/supplier-debit-notes/{note['id']}/apply",
        json={"supplier_invoice_id": invoice_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200, applied.text
    return applied.json()["data"]


def get_statement(token, supplier_id, from_iso, to_iso):
    return client.get(
        f"/api/v1/suppliers/{supplier_id}/statement?from={from_iso}&to={to_iso}",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_dn_activity_line_and_ordering():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "ST1", 1000, days_ago=0)

    create_issue_apply(token, supplier_id, invoice_id, "300")

    today = datetime.now(timezone.utc).date()
    from_iso = (today - timedelta(days=1)).isoformat()
    to_iso = (today + timedelta(days=1)).isoformat()

    r = get_statement(token, supplier_id, from_iso, to_iso)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    lines = data["lines"]
    types = [ln["doc_type"] for ln in lines]
    assert types == ["OPENING", "SUPPLIER_INVOICE", "SUPPLIER_DEBIT_NOTE"]

    dn = lines[2]
    assert dn["doc_type_label"] == "Supplier debit note"
    assert dn["credit"] == "300.00"
    assert dn["debit"] == "0.00"
    assert dn["cleared_cash"] is True
    assert dn["number"].startswith("SDN-")
    assert dn["running_balance"] == "700.00"
    assert lines[1]["running_balance"] == "1000.00"

    totals = data["totals"]
    assert totals["billed"] == "1000.00"
    assert totals["credited"] == "300.00"
    assert totals["paid"] == "0.00"
    assert totals["pending"] == "0.00"
    assert totals["closing_running"] == "700.00"

    assert data["opening_balance"] == "0.00"
    assert data["amount_due_now"] == "700.00"


def test_dn_opening_reconstruction_and_amount_due():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "ST2", 1500, days_ago=30)

    note = create_issue_apply(token, supplier_id, invoice_id, "400")

    # backdate the application so the DN falls BEFORE the statement window
    backdated = datetime.now(timezone.utc) - timedelta(days=20)

    async def _backdate():
        async with TestingSessionLocal() as session:
            await session.execute(
                update(SupplierDebitNote)
                .where(SupplierDebitNote.id == uuid.UUID(note["id"]))
                .values(applied_at=backdated)
            )
            await session.commit()

    asyncio.run(_backdate())

    today = datetime.now(timezone.utc).date()
    from_iso = (today - timedelta(days=7)).isoformat()
    to_iso = (today + timedelta(days=7)).isoformat()

    r = get_statement(token, supplier_id, from_iso, to_iso)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # 1500 billed before window - 400 credited before window
    assert data["opening_balance"] == "1100.00"
    types = [ln["doc_type"] for ln in data["lines"]]
    assert types == ["OPENING"]  # DN applied pre-window, so no activity line
    assert data["lines"][0]["running_balance"] == "1100.00"
    assert data["totals"]["credited"] == "0.00"
    assert data["totals"]["closing_running"] == "1100.00"
    assert data["amount_due_now"] == "1100.00"


def test_dn_with_payment_ordering_same_day():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "ST3", 1000, days_ago=0)

    create_issue_apply(token, supplier_id, invoice_id, "200")
    pay = client.post(
        "/api/v1/supplier-payments",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
        },
        json={"supplier_invoice_id": invoice_id, "amount": "300"},
    )
    assert pay.status_code in (200, 201), pay.text

    today = datetime.now(timezone.utc).date()
    from_iso = (today - timedelta(days=1)).isoformat()
    to_iso = (today + timedelta(days=1)).isoformat()

    r = get_statement(token, supplier_id, from_iso, to_iso)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    types = [ln["doc_type"] for ln in data["lines"]]
    assert types == [
        "OPENING",
        "SUPPLIER_INVOICE",
        "SUPPLIER_DEBIT_NOTE",
        "SUPPLIER_PAYMENT",
    ]
    assert data["lines"][2]["credit"] == "200.00"
    assert data["lines"][3]["credit"] == "300.00"
    assert data["lines"][3]["running_balance"] == "500.00"
    assert data["totals"]["credited"] == "200.00"
    assert data["totals"]["closing_running"] == "500.00"
    assert data["amount_due_now"] == "500.00"


def test_cancelled_note_never_hits_statement():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    seed_invoice(workspace_id, supplier_id, "ST4", 1000, days_ago=0)

    r = client.post(
        "/api/v1/supplier-debit-notes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier_id,
            "amount": "100",
            "reason": "Then cancelled",
            "issue_date": date.today().isoformat(),
        },
    ).json()["data"]
    client.post(
        f"/api/v1/supplier-debit-notes/{r['id']}/cancel",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    today = datetime.now(timezone.utc).date()
    r = get_statement(
        token,
        supplier_id,
        (today - timedelta(days=1)).isoformat(),
        (today + timedelta(days=1)).isoformat(),
    )
    data = r.json()["data"]
    types = [ln["doc_type"] for ln in data["lines"]]
    assert types == ["OPENING", "SUPPLIER_INVOICE"]
    assert data["totals"]["credited"] == "0.00"
    assert data["totals"]["closing_running"] == "1000.00"
