"""Wave 24 — PDC-to-supplier (AP post-dated cheque issued) lifecycle tests.

Covers: PDC insert rule (PENDING + RECEIVED, balance unchanged, stays APPROVED),
pdc_date required + deposit-date gate, deposit/clear/bounce/return transitions,
over-clear 400 lock, illegal transitions 403, idempotent 200s, the supplier
statement mapping (payment pending vs cleared), MEMBER RBAC 403, and cross-workspace
isolation 404 (never 403).
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
    email = f"pdcsp_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "PDC Supplier Tester",
            "workspace_name": "PDC Supplier Workspace",
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


def create_supplier(token, name="PDCCo"):
    r = client.post(
        "/api/v1/suppliers",
        headers=_headers(token),
        json={
            "name": name,
            "supplier_code": f"PD{uuid.uuid4().hex[:4]}",
            "email": "pdc@example.com",
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


def post_payment(token, invoice_id, amount, idem_key, method="PDC", pdc_date=None):
    body = {
        "supplier_invoice_id": str(invoice_id),
        "amount": amount,
        "payment_method": method,
    }
    if method == "PDC":
        body["pdc_date"] = (pdc_date or (utc_today() + timedelta(days=7))).isoformat()
    return client.post(
        "/api/v1/supplier-payments",
        headers={**_headers(token), "Idempotency-Key": idem_key},
        json=body,
    )


def ap_balance(token, invoice_id):
    r = client.get(
        f"/api/v1/supplier-invoices/{invoice_id}/ap-balance", headers=_headers(token)
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def pdc_action(token, invoice_id, payment_id, action, body=None):
    url = f"/api/v1/supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/{action}"
    return client.post(url, headers=_headers(token), json=body or {})


def test_future_pdc_pending_no_balance_effect():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "P1", 10000)

    r = post_payment(token, invoice_id, 4000, "pdc-future-1")
    assert r.status_code == 200, r.json()
    p = r.json()["data"]
    assert p["status"] == "PENDING"
    assert p["pdc_status"] == "RECEIVED"
    assert p["payment_method"] == "PDC"
    assert p["pdc_date"] is not None

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "0.00"
    assert bal["balance_due"] == "10000.00"


def test_pdc_date_required_schema_validator():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="ReqCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P2", 1000)

    r = client.post(
        "/api/v1/supplier-payments",
        headers={**_headers(token), "Idempotency-Key": "pdc-missing-date"},
        json={
            "supplier_invoice_id": str(invoice_id),
            "amount": 100,
            "payment_method": "PDC",
        },
    )
    assert r.status_code == 422, r.text


def test_pdc_dated_today_still_pending_deposit_allowed():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="TodayCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P3", 1000)

    r = post_payment(token, invoice_id, 100, "pdc-today-1", pdc_date=utc_today())
    assert r.status_code == 200, r.json()
    p = r.json()["data"]
    assert p["status"] == "PENDING"
    assert p["pdc_status"] == "RECEIVED"


def test_non_pdc_methods_still_success():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="CashCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P4", 1000)

    r = post_payment(token, invoice_id, 400, "cash-1", method="CASH")
    assert r.status_code == 200, r.json()
    assert r.json()["data"]["status"] == "SUCCESS"
    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "400.00"
    assert bal["balance_due"] == "600.00"


def test_deposit_before_pdc_date_rejected():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="BeforeCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P5", 1000)

    r = post_payment(
        token, invoice_id, 100, "pdc-before-1", pdc_date=utc_today() + timedelta(days=3)
    )
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    resp = pdc_action(token, invoice_id, pid, "deposit")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["field"] == "pdc_date"


def test_deposit_then_clear_lifecycle():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="LifeCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P6", 10000)

    r = post_payment(token, invoice_id, 10000, "pdc-life-1", pdc_date=utc_today())
    assert r.status_code == 200, r.json()
    pid = r.json()["data"]["id"]

    d = pdc_action(token, invoice_id, pid, "deposit")
    assert d.status_code == 200, d.text
    assert d.json()["data"]["pdc_status"] == "DEPOSITED"
    assert d.json()["data"]["status"] == "PENDING"

    bal = ap_balance(token, invoice_id)
    assert bal["balance_due"] == "10000.00"

    d2 = pdc_action(token, invoice_id, pid, "deposit")
    assert d2.status_code == 200, d2.text

    c = pdc_action(token, invoice_id, pid, "clear")
    assert c.status_code == 200, c.text
    cleared = c.json()["data"]
    assert cleared["status"] == "SUCCESS"
    assert cleared["pdc_status"] == "CLEARED"

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "10000.00"
    assert bal["balance_due"] == "0.00"


def test_bounce_after_deposit_failed_no_balance_change():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="BounceCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P7", 10000)

    r = post_payment(token, invoice_id, 4000, "pdc-bounce-1", pdc_date=utc_today())
    pid = r.json()["data"]["id"]

    b = pdc_action(token, invoice_id, pid, "bounce")
    assert b.status_code == 403, b.text  # must DEPOSIT first

    d = pdc_action(token, invoice_id, pid, "deposit")
    assert d.status_code == 200, d.text

    b = pdc_action(token, invoice_id, pid, "bounce")
    assert b.status_code == 200, b.text
    bounced = b.json()["data"]
    assert bounced["status"] == "FAILED"
    assert bounced["pdc_status"] == "BOUNCED"
    assert bounced["amount"] == "4000.00"

    bal = ap_balance(token, invoice_id)
    assert bal["balance_due"] == "10000.00"

    b2 = pdc_action(token, invoice_id, pid, "bounce")
    assert b2.status_code == 200, b2.text


def test_return_from_received_cancelled():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="ReturnCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P8", 10000)

    r = post_payment(token, invoice_id, 100, "pdc-return-1")
    pid = r.json()["data"]["id"]

    ret = pdc_action(token, invoice_id, pid, "return")
    assert ret.status_code == 200, ret.text
    returned = ret.json()["data"]
    assert returned["status"] == "CANCELLED"
    assert returned["pdc_status"] == "RETURNED"


def test_return_from_deposited_forbidden():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="DepReturnCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P9", 10000)

    r = post_payment(token, invoice_id, 100, "pdc-depreturn-1", pdc_date=utc_today())
    pid = r.json()["data"]["id"]
    d = pdc_action(token, invoice_id, pid, "deposit")
    assert d.status_code == 200, d.text

    ret = pdc_action(token, invoice_id, pid, "return")
    assert ret.status_code == 403, ret.text


def test_illegal_transitions_forbidden():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="IllegalCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P10", 10000)

    # RECEIVED -> clear is illegal
    r = post_payment(token, invoice_id, 100, "pdc-illegal-1")
    pid = r.json()["data"]["id"]
    c = pdc_action(token, invoice_id, pid, "clear")
    assert c.status_code == 403, c.text

    # CHEQUE -> bounce is illegal (not a PDC)
    token2, ws2 = register_and_token()
    sup2 = create_supplier(token2, name="CheqCo")
    inv2 = seed_invoice(ws2, sup2, "P10B", 1000)
    r2 = post_payment(token2, inv2, 100, "pdc-cheq", method="CHEQUE")
    pid2 = r2.json()["data"]["id"]
    b = pdc_action(token2, inv2, pid2, "bounce")
    assert b.status_code == 403, b.text
    assert b.json()["error"]["code"] == "INVALID_STATE"


def test_over_clear_rejected_no_negative_amount():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="OverCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P11", 1000)

    r1 = post_payment(token, invoice_id, 1000, "pdc-over-1", pdc_date=utc_today())
    assert r1.status_code == 200, r1.json()
    pid1 = r1.json()["data"]["id"]
    d1 = pdc_action(token, invoice_id, pid1, "deposit")
    assert d1.status_code == 200, d1.text

    r2 = post_payment(token, invoice_id, 1000, "pdc-over-2", method="CASH")
    assert r2.status_code == 200, r2.json()

    c = pdc_action(token, invoice_id, pid1, "clear")
    assert c.status_code == 400, c.text
    assert c.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"

    bal = ap_balance(token, invoice_id)
    assert bal["amount_paid"] == "1000.00"
    assert bal["balance_due"] == "0.00"


def test_statement_pending_then_cleared_mapping():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="StmtPDCCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P12", 1000)

    r = post_payment(token, invoice_id, 400, "pdc-stmt-1", pdc_date=utc_today())
    pid = r.json()["data"]["id"]

    today = utc_today()
    from_iso = (today - timedelta(days=1)).isoformat()
    to_iso = (today + timedelta(days=1)).isoformat()

    st = client.get(
        f"/api/v1/suppliers/{supplier_id}/statement?from={from_iso}&to={to_iso}",
        headers=_headers(token),
    )
    assert st.status_code == 200, st.text
    data = st.json()["data"]

    pending = [
        ln for ln in data["lines"] if ln["doc_type"] == "SUPPLIER_PAYMENT_PENDING"
    ]
    assert len(pending) == 1
    assert pending[0]["pending_amount"] == "400.00"
    assert pending[0]["credit"] == "0.00"
    assert pending[0]["cleared_cash"] is False
    assert data["totals"]["pending"] == "400.00"
    assert data["totals"]["paid"] == "0.00"

    d = pdc_action(token, invoice_id, pid, "deposit")
    assert d.status_code == 200, d.text
    c = pdc_action(token, invoice_id, pid, "clear")
    assert c.status_code == 200, c.text

    st2 = client.get(
        f"/api/v1/suppliers/{supplier_id}/statement?from={from_iso}&to={to_iso}",
        headers=_headers(token),
    )
    data2 = st2.json()["data"]
    cleared = [ln for ln in data2["lines"] if ln["doc_type"] == "SUPPLIER_PAYMENT"]
    assert len(cleared) == 1
    assert data2["totals"]["paid"] == "400.00"
    assert data2["totals"]["pending"] == "0.00"


def test_bounced_and_returned_omitted_from_statement():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="OmitCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P13", 1000)

    r1 = post_payment(token, invoice_id, 100, "pdc-omit-1", pdc_date=utc_today())
    pid1 = r1.json()["data"]["id"]
    pdc_action(token, invoice_id, pid1, "deposit")
    pdc_action(token, invoice_id, pid1, "bounce")

    r2 = post_payment(token, invoice_id, 100, "pdc-omit-2", pdc_date=utc_today())
    pid2 = r2.json()["data"]["id"]
    pdc_action(token, invoice_id, pid2, "return")

    today = utc_today()
    st = client.get(
        f"/api/v1/suppliers/{supplier_id}/statement?from={(today - timedelta(days=1)).isoformat()}&to={(today + timedelta(days=1)).isoformat()}",
        headers=_headers(token),
    )
    data = st.json()["data"]
    doc_types = {ln["doc_type"] for ln in data["lines"]}
    assert "SUPPLIER_PAYMENT_PENDING" not in doc_types
    assert "SUPPLIER_PAYMENT" not in doc_types
    assert data["totals"]["pending"] == "0.00"
    assert data["totals"]["paid"] == "0.00"


def test_member_cannot_pdc_action():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token, name="MemberCo")
    invoice_id = seed_invoice(workspace_id, supplier_id, "P14", 10000)

    r = post_payment(token, invoice_id, 100, "pdc-member-1", pdc_date=utc_today())
    pid = r.json()["data"]["id"]

    email = f"member_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="Member",
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

    # MEMBER can still record a PDC
    r2 = post_payment(
        member_token, invoice_id, 100, "pdc-member-2", pdc_date=utc_today()
    )
    assert r2.status_code == 200, r2.json()

    resp = pdc_action(member_token, invoice_id, pid, "deposit")
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_isolation_cross_workspace_404():
    token_a, ws_a = register_and_token()
    supplier_a = create_supplier(token_a, name="IsolateA")
    invoice_a = seed_invoice(ws_a, supplier_a, "PA", 1000)

    r = post_payment(token_a, invoice_a, 100, "pdc-iso-a", pdc_date=utc_today())
    pid_a = r.json()["data"]["id"]

    token_b, _ = register_and_token()
    resp = pdc_action(token_b, invoice_a, pid_a, "deposit")
    assert resp.status_code == 404, resp.text
