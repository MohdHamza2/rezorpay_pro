"""Wave 31 Item 2.2 — SPO amendments persistence tests.

Covers: propose persistence + snapshots + numbering, SPO-012 reason gate,
SPO-013 received floor, threshold routing (PENDING vs auto-APPROVED),
maker-checker approval, apply semantics (value writes, totals recompute,
flag clearing, reconfirmation gate), ack auto-creation (SPO-005), header
totals fix on partial ack (C-25), SPO-014 GRN/ack blocks, idempotent
re-propose, terminal-state guard, workspace isolation, OTHER no-mutation,
and the D-22 boundary (landed-cost rows untouched by price apply).

Follows the suite's standard harness: sync ``TestClient`` against a real
PostgreSQL ``_test`` database, module-scoped schema create/drop.
"""

import sys
import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app
from app.database import get_session
from app.config import get_settings

# Import all models so SQLModel.metadata is fully populated before create_all
from app.models import *  # noqa: F401, F403
from app.auth.utils import hash_password

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


def _register(prefix="owner"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": prefix,
            "workspace_name": f"{prefix} Workspace",
        },
    )
    assert r.status_code == 201, f"register failed: {r.text}"
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["data"]["workspace_id"]


def _second_user_token(workspace_id):
    """Insert a second active user directly into the workspace and log in."""

    async def _insert():
        async with TestingSessionLocal() as session:
            from app.models.user import User

            email = f"second_{uuid.uuid4().hex[:8]}@example.com"
            user = User(
                workspace_id=uuid.UUID(str(workspace_id)),
                email=email,
                password_hash=hash_password("securepassword123"),
                name="Second User",
            )
            session.add(user)
            await session.commit()
            return email

    email = asyncio.run(_insert())
    r = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert r.status_code == 200, f"second login failed: {r.text}"
    return r.json()["data"]["access_token"]


def _set_amendment_threshold(workspace_id, value):
    async def _update():
        async with TestingSessionLocal() as session:
            from app.models.workspace import Workspace

            ws = await session.get(Workspace, uuid.UUID(str(workspace_id)))
            ws.spo_amendment_approval_threshold = Decimal(str(value))
            await session.commit()

    asyncio.run(_update())


