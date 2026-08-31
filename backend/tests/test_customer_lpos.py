"""WP-A customer LPO API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
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


async def override_get_session():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create all tables before tests run, drop them after."""

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


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _create_client(headers: dict, name: str = "Dealer", **extra) -> str:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _adhoc_item(**extra) -> dict:
    item = {
        "description": "NYM 3x2.5 cable",
        "quantity": "100",
        "unit_price": "10.00",
    }
    item.update(extra)
    return item


def _lpo_payload(client_id: str, items: list[dict], **extra) -> dict:
    body = {"client_id": client_id, "items": items}
    body.update(extra)
    return body


def _create_lpo(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    r = client.post(
        "/api/v1/customer-purchase-orders",
        json=_lpo_payload(client_id, items, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _get_lpo(headers: dict, lpo_id: str):
    return client.get(f"/api/v1/customer-purchase-orders/{lpo_id}", headers=headers)


def _receive(headers: dict, lpo_id: str):
    return client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/receive", json={}, headers=headers
    )


def _cancel(headers: dict, lpo_id: str, reason: str | None = None):
    body = {} if reason is None else {"reason": reason}
    return client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/cancel", json=body, headers=headers
    )


def _invoice_lpo(headers: dict, lpo_id: str, body: dict | None = None):
    return client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/invoices",
        json=body or {},
        headers=headers,
    )


