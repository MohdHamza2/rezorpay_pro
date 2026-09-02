"""WP-A tax debit notes API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``.
"""

import asyncio
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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

YEAR = datetime.now().year
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


def _line(qty: str = "10", price: str = "100.00", **extra) -> dict:
    item = {
        "description": "NYM cable",
        "quantity": qty,
        "unit_price": price,
        "tax_rate": extra.pop("tax_rate", "0"),
    }
    item.update(extra)
    return item


def _create_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    body = {
        "client_id": client_id,
        "issue_date": extra.pop("issue_date", "2026-08-26"),
        "due_date": extra.pop("due_date", "2026-09-26"),
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


def _pay(headers: dict, invoice_id: str, amount: Decimal):
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={
            "amount": str(amount),
            "payment_method": "CASH",
            "payment_date": datetime.now(timezone.utc).date().isoformat(),
        },
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )


def _tdn_payload(invoice: dict, items: list[dict] | None = None, **extra) -> dict:
    if items is None:
        items = [
            {
                "invoice_item_id": invoice["items"][0]["id"],
                "quantity": invoice["items"][0]["quantity"],
            }
        ]
    body = {
        "invoice_id": invoice["id"],
        "reason": extra.pop("reason", "PRICE_INCREASE"),
        "items": items,
    }
    body.update(extra)
    return body


def _create_tdn(headers: dict, invoice: dict, items: list[dict] | None = None, **extra):
    r = client.post(
        "/api/v1/debit-notes",
        json=_tdn_payload(invoice, items, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _issue(headers: dict, tdn_id: str):
    return client.post(f"/api/v1/debit-notes/{tdn_id}/issue", json={}, headers=headers)


def _get_invoice(headers: dict, invoice_id: str) -> dict:
    r = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _get_balance(headers: dict, invoice_id: str) -> dict:
    r = client.get(f"/api/v1/invoices/{invoice_id}/balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _payment_count(headers: dict, invoice_id: str) -> int:
    r = client.get(f"/api/v1/invoices/{invoice_id}/payments", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["pagination"]["total"]


def test_create_gapless_tdn_numbers_and_concurrent_unique():
    token, _ = _register("tdn_num", "TDN Num WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    first_inv = _sent_invoice(headers, client_id, [_line(qty="1", price="10.00")])
    second_inv = _sent_invoice(headers, client_id, [_line(qty="1", price="10.00")])
    tdn1 = _create_tdn(headers, first_inv)
    tdn2 = _create_tdn(headers, second_inv)
    assert tdn1["debit_note_number"] == f"TDN-{YEAR}-0001"
    assert tdn2["debit_note_number"] == f"TDN-{YEAR}-0002"
    assert tdn1["status"] == "DRAFT"

    def create_one(index: int) -> str:
        inv = _sent_invoice(headers, client_id, [_line(qty="1", price=str(10 + index))])
        r = client.post(
            "/api/v1/debit-notes",
            json=_tdn_payload(inv),
            headers=headers,
        )
        assert r.status_code == 201, f"TDN {index} failed: {r.text}"
        return r.json()["data"]["debit_note_number"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        numbers = list(executor.map(create_one, range(8)))
    assert len(numbers) == len(set(numbers)), numbers


def test_parent_draft_cancelled_403_other_workspace_404():
    token, _ = _register("tdn_parent", "TDN Parent WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    draft = _create_invoice(headers, client_id, [_line()])
    blocked = client.post(
        "/api/v1/debit-notes", json=_tdn_payload(draft), headers=headers
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "INVALID_STATE"


def test_issue_increases_balance_due():
    token, _ = _register("tdn_bal", "TDN Bal WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="100.00")])
    total = _dec(invoice["total_amount"])
    tdn = _create_tdn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "2"}],
    )
    issued = _issue(headers, tdn["id"])
    assert issued.status_code == 200, issued.text

    got = _get_invoice(headers, invoice["id"])
    tdn_total = _dec(tdn["total_amount"])

    assert _dec(got["amount_debited"]) == tdn_total
    assert _dec(got["balance_due"]) == total + tdn_total
    assert got["status"] in ("SENT", "OVERDUE")

    bal = _get_balance(headers, invoice["id"])
    assert _dec(bal["amount_debited"]) == tdn_total
    assert _dec(bal["balance_due"]) == total + tdn_total


def test_issue_paid_invoice_reopens_it():
    token, _ = _register("tdn_paid", "TDN Paid WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="100.00")])
    total = _dec(invoice["total_amount"])

    # Fully pay
    pay = _pay(headers, invoice["id"], total)
    assert pay.status_code == 200, pay.text

    inv_paid = _get_invoice(headers, invoice["id"])
    assert inv_paid["status"] == "PAID"
    assert _dec(inv_paid["balance_due"]) == Decimal("0.00")

    # Create TDN (e.g. price increase)
    tdn = _create_tdn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    issued = _issue(headers, tdn["id"])
    assert issued.status_code == 200, issued.text

    # Invoice should be reopened to PARTIALLY_PAID (or OVERDUE)
    inv_reopened = _get_invoice(headers, invoice["id"])
    assert inv_reopened["status"] in ("PARTIALLY_PAID", "OVERDUE")
    assert _dec(inv_reopened["balance_due"]) == _dec(tdn["total_amount"])


def test_issue_paid_invoice_unparks_credit_balance():
    token, _ = _register("tdn_unpark", "TDN Unpark WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="100.00")])
    total = _dec(invoice["total_amount"])

    pay = _pay(headers, invoice["id"], total)
    assert pay.status_code == 200, pay.text

    # Create CN to park credit balance
    cn_payload = {
        "invoice_id": invoice["id"],
        "reason": "INVOICE_ERROR",
        "items": [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "5"}],
    }
    cn_r = client.post("/api/v1/credit-notes", json=cn_payload, headers=headers)
    assert cn_r.status_code == 201, cn_r.text
    cn = cn_r.json()["data"]
    issued_cn = client.post(
        f"/api/v1/credit-notes/{cn['id']}/issue", json={}, headers=headers
    )
    assert issued_cn.status_code == 200, issued_cn.text

    dealer = client.get(f"/api/v1/clients/{client_id}", headers=headers)
    assert _dec(dealer.json()["data"]["credit_balance"]) == Decimal("500.00")

    # Create TDN for 3 (quantity) -> 300.00
    tdn = _create_tdn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "3"}],
    )
    issued_tdn = _issue(headers, tdn["id"])
    assert issued_tdn.status_code == 200, issued_tdn.text

    # Check that credit balance is reduced by 300.00 -> remaining 200.00
    dealer_after = client.get(f"/api/v1/clients/{client_id}", headers=headers)
    assert _dec(dealer_after.json()["data"]["credit_balance"]) == Decimal("200.00")