def _seed_fks(headers, workspace_id, tag):
    suffix = uuid.uuid4().hex[:6]
    q = f"?workspace_id={workspace_id}"
    r = client.post(
        f"/api/v1/suppliers/{q}",
        json={
            "name": f"SUP-{tag}",
            "email": f"sup-{tag}-{suffix}@example.com",
            "currency": "AED",
            "supplier_code": f"SUP-{tag}-{suffix}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), f"supplier: {r.text}"
    supplier_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses/{q}",
        json={"name": f"WH-{tag}", "code": f"WH-{tag}-{suffix}", "address": "123"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"warehouse: {r.text}"
    warehouse_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        json={"code": f"BIN-{tag}-{suffix}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"bin: {r.text}"

    r = client.post(
        f"/api/v1/products/uom/{q}",
        json={"name": "Pieces", "code": f"PCS-{tag}-{suffix}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"uom: {r.text}"
    uom_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/{q}",
        json={
            "name": f"Widget-{tag}",
            "internal_sku": f"WDGT-{tag}-{suffix}",
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), f"product: {r.text}"
    product_id = r.json()["data"]["id"]
    return {
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "uom_id": uom_id,
        "product_id": product_id,
    }


def _spo(headers, workspace_id, fks, lines, tag=""):
    r = client.post(
        "/api/v1/spos/",
        json={
            "supplier_id": fks["supplier_id"],
            "procurement_method": "DIRECT",
            "warehouse_id": fks["warehouse_id"],
            "currency": "AED",
            "items": lines,
        },
        headers=headers,
    )
    assert r.status_code == 200, f"SPO create failed: {r.text}"
    return r.json()["data"]


def _line(product_id, uom_id, qty, price, n=1):
    return {
        "line_number": n,
        "product_id": product_id,
        "description": "Widget",
        "uom_id": uom_id,
        "quantity_ordered": qty,
        "unit_price": price,
        "vat_rate": 5.0,
    }


def _send_spo(headers, spo_id, ack_map=None):
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    if ack_map is not None:
        r = client.post(
            f"/api/v1/spos/{spo_id}/items/acknowledge",
            json={"lines": ack_map},
            headers=headers,
        )
        assert r.status_code == 200, f"ack failed: {r.text}"
        return r.json()["data"]
    return None


def _propose(headers, spo_id, reason, lines):
    return client.post(
        f"/api/v1/spos/{spo_id}/amendments",
        json={"reason": reason, "lines": lines},
        headers=headers,
    )


def test_propose_persists_with_snapshots_and_numbering():
    token, ws = _register("amend_propose")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P1")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])

    r = _propose(
        headers,
        spo["id"],
        "Supplier raised steel prices this quarter",
        [
            {"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "55.00"},
            {
                "spo_item_id": item_id,
                "field_name": "QUANTITY_ORDERED",
                "new_value": "120",
            },
        ],
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # Default threshold is 0.00: monetary impact routes to maker-checker.
    assert data["status"] == "PENDING_APPROVAL"
    assert data["amendment_number"] == 1
    assert data["requires_supplier_reconfirmation"] is True
    assert data["applied_at"] is None
    by_field = {ln["field_name"]: ln for ln in data["lines"]}
    assert by_field["UNIT_PRICE"]["old_value"] == "50.00"
    assert by_field["UNIT_PRICE"]["new_value"] == "55.00"
    assert by_field["QUANTITY_ORDERED"]["old_value"] == "100.0000"
    assert by_field["QUANTITY_ORDERED"]["new_value"] == "120"

    # Retrieval surfaces the persisted amendment (no overwrite of history).
    r = client.get(f"/api/v1/spos/{spo['id']}", headers=headers)
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert got["has_open_amendment"] is True
    assert len(got["amendments"]) == 1
    assert got["amendments"][0]["id"] == data["id"]


def test_propose_validation_gates():
    token, ws = _register("amend_valid")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P2")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])
    good = [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "55.00"}]

    r = _propose(headers, spo["id"], "short", good)
    assert r.status_code == 422, r.text  # SPO-012 reason minimum

    r = _propose(headers, spo["id"], "Valid reason here", [])
    assert r.status_code == 422, r.text  # lines required

    r = _propose(
        headers,
        spo["id"],
        "Valid reason here",
        [
            {
                "spo_item_id": str(uuid.uuid4()),
                "field_name": "UNIT_PRICE",
                "new_value": "1",
            }
        ],
    )
    assert r.status_code == 404, r.text  # foreign line

    r = _propose(
        headers,
        spo["id"],
        "Valid reason here",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "abc"}],
    )
    assert r.status_code == 422, r.text  # unparsable decimal

    r = _propose(
        headers,
        spo["id"],
        "Valid reason here",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "50.00"}],
    )
    assert r.status_code == 422, r.text  # unchanged value


def test_below_threshold_auto_approves():
    token, ws = _register("amend_thresh")
    headers = {"Authorization": f"Bearer {token}"}
    _set_amendment_threshold(ws, "1000000")
    fks = _seed_fks(headers, ws, "P3")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])

    r = _propose(
        headers,
        spo["id"],
        "Minor delivery date slide",
        [
            {
                "spo_item_id": item_id,
                "field_name": "DELIVERY_DATE",
                "new_value": "2026-12-31",
            }
        ],
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "APPROVED"  # zero impact: no maker-checker needed
    assert data["approved_by"] is not None


def test_maker_checker_rejects_self_approval():
    token_a, ws = _register("amend_maker")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "P4")
    spo = _spo(headers_a, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers_a, spo["id"])

    r = _propose(
        headers_a,
        spo["id"],
        "Supplier raised steel prices this quarter",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    aid = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/approve", headers=headers_a
    )
    assert r.status_code == 400, r.text  # maker cannot check own work

    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/approve", headers=headers_b
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "APPROVED"


def test_apply_writes_values_and_clears():
    token_a, ws = _register("amend_apply")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "P5")
    spo = _spo(headers_a, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers_a, spo["id"])

    r = _propose(
        headers_a,
        spo["id"],
        "Supplier raised steel prices this quarter",
        [
            {"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"},
            {
                "spo_item_id": item_id,
                "field_name": "QUANTITY_ORDERED",
                "new_value": "110",
            },
        ],
    )
    aid = r.json()["data"]["id"]
    client.post(f"/api/v1/spos/{spo['id']}/amendments/{aid}/approve", headers=headers_b)

    # Reconfirmation gate: price/qty amendments require the attestation.
    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={},
        headers=headers_b,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={"supplier_reconfirmed": True},
        headers=headers_b,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "APPLIED"
    assert r.json()["data"]["applied_at"] is not None

    r = client.get(f"/api/v1/spos/{spo['id']}", headers=headers_a)
    got = r.json()["data"]
    item = got["items"][0]
    assert float(item["unit_price"]) == 60.00
    assert float(item["quantity_ordered"]) == 110.0
    assert float(item["total_price"]) == 6600.00
    assert float(got["subtotal"]) == 6600.00
    assert got["has_open_amendment"] is False

    # Re-applying is rejected: no double application.
    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={"supplier_reconfirmed": True},
        headers=headers_b,
    )
    assert r.status_code == 400, r.text


