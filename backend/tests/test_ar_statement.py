"""WP-A AR aging + Account Statement API tests.

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
from sqlalchemy import func, select
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
from app.models.client import Client
from app.models.credit_note import CreditNote
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.services.credit_control_service import _bucket_key, utc_today
from app.services.line_money import money

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


def _pay(
    headers: dict,
    invoice_id: str,
    amount: Decimal,
    method: str = "CASH",
    payment_date: str | None = None,
    **extra,
):
    body = {
        "amount": str(amount),
        "payment_method": method,
        "payment_date": payment_date or utc_today().isoformat(),
        **extra,
    }
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )


def _cn_payload(invoice: dict, items: list[dict] | None = None, **extra) -> dict:
    if items is None:
        items = [
            {
                "invoice_item_id": invoice["items"][0]["id"],
                "quantity": invoice["items"][0]["quantity"],
            }
        ]
    body = {
        "invoice_id": invoice["id"],
        "reason": extra.pop("reason", "INVOICE_ERROR"),
        "items": items,
    }
    body.update(extra)
    return body


def _create_cn(headers: dict, invoice: dict, items: list[dict] | None = None, **extra):
    r = client.post(
        "/api/v1/credit-notes",
        json=_cn_payload(invoice, items, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _issue(headers: dict, cn_id: str):
    return client.post(f"/api/v1/credit-notes/{cn_id}/issue", json={}, headers=headers)


def _stmt(headers: dict, client_id: str, period_from, period_to, as_of=None):
    params = {"from": str(period_from), "to": str(period_to)}
    if as_of is not None:
        params["as_of"] = str(as_of)
    return client.get(
        f"/api/v1/clients/{client_id}/ar-statement",
        headers=headers,
        params=params,
    )


def _ready() -> tuple[dict, str]:
    token, _ = _register("ar_ws", "AR Statement WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers, credit_limit="100000.00")
    return headers, client_id


def _by_type(data: dict, doc_type: str) -> list[dict]:
    return [row for row in data["lines"] if row["doc_type"] == doc_type]


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


async def _insert_payment(
    invoice_id: str,
    amount: Decimal,
    pay_status: PaymentStatus,
    method: PaymentMethod = PaymentMethod.CASH,
    on=None,
) -> None:
    when = on or utc_today()
    async with TestingSessionLocal() as session:
        session.add(
            Payment(
                invoice_id=uuid.UUID(invoice_id),
                amount=amount,
                payment_method=method,
                status=pay_status,
                payment_date=datetime.combine(when, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ),
            )
        )
        await session.commit()


async def _table_counts() -> dict[str, int]:
    async with TestingSessionLocal() as session:
        invoices = (
            await session.execute(select(func.count()).select_from(Invoice))
        ).scalar()
        payments = (
            await session.execute(select(func.count()).select_from(Payment))
        ).scalar()
        notes = (
            await session.execute(select(func.count()).select_from(CreditNote))
        ).scalar()
        return {
            "invoices": int(invoices or 0),
            "payments": int(payments or 0),
            "credit_notes": int(notes or 0),
        }


async def _mutation_snapshot(
    invoice_id: str, payment_id: str, cn_id: str, client_id: str
):
    async with TestingSessionLocal() as session:
        inv = await session.get(Invoice, uuid.UUID(invoice_id))
        pay = await session.get(Payment, uuid.UUID(payment_id))
        note = await session.get(CreditNote, uuid.UUID(cn_id))
        dealer = await session.get(Client, uuid.UUID(client_id))
        assert inv is not None and pay is not None and note is not None
        assert dealer is not None
        return (
            inv.status,
            inv.updated_at,
            inv.amount_credited,
            pay.status,
            pay.amount,
            pay.updated_at,
            note.status,
            note.total_amount,
            note.updated_at,
            dealer.credit_balance,
        )


def test_query_validation_422():
    headers, client_id = _ready()
    missing_from = client.get(
        f"/api/v1/clients/{client_id}/ar-statement",
        headers=headers,
        params={"to": utc_today().isoformat()},
    )
    assert missing_from.status_code == 422, missing_from.text
    missing_to = client.get(
        f"/api/v1/clients/{client_id}/ar-statement",
        headers=headers,
        params={"from": utc_today().isoformat()},
    )
    assert missing_to.status_code == 422, missing_to.text
    inverted = _stmt(headers, client_id, "2026-06-01", "2026-01-01")
    assert inverted.status_code == 422, inverted.text
    assert inverted.json()["error"]["code"] == "VALIDATION_ERROR"
    assert inverted.json()["error"]["field"] == "from"
    too_long = _stmt(headers, client_id, "2025-01-01", "2026-01-03")
    assert too_long.status_code == 422, too_long.text
    assert too_long.json()["error"]["code"] == "DATE_RANGE_TOO_LONG"
    assert too_long.json()["error"]["field"] == "to"
    future = utc_today() + timedelta(days=1)
    future_as_of = _stmt(
        headers, client_id, utc_today(), utc_today(), as_of=future.isoformat()
    )
    assert future_as_of.status_code == 422, future_as_of.text
    assert future_as_of.json()["error"]["code"] == "VALIDATION_ERROR"
    assert future_as_of.json()["error"]["field"] == "as_of"


def test_other_workspace_404_not_403():
    headers_a, client_id = _ready()
    token_b, _ = _register("ar_iso_b", "AR Iso B")
    headers_b = _headers(token_b)
    _set_workspace(headers_b)
    today = utc_today().isoformat()
    r = _stmt(headers_b, client_id, today, today)
    assert r.status_code == 404, r.text
    assert r.status_code != 403
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_sent_invoice_debit_draft_omitted():
    headers, client_id = _ready()
    today = utc_today()
    sent = _sent_invoice(headers, client_id, [_line(price="100.00")])
    _create_invoice(headers, client_id, [_line(price="77.00")])
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "from" in data
    assert data["from"] == today.isoformat()
    invoices = _by_type(data, "TAX_INVOICE")
    assert len(invoices) == 1
    assert invoices[0]["doc_type_label"] == "Tax Invoice"
    assert _dec(invoices[0]["debit"]) == _dec(sent["total_amount"])
    assert _dec(invoices[0]["credit"]) == Decimal("0.00")
    assert invoices[0]["number"] == sent["invoice_number"]


def test_success_payment_and_issued_cn():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="10.00")])
    total = _dec(invoice["total_amount"])
    cash = Decimal("40.00")
    pay = _pay(headers, invoice["id"], cash)
    assert pay.status_code == 200, pay.text
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "2"}],
    )
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    payments = _by_type(data, "PAYMENT")
    notes = _by_type(data, "TAX_CREDIT_NOTE")
    assert len(payments) == 1
    assert payments[0]["doc_type_label"] == "Payment"
    assert payments[0]["cleared_cash"] is True
    assert _dec(payments[0]["credit"]) == cash
    assert _dec(data["totals"]["paid"]) == cash
    assert len(notes) == 1
    assert notes[0]["doc_type_label"] == "Tax Credit Note"
    assert _dec(notes[0]["credit"]) == _dec(cn["total_amount"])
    assert _dec(data["totals"]["credited"]) == _dec(cn["total_amount"])
    assert _dec(data["totals"]["paid"]) != _dec(data["totals"]["credited"])
    assert _dec(data["totals"]["paid"]) == cash
    assert _dec(data["totals"]["billed"]) == total
    assert notes[0]["reference"] == invoice["invoice_number"]


def test_draft_cn_cancelled_paid_omitted_from_aging():
    headers, client_id = _ready()
    today = utc_today()
    paid = _sent_invoice(headers, client_id, [_line(price="50.00")])
    pay = _pay(headers, paid["id"], _dec(paid["total_amount"]))
    assert pay.status_code == 200, pay.text
    cancelled = _sent_invoice(headers, client_id, [_line(price="30.00")])
    cancelled_pay = _pay(headers, cancelled["id"], Decimal("5.00"))
    assert cancelled_pay.status_code == 200, cancelled_pay.text
    cancelled_cn = _create_cn(
        headers,
        cancelled,
        [{"invoice_item_id": cancelled["items"][0]["id"], "quantity": "1"}],
    )
    assert _issue(headers, cancelled_cn["id"]).status_code == 200
    voided = client.post(
        f"/api/v1/invoices/{cancelled['id']}/void",
        json={"reason": "void for statement omit"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    draft_parent = _sent_invoice(headers, client_id, [_line(price="20.00")])
    _create_cn(headers, draft_parent)
    asyncio.run(
        _insert_payment(paid["id"], Decimal("9.99"), PaymentStatus.FAILED, on=today)
    )
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    numbers = {row["number"] for row in data["lines"] if row["number"]}
    assert paid["invoice_number"] in numbers
    assert cancelled["invoice_number"] not in numbers
    assert cancelled_cn["credit_note_number"] not in numbers
    assert all(_dec(row.get("credit") or 0) != Decimal("9.99") for row in data["lines"])
    assert _by_type(data, "TAX_CREDIT_NOTE") == []
    paid_line = _by_type(data, "TAX_INVOICE")
    assert any(row["number"] == paid["invoice_number"] for row in paid_line)
    buckets = data["aging"]["buckets"]
    assert _dec(paid["total_amount"]) not in {_dec(v) for v in buckets.values()}
    assert _dec(data["amount_due_now"]) == _dec(draft_parent["total_amount"])


def test_pending_payment_not_in_paid():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="80.00")])
    asyncio.run(
        _insert_payment(
            invoice["id"], Decimal("12.00"), PaymentStatus.PENDING, on=today
        )
    )
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    pending = _by_type(data, "PAYMENT_PENDING")
    assert len(pending) == 1
    assert pending[0]["doc_type_label"] == "Payment (pending)"
    assert pending[0]["cleared_cash"] is False
    assert _dec(pending[0]["credit"]) == Decimal("0.00")
    assert _dec(pending[0]["pending_amount"]) == Decimal("12.00")
    assert _dec(data["totals"]["paid"]) == Decimal("0.00")
    assert _dec(data["totals"]["pending"]) == Decimal("12.00")
    assert _dec(data["amount_due_now"]) == _dec(invoice["total_amount"])


def test_success_pdc_in_paid():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="60.00")])
    pay = _pay(
        headers,
        invoice["id"],
        Decimal("25.00"),
        method="PDC",
        pdc_date=today.isoformat(),
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["data"]["status"] == "PENDING"
    payment_id = pay.json()["data"]["id"]
    dep = client.post(
        f"/api/v1/invoices/{invoice['id']}/payments/{payment_id}/pdc/deposit",
        json={},
        headers=headers,
    )
    assert dep.status_code == 200, dep.text
    cleared = client.post(
        f"/api/v1/invoices/{invoice['id']}/payments/{payment_id}/pdc/clear",
        json={},
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["status"] == "SUCCESS"
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    payments = _by_type(data, "PAYMENT")
    assert len(payments) == 1
    assert payments[0]["payment_method"] == "PDC"
    assert payments[0]["doc_type_label"] == "Payment"
    assert payments[0]["doc_type_label"] != "Tax Credit Note"
    assert _dec(data["totals"]["paid"]) == Decimal("25.00")
    assert payments[0]["cleared_cash"] is True


def test_aging_matches_credit_and_bucket_sum():
    headers, client_id = _ready()
    today = utc_today()
    due = today - timedelta(days=10)
    issue = today - timedelta(days=40)
    open_inv = _sent_invoice(
        headers,
        client_id,
        [_line(price="100.00")],
        issue_date=issue.isoformat(),
        due_date=due.isoformat(),
    )
    paid = _sent_invoice(headers, client_id, [_line(price="40.00")])
    assert _pay(headers, paid["id"], _dec(paid["total_amount"])).status_code == 200
    cancelled = _sent_invoice(headers, client_id, [_line(price="30.00")])
    voided = client.post(
        f"/api/v1/invoices/{cancelled['id']}/void",
        json={"reason": "void cancelled aging exclude"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    r = _stmt(headers, client_id, issue, today, as_of=today.isoformat())
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    buckets = data["aging"]["buckets"]
    key = _bucket_key((today - due).days)
    assert _dec(buckets[key]) == _dec(open_inv["total_amount"])
    assert _dec(paid["total_amount"]) not in {
        _dec(v) for v in buckets.values() if _dec(v)
    }
    bucket_sum = money(sum((_dec(v) for v in buckets.values()), Decimal("0.00")))
    assert bucket_sum == _dec(data["amount_due_now"])
    assert bucket_sum == _dec(open_inv["total_amount"])
    credit = client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)
    assert credit.status_code == 200, credit.text
    credit_data = credit.json()["data"]
    for name in ("current", "days_1_30", "days_31_60", "days_61_90", "days_90_plus"):
        assert _dec(data["aging"]["buckets"][name]) == _dec(
            credit_data["buckets"][name]
        )
    assert _dec(data["amount_due_now"]) == _dec(credit_data["exposure"])
    assert _dec(data["credit_balance"]) == _dec(credit_data["credit_balance"])
    parked = _dec(data["credit_balance"])
    if parked > 0:
        assert parked not in {_dec(v) for v in buckets.values()}


def test_wide_range_closing_equals_exposure_minus_credit():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(qty="1", price="100.00")])
    total = _dec(invoice["total_amount"])
    assert _pay(headers, invoice["id"], total).status_code == 200
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    assert _issue(headers, cn["id"]).status_code == 200
    r = _stmt(headers, client_id, today - timedelta(days=30), today, as_of=today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    expected = money(_dec(data["amount_due_now"]) - _dec(data["credit_balance"]))
    assert _dec(data["totals"]["closing_running"]) == expected
    assert _dec(data["credit_balance"]) == _dec(cn["total_amount"])
    assert _dec(data["amount_due_now"]) == Decimal("0.00")


def test_opening_invoice_before_from_payment_in_range():
    headers, client_id = _ready()
    today = utc_today()
    issue = today - timedelta(days=20)
    period_from = today - timedelta(days=5)
    invoice = _sent_invoice(
        headers,
        client_id,
        [_line(price="100.00")],
        issue_date=issue.isoformat(),
        due_date=(issue + timedelta(days=30)).isoformat(),
    )
    cash = Decimal("35.00")
    pay = _pay(headers, invoice["id"], cash, payment_date=today.isoformat())
    assert pay.status_code == 200, pay.text
    r = _stmt(headers, client_id, period_from, today)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert _dec(data["opening_balance"]) == _dec(invoice["total_amount"])
    opening = data["lines"][0]
    assert opening["doc_type"] == "OPENING"
    assert opening["doc_type_label"] == "Opening balance"
    assert _dec(opening["debit"]) == _dec(invoice["total_amount"])
    assert _by_type(data, "TAX_INVOICE") == []
    payments = _by_type(data, "PAYMENT")
    assert len(payments) == 1
    assert _dec(payments[0]["credit"]) == cash
    assert _dec(data["totals"]["billed"]) == Decimal("0.00")
    assert _dec(data["totals"]["paid"]) == cash


def test_statement_too_large_400(monkeypatch):
    monkeypatch.setattr(
        "app.services.ar_statement_service.ACTIVITY_LINE_CAP",
        0,
    )
    headers, client_id = _ready()
    today = utc_today()
    _sent_invoice(headers, client_id, [_line(price="10.00")])
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "STATEMENT_TOO_LARGE"
    assert r.json()["error"]["field"] == "to"


def test_get_does_not_mutate_rows():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(qty="2", price="50.00")])
    pay = _pay(headers, invoice["id"], Decimal("20.00"))
    assert pay.status_code == 200, pay.text
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    before_counts = asyncio.run(_table_counts())
    before_rows = asyncio.run(
        _mutation_snapshot(invoice["id"], pay.json()["data"]["id"], cn["id"], client_id)
    )
    r = _stmt(headers, client_id, today, today)
    assert r.status_code == 200, r.text
    after_counts = asyncio.run(_table_counts())
    after_rows = asyncio.run(
        _mutation_snapshot(invoice["id"], pay.json()["data"]["id"], cn["id"], client_id)
    )
    assert after_counts == before_counts
    assert after_rows == before_rows


def test_member_can_get_and_hold_does_not_block():
    token, workspace_id = _register("ar_mem", "AR Member WS")
    headers = _headers(token)
    _set_workspace(headers)
    hold_client = _create_client(headers, credit_limit="0")
    today = utc_today()
    invoice = _sent_invoice(headers, hold_client, [_line(price="15.00")])
    credit = client.get(f"/api/v1/clients/{hold_client}/credit", headers=headers)
    assert credit.status_code == 200, credit.text
    assert credit.json()["data"]["credit_status"] == "HOLD"
    member = _headers(_member_token(workspace_id))
    r = _stmt(member, hold_client, today, today)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lines"][0]["doc_type"] == "OPENING"
    assert any(
        row["number"] == invoice["invoice_number"] for row in r.json()["data"]["lines"]
    )


def test_stmt_with_tdn():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="100.00")])
    # create TDN
    tdn_resp = client.post(
        "/api/v1/debit-notes",
        json={
            "invoice_id": invoice["id"],
            "reason": "PRICE_INCREASE",
            "items": [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}]
        },
        headers=headers
    )
    assert tdn_resp.status_code == 201, tdn_resp.text
    tdn = tdn_resp.json()["data"]
    # issue TDN
    issue_resp = client.post(f"/api/v1/debit-notes/{tdn['id']}/issue", json={}, headers=headers)
    assert issue_resp.status_code == 200, issue_resp.text
    # Get stmt
    stmt = _stmt(headers, client_id, today, today)
    assert stmt.status_code == 200, stmt.text
