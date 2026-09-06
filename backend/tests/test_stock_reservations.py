"""Wave 18 stock reservation API tests.

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
from sqlalchemy import update
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
from app.models.stock_reservation import StockReservation
from app.models.user import User, UserRole

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


def _create_client(headers: dict, name: str = "Dealer") -> str:
    r = client.post(
        "/api/v1/clients",
        json={"name": name, "email": f"{uuid.uuid4().hex[:8]}@ex.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


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


def _level(headers: dict, product_id: str) -> dict | None:
    r = client.get(f"/api/v1/inventory/levels?product_id={product_id}", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    return rows[0] if rows else None


def _received_lpo(
    headers: dict, client_id: str, product_id: str, quantity: str = "100"
) -> dict:
    body = {
        "client_id": client_id,
        "items": [
            {
                "product_id": product_id,
                "description": "NYM 3x2.5 cable",
                "quantity": quantity,
                "unit_price": "10.00",
            }
        ],
    }
    r = client.post("/api/v1/customer-purchase-orders", json=body, headers=headers)
    assert r.status_code == 201, r.text
    lpo_id = r.json()["data"]["id"]
    rec = client.post(
        f"/api/v1/customer-purchase-orders/{lpo_id}/receive",
        json={},
        headers=headers,
    )
    assert rec.status_code == 200, rec.text
    return rec.json()["data"]


def _reserve(headers: dict, lpo_id: str, warehouse_id: str, line_id: str, qty: str):
    return client.post(
        "/api/v1/inventory/reservations",
        json={
            "customer_purchase_order_id": lpo_id,
            "warehouse_id": warehouse_id,
            "items": [
                {
                    "customer_purchase_order_item_id": line_id,
                    "quantity": qty,
                }
            ],
        },
        headers=headers,
    )


def _create_dn(
    headers: dict,
    warehouse_id: str,
    lpo_id: str,
    line_id: str,
    qty: str,
) -> dict:
    r = client.post(
        "/api/v1/delivery-notes",
        json={
            "warehouse_id": warehouse_id,
            "customer_purchase_order_id": lpo_id,
            "items": [
                {
                    "customer_purchase_order_item_id": line_id,
                    "quantity": qty,
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _confirm_dn(headers: dict, dn_id: str):
    return client.post(
        f"/api/v1/delivery-notes/{dn_id}/confirm", json={}, headers=headers
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


def test_create_cancel_reservations_track_reserved():
    token, _ = _register("res_a", "Res WS A")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    assert (
        _adjust(headers, product["id"], warehouse_id, bin_id, "50").status_code == 200
    )
    lpo = _received_lpo(headers, client_id, product["id"])
    line_id = lpo["items"][0]["id"]

    created = _reserve(headers, lpo["id"], warehouse_id, line_id, "30")
    assert created.status_code == 201, created.text
    created_body = created.json()["data"]
    assert created_body["status"] == "ACTIVE"
    assert _dec(created_body["items"][0]["remaining"]) == Decimal("30.00")
    assert _dec(created_body["items"][0]["quantity_consumed"]) == Decimal("0.00")

    level = _level(headers, product["id"])
    assert _dec(level["reserved"]) == Decimal("30.00")
    assert _dec(level["on_hand"]) == Decimal("50.00")
    assert _dec(level["available"]) == Decimal("20.00")

    over_available = _reserve(headers, lpo["id"], warehouse_id, line_id, "25")
    assert over_available.status_code == 400, over_available.text
    assert over_available.json()["error"]["code"] == "VALIDATION_ERROR"
    assert over_available.json()["error"]["field"] == "quantity"

    over_undelivered = _reserve(headers, lpo["id"], warehouse_id, line_id, "80")
    assert over_undelivered.status_code == 400, over_undelivered.text
    assert over_undelivered.json()["error"]["code"] == "VALIDATION_ERROR"

    cancel = client.post(
        f"/api/v1/inventory/reservations/{created_body['id']}/cancel",
        json={"reason": "Replanned"},
        headers=headers,
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["data"]["status"] == "CANCELLED"

    level = _level(headers, product["id"])
    assert _dec(level["reserved"]) == Decimal("0.00")
    assert _dec(level["available"]) == Decimal("50.00")


def test_draft_lpo_cannot_be_reserved():
    token, _ = _register("res_draft", "Res Draft WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    _adjust(headers, product["id"], warehouse_id, bin_id, "10")
    r = client.post(
        "/api/v1/customer-purchase-orders",
        json={
            "client_id": client_id,
            "items": [
                {
                    "product_id": product["id"],
                    "description": "NYM 3x2.5 cable",
                    "quantity": "10",
                    "unit_price": "10.00",
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    lpo = r.json()["data"]
    res = _reserve(headers, lpo["id"], warehouse_id, lpo["items"][0]["id"], "5")
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "INVALID_STATE"


def test_dn_confirm_consumes_reservation_fifo():
    token, _ = _register("res_fifo", "Res FIFO WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    _adjust(headers, product["id"], warehouse_id, bin_id, "100")
    lpo = _received_lpo(headers, client_id, product["id"])
    line_id = lpo["items"][0]["id"]
    first = _reserve(headers, lpo["id"], warehouse_id, line_id, "40")
    assert first.status_code == 201, first.text
    second = _reserve(headers, lpo["id"], warehouse_id, line_id, "20")
    assert second.status_code == 201, second.text
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]

    dn = _create_dn(headers, warehouse_id, lpo["id"], line_id, "25")
    conf = _confirm_dn(headers, dn["id"])
    assert conf.status_code == 200, conf.text

    level = _level(headers, product["id"])
    assert _dec(level["on_hand"]) == Decimal("75.00")
    assert _dec(level["reserved"]) == Decimal("35.00")
    assert _dec(level["available"]) == Decimal("40.00")

    got_first = client.get(
        f"/api/v1/inventory/reservations/{first_id}", headers=headers
    )
    got_second = client.get(
        f"/api/v1/inventory/reservations/{second_id}", headers=headers
    )
    first_item = got_first.json()["data"]["items"][0]
    second_item = got_second.json()["data"]["items"][0]
    assert _dec(first_item["remaining"]) == Decimal("15.00")
    assert _dec(first_item["quantity_consumed"]) == Decimal("25.00")
    assert first_item["status"] == "ACTIVE"
    assert second_item["status"] == "ACTIVE"
    assert got_first.json()["data"]["status"] == "ACTIVE"


def test_full_dispatch_marks_reservation_dispatched():
    token, _ = _register("res_full", "Res Full WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    _adjust(headers, product["id"], warehouse_id, bin_id, "100")
    lpo = _received_lpo(headers, client_id, product["id"])
    line_id = lpo["items"][0]["id"]
    created = _reserve(headers, lpo["id"], warehouse_id, line_id, "40")
    reservation_id = created.json()["data"]["id"]

    dn = _create_dn(headers, warehouse_id, lpo["id"], line_id, "40")
    conf = _confirm_dn(headers, dn["id"])
    assert conf.status_code == 200, conf.text

    got = client.get(
        f"/api/v1/inventory/reservations/{reservation_id}", headers=headers
    )
    body = got.json()["data"]
    assert body["status"] == "DISPATCHED"
    item = body["items"][0]
    assert item["status"] == "DISPATCHED"
    assert _dec(item["remaining"]) == Decimal("0.00")

    level = _level(headers, product["id"])
    assert _dec(level["reserved"]) == Decimal("0.00")
    assert _dec(level["on_hand"]) == Decimal("60.00")


def test_expire_releases_due_reservations_and_owner_only():
    token, workspace_id = _register("res_exp", "Res Exp WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    _adjust(headers, product["id"], warehouse_id, bin_id, "30")
    lpo = _received_lpo(headers, client_id, product["id"])
    line_id = lpo["items"][0]["id"]
    created = _reserve(headers, lpo["id"], warehouse_id, line_id, "10")
    reservation_id = created.json()["data"]["id"]

    old = datetime.now(timezone.utc) - timedelta(days=1)

    async def _backdate() -> None:
        async with TestingSessionLocal() as session:
            await session.execute(
                update(StockReservation)
                .where(StockReservation.id == uuid.UUID(reservation_id))
                .values(expires_at=old)
            )
            await session.commit()

    asyncio.run(_backdate())

    member_headers = _headers(_member_token(workspace_id))
    denied = client.post(
        "/api/v1/inventory/reservations/expire", json={}, headers=member_headers
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    ok = client.post("/api/v1/inventory/reservations/expire", json={}, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["expired"] == 1

    got = client.get(
        f"/api/v1/inventory/reservations/{reservation_id}", headers=headers
    )
    assert got.json()["data"]["status"] == "EXPIRED"
    level = _level(headers, product["id"])
    assert _dec(level["reserved"]) == Decimal("0.00")
    assert _dec(level["available"]) == Decimal("30.00")


def test_multi_tenant_isolation():
    token_a, _ = _register("res_iso_a", "Res Iso A")
    headers_a = _headers(token_a)
    token_b, _ = _register("res_iso_b", "Res Iso B")
    headers_b = _headers(token_b)

    client_id = _create_client(headers_a)
    uom_id = _uom(headers_a)
    product = _product(headers_a, uom_id)
    warehouse_a, bin_a = _warehouse_bin(headers_a)
    _adjust(headers_a, product["id"], warehouse_a, bin_a, "10")
    lpo_a = _received_lpo(headers_a, client_id, product["id"], quantity="10")
    created = _reserve(
        headers_a, lpo_a["id"], warehouse_a, lpo_a["items"][0]["id"], "5"
    )
    reservation_id = created.json()["data"]["id"]

    cross_read = client.get(
        f"/api/v1/inventory/reservations/{reservation_id}", headers=headers_b
    )
    assert cross_read.status_code == 404, cross_read.text
    cross_cancel = client.post(
        f"/api/v1/inventory/reservations/{reservation_id}/cancel",
        json={},
        headers=headers_b,
    )
    assert cross_cancel.status_code == 404, cross_cancel.text
    cross_list = client.get("/api/v1/inventory/reservations", headers=headers_b)
    assert cross_list.status_code == 200, cross_list.text
    assert cross_list.json()["pagination"]["total"] == 0


def test_list_pagination_and_filters():
    token, _ = _register("res_list", "Res List WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    uom_id = _uom(headers)
    product = _product(headers, uom_id)
    warehouse_id, bin_id = _warehouse_bin(headers)
    _adjust(headers, product["id"], warehouse_id, bin_id, "100")
    lpo = _received_lpo(headers, client_id, product["id"])
    line_id = lpo["items"][0]["id"]
    for qty in ("5", "6", "7"):
        assert (
            _reserve(headers, lpo["id"], warehouse_id, line_id, qty).status_code == 201
        )

    page = client.get(
        "/api/v1/inventory/reservations",
        params={"page": 1, "per_page": 2},
        headers=headers,
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["pages"] == 2
    assert len(body["data"]) == 2
    assert body["data"][0]["warehouse_id"] == warehouse_id

    filtered = client.get(
        "/api/v1/inventory/reservations",
        params={"cpo_id": lpo["id"], "status": "ACTIVE"},
        headers=headers,
    )
    assert filtered.json()["pagination"]["total"] == 3

    missing = client.get(
        "/api/v1/inventory/reservations",
        params={"warehouse_id": uuid.uuid4()},
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["pagination"]["total"] == 0