def test_ack_price_change_creates_pending_amendment():
    token, ws = _register("amend_ack")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P6")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    acked = _send_spo(
        headers,
        spo["id"],
        {item_id: {"quantity_confirmed": 100, "unit_price": 55.0}},
    )
    assert acked["status"] == "PARTIALLY_ACKNOWLEDGED"
    assert acked["items"][0]["price_amendment_pending"] is True

    r = client.get(f"/api/v1/spos/{spo['id']}", headers=headers)
    got = r.json()["data"]
    assert got["has_open_amendment"] is True
    assert len(got["amendments"]) == 1
    amd = got["amendments"][0]
    assert amd["status"] == "PENDING_APPROVAL"
    assert amd["requires_supplier_reconfirmation"] is True
    assert len(amd["lines"]) == 1
    assert amd["lines"][0]["field_name"] == "UNIT_PRICE"
    assert amd["lines"][0]["old_value"] == "50.00"
    assert amd["lines"][0]["new_value"] == "55.0"


def test_ack_partial_recomputes_header_totals_without_amendment():
    token, ws = _register("amend_totals")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P7")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    acked = _send_spo(
        headers,
        spo["id"],
        {item_id: {"quantity_confirmed": 90, "unit_price": 50.0}},
    )
    assert acked["status"] == "ACKNOWLEDGED"
    assert float(acked["quantity_confirmed_total"]) == 90.0
    assert float(acked["quantity_backordered_total"]) == 10.0

    r = client.get(f"/api/v1/spos/{spo['id']}", headers=headers)
    got = r.json()["data"]
    assert got["has_open_amendment"] is False
    assert got["amendments"] == []


def test_open_amendment_blocks_grn_and_reack():
    token, ws = _register("amend_block")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P8")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])
    r = _propose(
        headers,
        spo["id"],
        "Supplier raised steel prices this quarter",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": fks["supplier_id"],
            "spo_id": spo["id"],
            "warehouse_id": fks["warehouse_id"],
            "received_date": "2026-08-20",
        },
    )
    assert r.status_code == 400, r.text  # SPO-014

    r = client.post(
        f"/api/v1/spos/{spo['id']}/items/acknowledge",
        json={"lines": {item_id: {"quantity_confirmed": 100, "unit_price": 50.0}}},
        headers=headers,
    )
    assert r.status_code == 400, r.text  # SPO-014


