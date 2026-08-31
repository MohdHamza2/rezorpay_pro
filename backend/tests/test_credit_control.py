"""WP-A credit HOLD / overdue API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

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
from app.models.invoice import Invoice

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


def _utc_today():
    return datetime.now(timezone.utc).date()


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _create_client(headers: dict, name: str = "Dealer", **extra) -> dict:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _set_workspace(headers: dict, **fields) -> dict:
    body = {"trn": VALID_TRN, "address": SELLER_ADDRESS}
    body.update(fields)
    r = client.put("/api/v1/workspaces/me", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _line(qty: str = "1", price: str = "100.00", **extra) -> dict:
    item = {
        "description": "NYM cable",
        "quantity": qty,
        "unit_price": price,
        "tax_rate": "0",
    }
    item.update(extra)
    return item


def _create_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    today = _utc_today()
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


def _pay(headers: dict, invoice_id: str, amount: Decimal):
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={
            "amount": str(amount),
            "payment_method": "CASH",
            "payment_date": _utc_today().isoformat(),
        },
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )


def _credit(headers: dict, client_id: str):
    return client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)


async def _set_due_date(invoice_id: str, due) -> None:
    async with TestingSessionLocal() as session:
        inv = await session.get(Invoice, uuid.UUID(invoice_id))
        assert inv is not None
        inv.due_date = due
        await session.commit()


async def _invoice_status(invoice_id: str) -> str:
    async with TestingSessionLocal() as session:
        inv = await session.get(Invoice, uuid.UUID(invoice_id))
        assert inv is not None
        return inv.status.value


def _adhoc_quote_item(**extra) -> dict:
    item = {
        "description": "NYM 3x2.5 cable",
        "quantity": "10",
        "unit_price": "100.00",
        "tax_rate": "0",
    }
    item.update(extra)
    return item


def test_create_client_omits_credit_inherits_workspace_default():
    token, _ = _register("cc_omit", "Credit Omit WS")
    headers = _headers(token)
    data = _create_client(headers)
    assert data["payment_terms_days"] == 0
    assert data["credit_limit"] is None
    assert data["credit_status"] == "ACTIVE"
    assert _dec(data["effective_credit_limit"]) == Decimal("0.00")
    assert _dec(data["exposure"]) == Decimal("0.00")


def test_payment_terms_allowlist_and_extra_key_422():
    token, _ = _register("cc_terms", "Credit Terms WS")
    headers = _headers(token)
    for days in (15, 90):
        r = client.post(
            "/api/v1/clients",
            json={"name": "Bad", "payment_terms_days": days},
            headers=headers,
        )
        assert r.status_code == 422, r.text
    r = client.post(
        "/api/v1/clients",
        json={"name": "Bad", "credit_status": "HOLD"},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    r = client.post(
        "/api/v1/clients",
        json={"name": "Bad", "unknown_field": 1},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_exposure_draft_sent_payment_cancelled_fils():
    token, _ = _register("cc_exp", "Credit Exp WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="10000.00")
    dealer = _create_client(headers, credit_limit="10000.00")
    cid = dealer["id"]
    draft = _create_invoice(headers, cid, [_line(price="10.01")])
    assert draft["status"] == "DRAFT"
    sent = _create_invoice(headers, cid, [_line(price="20.02")])
    assert _send(headers, sent["id"]).status_code == 200
    credit = _credit(headers, cid).json()["data"]
    assert _dec(credit["exposure"]) == Decimal("20.02")
    pay = _pay(headers, sent["id"], Decimal("5.00"))
    assert pay.status_code == 200, pay.text
    credit = _credit(headers, cid).json()["data"]
    assert _dec(credit["exposure"]) == Decimal("15.02")
    cancelled = _create_invoice(headers, cid, [_line(price="7.77")])
    assert _send(headers, cancelled["id"]).status_code == 200
    void = client.post(
        f"/api/v1/invoices/{cancelled['id']}/void",
        json={"reason": "void for exposure test"},
        headers=headers,
    )
    assert void.status_code == 200, void.text
    credit = _credit(headers, cid).json()["data"]
    assert _dec(credit["exposure"]) == Decimal("15.02")


def test_cod_first_send_ok_second_send_hold():
    token, _ = _register("cc_cod", "Credit COD WS")
    headers = _headers(token)
    _set_workspace(headers)
    dealer = _create_client(headers, credit_limit="0")
    cid = dealer["id"]
    first = _create_invoice(headers, cid, [_line(price="50.00")])
    sent = _send(headers, first["id"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["status"] == "SENT"
    hold = _credit(headers, cid).json()["data"]
    assert hold["credit_status"] == "HOLD"
    second = _create_invoice(headers, cid, [_line(price="10.00")])
    blocked = _send(headers, second["id"])
    assert blocked.status_code == 400, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "CREDIT_HOLD"
    assert err["field"] == "client.credit_status"
    got = client.get(f"/api/v1/invoices/{second['id']}", headers=headers)
    assert got.json()["data"]["status"] == "DRAFT"


def test_limit_strict_greater_than_not_gte():
    token, _ = _register("cc_gt", "Credit GT WS")
    headers = _headers(token)
    _set_workspace(headers)
    dealer = _create_client(headers, credit_limit="1000.00")
    cid = dealer["id"]
    first = _create_invoice(headers, cid, [_line(price="1000.00")])
    assert _send(headers, first["id"]).status_code == 200
    credit = _credit(headers, cid).json()["data"]
    assert _dec(credit["exposure"]) == Decimal("1000.00")
    assert credit["credit_status"] != "HOLD"
    second = _create_invoice(headers, cid, [_line(price="0.01")])
    assert _send(headers, second["id"]).status_code == 200
    credit = _credit(headers, cid).json()["data"]
    assert _dec(credit["exposure"]) == Decimal("1000.01")
    assert credit["credit_status"] == "HOLD"
    third = _create_invoice(headers, cid, [_line(price="1.00")])
    blocked = _send(headers, third["id"])
    assert blocked.status_code == 400
    assert blocked.json()["error"]["code"] == "CREDIT_HOLD"


def test_null_limit_inherits_workspace_zero_is_cod():
    token, _ = _register("cc_inh", "Credit Inherit WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="5000.00")
    dealer = _create_client(headers)
    assert dealer["credit_limit"] is None
    assert _dec(dealer["effective_credit_limit"]) == Decimal("5000.00")
    r = client.put(
        f"/api/v1/clients/{dealer['id']}",
        json={"credit_limit": "0"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert _dec(r.json()["data"]["credit_limit"]) == Decimal("0.00")
    assert _dec(r.json()["data"]["effective_credit_limit"]) == Decimal("0.00")


def test_overdue_on_read_excludes_from_sent_list():
    token, _ = _register("cc_od", "Credit Overdue WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="10000.00")
    dealer = _create_client(headers, credit_limit="10000.00")
    today = _utc_today()
    yesterday = (today - timedelta(days=1)).isoformat()
    inv = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="80.00")],
        issue_date=yesterday,
        due_date=yesterday,
    )
    sent = _send(headers, inv["id"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["status"] == "OVERDUE"
    got = client.get(f"/api/v1/invoices/{inv['id']}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["status"] == "OVERDUE"
    listed = client.get("/api/v1/invoices?status=SENT", headers=headers)
    assert listed.status_code == 200, listed.text
    ids = [row["id"] for row in listed.json()["data"]]
    assert inv["id"] not in ids
    paid_inv = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="40.00")],
        issue_date=yesterday,
        due_date=yesterday,
    )
    assert _send(headers, paid_inv["id"]).status_code == 200
    total = _dec(
        client.get(f"/api/v1/invoices/{paid_inv['id']}", headers=headers).json()[
            "data"
        ]["total_amount"]
    )
    # GET already flipped OVERDUE; pay in full → PAID
    assert _pay(headers, paid_inv["id"], total).status_code == 200
    paid_got = client.get(f"/api/v1/invoices/{paid_inv['id']}", headers=headers)
    assert paid_got.json()["data"]["status"] == "PAID"
    voided = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="15.00")],
        issue_date=yesterday,
        due_date=yesterday,
    )
    assert _send(headers, voided["id"]).status_code == 200
    assert (
        client.post(
            f"/api/v1/invoices/{voided['id']}/void",
            json={"reason": "cancel overdue candidate"},
            headers=headers,
        ).status_code
        == 200
    )
    void_got = client.get(f"/api/v1/invoices/{voided['id']}", headers=headers)
    assert void_got.json()["data"]["status"] == "CANCELLED"


def test_partial_payment_on_overdue_stays_overdue():
    token, _ = _register("cc_part", "Credit Partial WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="10000.00")
    dealer = _create_client(headers, credit_limit="10000.00")
    yesterday = (_utc_today() - timedelta(days=1)).isoformat()
    inv = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="100.00")],
        issue_date=yesterday,
        due_date=yesterday,
    )
    assert _send(headers, inv["id"]).status_code == 200
    assert (
        client.get(f"/api/v1/invoices/{inv['id']}", headers=headers).json()["data"][
            "status"
        ]
        == "OVERDUE"
    )
    assert _pay(headers, inv["id"], Decimal("40.00")).status_code == 200
    after = client.get(f"/api/v1/invoices/{inv['id']}", headers=headers).json()["data"]
    assert after["status"] == "OVERDUE"
    assert _dec(after["balance_due"]) == Decimal("60.00")
    assert _pay(headers, inv["id"], Decimal("60.00")).status_code == 200
    done = client.get(f"/api/v1/invoices/{inv['id']}", headers=headers).json()["data"]
    assert done["status"] == "PAID"


def test_aging_hold_when_overdue_exceeds_hold_days():
    token, _ = _register("cc_age", "Credit Age WS")
    headers = _headers(token)
    _set_workspace(
        headers,
        credit_limit_default="10000.00",
        credit_warning_days=5,
        credit_hold_days=10,
    )
    dealer = _create_client(headers, credit_limit="10000.00")
    past = (_utc_today() - timedelta(days=12)).isoformat()
    inv = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="25.00")],
        issue_date=past,
        due_date=past,
    )
    assert _send(headers, inv["id"]).status_code == 200
    credit = _credit(headers, dealer["id"]).json()["data"]
    assert credit["oldest_overdue_days"] == 12
    assert credit["credit_status"] == "HOLD"
    assert _dec(credit["buckets"]["days_1_30"]) == Decimal("25.00")


def test_warning_does_not_block_send():
    token, _ = _register("cc_warn", "Credit Warn WS")
    headers = _headers(token)
    _set_workspace(
        headers,
        credit_limit_default="10000.00",
        credit_warning_days=5,
        credit_hold_days=90,
    )
    dealer = _create_client(headers, credit_limit="10000.00")
    past = (_utc_today() - timedelta(days=8)).isoformat()
    first = _create_invoice(
        headers,
        dealer["id"],
        [_line(price="25.00")],
        issue_date=past,
        due_date=past,
    )
    assert _send(headers, first["id"]).status_code == 200
    credit = _credit(headers, dealer["id"]).json()["data"]
    assert credit["credit_status"] == "WARNING"
    second = _create_invoice(headers, dealer["id"], [_line(price="10.00")])
    sent = _send(headers, second["id"])
    assert sent.status_code == 200, sent.text


def test_lpo_receive_respects_block_po_on_hold():
    token, _ = _register("cc_lpo", "Credit LPO WS")
    headers = _headers(token)
    _set_workspace(headers, block_po_on_hold=True)
    dealer = _create_client(headers, credit_limit="0")
    inv = _create_invoice(headers, dealer["id"], [_line(price="50.00")])
    assert _send(headers, inv["id"]).status_code == 200
    assert _credit(headers, dealer["id"]).json()["data"]["credit_status"] == "HOLD"
    lpo = client.post(
        "/api/v1/customer-purchase-orders",
        json={"client_id": dealer["id"], "items": [_adhoc_quote_item()]},
        headers=headers,
    )
    assert lpo.status_code == 201, lpo.text
    lpo_id = lpo.json()["data"]["id"]
    blocked = client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/receive",
        json={},
        headers=headers,
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error"]["code"] == "CREDIT_HOLD"
    assert (
        client.get(
            f"/api/v1/customer-purchase-orders/{lpo_id}", headers=headers
        ).json()["data"]["status"]
        == "DRAFT"
    )
    _set_workspace(headers, block_po_on_hold=False)
    allowed = client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/receive",
        json={},
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["status"] == "RECEIVED"


def test_quote_convert_not_blocked_on_hold():
    token, _ = _register("cc_quo", "Credit Quote WS")
    headers = _headers(token)
    _set_workspace(headers)
    dealer = _create_client(headers, credit_limit="0", payment_terms_days=0)
    inv = _create_invoice(headers, dealer["id"], [_line(price="50.00")])
    assert _send(headers, inv["id"]).status_code == 200
    quote = client.post(
        "/api/v1/quotations",
        json={"client_id": dealer["id"], "items": [_adhoc_quote_item()]},
        headers=headers,
    ).json()["data"]
    assert (
        client.post(
            f"/api/v1/quotations/{quote['id']}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/quotations/{quote['id']}/accept", headers=headers
        ).status_code
        == 200
    )
    converted = client.post(
        f"/api/v1/quotations/{quote['id']}/convert-to-invoice", headers=headers
    )
    assert converted.status_code == 201, converted.text
    other = client.post(
        "/api/v1/quotations",
        json={"client_id": dealer["id"], "items": [_adhoc_quote_item()]},
        headers=headers,
    ).json()["data"]
    assert (
        client.post(
            f"/api/v1/quotations/{other['id']}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/quotations/{other['id']}/accept", headers=headers
        ).status_code
        == 200
    )
    lpo = client.post(
        f"/api/v1/quotations/{other['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert lpo.status_code in (200, 201), lpo.text


def test_payment_on_hold_and_credit_isolation_404():
    token_a, _ = _register("cc_iso_a", "Credit Iso A")
    headers_a = _headers(token_a)
    _set_workspace(headers_a)
    dealer = _create_client(headers_a, credit_limit="0")
    inv = _create_invoice(headers_a, dealer["id"], [_line(price="50.00")])
    assert _send(headers_a, inv["id"]).status_code == 200
    assert _credit(headers_a, dealer["id"]).json()["data"]["credit_status"] == "HOLD"
    paid = _pay(headers_a, inv["id"], Decimal("50.00"))
    assert paid.status_code == 200, paid.text
    token_b, _ = _register("cc_iso_b", "Credit Iso B")
    headers_b = _headers(token_b)
    r = _credit(headers_b, dealer["id"])
    assert r.status_code == 404, r.text


def test_workspace_warning_days_after_hold_422():
    token, _ = _register("cc_ws", "Credit WS Flags")
    headers = _headers(token)
    r = client.put(
        "/api/v1/workspaces/me",
        json={"credit_warning_days": 100, "credit_hold_days": 30},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_convert_due_date_uses_client_terms():
    token, _ = _register("cc_due", "Credit Due WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="10000.00")
    dealer = _create_client(headers, payment_terms_days=0, credit_limit="10000.00")
    quote = client.post(
        "/api/v1/quotations",
        json={"client_id": dealer["id"], "items": [_adhoc_quote_item()]},
        headers=headers,
    ).json()["data"]
    assert (
        client.post(
            f"/api/v1/quotations/{quote['id']}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/quotations/{quote['id']}/accept", headers=headers
        ).status_code
        == 200
    )
    converted = client.post(
        f"/api/v1/quotations/{quote['id']}/convert-to-invoice", headers=headers
    )
    assert converted.status_code == 201, converted.text
    today = _utc_today()
    assert converted.json()["data"]["due_date"] == today.isoformat()
    net30 = _create_client(
        headers, name="Net30", payment_terms_days=30, credit_limit="10000.00"
    )
    quote30 = client.post(
        "/api/v1/quotations",
        json={"client_id": net30["id"], "items": [_adhoc_quote_item()]},
        headers=headers,
    ).json()["data"]
    assert (
        client.post(
            f"/api/v1/quotations/{quote30['id']}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/quotations/{quote30['id']}/accept", headers=headers
        ).status_code
        == 200
    )
    conv30 = client.post(
        f"/api/v1/quotations/{quote30['id']}/convert-to-invoice", headers=headers
    )
    assert conv30.status_code == 201, conv30.text
    assert conv30.json()["data"]["due_date"] == (today + timedelta(days=30)).isoformat()


def test_evaluate_persists_sent_to_overdue_skips_paid():
    token, _ = _register("cc_eval_od", "Credit Eval OD WS")
    headers = _headers(token)
    _set_workspace(headers, credit_limit_default="10000.00")
    dealer = _create_client(headers, credit_limit="10000.00")
    today = _utc_today()
    future = (today + timedelta(days=14)).isoformat()
    live = _create_invoice(
        headers, dealer["id"], [_line(price="80.00")], due_date=future
    )
    sent = _send(headers, live["id"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["status"] == "SENT"
    paid_inv = _create_invoice(
        headers, dealer["id"], [_line(price="40.00")], due_date=future
    )
    assert _send(headers, paid_inv["id"]).status_code == 200
    total = _dec(
        client.get(f"/api/v1/invoices/{paid_inv['id']}", headers=headers).json()[
            "data"
        ]["total_amount"]
    )
    assert _pay(headers, paid_inv["id"], total).status_code == 200
    assert asyncio.run(_invoice_status(paid_inv["id"])) == "PAID"
    yesterday = today - timedelta(days=1)
    asyncio.run(_set_due_date(live["id"], yesterday))
    asyncio.run(_set_due_date(paid_inv["id"], yesterday))
    credit = _credit(headers, dealer["id"])
    assert credit.status_code == 200, credit.text
    assert asyncio.run(_invoice_status(live["id"])) == "OVERDUE"
    assert asyncio.run(_invoice_status(paid_inv["id"])) == "PAID"


def test_fta_valid_hold_send_is_credit_hold():
    token, _ = _register("cc_fta_hold", "Credit FTA Hold WS")
    headers = _headers(token)
    workspace = _set_workspace(headers)
    assert workspace.get("trn") == VALID_TRN
    assert workspace.get("address") == SELLER_ADDRESS
    dealer = _create_client(headers, credit_limit="0")
    first = _create_invoice(headers, dealer["id"], [_line(price="50.00")])
    assert _send(headers, first["id"]).status_code == 200
    assert _credit(headers, dealer["id"]).json()["data"]["credit_status"] == "HOLD"
    second = _create_invoice(headers, dealer["id"], [_line(price="10.00")])
    blocked = _send(headers, second["id"])
    assert blocked.status_code == 400, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "CREDIT_HOLD"
    assert err["code"] != "FTA_SEND_BLOCKED"
    assert err["field"] == "client.credit_status"
    got = client.get(f"/api/v1/invoices/{second['id']}", headers=headers)
    assert got.json()["data"]["status"] == "DRAFT"
