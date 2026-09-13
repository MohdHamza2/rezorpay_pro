"""Wave 31 Item 2.3 — RFQ award flow tests.

Covers: quote intake validation + revisions, UOM-gap non-comparability,
UOM conversion normalization, LOWEST_PRICE comparison, award guards
(availability, remainder, deviation, threshold, maker-checker), split and
single modes, idempotent conversion into DRAFT SPOs with traceability,
state transitions, and workspace isolation.

Follows the suite's standard harness: sync ``TestClient`` against a real
PostgreSQL ``_test`` database, module-scoped schema create/drop.
"""

import sys
import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
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


def _set_award_threshold(workspace_id, value):
    async def _update():
        async with TestingSessionLocal() as session:
            from app.models.workspace import Workspace

            ws = await session.get(Workspace, uuid.UUID(str(workspace_id)))
            ws.rfq_award_approval_threshold = Decimal(str(value))
            await session.commit()

    asyncio.run(_update())


def _seed_fks(headers, workspace_id, tag):
    """Supplier (ACTIVE) + warehouse/bin + two UOMs + product on base UOM."""
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
    pcs_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/uom/{q}",
        json={"name": "Boxes", "code": f"BOX-{tag}-{suffix}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"box uom: {r.text}"
    box_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/{q}",
        json={
            "name": f"Widget-{tag}",
            "internal_sku": f"WDGT-{tag}-{suffix}",
            "base_uom_id": pcs_id,
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), f"product: {r.text}"
    product_id = r.json()["data"]["id"]
    return {
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "pcs_id": pcs_id,
        "box_id": box_id,
        "product_id": product_id,
    }


def _second_supplier(headers, workspace_id, tag):
    suffix = uuid.uuid4().hex[:6]
    r = client.post(
        f"/api/v1/suppliers/?workspace_id={workspace_id}",
        json={
            "name": f"SUP2-{tag}",
            "email": f"sup2-{tag}-{suffix}@example.com",
            "currency": "AED",
            "supplier_code": f"SUP2-{tag}-{suffix}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _create_rfq(headers, fks, qty=100, price_uom=None, award_mode=None):
    body = {
        "deadline": "2026-12-31T00:00:00Z",
        "currency": "AED",
        "items": [
            {
                "product_id": fks["product_id"],
                "uom_id": price_uom or fks["pcs_id"],
                "quantity": qty,
            }
        ],
    }
    if award_mode:
        body["award_mode"] = award_mode
    r = client.post("/api/v1/rfq/requests", json=body, headers=headers)
    assert r.status_code in (200, 201), f"rfq create: {r.text}"
    data = r.json()["data"]
    return data["id"], data["items"][0]["id"]


def _quote(headers, rfq_id, supplier_id, lines, currency="AED", rate="1.0"):
    return client.post(
        f"/api/v1/rfq/requests/{rfq_id}/responses",
        json={
            "supplier_id": supplier_id,
            "quote_currency": currency,
            "exchange_rate": rate,
            "items": lines,
        },
        headers=headers,
    )


def _qli(rfq_item_id, qty, price, uom_id=None, alternate=False, alt_product=None):
    payload = {
        "rfq_item_id": rfq_item_id,
        "quantity_available": qty,
        "quoted_unit_price": price,
    }
    if uom_id is not None:
        payload["uom_id"] = uom_id
    if alternate:
        payload["is_alternate"] = True
        payload["alternate_product_id"] = alt_product
    return payload


def test_intake_validation_gates():
    token, ws = _register("rfq_gate")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G1")
    rfq_id, item_id = _create_rfq(headers, fks)

    # DRAFT RFQs cannot receive quotes.
    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    assert r.status_code == 400, r.text

    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)

    # Unknown supplier → 404.
    r = _quote(headers, rfq_id, str(uuid.uuid4()), [_qli(item_id, 100, 50.0)])
    assert r.status_code == 404, r.text

    # Foreign RFQ line → 404.
    r = _quote(
        headers,
        rfq_id,
        fks["supplier_id"],
        [_qli(str(uuid.uuid4()), 100, 50.0)],
    )
    assert r.status_code == 404, r.text

    # Non-positive rate rejected at the schema boundary.
    r = _quote(
        headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)], rate="0"
    )
    assert r.status_code == 422, r.text


