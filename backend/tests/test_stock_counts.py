"""Wave 19b stock counting / reconciliation tests.

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

from app.auth.utils import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: F401, F403, E402
from app.models.inventory import InventoryTransaction, TransactionType  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.stock_count_service import needs_approval  # noqa: E402

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


def _create_count(headers: dict, warehouse_id: str, notes: str = "Year-end count"):
    return client.post(
        "/api/v1/inventory/counts",
        json={"warehouse_id": warehouse_id, "notes": notes},
        headers=headers,
    )


def _record(headers: dict, count_id: str, item_id: str, qty: str):
    return client.post(
        f"/api/v1/inventory/counts/{count_id}/record",
        json={"item_id": item_id, "counted_quantity": qty},
        headers=headers,
    )


def _state_call(headers: dict, count_id: str, action: str):
    return client.post(
        f"/api/v1/inventory/counts/{count_id}/{action}", json={}, headers=headers
    )


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


async def _count_ledger(reference_id: str) -> list[dict]:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.reference_type == "COUNT",
                InventoryTransaction.reference_id == uuid.UUID(reference_id),
            )
        )
        rows = result.scalars().all()
        return [
            {
                "type": row.transaction_type,
                "quantity": row.quantity,
                "reason": row.reason,
                "source_bin_id": str(row.source_bin_id) if row.source_bin_id else None,
                "dest_bin_id": (
                    str(row.destination_bin_id) if row.destination_bin_id else None
                ),
            }
            for row in rows
        ]


def test_create_snapshots_expected_with_gapless_numbers():
    token, _ = _register("cnt_a", "Count WS A")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, _bin_id = _warehouse_bin(headers, "Alpha")
    _adjust(headers, product["id"], warehouse_id, _bin_id, "100")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["count_number"].startswith("SC-")
    assert data["status"] == "SCHEDULED"
    assert data["warehouse_id"] == warehouse_id
    assert data["items"] and len(data["items"]) == 1
    line = data["items"][0]
    assert _dec(line["expected_quantity"]) == _dec("100.00")
    assert line["counted_quantity"] is None
    assert line["requires_approval"] is False
    assert _dec(line["variance"]) == _dec("0.00")

    r2 = _create_count(headers, warehouse_id, notes="Partial")
    assert r2.status_code == 201, r2.text
    assert r2.json()["data"]["count_number"] != data["count_number"]

    r3 = client.post(
        "/api/v1/inventory/counts",
        json={"warehouse_id": uuid.uuid4().hex, "notes": "Ghost WH"},
        headers=headers,
    )
    assert r3.status_code == 404, r3.text


def test_record_and_complete_require_all_lines_counted():
    token, _ = _register("cnt_b", "Count WS B")
    headers = _headers(token)
    uom_id = _uom(headers)
    prod_a = _product(headers, uom_id)
    prod_b = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers, "Beta")
    _adjust(headers, prod_a["id"], warehouse_id, bin_id, "100")
    _adjust(headers, prod_b["id"], warehouse_id, bin_id, "200")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]
    lines = {line["product_id"]: line for line in r.json()["data"]["items"]}
    assert len(lines) == 2

    rec = _record(headers, count_id, lines[prod_a["id"]]["id"], "99")
    assert rec.status_code == 200, rec.text
    assert rec.json()["data"]["status"] == "IN_PROGRESS"
    assert rec.json()["data"]["started_at"] is not None

    open_count = client.get(
        f"/api/v1/inventory/counts/{count_id}", headers=headers
    ).json()["data"]
    a_line = next(
        (li for li in open_count["items"] if li["product_id"] == prod_a["id"]), None
    )
    assert _dec(a_line["counted_quantity"]) == _dec("99")

    incomplete = _state_call(headers, count_id, "complete")
    assert incomplete.status_code == 400, incomplete.text

    rec2 = _record(headers, count_id, lines[prod_b["id"]]["id"], "-5")
    assert rec2.status_code == 422, rec2.text
    rec3 = _record(headers, count_id, uuid.uuid4().hex, "1")
    assert rec3.status_code == 404, rec3.text

    rec4 = _record(headers, count_id, lines[prod_b["id"]]["id"], "200")
    assert rec4.status_code == 200, rec4.text
    done = _state_call(headers, count_id, "complete")
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "COMPLETED"
    assert done.json()["data"]["completed_at"] is not None
    day = done.json()["data"]["items"]
    assert all(line["counted_quantity"] is not None for line in day)


def test_tolerance_flagging_and_needs_approval_helper():
    assert needs_approval(Decimal("100"), Decimal("99")) is False
    assert needs_approval(Decimal("100"), Decimal("98")) is False
    assert needs_approval(Decimal("100"), Decimal("97")) is True
    assert needs_approval(Decimal("0"), Decimal("0")) is False
    assert needs_approval(Decimal("0"), Decimal("10")) is True
    assert needs_approval(Decimal("100"), Decimal("100")) is False
    assert needs_approval(Decimal("100"), None) is False

    token, _ = _register("cnt_c", "Count WS C")
    headers = _headers(token)
    uom_id = _uom(headers)
    prod_small = _product(headers, uom_id)
    prod_big = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers, "Gamma")
    _adjust(headers, prod_small["id"], warehouse_id, bin_id, "100")
    _adjust(headers, prod_big["id"], warehouse_id, bin_id, "100")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]
    lines = {line["product_id"]: line for line in r.json()["data"]["items"]}
    _record(headers, count_id, lines[prod_small["id"]]["id"], "99")
    _record(headers, count_id, lines[prod_big["id"]]["id"], "50")
    done = _state_call(headers, count_id, "complete")
    assert done.status_code == 200, done.text
    after = {line["product_id"]: line for line in done.json()["data"]["items"]}
    assert after[prod_small["id"]]["requires_approval"] is False
    assert after[prod_big["id"]]["requires_approval"] is True


def test_reconcile_applies_deltas_and_writes_ledger():
    token, _ = _register("cnt_d", "Count WS D")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers, "Delta")
    _adjust(headers, product["id"], warehouse_id, bin_id, "100")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]
    data = r.json()["data"]
    count_number = data["count_number"]
    line = data["items"][0]

    _record(headers, count_id, line["id"], "82")
    done = _state_call(headers, count_id, "complete")
    assert done.status_code == 200, done.text
    assert done.json()["data"]["items"][0]["requires_approval"] is True

    reconcile_no_approve = _state_call(headers, count_id, "reconcile")
    assert reconcile_no_approve.status_code == 400, reconcile_no_approve.text

    approved = _state_call(headers, count_id, "approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["approved_at"] is not None
    assert all(line["approved"] for line in approved.json()["data"]["items"])

    reconcile = _state_call(headers, count_id, "reconcile")
    assert reconcile.status_code == 200, reconcile.text
    resp = reconcile.json()["data"]
    assert resp["status"] == "RECONCILED"
    assert resp["reconciled_at"] is not None

    level = _level_for(headers, product["id"], warehouse_id)
    assert _dec(level["on_hand"]) == _dec("82.00")
    assert _dec(level["available"]) == _dec("82.00")

    ledger = asyncio.run(_count_ledger(count_id))
    assert len(ledger) == 1
    assert ledger[0]["type"] == TransactionType.ADJUSTMENT
    assert _dec(ledger[0]["quantity"]) == _dec("-18.00")
    assert ledger[0]["reason"] == "COUNT_CORRECTION"
    assert ledger[0]["source_bin_id"] == bin_id
    assert str(count_number).startswith("SC-")


def test_zero_expected_and_counts_ledger_ordering():
    token, _ = _register("cnt_e", "Count WS E")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_src, bin_src = _warehouse_bin(headers, "Source")
    wh_dst, _bin_dst = _warehouse_bin(headers, "Destination")
    _adjust(headers, product["id"], wh_src, bin_src, "100")

    _deplete_source(headers, product["id"], wh_src, wh_dst, "100")
    depleted = _level_for(headers, product["id"], wh_src)
    assert _dec(depleted["on_hand"]) == _dec("0.00")

    r = _create_count(headers, wh_src)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]
    line = r.json()["data"]["items"][0]
    assert _dec(line["expected_quantity"]) == _dec("0.00")

    _record(headers, count_id, line["id"], "10")
    done = _state_call(headers, count_id, "complete")
    assert done.status_code == 200, done.text
    assert done.json()["data"]["items"][0]["requires_approval"] is True

    approve = _state_call(headers, count_id, "approve")
    assert approve.status_code == 200, approve.text
    reconcile = _state_call(headers, count_id, "reconcile")
    assert reconcile.status_code == 200, reconcile.text
    level = _level_for(headers, product["id"], wh_src)
    assert _dec(level["on_hand"]) == _dec("10.00")

    ledger = asyncio.run(_count_ledger(count_id))
    assert any(_dec(row["quantity"]) == _dec("10.00") for row in ledger)


def test_cancel_rules_no_stock_movement_and_terminal_guards():
    token, _ = _register("cnt_f", "Count WS F")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers, "Epsilon")
    _adjust(headers, product["id"], warehouse_id, bin_id, "100")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]

    cancelled = _state_call(headers, count_id, "cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert cancelled.json()["data"]["cancelled_at"] is not None
    assert _dec(_level_for(headers, product["id"], warehouse_id)["on_hand"]) == _dec(
        "100.00"
    )
    assert _state_call(headers, count_id, "cancel").status_code == 400

    r2 = _create_count(headers, warehouse_id)
    assert r2.status_code == 201, r2.text
    count2 = r2.json()["data"]["id"]
    line2 = r2.json()["data"]["items"][0]
    _record(headers, count2, line2["id"], "100")
    _state_call(headers, count2, "complete")
    reconcile_on_open = _state_call(headers, count2, "reconcile")
    assert reconcile_on_open.status_code == 200, reconcile_on_open.text
    assert _state_call(headers, count2, "cancel").status_code == 400
    assert _state_call(headers, count2, "complete").status_code == 400


def test_member_permissions_and_get_is_open():
    token, ws_id = _register("cnt_g", "Count WS G")
    headers = _headers(token)
    member_headers = _headers(_member_token(ws_id))
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, _bin_id = _warehouse_bin(headers, "Zeta")
    _adjust(headers, product["id"], warehouse_id, _bin_id, "100")

    r = _create_count(headers, warehouse_id)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]

    assert _create_count(member_headers, warehouse_id).status_code == 403
    assert _state_call(member_headers, count_id, "complete").status_code == 403
    assert _state_call(member_headers, count_id, "approve").status_code == 403
    assert _state_call(member_headers, count_id, "reconcile").status_code == 403
    assert _state_call(member_headers, count_id, "cancel").status_code == 403

    listing = client.get("/api/v1/inventory/counts", headers=member_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"]


def test_multi_tenant_isolation_404():
    token_a, _ = _register("cnt_h", "Count WS H")
    headers_a = _headers(token_a)
    token_b, _ = _register("cnt_i", "Count WS I")
    headers_b = _headers(token_b)

    uom_a = _uom(headers_a)
    product_a = _product(headers_a, uom_a)
    warehouse_a, _bin_a = _warehouse_bin(headers_a, "Eta")
    _adjust(headers_a, product_a["id"], warehouse_a, _bin_a, "50")

    r = _create_count(headers_a, warehouse_a)
    assert r.status_code == 201, r.text
    count_id = r.json()["data"]["id"]
    line = r.json()["data"]["items"][0]

    assert (
        client.get(
            f"/api/v1/inventory/counts/{count_id}", headers=headers_b
        ).status_code
        == 404
    )
    assert _record(headers_b, count_id, line["id"], "1").status_code == 404
    assert _state_call(headers_b, count_id, "complete").status_code == 404
    assert _state_call(headers_b, count_id, "cancel").status_code == 404


def test_list_filters_and_misc_guards():
    token, _ = _register("cnt_j", "Count WS J")
    headers = _headers(token)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    wh_a, _bin_a = _warehouse_bin(headers, "Theta")
    wh_b, _bin_b = _warehouse_bin(headers, "Kappa")
    _adjust(headers, product["id"], wh_a, _bin_a, "100")

    _create_count(headers, wh_a)
    _create_count(headers, wh_a, notes="Second")
    _create_count(headers, wh_b, notes="Other wh")

    page = client.get("/api/v1/inventory/counts", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["pagination"]["total"] == 3
    assert page.json()["pagination"]["pages"] == 1

    by_status = client.get("/api/v1/inventory/counts?status=SCHEDULED", headers=headers)
    assert by_status.status_code == 200, by_status.text
    assert by_status.json()["pagination"]["total"] == 3

    by_wh = client.get(f"/api/v1/inventory/counts?warehouse_id={wh_a}", headers=headers)
    assert by_wh.status_code == 200, by_wh.text
    assert by_wh.json()["pagination"]["total"] == 2

    per_page = client.get(
        "/api/v1/inventory/counts?per_page=2&page=2&warehouse_id=" + wh_a,
        headers=headers,
    )
    assert per_page.status_code == 200, per_page.text
    assert per_page.json()["pagination"]["page"] == 2
    assert per_page.json()["pagination"]["has_prev"] is True

    bad = client.get("/api/v1/inventory/counts?status=BOGUS", headers=headers)
    assert bad.status_code == 422, bad.text


def _deplete_source(headers, product_id, wh_src, wh_dst, qty):
    t = client.post(
        "/api/v1/inventory/transfers",
        json={
            "source_warehouse_id": wh_src,
            "destination_warehouse_id": wh_dst,
            "notes": "Deplete source",
            "items": [{"product_id": product_id, "quantity": qty}],
        },
        headers=headers,
    )
    assert t.status_code == 201, t.text
    tid = t.json()["data"]["id"]
    assert (
        client.post(
            f"/api/v1/inventory/transfers/{tid}/approve", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/inventory/transfers/{tid}/dispatch", json={}, headers=headers
        ).status_code
        == 200
    )
