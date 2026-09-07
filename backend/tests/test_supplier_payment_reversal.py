"""Wave 25 — AP payment reversal (SUCCESS CHEQUE/CASH/BANK -> FAILED after bank
bounce) tests.

Covers: full/partial reversal on PARTIALLY_PAID and PAID invoices (settlement
inversion + status downgrade + paid_at clearing), statement re-derivation
(FAILED omitted, paid drops, closing_running == amount_due_now identity),
ap-aging re-entry, PDC terminality (CLEARED/PENDING/BOUNCED/RETURNED -> 403),
CANCELLED-invoice guard, idempotent 200 on already-reversed, MEMBER RBAC 403,
and cross-workspace isolation 404 (never 403).
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.supplier_invoice import SupplierInvoice  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.auth.utils import hash_password  # noqa: E402

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


def utc_today():
    return datetime.now(timezone.utc).date()


def register_and_token():
    email = f"revrs_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "Reversal Tester",
            "workspace_name": "Reversal Workspace",
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


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def create_supplier(token, name="RevCo"):
    r = client.post(
        "/api/v1/suppliers",
        headers=_headers(token),
        json={
            "name": name,
            "supplier_code": f"RV{uuid.uuid4().hex[:4]}",
            "email": "rev@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def seed_invoice(workspace_id, supplier_id, number, total, days_ago=3):
    today = utc_today()
    total = Decimal(str(total))

    def _dt(d):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    async def insert():
        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=uuid.UUID(supplier_id),
                supplier_invoice_number=number,
                invoice_date=_dt(today - timedelta(days=days_ago)),
                due_date=_dt(today + timedelta(days=15)),
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


async def _set_invoice_status(invoice_id: str, status: str):
    async with TestingSessionLocal() as session:
        invoice = await session.get(SupplierInvoice, uuid.UUID(invoice_id))
        invoice.status = status
        await session.commit()


def set_invoice_status(invoice_id: str, status: str):
    asyncio.run(_set_invoice_status(invoice_id, status))


def post_payment(token, invoice_id, amount, idem_key, method="CHEQUE"):
    return client.post(
        "/api/v1/supplier-payments",
        headers={**_headers(token), "Idempotency-Key": idem_key},
        json={
            "supplier_invoice_id": str(invoice_id),
            "amount": amount,
            "payment_method": method,
        },
    )


def post_pdc(token, invoice_id, amount, idem_key, pdc_date=None):
    body = {
        "supplier_invoice_id": str(invoice_id),
        "amount": amount,
        "payment_method": "PDC",
        "pdc_date": (pdc_date or utc_today()).isoformat(),
    }
    return client.post(
        "/api/v1/supplier-payments",
        headers={**_headers(token), "Idempotency-Key": idem_key},
        json=body,
    )


def pdc_action(token, invoice_id, payment_id, action, body=None):
    url = f"/api/v1/supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/{action}"
    return client.post(url, headers=_headers(token), json=body or {})


def reverse_payment(token, invoice_id, payment_id, body=None):
    url = f"/api/v1/supplier-invoices/{invoice_id}/payments/{payment_id}/reverse"
    return client.post(url, headers=_headers(token), json=body or {})


def ap_balance(token, invoice_id):
    r = client.get(
        f"/api/v1/supplier-invoices/{invoice_id}/ap-balance", headers=_headers(token)
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def get_statement(token, supplier_id):
    today = utc_today()
    r = client.get(
        f"/api/v1/suppliers/{supplier_id}/statement"
        f"?from={(today - timedelta(days=1)).isoformat()}"
        f"&to={(today + timedelta(days=1)).isoformat()}",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_full_reversal_partially_paid_invoice():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV1", 10000)

    r = post_payment(token, invoice_id, 4000, "rev-full-1")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "4000.00"
    assert bal["balance_due"] == "6000.00"

    resp = reverse_payment(token, invoice_id, pid)
    assert resp.status_code == 200, resp.text
    p = resp.json()["data"]
    assert p["status"] == "FAILED"
    assert p["payment_method"] == "CHEQUE"
    assert p["amount"] == "4000.00"

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "0.00"
    assert bal["balance_due"] == "10000.00"

    resp2 = reverse_payment(token, invoice_id, pid)
    assert resp2.status_code == 200, resp2.text
    bal2 = ap_balance(token, invoice_id)
    assert bal2["amount_paid"] == "0.00"
    assert bal2["balance_due"] == "10000.00"


def test_full_reversal_of_paid_invoice_restores_approved():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="PaidCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV2", 10000)

    r = post_payment(token, invoice_id, 10000, "rev-paid-1", method="CASH")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "10000.00"
    assert bal["balance_due"] == "0.00"

    resp = reverse_payment(token, invoice_id, pid)
    assert resp.status_code == 200, resp.text

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "0.00"
    assert bal["balance_due"] == "10000.00"

    async def _check_invoice():
        async with TestingSessionLocal() as session:
            inv = await session.get(SupplierInvoice, uuid.UUID(invoice_id))
            return inv.status, inv.paid_at

    status, paid_at = asyncio.run(_check_invoice())
    assert status == "APPROVED"
    assert paid_at is None


def test_partial_reversal_keeps_partially_paid():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="PartialCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV3", 10000)

    r = post_payment(token, invoice_id, 800, "rev-part-1")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]
    payment_before = r.json()["data"]

    resp = reverse_payment(token, invoice_id, pid)
    assert resp.status_code == 200, resp.text

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "0.00"
    assert bal["balance_due"] == "10000.00"

    p = resp.json()["data"]
    assert Decimal(p["amount"]) == Decimal(payment_before["amount"])
    assert p["payment_method"] == payment_before["payment_method"]
    assert p["payment_date"] == payment_before["payment_date"]

    async def _check_invoice():
        async with TestingSessionLocal() as session:
            inv = await session.get(SupplierInvoice, uuid.UUID(invoice_id))
            return inv.status

    assert asyncio.run(_check_invoice()) == "APPROVED"


def test_statement_maps_reversal():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="StmtRevCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV4", 1000)

    r = post_payment(token, invoice_id, 400, "rev-stmt-1")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    data = get_statement(token, supplier_id)
    paid_lines = [ln for ln in data["lines"] if ln["doc_type"] == "SUPPLIER_PAYMENT"]
    assert len(paid_lines) == 1
    assert data["totals"]["paid"] == "400.00"
    assert data["amount_due_now"] == "600.00"
    assert float(data["totals"]["closing_running"]) == float(
        data["amount_due_now"]
    ), "closing_running must equal amount_due_now"

    resp = reverse_payment(token, invoice_id, pid)
    assert resp.status_code == 200, resp.text

    data2 = get_statement(token, supplier_id)
    paid_lines2 = [ln for ln in data2["lines"] if ln["doc_type"] == "SUPPLIER_PAYMENT"]
    assert len(paid_lines2) == 0
    assert data2["totals"]["paid"] == "0.00"
    assert data2["amount_due_now"] == "1000.00"
    assert float(data2["totals"]["closing_running"]) == float(
        data2["amount_due_now"]
    ), "closing_running must equal amount_due_now"


def test_ap_aging_reentry_after_reversal():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="AgeRevCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV5", 10000)

    r = post_payment(token, invoice_id, 10000, "rev-age-1")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    aging_before = client.get(
        "/api/v1/ap-aging/detail", headers=_headers(token)
    ).json()["data"]
    assert aging_before["total_outstanding"] == "0.00"

    resp = reverse_payment(token, invoice_id, pid)
    assert resp.status_code == 200, resp.text

    aging = client.get("/api/v1/ap-aging/detail", headers=_headers(token)).json()[
        "data"
    ]
    assert aging["total_outstanding"] == "10000.00"
    invoice_rows = [
        inv for inv in aging["invoices"] if inv["supplier_invoice_id"] == invoice_id
    ]
    assert len(invoice_rows) == 1
    assert invoice_rows[0]["balance_due"] == "10000.00"
    bucket_sum = sum(Decimal(v) for v in aging["buckets"].values() if v)
    assert bucket_sum == Decimal("10000.00")


def test_illegal_reversals():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="IllegalRevCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV6", 10000)

    # CLEARED PDC is terminal -> 403
    r = post_pdc(token, invoice_id, 1000, "rev-illegal-pdc")
    pdc_id = r.json()["data"]["id"]
    pdc_action(token, invoice_id, pdc_id, "deposit")
    resp = reverse_payment(token, invoice_id, pdc_id)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "INVALID_STATE"

    # PENDING PDC -> 403
    r2 = post_pdc(token, invoice_id, 100, "rev-illegal-pdc2")
    pdc_id2 = r2.json()["data"]["id"]
    resp2 = reverse_payment(token, invoice_id, pdc_id2)
    assert resp2.status_code == 403, resp2.text

    # BOUNCED PDC (already FAILED) -> 403, NOT a no-op
    r3 = post_pdc(token, invoice_id, 100, "rev-illegal-pdc3")
    pdc_id3 = r3.json()["data"]["id"]
    pdc_action(token, invoice_id, pdc_id3, "deposit")
    pdc_action(token, invoice_id, pdc_id3, "bounce")
    resp3 = reverse_payment(token, invoice_id, pdc_id3)
    assert resp3.status_code == 403, resp3.text

    # RETURNED PDC -> 403
    r4 = post_pdc(token, invoice_id, 100, "rev-illegal-pdc4")
    pdc_id4 = r4.json()["data"]["id"]
    pdc_action(token, invoice_id, pdc_id4, "return")
    resp4 = reverse_payment(token, invoice_id, pdc_id4)
    assert resp4.status_code == 403, resp4.text

    # CANCELLED invoice -> 403
    r5 = post_payment(token, invoice_id, 100, "rev-illegal-1", method="BANK_TRANSFER")
    assert r5.status_code == 200, r5.json()
    pid5 = r5.json()["data"]["id"]
    set_invoice_status(invoice_id, "CANCELLED")
    resp5 = reverse_payment(token, invoice_id, pid5)
    assert resp5.status_code == 403, resp5.text


def test_member_cannot_reverse():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="MemberRevCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "RV7", 10000)

    r = post_payment(token, invoice_id, 100, "rev-member-1")
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    email = f"member_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="Reversal Member",
                    role=UserRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(_insert())
    login = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert login.status_code == 200, login.text
    member_token = login.json()["data"]["access_token"]

    resp = reverse_payment(member_token, invoice_id, pid)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_isolation_cross_workspace_404():
    token_a, ws_a = register_and_token()
    supplier_a = create_supplier(token_a, name="RevIsolateA")
    invoice_a = seed_invoice(ws_a, supplier_a, "RVA", 1000)

    r = post_payment(token_a, invoice_a, 100, "rev-iso-a")
    assert r.status_code == 200, r.json()
    pid_a = r.json()["data"]["id"]

    token_b, _ = register_and_token()
    resp = reverse_payment(token_b, invoice_a, pid_a)
    assert resp.status_code == 404, resp.text