def test_inactive_supplier_cannot_quote():
    token, ws = _register("rfq_hold")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G2")
    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)

    async def _hold():
        async with TestingSessionLocal() as session:
            from app.models.supplier import Supplier

            sup = await session.get(Supplier, uuid.UUID(fks["supplier_id"]))
            sup.status = "HOLD"
            await session.commit()

    asyncio.run(_hold())
    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    assert r.status_code == 422, r.text  # RFQ-012 mapping


def test_revision_immutable_and_latest_wins():
    token, ws = _register("rfq_rev")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G3")
    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)

    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    assert r.json()["data"]["revision_number"] == 1
    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 48.0)])
    assert r.json()["data"]["revision_number"] == 2

    r = client.get(f"/api/v1/rfq/requests/{rfq_id}/comparison", headers=headers)
    rows = r.json()["data"]["lines"][0]["rows"]
    assert len(rows) == 1  # only the latest revision participates
    assert float(rows[0]["quoted_unit_price"]) == 48.00
    assert rows[0]["is_lowest"] is True


def test_uom_gap_is_non_comparable_and_non_awardable():
    token, ws = _register("rfq_uom")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G4")
    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)

    # Quoted in BOX with no conversion row: accepted at intake, flagged later.
    r = _quote(
        headers,
        rfq_id,
        fks["supplier_id"],
        [_qli(item_id, 10, 500.0, uom_id=fks["box_id"])],
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["data"]["quote_items"][0]["normalized_unit_price"] is None

    r = client.get(f"/api/v1/rfq/requests/{rfq_id}/comparison", headers=headers)
    row = r.json()["data"]["lines"][0]["rows"][0]
    assert row["comparable"] is False
    assert row["non_comparable_reason"] == "no UOM conversion to base unit"
    assert row["is_lowest"] is False

    qi = r.json()["data"]["lines"][0]["rows"][0]["quote_item_id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 5}],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_uom_conversion_normalizes():
    token, ws = _register("rfq_conv")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G5")

    async def _conversion():
        async with TestingSessionLocal() as session:
            from app.models.product import ProductUOMConversion

            session.add(
                ProductUOMConversion(
                    workspace_id=uuid.UUID(ws),
                    product_id=uuid.UUID(fks["product_id"]),
                    to_uom_id=uuid.UUID(fks["box_id"]),
                    conversion_factor=Decimal("10"),
                )
            )
            await session.commit()

    asyncio.run(_conversion())

    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)
    # 500/BOX over 10 PCS/BOX → 50/PCS normalized.
    r = _quote(
        headers,
        rfq_id,
        fks["supplier_id"],
        [_qli(item_id, 10, 500.0, uom_id=fks["box_id"])],
    )
    assert float(r.json()["data"]["quote_items"][0]["normalized_unit_price"]) == 50.00

    other = _second_supplier(headers, ws, "G5")
    r = _quote(headers, rfq_id, other, [_qli(item_id, 100, 45.0)])
    assert r.status_code in (200, 201), r.text

    r = client.get(f"/api/v1/rfq/requests/{rfq_id}/comparison", headers=headers)
    rows = {x["supplier_id"]: x for x in r.json()["data"]["lines"][0]["rows"]}
    assert rows[other]["is_lowest"] is True
    assert rows[fks["supplier_id"]]["is_lowest"] is False


def test_award_guards_availability_remainder_deviation():
    token, ws = _register("rfq_guards")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G6")
    other = _second_supplier(headers, ws, "G6")
    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)
    _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    r = _quote(headers, rfq_id, other, [_qli(item_id, 100, 45.0)])
    other_qi = r.json()["data"]["quote_items"][0]["id"]

    # Over availability.
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": other,
            "lines": [{"quote_item_id": other_qi, "awarded_quantity": 101}],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text

    # Non-lowest without deviation reason.
    mine = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    mine_qi = mine.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": mine_qi, "awarded_quantity": 10}],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text

    # With deviation reason: drafts fine (PENDING at default threshold 0).
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [
                {
                    "quote_item_id": mine_qi,
                    "awarded_quantity": 10,
                    "deviation_reason": "Incumbent supplier continuity",
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "PENDING_APPROVAL"
    assert r.json()["data"]["award_number"].startswith("AWD-")


def test_threshold_and_maker_checker():
    token_a, ws = _register("rfq_maker")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "G7")
    rfq_id, item_id = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_a)
    r = _quote(headers_a, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi = r.json()["data"]["quote_items"][0]["id"]

    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 100}],
        },
        headers=headers_a,
    )
    aid = r.json()["data"]["id"]
    assert r.json()["data"]["total_awarded_value"] == "5000.00"

    r = client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_a)
    assert r.status_code == 400, r.text  # maker cannot check own work

    r = client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_b)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "APPROVED"

    # Below-threshold awards auto-approve.
    _set_award_threshold(ws, "1000000")
    rfq2, item2 = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq2}/send", headers=headers_a)
    r = _quote(headers_a, rfq2, fks["supplier_id"], [_qli(item2, 10, 50.0)])
    qi2 = r.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq2}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi2, "awarded_quantity": 10}],
        },
        headers=headers_a,
    )
    assert r.json()["data"]["status"] == "APPROVED"
    assert r.json()["data"]["approved_by"] is not None


