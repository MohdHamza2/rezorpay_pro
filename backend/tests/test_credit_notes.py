"""WP-A tax credit notes API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import shutil
import subprocess
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


def test_create_gapless_cn_numbers_and_concurrent_unique():
    token, _ = _register("cn_num", "CN Num WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    first_inv = _sent_invoice(headers, client_id, [_line(qty="1", price="10.00")])
    second_inv = _sent_invoice(headers, client_id, [_line(qty="1", price="10.00")])
    cn1 = _create_cn(headers, first_inv)
    cn2 = _create_cn(headers, second_inv)
    assert cn1["credit_note_number"] == f"CN-{YEAR}-0001"
    assert cn2["credit_note_number"] == f"CN-{YEAR}-0002"
    assert cn1["status"] == "DRAFT"

    def create_one(index: int) -> str:
        inv = _sent_invoice(headers, client_id, [_line(qty="1", price=str(10 + index))])
        r = client.post(
            "/api/v1/credit-notes",
            json=_cn_payload(inv),
            headers=headers,
        )
        assert r.status_code == 201, f"CN {index} failed: {r.text}"
        return r.json()["data"]["credit_note_number"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        numbers = list(executor.map(create_one, range(8)))
    assert len(numbers) == len(set(numbers)), numbers


def test_parent_draft_cancelled_403_other_workspace_404():
    token, _ = _register("cn_parent", "CN Parent WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    draft = _create_invoice(headers, client_id, [_line()])
    blocked = client.post(
        "/api/v1/credit-notes", json=_cn_payload(draft), headers=headers
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "INVALID_STATE"

    sent = _sent_invoice(headers, client_id, [_line(qty="1", price="20.00")])
    voided = client.post(
        f"/api/v1/invoices/{sent['id']}/void",
        json={"reason": "void parent for credit note"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    cancelled = client.post(
        "/api/v1/credit-notes", json=_cn_payload(sent), headers=headers
    )
    assert cancelled.status_code == 403, cancelled.text
    assert cancelled.json()["error"]["code"] == "INVALID_STATE"

    other_token, _ = _register("cn_other", "CN Other WS")
    other = _headers(other_token)
    _set_workspace(other)
    other_client = _create_client(other)
    other_inv = _sent_invoice(other, other_client, [_line(qty="1", price="15.00")])
    missing = client.post(
        "/api/v1/credit-notes", json=_cn_payload(other_inv), headers=headers
    )
    assert missing.status_code == 404, missing.text


def test_qty_header_extra_key_and_price_mismatch():
    token, _ = _register("cn_val", "CN Val WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(
        headers,
        client_id,
        [_line(qty="1", price="100.00"), _line(qty="1", price="100.00")],
    )
    over_qty = client.post(
        "/api/v1/credit-notes",
        json=_cn_payload(
            invoice,
            [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "2"}],
        ),
        headers=headers,
    )
    assert over_qty.status_code == 400, over_qty.text
    extra = client.post(
        "/api/v1/credit-notes",
        json={**_cn_payload(invoice), "nope": True},
        headers=headers,
    )
    assert extra.status_code == 422, extra.text
    mismatch = client.post(
        "/api/v1/credit-notes",
        json=_cn_payload(
            invoice,
            [
                {
                    "invoice_item_id": invoice["items"][0]["id"],
                    "quantity": "1",
                    "unit_price": "999.00",
                }
            ],
        ),
        headers=headers,
    )
    assert mismatch.status_code == 422, mismatch.text

    full_items = [
        {"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"},
        {"invoice_item_id": invoice["items"][1]["id"], "quantity": "1"},
    ]
    first = _create_cn(headers, invoice, full_items)
    second = _create_cn(headers, invoice, full_items)
    issued = _issue(headers, first["id"])
    assert issued.status_code == 200, issued.text
    blocked = _issue(headers, second["id"])
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error"]["code"] == "CREDIT_EXCEEDS_REMAINING"
    assert blocked.json()["error"]["field"] == "total_amount"


def test_omit_tax_rate_copies_invoice_line_five_percent():
    token, _ = _register("cn_tax", "CN Tax WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "10", "unit_price": "100.00"}],
    )
    line = invoice["items"][0]
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": line["id"], "quantity": "2"}],
    )
    stored = cn["items"][0]
    assert _dec(stored["tax_rate"]) == Decimal("5.00")
    assert _dec(stored["unit_price"]) == Decimal("100.00")
    assert _dec(stored["line_net"]) == Decimal("200.00")
    assert _dec(stored["tax_amount"]) == Decimal("10.00")
    assert _dec(cn["total_amount"]) == Decimal("210.00")


def test_put_delete_issued_403_soft_delete_does_not_rewind():
    token, _ = _register("cn_state", "CN State WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="1", price="40.00")])
    draft = _create_cn(headers, invoice)
    assert draft["credit_note_number"] == f"CN-{YEAR}-0001"
    deleted = client.delete(f"/api/v1/credit-notes/{draft['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    gone = client.get(f"/api/v1/credit-notes/{draft['id']}", headers=headers)
    assert gone.status_code == 404, gone.text
    next_cn = _create_cn(headers, invoice)
    assert next_cn["credit_note_number"] == f"CN-{YEAR}-0002"
    issued = _issue(headers, next_cn["id"])
    assert issued.status_code == 200, issued.text
    put = client.put(
        f"/api/v1/credit-notes/{next_cn['id']}",
        json={"reason": "GOODWILL"},
        headers=headers,
    )
    assert put.status_code == 403, put.text
    assert put.json()["error"]["code"] == "INVALID_STATE"
    delete_issued = client.delete(
        f"/api/v1/credit-notes/{next_cn['id']}", headers=headers
    )
    assert delete_issued.status_code == 403, delete_issued.text
    assert delete_issued.json()["error"]["code"] == "INVALID_STATE"


def test_issue_unpaid_sent_shrinks_balance_payments_unchanged():
    token, _ = _register("cn_unpaid", "CN Unpaid WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="100.00")])
    total = _dec(invoice["total_amount"])
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "2"}],
    )
    before_payments = _payment_count(headers, invoice["id"])
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    assert issued.json()["data"]["status"] == "ISSUED"
    assert issued.json()["data"]["original_invoice_number"] == invoice["invoice_number"]
    assert issued.json()["data"]["seller_trn_snapshot"] == VALID_TRN
    got = _get_invoice(headers, invoice["id"])
    cn_total = _dec(cn["total_amount"])
    assert _dec(got["amount_credited"]) == cn_total
    assert _dec(got["balance_due"]) == total - cn_total
    assert got["status"] in ("SENT", "OVERDUE")
    assert _payment_count(headers, invoice["id"]) == before_payments
    bal = _get_balance(headers, invoice["id"])
    assert _dec(bal["amount_paid"]) == Decimal("0.00")
    assert _dec(bal["total_paid"]) == Decimal("0.00")
    assert _dec(bal["amount_credited"]) == cn_total
    assert _dec(bal["balance_due"]) == total - cn_total


def test_issue_covering_full_unpaid_marks_paid_no_payment():
    token, _ = _register("cn_full", "CN Full WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="2", price="50.00")])
    cn = _create_cn(headers, invoice)
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    got = _get_invoice(headers, invoice["id"])
    assert got["status"] == "PAID"
    assert _dec(got["balance_due"]) == Decimal("0.00")
    assert _payment_count(headers, invoice["id"]) == 0


def test_paid_invoice_cn_stays_paid_parks_credit_balance():
    token, _ = _register("cn_paid", "CN Paid WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="1", price="100.00")])
    total = _dec(invoice["total_amount"])
    pay = _pay(headers, invoice["id"], total)
    assert pay.status_code == 200, pay.text
    payments_before = _payment_count(headers, invoice["id"])
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    got = _get_invoice(headers, invoice["id"])
    assert got["status"] == "PAID"
    assert _dec(got["balance_due"]) == Decimal("0.00")
    assert _payment_count(headers, invoice["id"]) == payments_before
    dealer = client.get(f"/api/v1/clients/{client_id}", headers=headers)
    assert dealer.status_code == 200, dealer.text
    assert _dec(dealer.json()["data"]["credit_balance"]) == _dec(cn["total_amount"])
    credit = client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)
    assert credit.status_code == 200, credit.text
    assert _dec(credit.json()["data"]["credit_balance"]) == _dec(cn["total_amount"])


def test_second_issue_idempotent_no_double_credit():
    token, _ = _register("cn_idem", "CN Idem WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="4", price="25.00")])
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    first = _issue(headers, cn["id"])
    assert first.status_code == 200, first.text
    credited = _dec(_get_invoice(headers, invoice["id"])["amount_credited"])
    second = _issue(headers, cn["id"])
    assert second.status_code == 200, second.text
    assert second.json()["data"]["status"] == "ISSUED"
    assert _dec(_get_invoice(headers, invoice["id"])["amount_credited"]) == credited


def test_balance_endpoint_does_not_treat_credits_as_paid():
    token, _ = _register("cn_bal", "CN Bal WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="100.00")])
    total = _dec(invoice["total_amount"])
    cash = Decimal("200.00")
    pay = _pay(headers, invoice["id"], cash)
    assert pay.status_code == 200, pay.text
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "2"}],
    )
    assert _issue(headers, cn["id"]).status_code == 200
    cn_total = _dec(cn["total_amount"])
    due = total - cash - cn_total
    bal = _get_balance(headers, invoice["id"])
    assert _dec(bal["amount_paid"]) == cash
    assert _dec(bal["total_paid"]) == cash
    assert _dec(bal["amount_credited"]) == cn_total
    assert _dec(bal["balance_due"]) == due
    assert _dec(bal["total_paid"]) != total - due


def test_payment_after_cn_respects_new_balance():
    token, _ = _register("cn_pay", "CN Pay WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers)
    invoice = _sent_invoice(headers, client_id, [_line(qty="10", price="10.00")])
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "4"}],
    )
    assert _issue(headers, cn["id"]).status_code == 200
    got = _get_invoice(headers, invoice["id"])
    due = _dec(got["balance_due"])
    over = _pay(headers, invoice["id"], due + Decimal("1.00"))
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"
    ok = _pay(headers, invoice["id"], due)
    assert ok.status_code == 200, ok.text
    paid = _get_invoice(headers, invoice["id"])
    assert paid["status"] == "PAID"
    assert _dec(paid["balance_due"]) == Decimal("0.00")


def test_hold_client_issue_not_blocked_exposure_drops():
    token, _ = _register("cn_hold", "CN Hold WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers, credit_limit="0")
    invoice = _sent_invoice(headers, client_id, [_line(qty="1", price="80.00")])
    hold = client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)
    assert hold.status_code == 200, hold.text
    assert hold.json()["data"]["credit_status"] == "HOLD"
    exposure_before = _dec(hold.json()["data"]["exposure"])
    cn = _create_cn(
        headers,
        invoice,
        [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
    )
    issued = _issue(headers, cn["id"])
    assert issued.status_code == 200, issued.text
    assert issued.json().get("error") is None
    after = client.get(f"/api/v1/clients/{client_id}/credit", headers=headers)
    assert after.status_code == 200, after.text
    assert _dec(after.json()["data"]["exposure"]) < exposure_before


def test_workspace_b_isolation_404():
    token_a, _ = _register("cn_iso_a", "CN Iso A")
    headers_a = _headers(token_a)
    _set_workspace(headers_a)
    client_id = _create_client(headers_a)
    invoice = _sent_invoice(headers_a, client_id, [_line(qty="1", price="12.00")])
    cn = _create_cn(headers_a, invoice)
    token_b, _ = _register("cn_iso_b", "CN Iso B")
    headers_b = _headers(token_b)
    missing = client.get(f"/api/v1/credit-notes/{cn['id']}", headers=headers_b)
    assert missing.status_code == 404, missing.text
    issue = _issue(headers_b, cn["id"])
    assert issue.status_code == 404, issue.text


def test_alembic_upgrade_head_and_check():
    alembic_bin = shutil.which("alembic")
    assert alembic_bin, "alembic CLI not found"
    upgrade = subprocess.run(
        [alembic_bin, "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    check = subprocess.run(
        [alembic_bin, "check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    combined = check.stdout + check.stderr
    assert "No new upgrade operations detected" in combined
