"""WP-A delivery notes API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import shutil
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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
from app.models.inventory import InventoryLevel, InventoryTransaction, TransactionType
from app.models.user import User, UserRole

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
    body = {"trn": VALID_TRN, "address": SELLER_ADDRESS}
    body.update(fields)
    r = client.put("/api/v1/workspaces/me", json=body, headers=headers)
    assert r.status_code == 200, r.text


def _uom(headers: dict) -> str:
    r = client.post(
        "/api/v1/products/uom",
        json={"name": "Metres", "code": f"M-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _product(headers: dict, uom_id: str, name: str = "NYM cable") -> dict:
    r = client.post(
        "/api/v1/products",
        json={
            "name": name,
            "internal_sku": f"ELE-{uuid.uuid4().hex[:8]}",
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _warehouse_bin(headers: dict) -> tuple[str, str]:
    code = f"WH-{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/api/v1/inventory/warehouses",
        json={"code": code, "name": "Main warehouse"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    warehouse_id = r.json()["data"]["id"]
    br = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        json={"code": "A-01"},
        headers=headers,
    )
    assert br.status_code in (200, 201), br.text
    return warehouse_id, br.json()["data"]["id"]


def _adjust(
    headers: dict,
    product_id: str,
    warehouse_id: str,
    bin_id: str,
    quantity: str,
    reason: str = "OPENING",
    notes: str = "Opening stock",
):
    return client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "bin_id": bin_id,
            "quantity": quantity,
            "reason": reason,
            "notes": notes,
        },
        headers=headers,
    )


def _on_hand(headers: dict, product_id: str) -> Decimal:
    r = client.get(f"/api/v1/inventory/levels?product_id={product_id}", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    if not rows:
        return Decimal("0.00")
    return _dec(rows[0]["on_hand"])


def _adhoc_item(quantity: str = "100", **extra) -> dict:
    item = {
        "description": "NYM 3x2.5 cable",
        "quantity": quantity,
        "unit_price": "10.00",
    }
    item.update(extra)
    return item


def _create_lpo(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    body = {"client_id": client_id, "items": items}
    body.update(extra)
    r = client.post("/api/v1/customer-purchase-orders", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _receive(headers: dict, lpo_id: str):
    return client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/receive", json={}, headers=headers
    )


def _received_lpo(headers: dict, client_id: str, items: list[dict]) -> dict:
    lpo = _create_lpo(headers, client_id, items)
    rec = _receive(headers, lpo["id"])
    assert rec.status_code == 200, rec.text
    return rec.json()["data"]


def _invoice_lpo(headers: dict, lpo_id: str, body: dict | None = None):
    return client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/invoices",
        json=body or {},
        headers=headers,
    )


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


def _dn_payload(warehouse_id: str, **extra) -> dict:
    body = {"warehouse_id": warehouse_id}
    body.update(extra)
    return body


def _create_dn(headers: dict, warehouse_id: str, **extra) -> dict:
    r = client.post(
        "/api/v1/delivery-notes",
        json=_dn_payload(warehouse_id, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _confirm(headers: dict, dn_id: str):
    return client.post(
        f"/api/v1/delivery-notes/{dn_id}/confirm", json={}, headers=headers
    )


def _cancel_dn(headers: dict, dn_id: str, reason: str | None = None):
    body = {} if reason is None else {"reason": reason}
    return client.post(
        f"/api/v1/delivery-notes/{dn_id}/cancel", json=body, headers=headers
    )


def _get_dn(headers: dict, dn_id: str):
    return client.get(f"/api/v1/delivery-notes/{dn_id}", headers=headers)


def _get_lpo(headers: dict, lpo_id: str):
    return client.get(f"/api/v1/customer-purchase-orders/{lpo_id}", headers=headers)


async def _txns(
    workspace_id: str,
    product_id: str | None = None,
    reference_type: str | None = None,
) -> list[InventoryTransaction]:
    async with TestingSessionLocal() as session:
        query = select(InventoryTransaction).where(
            InventoryTransaction.workspace_id == uuid.UUID(workspace_id)
        )
        if product_id:
            query = query.where(
                InventoryTransaction.product_id == uuid.UUID(product_id)
            )
        if reference_type:
            query = query.where(InventoryTransaction.reference_type == reference_type)
        result = await session.execute(query)
        return list(result.scalars().all())


async def _level_on_hand(workspace_id: str, product_id: str, bin_id: str) -> Decimal:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryLevel).where(
                InventoryLevel.workspace_id == uuid.UUID(workspace_id),
                InventoryLevel.product_id == uuid.UUID(product_id),
                InventoryLevel.bin_id == uuid.UUID(bin_id),
            )
        )
        level = result.scalar_one_or_none()
        if level is None:
            return Decimal("0.00")
        return Decimal(str(level.on_hand))


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


def test_create_sequential_dn_numbers():
    token, _ = _register("dn_num", "DN Number WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, _ = _warehouse_bin(headers)
    lpo = _received_lpo(headers, client_id, [_adhoc_item(quantity="10")])
    first = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    second = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    assert first["dn_number"] == f"DN-{YEAR}-0001"
    assert second["dn_number"] == f"DN-{YEAR}-0002"
    assert first["status"] == "DRAFT"


def test_both_or_neither_parent_422_and_cross_workspace_404():
    token_a, _ = _register("dn_xor_a", "DN XOR A")
    token_b, _ = _register("dn_xor_b", "DN XOR B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    client_id = _create_client(headers_a)
    warehouse_a, _ = _warehouse_bin(headers_a)
    warehouse_b, _ = _warehouse_bin(headers_b)
    lpo = _received_lpo(headers_a, client_id, [_adhoc_item(quantity="5")])
    invoice = _create_invoice(headers_a, client_id, [_adhoc_item(quantity="5")])
    neither = client.post(
        "/api/v1/delivery-notes",
        json={"warehouse_id": warehouse_a},
        headers=headers_a,
    )
    assert neither.status_code == 422, neither.text
    both = client.post(
        "/api/v1/delivery-notes",
        json={
            "warehouse_id": warehouse_a,
            "customer_purchase_order_id": lpo["id"],
            "invoice_id": invoice["id"],
        },
        headers=headers_a,
    )
    assert both.status_code == 422, both.text
    extra = client.post(
        "/api/v1/delivery-notes",
        json={
            "warehouse_id": warehouse_a,
            "customer_purchase_order_id": lpo["id"],
            "mystery": True,
        },
        headers=headers_a,
    )
    assert extra.status_code == 422, extra.text
    cross_lpo = client.post(
        "/api/v1/delivery-notes",
        json={"warehouse_id": warehouse_b, "customer_purchase_order_id": lpo["id"]},
        headers=headers_b,
    )
    assert cross_lpo.status_code == 404, cross_lpo.text
    cross_wh = client.post(
        "/api/v1/delivery-notes",
        json={"warehouse_id": warehouse_b, "customer_purchase_order_id": lpo["id"]},
        headers=headers_a,
    )
    assert cross_wh.status_code == 404, cross_wh.text
    inv_b = _create_invoice(
        headers_b, _create_client(headers_b), [_adhoc_item(quantity="1")]
    )
    cross_inv = client.post(
        "/api/v1/delivery-notes",
        json={"warehouse_id": warehouse_a, "invoice_id": inv_b["id"]},
        headers=headers_a,
    )
    assert cross_inv.status_code == 404, cross_inv.text


def test_lpo_remaining_independent_of_invoiced():
    token, _ = _register("dn_rem", "DN Remaining WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, _ = _warehouse_bin(headers)
    lpo = _received_lpo(headers, client_id, [_adhoc_item(quantity="100")])
    line_id = lpo["items"][0]["id"]
    first = _create_dn(
        headers,
        warehouse_id,
        customer_purchase_order_id=lpo["id"],
        items=[
            {
                "customer_purchase_order_item_id": line_id,
                "quantity": "40",
            }
        ],
    )
    conf = _confirm(headers, first["id"])
    assert conf.status_code == 200, conf.text
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert _dec(got["items"][0]["quantity_delivered"]) == Decimal("40.00")
    assert _dec(got["items"][0]["quantity_invoiced"]) == Decimal("0.00")
    over = client.post(
        "/api/v1/delivery-notes",
        json=_dn_payload(
            warehouse_id,
            customer_purchase_order_id=lpo["id"],
            items=[
                {
                    "customer_purchase_order_item_id": line_id,
                    "quantity": "70",
                }
            ],
        ),
        headers=headers,
    )
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "VALIDATION_ERROR"
    assert over.json()["error"]["field"] == "quantity"
    second = _create_dn(
        headers,
        warehouse_id,
        customer_purchase_order_id=lpo["id"],
        items=[
            {
                "customer_purchase_order_item_id": line_id,
                "quantity": "60",
            }
        ],
    )
    conf2 = _confirm(headers, second["id"])
    assert conf2.status_code == 200, conf2.text
    assert conf2.json()["data"]["status"] == "CONFIRMED"
    final = _get_lpo(headers, lpo["id"]).json()["data"]
    assert _dec(final["items"][0]["quantity_delivered"]) == Decimal("100.00")
    listed = client.get(
        "/api/v1/delivery-notes",
        params={"customer_purchase_order_id": lpo["id"], "page": 1, "per_page": 20},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total"] == 2


def test_invoice_backed_dn_cannot_exceed_invoice_qty():
    token, _ = _register("dn_inv", "DN Invoice WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, _ = _warehouse_bin(headers)
    invoice = _create_invoice(headers, client_id, [_adhoc_item(quantity="10")])
    line_id = invoice["items"][0]["id"]
    over = client.post(
        "/api/v1/delivery-notes",
        json=_dn_payload(
            warehouse_id,
            invoice_id=invoice["id"],
            items=[{"invoice_item_id": line_id, "quantity": "11"}],
        ),
        headers=headers,
    )
    assert over.status_code == 400, over.text
    dn = _create_dn(
        headers,
        warehouse_id,
        invoice_id=invoice["id"],
        items=[{"invoice_item_id": line_id, "quantity": "10"}],
    )
    assert _confirm(headers, dn["id"]).status_code == 200
    lpo = _received_lpo(headers, client_id, [_adhoc_item(quantity="50")])
    sliced = _invoice_lpo(headers, lpo["id"])
    assert sliced.status_code == 201, sliced.text
    from_lpo = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    assert from_lpo["customer_purchase_order_id"] == lpo["id"]
    assert from_lpo["invoice_id"] is None
    assert _dec(from_lpo["items"][0]["quantity"]) == Decimal("50.00")


def test_catalog_issue_and_adhoc_no_ledger():
    token, ws = _register("dn_stock", "DN Stock WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    adj = _adjust(headers, product["id"], warehouse_id, bin_id, "80")
    assert adj.status_code == 200, adj.text
    lpo = _received_lpo(
        headers,
        client_id,
        [
            {
                "product_id": product["id"],
                "quantity": "30",
                "unit_price": "5.00",
            },
            _adhoc_item(quantity="5", description="Labour"),
        ],
    )
    dn = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    catalog = next(i for i in dn["items"] if i["product_id"] == product["id"])
    adhoc = next(i for i in dn["items"] if i["product_id"] is None)
    conf = _confirm(headers, dn["id"])
    assert conf.status_code == 200, conf.text
    assert _on_hand(headers, product["id"]) == Decimal("50.00")
    issues = asyncio.run(_txns(ws, product["id"], "DN"))
    assert len(issues) == 1
    assert issues[0].transaction_type == TransactionType.ISSUE
    assert Decimal(str(issues[0].quantity)) == Decimal("-30.00")
    assert issues[0].reference_type == "DN"
    assert str(issues[0].reference_id) == catalog["id"]
    adhoc_txns = asyncio.run(_txns(ws, reference_type="DN"))
    assert all(str(t.reference_id) != adhoc["id"] for t in adhoc_txns)


def test_insufficient_stock_stays_draft():
    token, ws = _register("dn_insuf", "DN Insufficient WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    assert _adjust(headers, product["id"], warehouse_id, bin_id, "5").status_code == 200
    lpo = _received_lpo(
        headers,
        client_id,
        [{"product_id": product["id"], "quantity": "10", "unit_price": "1.00"}],
    )
    dn = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    failed = _confirm(headers, dn["id"])
    assert failed.status_code == 400, failed.text
    assert failed.json()["error"]["code"] == "VALIDATION_ERROR"
    assert failed.json()["error"]["field"] == "quantity"
    assert _get_dn(headers, dn["id"]).json()["data"]["status"] == "DRAFT"
    assert asyncio.run(_level_on_hand(ws, product["id"], bin_id)) == Decimal("5.00")


def test_concurrent_confirm_last_ten_units():
    token, ws = _register("dn_race", "DN Race WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    assert (
        _adjust(headers, product["id"], warehouse_id, bin_id, "10").status_code == 200
    )
    lpo = _received_lpo(
        headers,
        client_id,
        [{"product_id": product["id"], "quantity": "10", "unit_price": "1.00"}],
    )
    line_id = lpo["items"][0]["id"]

    def make_dn(_: int) -> str:
        data = _create_dn(
            headers,
            warehouse_id,
            customer_purchase_order_id=lpo["id"],
            items=[{"customer_purchase_order_item_id": line_id, "quantity": "10"}],
        )
        return data["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(make_dn, range(2)))

    def confirm_one(dn_id: str):
        return _confirm(headers, dn_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm_one, ids))
    codes = sorted(r.status_code for r in results)
    assert 200 in codes
    assert 400 in codes
    on_hand = asyncio.run(_level_on_hand(ws, product["id"], bin_id))
    assert on_hand >= Decimal("0.00")
    assert on_hand == Decimal("0.00")


def test_confirm_idempotent_single_issue():
    token, ws = _register("dn_idemp", "DN Idemp WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    assert (
        _adjust(headers, product["id"], warehouse_id, bin_id, "20").status_code == 200
    )
    lpo = _received_lpo(
        headers,
        client_id,
        [{"product_id": product["id"], "quantity": "8", "unit_price": "1.00"}],
    )
    dn = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    first = _confirm(headers, dn["id"])
    second = _confirm(headers, dn["id"])
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "CONFIRMED"
    issues = asyncio.run(_txns(ws, product["id"], "DN"))
    assert len(issues) == 1


def test_cancel_confirmed_reverses_stock_and_delivered():
    token, ws = _register("dn_cancel", "DN Cancel WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    assert (
        _adjust(headers, product["id"], warehouse_id, bin_id, "15").status_code == 200
    )
    lpo = _received_lpo(
        headers,
        client_id,
        [{"product_id": product["id"], "quantity": "7", "unit_price": "1.00"}],
    )
    dn = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    assert _confirm(headers, dn["id"]).status_code == 200
    cancelled = _cancel_dn(headers, dn["id"], reason="Customer refused")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert asyncio.run(_level_on_hand(ws, product["id"], bin_id)) == Decimal("15.00")
    reverses = asyncio.run(_txns(ws, product["id"], "DN_CANCEL"))
    assert len(reverses) == 1
    assert Decimal(str(reverses[0].quantity)) == Decimal("7.00")
    got = _get_lpo(headers, lpo["id"]).json()["data"]
    assert _dec(got["items"][0]["quantity_delivered"]) == Decimal("0.00")
    draft_del = client.delete(f"/api/v1/delivery-notes/{dn['id']}", headers=headers)
    assert draft_del.status_code == 403


def test_hold_blocks_confirm_only_when_block_do_on_hold():
    token, _ = _register("dn_hold", "DN Hold WS")
    headers = _headers(token)
    _set_workspace(headers, block_do_on_hold=True, block_po_on_hold=False)
    client_id = _create_client(headers, credit_limit="0")
    invoice = _create_invoice(
        headers, client_id, [_adhoc_item(quantity="1", unit_price="50.00")]
    )
    sent = client.post(
        f"/api/v1/invoices/{invoice['id']}/send", json={}, headers=headers
    )
    assert sent.status_code == 200, sent.text
    warehouse_id, _ = _warehouse_bin(headers)
    lpo = _received_lpo(headers, client_id, [_adhoc_item(quantity="3")])
    dn = _create_dn(headers, warehouse_id, customer_purchase_order_id=lpo["id"])
    blocked = _confirm(headers, dn["id"])
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error"]["code"] == "CREDIT_HOLD"
    assert blocked.json()["error"]["field"] == "client.credit_status"
    assert _get_dn(headers, dn["id"]).json()["data"]["status"] == "DRAFT"
    _set_workspace(headers, block_do_on_hold=False, block_po_on_hold=False)
    allowed = _confirm(headers, dn["id"])
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["status"] == "CONFIRMED"


def test_put_delete_non_draft_403_and_isolation():
    token_a, _ = _register("dn_iso_a", "DN Iso A")
    token_b, _ = _register("dn_iso_b", "DN Iso B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    client_id = _create_client(headers_a)
    warehouse_id, _ = _warehouse_bin(headers_a)
    lpo = _received_lpo(headers_a, client_id, [_adhoc_item(quantity="4")])
    dn = _create_dn(headers_a, warehouse_id, customer_purchase_order_id=lpo["id"])
    assert _confirm(headers_a, dn["id"]).status_code == 200
    put = client.put(
        f"/api/v1/delivery-notes/{dn['id']}", json={"notes": "nope"}, headers=headers_a
    )
    assert put.status_code == 403, put.text
    deleted = client.delete(f"/api/v1/delivery-notes/{dn['id']}", headers=headers_a)
    assert deleted.status_code == 403
    assert _get_dn(headers_b, dn["id"]).status_code == 404
    assert (
        client.post(
            f"/api/v1/delivery-notes/{dn['id']}/confirm", json={}, headers=headers_b
        ).status_code
        == 404
    )
    listed = client.get("/api/v1/delivery-notes", headers=headers_b)
    assert listed.status_code == 200
    assert listed.json()["data"] == []


def test_adjust_admin_reason_member_403_isolation_extra_key():
    token, ws = _register("dn_adj", "DN Adjust WS")
    headers = _headers(token)
    warehouse_id, bin_id = _warehouse_bin(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    ok = _adjust(headers, product["id"], warehouse_id, bin_id, "12", "OPENING")
    assert ok.status_code == 200, ok.text
    assert _dec(ok.json()["data"]["on_hand"]) == Decimal("12.00")
    ledgers = asyncio.run(_txns(ws, product["id"]))
    adj_rows = [t for t in ledgers if t.transaction_type == TransactionType.ADJUSTMENT]
    assert len(adj_rows) == 1
    assert adj_rows[0].reason == "OPENING"
    member = _member_token(ws)
    forbidden = _adjust(
        _headers(member), product["id"], warehouse_id, bin_id, "1", "OPENING"
    )
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    token_b, _ = _register("dn_adj_b", "DN Adjust B")
    prod_b = _product(_headers(token_b), _uom(_headers(token_b)))
    cross = _adjust(headers, prod_b["id"], warehouse_id, bin_id, "1")
    assert cross.status_code == 404, cross.text
    extra = client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse_id,
            "bin_id": bin_id,
            "quantity": "1",
            "reason": "OPENING",
            "notes": "ok notes",
            "nope": True,
        },
        headers=headers,
    )
    assert extra.status_code == 422, extra.text


def test_concurrent_dn_numbers_unique():
    token, _ = _register("dn_conc", "DN Conc WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    warehouse_id, _ = _warehouse_bin(headers)
    lpo = _received_lpo(headers, client_id, [_adhoc_item(quantity="100")])

    def create_one(index: int) -> str:
        r = client.post(
            "/api/v1/delivery-notes",
            json=_dn_payload(warehouse_id, customer_purchase_order_id=lpo["id"]),
            headers=headers,
        )
        assert r.status_code == 201, f"DN {index} failed: {r.text}"
        return r.json()["data"]["dn_number"]

    with ThreadPoolExecutor(max_workers=5) as executor:
        numbers = list(executor.map(create_one, range(8)))
    assert len(numbers) == len(set(numbers)), numbers
    seq = sorted(int(num.split("-")[-1]) for num in numbers)
    assert seq == list(range(1, 9)), seq


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