def test_convert_creates_draft_spo_idempotently():
    token_a, ws = _register("rfq_conv2")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "G8")
    rfq_id, item_id = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_a)
    r = _quote(headers_a, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi = r.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 100}],
        },
        headers=headers_a,
    )
    aid = r.json()["data"]["id"]
    client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_b)

    body = {"warehouse_id": fks["warehouse_id"]}
    r = client.post(
        f"/api/v1/rfq/awards/{aid}/generate-spos", json=body, headers=headers_b
    )
    assert r.status_code == 200, r.text
    spo_ids = r.json()["data"]["spo_ids"]
    assert len(spo_ids) == 1

    r = client.get(f"/api/v1/spos/{spo_ids[0]}", headers=headers_a)
    spo = r.json()["data"]
    assert spo["status"] == "DRAFT"  # never auto-submitted
    assert spo["rfq_id"] == rfq_id
    assert spo["supplier_id"] == fks["supplier_id"]
    assert spo["currency"] == "AED"
    line = spo["items"][0]
    assert float(line["quantity_ordered"]) == 100.0
    assert float(line["unit_price"]) == 50.00

    async def _award_link():
        async with TestingSessionLocal() as session:
            from app.models.spo import SupplierPurchaseOrderItem

            row = await session.get(SupplierPurchaseOrderItem, uuid.UUID(line["id"]))
            return row.rfq_award_line_id

    assert asyncio.run(_award_link()) is not None

    # Re-convert: same SPOs returned, nothing duplicated.
    r = client.post(
        f"/api/v1/rfq/awards/{aid}/generate-spos", json=body, headers=headers_b
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["spo_ids"] == spo_ids

    # Award + RFQ + response statuses rolled forward.
    r = client.get(f"/api/v1/rfq/requests/{rfq_id}", headers=headers_a)
    rfq = r.json()["data"]
    assert rfq["status"] == "AWARDED"
    assert rfq["items"][0]["awarded_quantity"] == "100.00"


def test_split_two_suppliers_partial_then_full():
    token_a, ws = _register("rfq_split")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "G9")
    other = _second_supplier(headers_a, ws, "G9")
    rfq_id, item_id = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_a)
    r = _quote(headers_a, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi_a = r.json()["data"]["quote_items"][0]["id"]
    r = _quote(headers_a, rfq_id, other, [_qli(item_id, 100, 45.0)])
    qi_b = r.json()["data"]["quote_items"][0]["id"]

    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": other,
            "lines": [{"quote_item_id": qi_b, "awarded_quantity": 60}],
        },
        headers=headers_a,
    )
    aid_b = r.json()["data"]["id"]
    client.post(f"/api/v1/rfq/awards/{aid_b}/approve", headers=headers_b)
    r = client.get(f"/api/v1/rfq/requests/{rfq_id}", headers=headers_a)
    assert r.json()["data"]["status"] == "PARTIALLY_AWARDED"

    # Remainder cap enforced against the approved 60.
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [
                {
                    "quote_item_id": qi_a,
                    "awarded_quantity": 50,
                    "deviation_reason": "Dual sourcing resilience",
                }
            ],
        },
        headers=headers_a,
    )
    assert r.status_code == 422, r.text
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [
                {
                    "quote_item_id": qi_a,
                    "awarded_quantity": 40,
                    "deviation_reason": "Dual sourcing resilience",
                }
            ],
        },
        headers=headers_a,
    )
    assert r.status_code == 200, r.text
    aid_a = r.json()["data"]["id"]
    client.post(f"/api/v1/rfq/awards/{aid_a}/approve", headers=headers_b)

    body = {"warehouse_id": fks["warehouse_id"]}
    r1 = client.post(
        f"/api/v1/rfq/awards/{aid_b}/generate-spos", json=body, headers=headers_b
    )
    r2 = client.post(
        f"/api/v1/rfq/awards/{aid_a}/generate-spos", json=body, headers=headers_b
    )
    assert r1.json()["data"]["spo_ids"] != r2.json()["data"]["spo_ids"]
    r = client.get(f"/api/v1/rfq/requests/{rfq_id}", headers=headers_a)
    assert r.json()["data"]["status"] == "AWARDED"