def _create_quote(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    body = {"client_id": client_id, "items": items}
    body.update(extra)
    r = client.post("/api/v1/quotations", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _accept_quote(headers: dict, quote_id: str) -> None:
    assert (
        client.post(
            f"/api/v1/quotations/{quote_id}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    acc = client.post(f"/api/v1/quotations/{quote_id}/accept", headers=headers)
    assert acc.status_code == 200, acc.text


def _set_workspace_fta(headers: dict) -> None:
    r = client.put(
        "/api/v1/workspaces/me",
        json={"trn": VALID_TRN, "address": SELLER_ADDRESS},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_create_sequential_lpo_numbers():
    token, _ = _register("lpo_num", "LPO Number WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    first = _create_lpo(headers, client_id, [_adhoc_item()])
    second = _create_lpo(
        headers, client_id, [_adhoc_item(description="Second", quantity="1")]
    )
    assert first["lpo_number"] == f"LPO-{YEAR}-0001"
    assert second["lpo_number"] == f"LPO-{YEAR}-0002"
    assert first["status"] == "DRAFT"
    assert first["quotation_id"] is None
    assert first["lpo_date"] == _utc_today().isoformat()


def test_customer_po_number_unique_per_client():
    token, _ = _register("lpo_po", "LPO PO WS")
    headers = _headers(token)
    client_a = _create_client(headers, name="Client A")
    client_b = _create_client(headers, name="Client B")
    first = _create_lpo(
        headers, client_a, [_adhoc_item(quantity="1")], customer_po_number="PO-001"
    )
    assert first["customer_po_number"] == "PO-001"
    dup = client.post(
        "/api/v1/customer-purchase-orders",
        json=_lpo_payload(
            client_a, [_adhoc_item(quantity="1")], customer_po_number="PO-001"
        ),
        headers=headers,
    )
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["code"] == "CONFLICT"
    assert dup.json()["error"]["field"] == "customer_po_number"
    other = _create_lpo(
        headers, client_b, [_adhoc_item(quantity="1")], customer_po_number="PO-001"
    )
    assert other["customer_po_number"] == "PO-001"


def test_line_tax_xor_extra_key_non_aed():
    token, _ = _register("lpo_val", "LPO Val WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_lpo(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "10", "unit_price": "100.00"}],
    )
    line = data["items"][0]
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    assert _dec(line["quantity_invoiced"]) == Decimal("0.00")
    assert _dec(line["quantity_remaining"]) == Decimal("10.00")
    assert _dec(line["line_net"]) == Decimal("1000.00")
    assert _dec(line["tax_amount"]) == Decimal("50.00")
    assert _dec(data["total_amount"]) == Decimal("1050.00")
    both = client.post(
        "/api/v1/customer-purchase-orders",
        json=_lpo_payload(
            client_id,
            [
                {
                    "description": "Cable",
                    "quantity": "1",
                    "unit_price": "100",
                    "discount_percent": "10",
                    "discount_amount": "5",
                }
            ],
        ),
        headers=headers,
    )
    assert both.status_code == 422, both.text
    extra = client.post(
        "/api/v1/customer-purchase-orders",
        json=_lpo_payload(
            client_id,
            [
                {
                    "description": "Cable",
                    "quantity": "1",
                    "unit_price": "100",
                    "hs_code": "8544",
                }
            ],
        ),
        headers=headers,
    )
    assert extra.status_code == 422, extra.text
    usd = client.post(
        "/api/v1/customer-purchase-orders",
        json=_lpo_payload(
            client_id,
            [{"description": "Cable", "quantity": "1", "unit_price": "100"}],
            currency="USD",
        ),
        headers=headers,
    )
    assert usd.status_code == 422, usd.text


def test_isolation_workspace_b_404():
    token_a, _ = _register("lpo_iso_a", "LPO Iso A")
    headers_a = _headers(token_a)
    client_id = _create_client(headers_a)
    lpo = _create_lpo(headers_a, client_id, [_adhoc_item(quantity="1")])
    token_b, _ = _register("lpo_iso_b", "LPO Iso B")
    headers_b = _headers(token_b)
    lid = lpo["id"]
    assert _get_lpo(headers_b, lid).status_code == 404
    assert (
        client.put(
            f"/api/v1/customer-purchase-orders/{lid}",
            json={"notes": "x"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert _receive(headers_b, lid).status_code == 404
    assert _invoice_lpo(headers_b, lid).status_code == 404
    assert _cancel(headers_b, lid).status_code == 404


def test_put_delete_receive_non_draft_and_soft_delete():
    token, _ = _register("lpo_state", "LPO State WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert _receive(headers, lpo["id"]).status_code == 200
    put = client.put(
        f"/api/v1/customer-purchase-orders/{lpo['id']}",
        json={"notes": "nope"},
        headers=headers,
    )
    assert put.status_code == 403, put.text
    assert put.json()["error"]["code"] == "INVALID_STATE"
    delete = client.delete(
        f"/api/v1/customer-purchase-orders/{lpo['id']}", headers=headers
    )
    assert delete.status_code == 403, delete.text
    again = _receive(headers, lpo["id"])
    assert again.status_code == 403, again.text
    draft = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert draft["lpo_number"] == f"LPO-{YEAR}-0002"
    deleted = client.delete(
        f"/api/v1/customer-purchase-orders/{draft['id']}", headers=headers
    )
    assert deleted.status_code == 200, deleted.text
    assert _get_lpo(headers, draft["id"]).status_code == 404
    third = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert third["lpo_number"] == f"LPO-{YEAR}-0003"


def test_quote_convert_to_lpo_frozen_and_idempotent():
    token, _ = _register("lpo_conv", "LPO Convert WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(
        headers,
        client_id,
        [
            {
                "description": "Cable",
                "quantity": "2",
                "unit_price": "20.00",
                "tax_rate": "5.00",
            }
        ],
        notes="Site visit",
    )
    _accept_quote(headers, quote["id"])
    first = client.post(
        f"/api/v1/quotations/{quote['id']}/convert-to-lpo",
        json={"customer_po_number": "ADNOC-PO-8821"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    lpo = first.json()["data"]
    assert lpo["status"] == "DRAFT"
    assert lpo["quotation_id"] == quote["id"]
    assert lpo["customer_po_number"] == "ADNOC-PO-8821"
    assert lpo["notes"].startswith(f"Converted from {quote['quotation_number']}.")
    assert _dec(lpo["items"][0]["unit_price"]) == Decimal("20.00")
    assert _dec(lpo["items"][0]["quantity"]) == Decimal("2.00")
    second = client.post(
        f"/api/v1/quotations/{quote['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == lpo["id"]
    got = client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert got.json()["data"]["status"] == "CONVERTED"
    assert got.json()["data"]["converted_lpo_id"] == lpo["id"]


def test_convert_mutex_and_non_accepted_403():
    token, _ = _register("lpo_mutex", "LPO Mutex WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    draft = _create_quote(headers, client_id, [_adhoc_item(quantity="1")])
    r = client.post(
        f"/api/v1/quotations/{draft['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"
    assert (
        client.post(
            f"/api/v1/quotations/{draft['id']}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    r = client.post(
        f"/api/v1/quotations/{draft['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert r.status_code == 403, r.text
    accepted = _create_quote(headers, client_id, [_adhoc_item(quantity="1")])
    _accept_quote(headers, accepted["id"])
    lpo = client.post(
        f"/api/v1/quotations/{accepted['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert lpo.status_code == 201, lpo.text
    inv = client.post(
        f"/api/v1/quotations/{accepted['id']}/convert-to-invoice", headers=headers
    )
    assert inv.status_code == 409, inv.text
    other = _create_quote(headers, client_id, [_adhoc_item(quantity="1")])
    _accept_quote(headers, other["id"])
    invoice = client.post(
        f"/api/v1/quotations/{other['id']}/convert-to-invoice", headers=headers
    )
    assert invoice.status_code == 201, invoice.text
    blocked = client.post(
        f"/api/v1/quotations/{other['id']}/convert-to-lpo", json={}, headers=headers
    )
    assert blocked.status_code == 409, blocked.text


def test_receive_invoice_all_remaining_invoiced_fta_blocked():
    token, _ = _register("lpo_inv_all", "LPO Invoice All WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    rec = _receive(headers, lpo["id"])
    assert rec.status_code == 200, rec.text
    assert rec.json()["data"]["status"] == "RECEIVED"
    created = _invoice_lpo(headers, lpo["id"])
    assert created.status_code == 201, created.text
    inv = created.json()["data"]
    assert inv["status"] == "DRAFT"
    assert inv["quotation_id"] is None
    assert inv["customer_purchase_order_id"] == lpo["id"]
    assert inv["invoice_kind"] is None
    assert inv["seller_trn_snapshot"] is None
    assert _dec(inv["items"][0]["quantity"]) == Decimal("100.00")
    got = _get_lpo(headers, lpo["id"])
    assert got.json()["data"]["status"] == "INVOICED"
    assert len(got.json()["data"]["invoices"]) == 1
    send = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert send.status_code == 400, send.text
    assert send.json()["error"]["code"] == "FTA_SEND_BLOCKED"


def test_partial_then_full_then_nothing_left():
    token, _ = _register("lpo_partial", "LPO Partial WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200
    line_id = lpo["items"][0]["id"]
    first = _invoice_lpo(
        headers,
        lpo["id"],
        {"items": [{"customer_purchase_order_item_id": line_id, "quantity": "40"}]},
    )
    assert first.status_code == 201, first.text
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "PARTIAL"
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("40.00")
    assert _dec(got["items"][0]["quantity_remaining"]) == Decimal("60.00")
    second = _invoice_lpo(
        headers,
        lpo["id"],
        {"items": [{"customer_purchase_order_item_id": line_id, "quantity": "60"}]},
    )
    assert second.status_code == 201, second.text
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "INVOICED"
    assert _dec(got["items"][0]["quantity_remaining"]) == Decimal("0.00")
    third = _invoice_lpo(headers, lpo["id"])
    assert third.status_code == 400, third.text
    assert third.json()["error"]["code"] == "VALIDATION_ERROR"


def test_over_invoice_400_lpo_unchanged():
    token, _ = _register("lpo_over", "LPO Over WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200
    line_id = lpo["items"][0]["id"]
    over = _invoice_lpo(
        headers,
        lpo["id"],
        {"items": [{"customer_purchase_order_item_id": line_id, "quantity": "101"}]},
    )
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "VALIDATION_ERROR"
    assert over.json()["error"]["field"] == "quantity"
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "RECEIVED"
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("0.00")


def test_duplicate_line_ids_over_invoice_400_cache_unchanged():
    token, _ = _register("lpo_dup_line", "LPO Dup Line WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200
    line_id = lpo["items"][0]["id"]
    before = _get_lpo(headers, lpo["id"]).json()["data"]
    over = _invoice_lpo(
        headers,
        lpo["id"],
        {
            "items": [
                {"customer_purchase_order_item_id": line_id, "quantity": "60"},
                {"customer_purchase_order_item_id": line_id, "quantity": "60"},
            ]
        },
    )
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "VALIDATION_ERROR"
    assert over.json()["error"]["field"] == "quantity"
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "RECEIVED"
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("0.00")
    assert _dec(got["items"][0]["quantity_invoiced"]) == _dec(
        before["items"][0]["quantity_invoiced"]
    )
    assert got["invoices"] == []


def test_concurrent_full_remaining_one_wins():
    token, _ = _register("lpo_race", "LPO Race WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200

    def post_all(_: int):
        return _invoice_lpo(headers, lpo["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(post_all, range(2)))
    codes = sorted(r.status_code for r in results)
    assert 201 in codes
    assert 400 in codes
    assert codes == [201, 400]
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("100.00")
    assert _dec(got["items"][0]["quantity_invoiced"]) <= _dec(
        got["items"][0]["quantity"]
    )


def test_delete_draft_invoice_restores_remaining():
    token, _ = _register("lpo_del_inv", "LPO Del Inv WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200
    created = _invoice_lpo(headers, lpo["id"])
    assert created.status_code == 201, created.text
    invoice_id = created.json()["data"]["id"]
    deleted = client.delete(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "RECEIVED"
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("0.00")
    assert got["invoices"] == []


def test_void_sent_invoice_restores_remaining():
    token, _ = _register("lpo_void", "LPO Void WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(headers, name="Cash buyer")
    lpo = _create_lpo(headers, client_id, [_adhoc_item()])
    assert _receive(headers, lpo["id"]).status_code == 200
    created = _invoice_lpo(headers, lpo["id"])
    invoice_id = created.json()["data"]["id"]
    sent = client.post(f"/api/v1/invoices/{invoice_id}/send", json={}, headers=headers)
    assert sent.status_code == 200, sent.text
    voided = client.post(
        f"/api/v1/invoices/{invoice_id}/void",
        json={"reason": "Customer cancelled the LPO slice"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert got["status"] == "RECEIVED"
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("0.00")


def test_put_lpo_linked_invoice_403():
    token, _ = _register("lpo_put_inv", "LPO Put Inv WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    lpo = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert _receive(headers, lpo["id"]).status_code == 200
    created = _invoice_lpo(headers, lpo["id"])
    invoice_id = created.json()["data"]["id"]
    put = client.put(
        f"/api/v1/invoices/{invoice_id}", json={"notes": "edit"}, headers=headers
    )
    assert put.status_code == 403, put.text
    assert put.json()["error"]["code"] == "INVALID_STATE"


def test_cancel_received_rules():
    token, _ = _register("lpo_cancel", "LPO Cancel WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    with_inv = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert _receive(headers, with_inv["id"]).status_code == 200
    assert _invoice_lpo(headers, with_inv["id"]).status_code == 201
    blocked = _cancel(headers, with_inv["id"])
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "INVALID_STATE"
    bare = _create_lpo(headers, client_id, [_adhoc_item(quantity="1")])
    assert _receive(headers, bare["id"]).status_code == 200
    cancelled = _cancel(headers, bare["id"], reason="Contractor withdrew")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    after = _invoice_lpo(headers, bare["id"])
    assert after.status_code == 403, after.text
    assert after.json()["error"]["code"] == "INVALID_STATE"


def test_concurrent_lpo_numbers_unique():
    token, _ = _register("lpo_conc", "LPO Conc WS")
    headers = _headers(token)
    client_id = _create_client(headers)

    def create_one(index: int) -> str:
        r = client.post(
            "/api/v1/customer-purchase-orders",
            json=_lpo_payload(
                client_id,
                [
                    {
                        "description": f"Item {index}",
                        "quantity": "1",
                        "unit_price": "10.00",
                    }
                ],
            ),
            headers=headers,
        )
        assert r.status_code == 201, f"LPO {index} failed: {r.text}"
        return r.json()["data"]["lpo_number"]

    with ThreadPoolExecutor(max_workers=5) as executor:
        numbers = list(executor.map(create_one, range(10)))
    assert len(numbers) == len(set(numbers)), numbers
    seq = sorted(int(num.split("-")[-1]) for num in numbers)
    assert seq == list(range(1, 11)), seq
    assert all(n.startswith(f"LPO-{YEAR}-") for n in numbers)
