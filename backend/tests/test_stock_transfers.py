"""Wave 19 multi-warehouse stock transfer tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import sys
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.inventory import InventoryTransaction

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


def _uom(headers: dict) -> str:
    r = client.post(
        "/api/v1/products/uom",
        json={"name": "Metres", "code": f"M-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _product(headers: dict, uom_id: str) -> dict:
    r = client.post(
        "/api/v1/products",
        json={
            "name": "NYM cable",
            "internal_sku": f"ELE-{uuid.uuid4().hex[:8]}",
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _warehouse_bin(headers: dict, name: str = "Warehouse") -> tuple[str, str]:
    code = f"WH-{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/api/v1/inventory/warehouses",
        json={"code": code, "name": name},
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


def _adjust(headers: dict, product_id: str, warehouse_id: str, bin_id: str, qty: str):
    r = client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "bin_id": bin_id,
            "quantity": qty,
            "reason": "OPENING",
            "notes": "Opening stock",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _level_for(headers: dict, product_id: str, warehouse_id: str) -> dict | None:
    r = client.get(f"/api/v1/inventory/levels?product_id={product_id}", headers=headers)
    assert r.status_code == 200, r.text
    for row in r.json()["data"]:
        if row["warehouse_id"] == warehouse_id:
            return row
    return None


def _create_transfer(
    headers: dict, source_wh: str, dest_wh: str, product_id: str, qty: str
):
    return client.post(
        "/api/v1/inventory/transfers",
        json={
            "source_warehouse_id": source_wh,
            "destination_warehouse_id": dest_wh,
            "notes": "Replenish the branch",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": qty,
                }
            ],
        },
        headers=headers,
    )


def _state_call(headers: dict, transfer_id: str, action: str, body=None):
    return client.post(
        f"/api/v1/inventory/transfers/{transfer_id}/{action}",
        json=body if body is not None else {},
        headers=headers,
    )


async def _ledger_txns(reference_id: str) -> list[dict]:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.reference_id == uuid.UUID(reference_id)
            )
        )
        rows = result.scalars().all()
        return [
            {
                "type": row.transaction_type,
                "quantity": row.quantity,
                "source_bin_id": str(row.source_bin_id) if row.source_bin_id else None,
                "dest_bin_id": (
                    str(row.destination_bin_id) if row.destination_bin_id else None
                ),
            }
            for row in rows
        ]


def test_create_draft_resolves_bins_and_numbers():
    token, _ = _register("tr_a", "Tr WS A")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, bin_src = _warehouse_bin(headers, "Source")
    wh_dst, bin_dst = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, bin_src, "50")

    r = _create_transfer(headers, wh_src, wh_dst, product["id"], "30")
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["status"] == "DRAFT"
    assert body["transfer_number"].startswith("ST-")
    assert body["source_warehouse_id"] == wh_src
    assert body["destination_warehouse_id"] == wh_dst
    item = body["items"][0]
    assert item["source_bin_id"] == bin_src
    assert item["destination_bin_id"] == bin_dst
    assert _dec(item["remaining"]) == Decimal("30.00")


def test_dispatch_moves_stock_to_in_transit_and_ledgers():
    token, _ = _register("tr_disp", "Tr Dispatch WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _bin_dst = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, bin_src, "100")

    created = _create_transfer(headers, wh_src, wh_dst, product["id"], "40")
    transfer_id = created.json()["data"]["id"]
    dispatched = _state_call(headers, transfer_id, "approve")
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["data"]["status"] == "APPROVED"
    dispatched = _state_call(headers, transfer_id, "dispatch")
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["data"]["status"] == "IN_TRANSIT"
    assert dispatched.json()["data"]["dispatched_at"] is not None

    src = _level_for(headers, product["id"], wh_src)
    dst = _level_for(headers, product["id"], wh_dst)
    assert _dec(src["on_hand"]) == Decimal("60.00")
    assert _dec(src["in_transit"]) == Decimal("40.00")
    assert _dec(src["reserved"]) == Decimal("0.00")
    assert dst is None or _dec(dst["on_hand"]) == Decimal("0.00")

    txns = asyncio.run(_ledger_txns(transfer_id))
    assert len(txns) == 1
    assert txns[0]["type"] == "TRANSFER"
    assert _dec(txns[0]["quantity"]) == Decimal("-40.00")
    assert txns[0]["source_bin_id"] == bin_src


def test_dispatch_rejects_insufficient_available():
    token, _ = _register("tr_insuff", "Tr Insuff WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _ = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, bin_src, "10")

    created = _create_transfer(headers, wh_src, wh_dst, product["id"], "15")
    transfer_id = created.json()["data"]["id"]
    _state_call(headers, transfer_id, "approve")
    bad = _state_call(headers, transfer_id, "dispatch")
    assert bad.status_code == 400, bad.text
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad.json()["error"]["field"] == "quantity"

    level = _level_for(headers, product["id"], wh_src)
    assert _dec(level["on_hand"]) == Decimal("10.00")
    assert _dec(level["in_transit"]) == Decimal("0.00")


def test_receive_full_clears_in_transit_and_increments_dest():
    token, _ = _register("tr_recv", "Tr Receive WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, bin_src = _warehouse_bin(headers, "Source")
    wh_dst, bin_dst = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, bin_src, "100")

    created = _create_transfer(headers, wh_src, wh_dst, product["id"], "30")
    transfer_id = created.json()["data"]["id"]
    _state_call(headers, transfer_id, "approve")
    _state_call(headers, transfer_id, "dispatch")
    received = _state_call(headers, transfer_id, "receive")
    assert received.status_code == 200, received.text
    assert received.json()["data"]["status"] == "RECEIVED"
    assert received.json()["data"]["received_at"] is not None
    item = received.json()["data"]["items"][0]
    assert _dec(item["received_quantity"]) == Decimal("30.00")
    assert _dec(item["remaining"]) == Decimal("0.00")

    src = _level_for(headers, product["id"], wh_src)
    dst = _level_for(headers, product["id"], wh_dst)
    assert _dec(src["on_hand"]) == Decimal("70.00")
    assert _dec(src["in_transit"]) == Decimal("0.00")
    assert _dec(dst["on_hand"]) == Decimal("30.00")
    assert _dec(dst["in_transit"]) == Decimal("0.00")

    txns = asyncio.run(_ledger_txns(transfer_id))
    assert len(txns) == 2
    received_txn = [t for t in txns if _dec(t["quantity"]) > Decimal("0.00")][0]
    assert received_txn["type"] == "TRANSFER"
    assert received_txn["dest_bin_id"] == bin_dst


def test_partial_receive_keeps_discrepancy():
    token, _ = _register("tr_partial", "Tr Partial WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, _bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _ = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, _bin_src, "100")

    created = _create_transfer(headers, wh_src, wh_dst, product["id"], "30")
    transfer_id = created.json()["data"]["id"]
    _state_call(headers, transfer_id, "approve")
    _state_call(headers, transfer_id, "dispatch")
    partial = _state_call(
        headers,
        transfer_id,
        "receive",
        body={"received": [{"product_id": product["id"], "quantity": "20"}]},
    )
    assert partial.status_code == 200, partial.text
    item = partial.json()["data"]["items"][0]
    assert _dec(item["received_quantity"]) == Decimal("20.00")
    assert _dec(item["remaining"]) == Decimal("10.00")

    src = _level_for(headers, product["id"], wh_src)
    dst = _level_for(headers, product["id"], wh_dst)
    assert _dec(src["in_transit"]) == Decimal("0.00")
    assert _dec(dst["on_hand"]) == Decimal("20.00")


def test_cancel_rules_and_state_machine_guards():
    token, _ = _register("tr_cancel", "Tr Cancel WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, _bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _ = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, _bin_src, "100")

    draft = _create_transfer(headers, wh_src, wh_dst, product["id"], "25")
    draft_id = draft.json()["data"]["id"]
    assert _state_call(headers, draft_id, "dispatch").status_code == 400
    assert _state_call(headers, draft_id, "receive").status_code == 400
    assert _state_call(headers, draft_id, "approve").status_code == 200
    assert _state_call(headers, draft_id, "approve").status_code == 400
    assert _state_call(headers, draft_id, "dispatch").status_code == 200
    assert _state_call(headers, draft_id, "dispatch").status_code == 400

    cancelled = _state_call(headers, draft_id, "cancel", body={"reason": "Lost truck"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    src = _level_for(headers, product["id"], wh_src)
    assert _dec(src["on_hand"]) == Decimal("100.00")
    assert _dec(src["in_transit"]) == Decimal("0.00")
    assert _state_call(headers, draft_id, "receive").status_code == 400
    assert _state_call(headers, draft_id, "cancel").status_code == 400

    approved = _create_transfer(headers, wh_src, wh_dst, product["id"], "15")
    approved_id = approved.json()["data"]["id"]
    _state_call(headers, approved_id, "approve")
    cancelled_approved = _state_call(headers, approved_id, "cancel", body={})
    assert cancelled_approved.status_code == 200, cancelled_approved.text
    src = _level_for(headers, product["id"], wh_src)
    assert _dec(src["on_hand"]) == Decimal("100.00")


def test_multi_tenant_isolation():
    token_a, _ = _register("tr_iso_a", "Tr Iso A")
    headers_a = _headers(token_a)
    token_b, _ = _register("tr_iso_b", "Tr Iso B")
    headers_b = _headers(token_b)

    uom_id = _uom(headers_a)
    product = _product(headers_a, uom_id)
    wh_src, _bin_src = _warehouse_bin(headers_a, "Source")
    wh_dst, _ = _warehouse_bin(headers_a, "Destination")
    _adjust(headers_a, product["id"], wh_src, _bin_src, "10")

    created = _create_transfer(headers_a, wh_src, wh_dst, product["id"], "5")
    transfer_id = created.json()["data"]["id"]
    _state_call(headers_a, transfer_id, "approve")

    cross_read = client.get(
        f"/api/v1/inventory/transfers/{transfer_id}", headers=headers_b
    )
    assert cross_read.status_code == 404, cross_read.text
    cross_dispatch = _state_call(headers_b, transfer_id, "dispatch")
    assert cross_dispatch.status_code == 404, cross_dispatch.text
    cross_list = client.get("/api/v1/inventory/transfers", headers=headers_b)
    assert cross_list.status_code == 200, cross_list.text
    assert cross_list.json()["pagination"]["total"] == 0


def test_list_pagination_filters_and_validation():
    token, _ = _register("tr_list", "Tr List WS")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, _bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _ = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, _bin_src, "100")

    ids = []
    for qty in ("5", "6", "7"):
        created = _create_transfer(headers, wh_src, wh_dst, product["id"], qty)
        assert created.status_code == 201, created.text
        ids.append(created.json()["data"]["id"])

    page = client.get(
        "/api/v1/inventory/transfers",
        params={"page": 1, "per_page": 2},
        headers=headers,
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["pages"] == 2
    assert len(body["data"]) == 2
    assert body["data"][0]["item_count"] == 1
    assert _dec(body["data"][0]["total_quantity"]) == Decimal("7.00")

    filtered = client.get(
        "/api/v1/inventory/transfers",
        params={"status": "DRAFT", "source_warehouse_id": wh_src},
        headers=headers,
    )
    assert filtered.json()["pagination"]["total"] == 3

    missing = client.get(
        "/api/v1/inventory/transfers",
        params={"destination_warehouse_id": uuid.uuid4()},
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["pagination"]["total"] == 0

    zero = _create_transfer(headers, wh_src, wh_dst, product["id"], "0")
    assert zero.status_code == 422, zero.text
    same_wh = client.post(
        "/api/v1/inventory/transfers",
        json={
            "source_warehouse_id": wh_src,
            "destination_warehouse_id": wh_src,
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert same_wh.status_code == 422, same_wh.text
