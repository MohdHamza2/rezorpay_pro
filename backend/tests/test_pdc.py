"""WP-A PDC truth + bounce API tests (addendum §12).

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.auth.utils import hash_password
from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.payment import Payment, PaymentMethod, PaymentStatus, PDCStatus
from app.models.user import User, UserRole
from app.services.credit_control_service import utc_today

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

VALID_TRN = "100123456789012"
SELLER_ADDRESS = "Warehouse 12, Al Quoz, Dubai"
BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _register(prefix: str, workspace_name: str) -> tuple[str, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": prefix,
            "workspace_name": workspace_name,
        },
    )
    assert r.status_code == 201, f"register failed: {r.text}"
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["data"]["workspace_id"]


def _create_client(headers: dict, name: str = "Dealer", **extra) -> str:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _set_workspace(headers: dict, **fields) -> None:
    body = {
        "trn": VALID_TRN,
        "address": SELLER_ADDRESS,
        "credit_limit_default": "100000.00",
    }
    body.update(fields)
    r = client.put("/api/v1/workspaces/me", json=body, headers=headers)
    assert r.status_code == 200, r.text


def _line(qty: str = "1", price: str = "100.00", **extra) -> dict:
    item = {
        "description": "NYM cable",
        "quantity": qty,
        "unit_price": price,
        "tax_rate": extra.pop("tax_rate", "0"),
    }
    item.update(extra)
    return item


def _create_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    today = utc_today()
    body = {
        "client_id": client_id,
        "issue_date": extra.pop("issue_date", today.isoformat()),
        "due_date": extra.pop("due_date", (today + timedelta(days=30)).isoformat()),
        "items": items,
    }
    body.update(extra)
    r = client.post("/api/v1/invoices", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _send(headers: dict, invoice_id: str):
    return client.post(f"/api/v1/invoices/{invoice_id}/send", json={}, headers=headers)


def _sent_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    inv = _create_invoice(headers, client_id, items, **extra)
    sent = _send(headers, inv["id"])
    assert sent.status_code == 200, sent.text
    return sent.json()["data"]


def _ready(prefix: str = "pdc", **client_extra) -> tuple[dict, str]:
    token, _ws = _register(prefix, f"{prefix} WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers, credit_limit="100000.00", **client_extra)
    return headers, client_id


def _pay(
    headers: dict,
    invoice_id: str,
    amount: Decimal,
    method: str = "CASH",
    payment_date: str | None = None,
    idempotency_key: str | None = None,
    **extra,
):
    body = {
        "amount": str(amount),
        "payment_method": method,
        "payment_date": payment_date or utc_today().isoformat(),
        **extra,
    }
    key = idempotency_key if idempotency_key is not None else str(uuid.uuid4())
    hdrs = {**headers}
    if key:
        hdrs["Idempotency-Key"] = key
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments", json=body, headers=hdrs
    )


def _pdc(headers: dict, invoice_id: str, payment_id: str, action: str):
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments/{payment_id}/pdc/{action}",
        json={},
        headers=headers,
    )


def _get_invoice(headers: dict, invoice_id: str) -> dict:
    r = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _balance(headers: dict, invoice_id: str) -> dict:
    r = client.get(f"/api/v1/invoices/{invoice_id}/balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _credit(headers: dict, client_id: str):
    return client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)


def _member_token(workspace_id: str) -> str:
    email = f"mem_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert() -> None:
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
    r = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


async def _insert_success_pdc(invoice_id: str, amount: Decimal) -> str:
    pay_id = uuid.uuid4()
    when = utc_today()
    async with TestingSessionLocal() as session:
        session.add(
            Payment(
                id=pay_id,
                invoice_id=uuid.UUID(invoice_id),
                amount=amount,
                payment_method=PaymentMethod.PDC,
                status=PaymentStatus.SUCCESS,
                pdc_status=PDCStatus.RECEIVED,
                pdc_date=when,
                payment_date=datetime.combine(when, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ),
            )
        )
        await session.commit()
    return str(pay_id)


def test_future_pdc_pending_not_paid():
    headers, client_id = _ready("pdc_future")
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="80.00")])
    due_before = _dec(invoice["balance_due"])
    pay = _pay(
        headers,
        invoice["id"],
        due_before,
        method="PDC",
        pdc_date=(today + timedelta(days=7)).isoformat(),
        pdc_status="CLEARED",
    )
    assert pay.status_code == 200, pay.text
    data = pay.json()["data"]
    assert data["status"] == "PENDING"
    assert data["pdc_status"] == "RECEIVED"
    got = _get_invoice(headers, invoice["id"])
    assert got["status"] == "SENT"
    assert _dec(got["balance_due"]) == due_before
    bal = _balance(headers, invoice["id"])
    assert _dec(bal["amount_paid"]) == Decimal("0.00")
    assert _dec(bal["balance_due"]) == due_before
    stmt = client.get(
        f"/api/v1/clients/{client_id}/ar-statement",
        headers=headers,
        params={
            "from": today.isoformat(),
            "to": (today + timedelta(days=7)).isoformat(),
        },
    )
    assert stmt.status_code == 200, stmt.text
    totals = stmt.json()["data"]["totals"]
    assert _dec(totals["paid"]) == Decimal("0.00")


def test_pdc_missing_date_422():
    headers, client_id = _ready("pdc_nodate")
    invoice = _sent_invoice(headers, client_id, [_line(price="40.00")])
    pay = _pay(headers, invoice["id"], Decimal("10.00"), method="PDC")
    assert pay.status_code == 422, pay.text
    err = pay.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "pdc_date"


def test_pdc_today_or_past_still_pending():
    headers, client_id = _ready("pdc_today")
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="90.00")])
    today_pay = _pay(
        headers,
        invoice["id"],
        Decimal("20.00"),
        method="PDC",
        pdc_date=today.isoformat(),
    )
    assert today_pay.status_code == 200, today_pay.text
    assert today_pay.json()["data"]["status"] == "PENDING"
    assert today_pay.json()["data"]["pdc_status"] == "RECEIVED"
    past_pay = _pay(
        headers,
        invoice["id"],
        Decimal("15.00"),
        method="PDC",
        pdc_date=(today - timedelta(days=1)).isoformat(),
    )
    assert past_pay.status_code == 200, past_pay.text
    assert past_pay.json()["data"]["status"] == "PENDING"
    dep = _pdc(headers, invoice["id"], today_pay.json()["data"]["id"], "deposit")
    assert dep.status_code == 200, dep.text
    assert dep.json()["data"]["pdc_status"] == "DEPOSITED"
    assert dep.json()["data"]["status"] == "PENDING"


def test_cash_bank_card_cheque_immediate_success():
    headers, client_id = _ready("pdc_cash")
    for method in ("CASH", "BANK_TRANSFER", "CREDIT_CARD", "CHEQUE"):
        invoice = _sent_invoice(headers, client_id, [_line(price="25.00")])
        total = _dec(invoice["total_amount"])
        pay = _pay(headers, invoice["id"], total, method=method)
        assert pay.status_code == 200, pay.text
        assert pay.json()["data"]["status"] == "SUCCESS"
        got = _get_invoice(headers, invoice["id"])
        assert got["status"] == "PAID"
        assert _dec(got["balance_due"]) == Decimal("0.00")


def test_hold_client_post_pdc_allowed():
    headers, client_id = _ready("pdc_hold")
    client.put(
        f"/api/v1/clients/{client_id}",
        json={"credit_limit": "0"},
        headers=headers,
    )
    invoice = _sent_invoice(headers, client_id, [_line(price="50.00")])
    hold = _credit(headers, client_id)
    assert hold.status_code == 200, hold.text
    assert hold.json()["data"]["credit_status"] == "HOLD"
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("10.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    assert pay.status_code == 200, pay.text
    assert pay.json().get("error") is None
    assert pay.json()["data"]["status"] == "PENDING"


def test_deposit_before_pdc_date_400():
    headers, client_id = _ready("pdc_early")
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="30.00")])
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("30.00"),
        method="PDC",
        pdc_date=(today + timedelta(days=5)).isoformat(),
    )
    payment_id = pay.json()["data"]["id"]
    dep = _pdc(headers, invoice["id"], payment_id, "deposit")
    assert dep.status_code == 400, dep.text
    err = dep.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "pdc_date"
    listed = client.get(f"/api/v1/invoices/{invoice['id']}/payments", headers=headers)
    assert listed.status_code == 200, listed.text
    row = listed.json()["data"][0]
    assert row["pdc_status"] == "RECEIVED"
    assert row["status"] == "PENDING"


def test_deposit_on_or_after_date_and_idempotent():
    headers, client_id = _ready("pdc_dep")
    invoice = _sent_invoice(headers, client_id, [_line(price="45.00")])
    due = _dec(invoice["balance_due"])
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("12.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    payment_id = pay.json()["data"]["id"]
    first = _pdc(headers, invoice["id"], payment_id, "deposit")
    assert first.status_code == 200, first.text
    assert first.json()["data"]["pdc_status"] == "DEPOSITED"
    assert first.json()["data"]["status"] == "PENDING"
    assert _dec(_balance(headers, invoice["id"])["balance_due"]) == due
    second = _pdc(headers, invoice["id"], payment_id, "deposit")
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == payment_id
    assert second.json()["data"]["pdc_status"] == "DEPOSITED"


def test_clear_after_deposit_pays_invoice():
    headers, client_id = _ready("pdc_clear")
    invoice = _sent_invoice(headers, client_id, [_line(price="70.00")])
    total = _dec(invoice["total_amount"])
    pay = _pay(
        headers,
        invoice["id"],
        total,
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    payment_id = pay.json()["data"]["id"]
    assert _pdc(headers, invoice["id"], payment_id, "deposit").status_code == 200
    cleared = _pdc(headers, invoice["id"], payment_id, "clear")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["status"] == "SUCCESS"
    assert cleared.json()["data"]["pdc_status"] == "CLEARED"
    got = _get_invoice(headers, invoice["id"])
    assert got["status"] == "PAID"
    assert _dec(got["balance_due"]) == Decimal("0.00")
    again = _pdc(headers, invoice["id"], payment_id, "clear")
    assert again.status_code == 200, again.text
    assert again.json()["data"]["status"] == "SUCCESS"


def test_bounce_after_deposit_failed_evaluate():
    headers, _ = _ready("pdc_bounce")
    client_id = _create_client(headers, name="COD", credit_limit="0")
    invoice = _sent_invoice(headers, client_id, [_line(price="55.00")])
    due = _dec(invoice["balance_due"])
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("20.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    payment_id = pay.json()["data"]["id"]
    amount = _dec(pay.json()["data"]["amount"])
    assert _pdc(headers, invoice["id"], payment_id, "deposit").status_code == 200
    bounced = _pdc(headers, invoice["id"], payment_id, "bounce")
    assert bounced.status_code == 200, bounced.text
    data = bounced.json()["data"]
    assert data["status"] == "FAILED"
    assert data["pdc_status"] == "BOUNCED"
    assert _dec(data["amount"]) == amount
    got = _get_invoice(headers, invoice["id"])
    assert got["status"] != "PAID"
    assert _dec(got["balance_due"]) == due
    credit = _credit(headers, client_id)
    assert credit.status_code == 200, credit.text
    assert credit.json()["data"]["credit_status"] == "HOLD"
    again = _pdc(headers, invoice["id"], payment_id, "bounce")
    assert again.status_code == 200, again.text
    assert again.json()["data"]["pdc_status"] == "BOUNCED"


def test_return_from_received_not_from_deposited():
    headers, client_id = _ready("pdc_ret")
    invoice = _sent_invoice(headers, client_id, [_line(price="60.00")])
    received = _pay(
        headers,
        invoice["id"],
        Decimal("10.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    rid = received.json()["data"]["id"]
    ret = _pdc(headers, invoice["id"], rid, "return")
    assert ret.status_code == 200, ret.text
    assert ret.json()["data"]["status"] == "CANCELLED"
    assert ret.json()["data"]["pdc_status"] == "RETURNED"
    deposited = _pay(
        headers,
        invoice["id"],
        Decimal("10.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    did = deposited.json()["data"]["id"]
    assert _pdc(headers, invoice["id"], did, "deposit").status_code == 200
    forbidden = _pdc(headers, invoice["id"], did, "return")
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["error"]["code"] == "INVALID_STATE"


def test_illegal_transitions_403():
    headers, client_id = _ready("pdc_ill")
    invoice = _sent_invoice(headers, client_id, [_line(price="200.00")])
    pdc = _pay(
        headers,
        invoice["id"],
        Decimal("20.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    pid = pdc.json()["data"]["id"]
    bad_clear = _pdc(headers, invoice["id"], pid, "clear")
    assert bad_clear.status_code == 403, bad_clear.text
    assert bad_clear.json()["error"]["code"] == "INVALID_STATE"
    cheque_inv = _sent_invoice(headers, client_id, [_line(price="15.00")])
    cheque = _pay(
        headers, cheque_inv["id"], _dec(cheque_inv["total_amount"]), method="CHEQUE"
    )
    bounce_cheque = _pdc(
        headers, cheque_inv["id"], cheque.json()["data"]["id"], "bounce"
    )
    assert bounce_cheque.status_code == 403, bounce_cheque.text
    assert bounce_cheque.json()["error"]["code"] == "INVALID_STATE"
    assert _pdc(headers, invoice["id"], pid, "deposit").status_code == 200
    cleared = _pdc(headers, invoice["id"], pid, "clear")
    assert cleared.status_code == 200, cleared.text
    bounce_cleared = _pdc(headers, invoice["id"], pid, "bounce")
    assert bounce_cleared.status_code == 403, bounce_cleared.text
    assert bounce_cleared.json()["error"]["code"] == "INVALID_STATE"
    hist_inv = _sent_invoice(headers, client_id, [_line(price="18.00")])
    hist_id = asyncio.run(_insert_success_pdc(hist_inv["id"], Decimal("5.00")))
    hist_clear = _pdc(headers, hist_inv["id"], hist_id, "clear")
    assert hist_clear.status_code == 200, hist_clear.text
    assert hist_clear.json()["data"]["status"] == "SUCCESS"
    assert _dec(hist_clear.json()["data"]["amount"]) == Decimal("5.00")
    hist_bounce = _pdc(headers, hist_inv["id"], hist_id, "bounce")
    assert hist_bounce.status_code == 403, hist_bounce.text
    assert hist_bounce.json()["error"]["code"] == "INVALID_STATE"
    hist_return = _pdc(headers, hist_inv["id"], hist_id, "return")
    assert hist_return.status_code == 403, hist_return.text
    assert hist_return.json()["error"]["code"] == "INVALID_STATE"
    hist_deposit = _pdc(headers, hist_inv["id"], hist_id, "deposit")
    assert hist_deposit.status_code == 403, hist_deposit.text
    assert hist_deposit.json()["error"]["code"] == "INVALID_STATE"
    hist_listed = client.get(
        f"/api/v1/invoices/{hist_inv['id']}/payments", headers=headers
    )
    assert hist_listed.status_code == 200, hist_listed.text
    hist_row = next(row for row in hist_listed.json()["data"] if row["id"] == hist_id)
    assert hist_row["status"] == "SUCCESS"
    assert hist_row["pdc_status"] == "RECEIVED"
    assert _dec(hist_row["amount"]) == Decimal("5.00")


def test_over_clear_400_no_credit_balance():
    headers, client_id = _ready("pdc_over")
    invoice = _sent_invoice(headers, client_id, [_line(price="100.00")])
    total = _dec(invoice["total_amount"])
    parked_before = _dec(_credit(headers, client_id).json()["data"]["credit_balance"])
    pdc = _pay(
        headers,
        invoice["id"],
        total,
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    assert pdc.status_code == 200, pdc.text
    pid = pdc.json()["data"]["id"]
    assert _pdc(headers, invoice["id"], pid, "deposit").status_code == 200
    cash = _pay(headers, invoice["id"], total, method="CASH")
    assert cash.status_code == 200, cash.text
    assert cash.json()["data"]["status"] == "SUCCESS"
    over = _pdc(headers, invoice["id"], pid, "clear")
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"
    listed = client.get(f"/api/v1/invoices/{invoice['id']}/payments", headers=headers)
    rows = {row["id"]: row for row in listed.json()["data"]}
    assert rows[pid]["status"] == "PENDING"
    assert rows[pid]["pdc_status"] == "DEPOSITED"
    assert _dec(rows[pid]["amount"]) == total
    assert rows[cash.json()["data"]["id"]]["status"] == "SUCCESS"
    parked_after = _dec(_credit(headers, client_id).json()["data"]["credit_balance"])
    assert parked_after == parked_before


def test_put_405_other_workspace_404():
    headers, client_id = _ready("pdc_put")
    invoice = _sent_invoice(headers, client_id, [_line(price="22.00")])
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("5.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    pid = pay.json()["data"]["id"]
    same = client.put(
        f"/api/v1/invoices/{invoice['id']}/payments/{pid}",
        json={"status": "FAILED"},
        headers=headers,
    )
    assert same.status_code == 405, same.text
    assert same.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    listed = client.get(f"/api/v1/invoices/{invoice['id']}/payments", headers=headers)
    assert listed.json()["data"][0]["status"] == "PENDING"
    token_b, _ = _register("pdc_put_b", "PDC Put B")
    other = client.put(
        f"/api/v1/invoices/{invoice['id']}/payments/{pid}",
        json={"status": "FAILED"},
        headers=_headers(token_b),
    )
    assert other.status_code == 404, other.text
    assert other.json()["error"]["code"] == "NOT_FOUND"
    assert other.status_code != 405


def test_isolation_pdc_actions_404():
    headers_a, client_id = _ready("pdc_iso_a")
    invoice = _sent_invoice(headers_a, client_id, [_line(price="33.00")])
    pay = _pay(
        headers_a,
        invoice["id"],
        Decimal("8.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    pid = pay.json()["data"]["id"]
    token_b, _ = _register("pdc_iso_b", "PDC Iso B")
    headers_b = _headers(token_b)
    for action in ("deposit", "clear", "bounce", "return"):
        r = _pdc(headers_b, invoice["id"], pid, action)
        assert r.status_code == 404, f"{action}: {r.text}"
        assert r.json()["error"]["code"] == "NOT_FOUND"
        assert r.status_code != 403
    missing = _pdc(headers_a, invoice["id"], str(uuid.uuid4()), "deposit")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_member_can_post_payment_not_pdc_actions():
    token, workspace_id = _register("pdc_mem", "PDC Member WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers, credit_limit="100000.00")
    invoice = _sent_invoice(headers, client_id, [_line(price="40.00")])
    member = _headers(_member_token(workspace_id))
    pay = _pay(
        member,
        invoice["id"],
        Decimal("9.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
    )
    assert pay.status_code == 200, pay.text
    pid = pay.json()["data"]["id"]
    owner_dep = _pdc(headers, invoice["id"], pid, "deposit")
    assert owner_dep.status_code == 200, owner_dep.text
    forbidden = _pdc(member, invoice["id"], pid, "clear")
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_idempotency_key_create_not_pdc_actions():
    headers, client_id = _ready("pdc_idem")
    invoice = _sent_invoice(headers, client_id, [_line(price="50.00")])
    missing = client.post(
        f"/api/v1/invoices/{invoice['id']}/payments",
        json={
            "amount": "10.00",
            "payment_method": "PDC",
            "payment_date": utc_today().isoformat(),
            "pdc_date": utc_today().isoformat(),
        },
        headers=headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    key = str(uuid.uuid4())
    first = _pay(
        headers,
        invoice["id"],
        Decimal("10.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
        idempotency_key=key,
    )
    second = _pay(
        headers,
        invoice["id"],
        Decimal("10.00"),
        method="PDC",
        pdc_date=utc_today().isoformat(),
        idempotency_key=key,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    pid = first.json()["data"]["id"]
    dep = client.post(
        f"/api/v1/invoices/{invoice['id']}/payments/{pid}/pdc/deposit",
        json={},
        headers=headers,
    )
    assert dep.status_code == 200, dep.text
    assert dep.json()["data"]["pdc_status"] == "DEPOSITED"


def test_fta_cn_hold_overpay_alembic():
    headers, client_id = _ready("pdc_compat")
    invoice = _sent_invoice(headers, client_id, [_line(price="12.00")])
    assert invoice["status"] == "SENT"
    over = _pay(headers, invoice["id"], _dec(invoice["total_amount"]) + Decimal("1.00"))
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"
    hold_client = _create_client(headers, name="HoldCN", credit_limit="0")
    hold_inv = _sent_invoice(headers, hold_client, [_line(price="80.00")])
    assert _credit(headers, hold_client).json()["data"]["credit_status"] == "HOLD"
    cn = client.post(
        "/api/v1/credit-notes",
        json={
            "invoice_id": hold_inv["id"],
            "reason": "INVOICE_ERROR",
            "items": [
                {
                    "invoice_item_id": hold_inv["items"][0]["id"],
                    "quantity": hold_inv["items"][0]["quantity"],
                }
            ],
        },
        headers=headers,
    )
    assert cn.status_code == 201, cn.text
    issued = client.post(
        f"/api/v1/credit-notes/{cn.json()['data']['id']}/issue",
        json={},
        headers=headers,
    )
    assert issued.status_code == 200, issued.text
    alembic_bin = shutil.which("alembic")
    assert alembic_bin, "alembic CLI not found"
    heads = subprocess.run(
        [alembic_bin, "heads"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert heads.returncode == 0, heads.stdout + heads.stderr
    assert "6d27f753e9e3" in (heads.stdout + heads.stderr)
    check = subprocess.run(
        [alembic_bin, "check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    combined = check.stdout + check.stderr
    assert "No new upgrade operations detected" in combined