def test_identical_repropose_returns_existing():
    token, ws = _register("amend_dedup")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P9")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])
    body = {
        "reason": "Supplier raised steel prices this quarter",
        "lines": [
            {"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}
        ],
    }
    first = client.post(
        f"/api/v1/spos/{spo['id']}/amendments", json=body, headers=headers
    )
    second = client.post(
        f"/api/v1/spos/{spo['id']}/amendments", json=body, headers=headers
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["amendment_number"] == 1

    third = client.post(
        f"/api/v1/spos/{spo['id']}/amendments",
        json={
            "reason": "A different commercial reason entirely",
            "lines": [
                {
                    "spo_item_id": item_id,
                    "field_name": "UNIT_PRICE",
                    "new_value": "61.00",
                }
            ],
        },
        headers=headers,
    )
    assert third.json()["data"]["amendment_number"] == 2


def test_terminal_spo_rejects_propose():
    token, ws = _register("amend_term")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P10")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(headers, spo["id"])
    r = client.post(
        f"/api/v1/spos/{spo['id']}/cancel?reason=Buyer%20withdrew%20the%20requirement",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = _propose(
        headers,
        spo["id"],
        "Trying to amend a cancelled order here",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    assert r.status_code == 400, r.text


def test_cross_workspace_isolation():
    token_a, _ = _register("amend_iso_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b, _ = _register("amend_iso_b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me = client.get("/auth/me", headers=headers_a).json()["data"]
    fks = _seed_fks(headers_a, me["workspace_id"], "P11")
    spo = _spo(
        headers_a,
        me["workspace_id"],
        fks,
        [_line(fks["product_id"], fks["uom_id"], 100, 50.0)],
    )
    item_id = spo["items"][0]["id"]
    _send_spo(headers_a, spo["id"])

    r = _propose(
        headers_b,
        spo["id"],
        "Cross tenant attempt at amendment here",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    assert r.status_code == 404, r.text

    r = _propose(
        headers_a,
        spo["id"],
        "Cross tenant attempt at amendment here",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    aid = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/approve", headers=headers_b
    )
    assert r.status_code == 404, r.text
    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={"supplier_reconfirmed": True},
        headers=headers_b,
    )
    assert r.status_code == 404, r.text


def _receive_via_grn(headers, ids, spo_id, spo_item_id, qty, lc_items=None):
    """Run a full GRN receive+disposition accepting `qty` units."""
    r = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": ids["supplier_id"],
            "spo_id": spo_id,
            "warehouse_id": ids["warehouse_id"],
            "received_date": "2026-08-20",
        },
    )
    assert r.status_code == 201, r.text
    grn_id = r.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    payload = {
        "spo_item_id": spo_item_id,
        "product_id": ids["product_id"],
        "internal_sku": "WDGT",
        "description": "Widget",
        "uom_id": ids["uom_id"],
        "quantity_received": qty,
    }
    if lc_items is not None:
        payload["landed_cost_items"] = lc_items
    r = client.post(f"/api/v1/grns/{grn_id}/items", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    grn_item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)
    r = client.post(
        f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition",
        json={
            "quantity_accepted": qty,
            "quantity_damaged": 0,
            "quantity_rejected": 0,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return grn_id, grn_item_id


def _landed_cost_rows(grn_item_id):
    async def _fetch():
        async with TestingSessionLocal() as session:
            from app.models.landed_cost import LandedCostAllocation

            result = await session.execute(
                select(LandedCostAllocation).where(
                    LandedCostAllocation.grn_item_id == uuid.UUID(str(grn_item_id))
                )
            )
            return [
                {"amount": r.amount, "status": r.status} for r in result.scalars().all()
            ]

    return asyncio.run(_fetch())


def test_spo013_floor_blocks_order_below_received():
    token, ws = _register("amend_floor")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "P13")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(
        headers, spo["id"], {item_id: {"quantity_confirmed": 100, "unit_price": 50.0}}
    )
    _receive_via_grn(headers, fks, spo["id"], item_id, 40)

    # Cannot amend ordered below the 40 physically received units.
    r = _propose(
        headers,
        spo["id"],
        "Trying to shrink the order below receipts",
        [{"spo_item_id": item_id, "field_name": "QUANTITY_ORDERED", "new_value": "30"}],
    )
    assert r.status_code == 422, r.text

    # Reducing to exactly the received floor is allowed (still pending approval).
    r = _propose(
        headers,
        spo["id"],
        "Trimming the order down to what arrived",
        [{"spo_item_id": item_id, "field_name": "QUANTITY_ORDERED", "new_value": "40"}],
    )
    assert r.status_code == 200, r.text


def test_price_apply_leaves_landed_cost_rows_untouched():
    # D-22 boundary: amendment apply must never rewrite capitalized LC rows.
    token_a, ws = _register("amend_lc")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "P14")
    spo = _spo(headers_a, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    _send_spo(
        headers_a, spo["id"], {item_id: {"quantity_confirmed": 100, "unit_price": 50.0}}
    )
    _, grn_item_id = _receive_via_grn(
        headers_a,
        fks,
        spo["id"],
        item_id,
        100,
        lc_items=[{"component_type": "FREIGHT", "amount": "5000.00"}],
    )
    before = _landed_cost_rows(grn_item_id)
    assert len(before) == 1
    assert before[0]["status"] == "CAPITALIZED"

    r = _propose(
        headers_a,
        spo["id"],
        "Supplier raised steel prices this quarter",
        [{"spo_item_id": item_id, "field_name": "UNIT_PRICE", "new_value": "60.00"}],
    )
    aid = r.json()["data"]["id"]
    client.post(f"/api/v1/spos/{spo['id']}/amendments/{aid}/approve", headers=headers_b)
    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={"supplier_reconfirmed": True},
        headers=headers_b,
    )
    assert r.status_code == 200, r.text

    after = _landed_cost_rows(grn_item_id)
    assert after == before


def test_other_field_records_without_mutation():
    token, ws = _register("amend_other")
    headers = {"Authorization": f"Bearer {token}"}
    _set_amendment_threshold(ws, "1000000")
    fks = _seed_fks(headers, ws, "P12")
    spo = _spo(headers, ws, fks, [_line(fks["product_id"], fks["uom_id"], 100, 50.0)])
    item_id = spo["items"][0]["id"]
    before_terms = spo["delivery_terms"]
    _send_spo(headers, spo["id"])

    r = _propose(
        headers,
        spo["id"],
        "Switching delivery to ex-works terms now",
        [
            {
                "spo_item_id": item_id,
                "field_name": "DELIVERY_TERMS",
                "new_value": "EXW Dubai",
            },
            {
                "spo_item_id": item_id,
                "field_name": "OTHER",
                "new_value": "Note for the file",
            },
        ],
    )
    assert r.status_code == 200, r.text
    # Zero monetary impact: auto-approved, no reconfirmation needed.
    assert r.json()["data"]["status"] == "APPROVED"
    assert r.json()["data"]["requires_supplier_reconfirmation"] is False
    aid = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/spos/{spo['id']}/amendments/{aid}/apply",
        json={},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "APPLIED"

    r = client.get(f"/api/v1/spos/{spo['id']}", headers=headers)
    got = r.json()["data"]
    assert got["delivery_terms"] == "EXW Dubai"
    assert float(got["items"][0]["unit_price"]) == 50.00
    assert float(got["items"][0]["quantity_ordered"]) == 100.0
    assert got["has_open_amendment"] is False
    assert before_terms != "EXW Dubai"