def test_single_mode_rejects_second_header():
    token, ws = _register("rfq_single")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws, "G10")
    other = _second_supplier(headers, ws, "G10")
    rfq_id, item_id = _create_rfq(headers, fks, award_mode="SINGLE")
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)
    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi_a = r.json()["data"]["quote_items"][0]["id"]
    r = _quote(headers, rfq_id, other, [_qli(item_id, 100, 45.0)])
    qi_b = r.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": other,
            "lines": [{"quote_item_id": qi_b, "awarded_quantity": 100}],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [
                {
                    "quote_item_id": qi_a,
                    "awarded_quantity": 10,
                    "deviation_reason": "Backup supplier cover",
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_invalid_award_transitions_rejected():
    token_a, ws = _register("rfq_trans")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers_a, ws, "G0")
    rfq_id, item_id = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_a)
    r = _quote(headers_a, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi = r.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 100}],
        },
        headers=headers_a,
    )
    aid = r.json()["data"]["id"]

    # Convert before approval is rejected.
    r = client.post(
        f"/api/v1/rfq/awards/{aid}/generate-spos",
        json={"warehouse_id": fks["warehouse_id"]},
        headers=headers_b,
    )
    assert r.status_code == 400, r.text

    client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_b)

    # Approving twice is rejected.
    r = client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_b)
    assert r.status_code == 400, r.text


def test_closed_rfq_rejects_quotes_and_awards():
    token, ws = _register("rfq_closed")
    headers = {"Authorization": f"Bearer {token}"}
    token_b = _second_user_token(ws)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    fks = _seed_fks(headers, ws, "G11")
    rfq_id, item_id = _create_rfq(headers, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers)
    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 100, 50.0)])
    qi = r.json()["data"]["quote_items"][0]["id"]
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 100}],
        },
        headers=headers,
    )
    aid = r.json()["data"]["id"]
    client.post(f"/api/v1/rfq/awards/{aid}/approve", headers=headers_b)
    body = {"warehouse_id": fks["warehouse_id"]}
    client.post(f"/api/v1/rfq/awards/{aid}/generate-spos", json=body, headers=headers_b)

    r = _quote(headers, rfq_id, fks["supplier_id"], [_qli(item_id, 10, 49.0)])
    assert r.status_code == 400, r.text
    r = client.post(
        f"/api/v1/rfq/requests/{rfq_id}/awards",
        json={
            "supplier_id": fks["supplier_id"],
            "lines": [{"quote_item_id": qi, "awarded_quantity": 1}],
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_cross_workspace_isolation():
    token_a, _ = _register("rfq_iso_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b, _ = _register("rfq_iso_b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me = client.get("/auth/me", headers=headers_a).json()["data"]
    fks = _seed_fks(headers_a, me["workspace_id"], "G12")
    rfq_id, item_id = _create_rfq(headers_a, fks)
    client.post(f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_a)

    assert (
        client.get(f"/api/v1/rfq/requests/{rfq_id}", headers=headers_b).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/rfq/requests/{rfq_id}/send", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        _quote(
            headers_b, rfq_id, fks["supplier_id"], [_qli(item_id, 1, 1.0)]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/rfq/requests/{rfq_id}/comparison", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/rfq/requests/{rfq_id}/awards",
            json={
                "supplier_id": fks["supplier_id"],
                "lines": [{"quote_item_id": str(uuid.uuid4()), "awarded_quantity": 1}],
            },
            headers=headers_b,
        ).status_code
        == 404
    )


def _set_award_threshold(workspace_id, value):
    async def _update():
        async with TestingSessionLocal() as session:
            from app.models.workspace import Workspace

            ws = await session.get(Workspace, uuid.UUID(str(workspace_id)))
            ws.rfq_award_approval_threshold = Decimal(str(value))
            await session.commit()

    asyncio.run(_update())
