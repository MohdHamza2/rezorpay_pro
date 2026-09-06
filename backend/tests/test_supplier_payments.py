"""Wave 22 AP — supplier payment recording tests.

Covers: happy-path partial + full settle, eligibility gate, no-overpayment,
idempotent replay, immutability (PUT 405), method/date validation, workspace
isolation, list / ap-balance / invoice-payments surface.
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
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus

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
    email = f"ap_pay_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AP Pay Tester",
            "workspace_name": "AP Pay Workspace",
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
    workspace_id,
    supplier_id,
    number,
    total_amount,
    due=None,
    invoice_date=None,
    status=SupplierInvoiceStatus.APPROVED,
    amount_paid=Decimal("0.00"),
):
    due = due or (date.today() + timedelta(days=15))
    invoice_date = invoice_date or (date.today() - timedelta(days=3))
    total_amount = Decimal(str(total_amount))

    def _dt(d):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    async def insert():
        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=workspace_id,
                supplier_id=supplier_id,
                supplier_invoice_number=number,
                invoice_date=_dt(invoice_date),
                due_date=_dt(due),
                currency="AED",
                subtotal=total_amount,
                discount_amount=Decimal("0.00"),
                vat_amount=Decimal("0.00"),
                total_amount=total_amount,
                amount_paid=amount_paid,
                balance_due=total_amount - amount_paid,
                status=status,
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def post_payment(token, invoice_id, amount, idem_key, method="BANK_TRANSFER", **extra):
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idem_key,
    }
    body = {
        "supplier_invoice_id": str(invoice_id),
        "amount": amount,
        "payment_method": method,
        **extra,
    }
    return client.post("/api/v1/supplier-payments", headers=headers, json=body)


def balance_of(token, invoice_id):
    r = client.get(
        f"/api/v1/supplier-invoices/{invoice_id}/ap-balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


def test_partial_then_full_settlement():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Settle Co", "STL-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "STL-INV-1", 10000)

    r1 = post_payment(token, invoice_id, 4000, "idem-partial")
    assert r1.status_code == 200, r1.json()
    p1 = r1.json()["data"]
    assert p1["status"] == "SUCCESS"
    assert p1["payment_method"] == "BANK_TRANSFER"
    assert float(p1["amount"]) == 4000.0

    bal = balance_of(token, invoice_id)
    assert bal.status_code == 200, bal.json()
    assert float(bal.json()["data"]["balance_due"]) == 6000.0
    assert float(bal.json()["data"]["amount_paid"]) == 4000.0

    r2 = post_payment(token, invoice_id, 6000, "idem-full")
    assert r2.status_code == 200, r2.json()
    assert float(r2.json()["data"]["amount"]) == 6000.0

    bal2 = balance_of(token, invoice_id).json()["data"]
    assert float(bal2["balance_due"]) == 0.0
    assert float(bal2["amount_paid"]) == 10000.0


def test_idempotent_replay_returns_same_payment():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Idem Co", "IDEM-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "IDEM-INV-1", 5000)

    key = "replay-key-1"
    r1 = post_payment(token, invoice_id, 2500, key)
    r2 = post_payment(token, invoice_id, 2500, key)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["data"]["id"] == r1.json()["data"]["id"]

    bal = balance_of(token, invoice_id).json()["data"]
    assert float(bal["amount_paid"]) == 2500.0


def test_overpayment_blocked():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Over Co", "OVR-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "OVR-INV-1", 1000)

    r = post_payment(token, invoice_id, 1500, "idem-over")
    assert r.status_code == 400, r.json()
    assert r.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"

    bal = balance_of(token, invoice_id).json()["data"]
    assert float(bal["amount_paid"]) == 0.0


def test_non_approved_invoice_rejected():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Gate Co", "GATE-001")
    invoice_id = seed_invoice(
        workspace_id,
        supplier_id,
        "GATE-INV-1",
        1000,
        status=SupplierInvoiceStatus.RECEIVED,
    )

    r = post_payment(token, invoice_id, 500, "idem-gate")
    assert r.status_code == 400, r.json()
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_unknown_invoice_404():
    token, _ = register_and_token()
    r = post_payment(token, uuid.uuid4(), 100, "idem-missing")
    assert r.status_code == 404, r.json()
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_missing_idempotency_key_400():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Key Co", "KEY-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "KEY-INV-1", 1000)

    r = client.post(
        "/api/v1/supplier-payments",
        headers={"Authorization": f"Bearer {token}"},
        json={"supplier_invoice_id": str(invoice_id), "amount": 100},
    )
    assert r.status_code == 400, r.json()
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_payment_immutable_put_405():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Immut Co", "IMM-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "IMM-INV-1", 2000)
    pid = post_payment(token, invoice_id, 2000, "idem-immut").json()["data"]["id"]

    r = client.put(
        f"/api/v1/supplier-payments/{pid}",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": 1},
    )
    assert r.status_code == 405, r.json()
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_pdc_method_rejected_422():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Meth Co", "MET-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "MET-INV-1", 1000)

    r = post_payment(token, invoice_id, 500, "idem-method", method="PDC")
    assert r.status_code == 422, r.json()


def test_future_payment_date_rejected_422():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Date Co", "DAT-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "DAT-INV-1", 1000)

    future = (date.today() + timedelta(days=10)).isoformat()
    r = post_payment(token, invoice_id, 500, "idem-date", payment_date=future)
    assert r.status_code == 422, r.json()


def test_cross_workspace_isolation():
    token_a, workspace_a = register_and_token()
    token_b, _workspace_b = register_and_token()
    supplier_a = create_supplier(token_a, "Iso A", "ISO-A1")
    invoice_a = seed_invoice(workspace_a, supplier_a, "ISO-INV-A", 1000)

    r = post_payment(token_b, invoice_a, 500, "idem-iso")
    assert r.status_code == 404, r.json()


def test_list_and_balance_surface():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "List Co", "LST-001")
    inv1 = seed_invoice(workspace_id, supplier_id, "LST-INV-1", 3000)
    inv2 = seed_invoice(workspace_id, supplier_id, "LST-INV-2", 3000)
    post_payment(token, inv1, 1000, "idem-list-a")
    post_payment(token, inv1, 500, "idem-list-b")

    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/supplier-payments", headers=headers)
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 2

    r = client.get(
        f"/api/v1/supplier-payments?supplier_invoice_id={inv1}", headers=headers
    )
    assert r.json()["pagination"]["total"] == 2

    r = client.get(f"/api/v1/supplier-invoices/{inv1}/payments", headers=headers)
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 2
    assert r.json()["pagination"]["has_next"] is False

    r = client.get(f"/api/v1/supplier-invoices/{inv2}/payments", headers=headers)
    assert r.json()["pagination"]["total"] == 0

    r = client.get(f"/api/v1/supplier-payments/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


def test_reference_and_bank_fields_roundtrip():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, "Ref Co", "REF-001")
    invoice_id = seed_invoice(workspace_id, supplier_id, "REF-INV-1", 1000)

    r = post_payment(
        token,
        invoice_id,
        300,
        "idem-ref",
        reference_number="WIRE-77",
        bank_name="Emirates NBD",
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["reference_number"] == "WIRE-77"
    assert data["bank_name"] == "Emirates NBD"
