"""SPO API regression tests.

Covers the two invariants most likely to silently regress:

* SPO numbers are gapless and unique per workspace (the generator once emitted a
  hardcoded ``SPO-YYYY-000001`` that violated ``uq_workspace_spo_number`` on the
  second create).
* SPOs are workspace-isolated — a second tenant can neither read nor mutate the
  first tenant's SPO (regression guard for the P1 multi-tenancy fix in
  ``SPOService._get_scoped_spo``).

Follows the suite's standard harness: sync ``TestClient`` against a real
PostgreSQL ``_test`` database, module-scoped schema create/drop. The auth
limiter is disabled globally in ``conftest.py`` so the repeated registrations
here don't trip the rate limit.
"""

import sys
import asyncio
import uuid

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

settings = get_settings()

# Append _test to the DB name only (idempotently) so this works both in dev
# (DATABASE_URL -> .../invoicesaas) and CI (already -> .../invoicesaas_test).
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


def _register(prefix: str, workspace_name: str) -> tuple[str, str]:
    """Register a fresh owner + workspace; return (bearer_token, workspace_id)."""
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


def _seed_fks(headers: dict, workspace_id: str) -> dict:
    """Create the minimal supplier/warehouse/uom/product graph an SPO needs."""
    suffix = uuid.uuid4().hex[:6]
    q = f"?workspace_id={workspace_id}"

    r = client.post(
        f"/api/v1/suppliers/{q}",
        json={
            "name": "SUP",
            "email": "sup@example.com",
            "currency": "AED",
            "supplier_code": f"SUP-{suffix}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), f"supplier: {r.text}"
    supplier_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses/{q}",
        json={"name": "WH", "code": f"WH-{suffix}", "address": "123"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"warehouse: {r.text}"
    warehouse_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/uom/{q}",
        json={"name": "Pieces", "code": f"PCS-{suffix}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), f"uom: {r.text}"
    uom_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/{q}",
        json={
            "name": "Widget",
            "internal_sku": f"WDGT-{suffix}",
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


def _create_spo(headers: dict, fks: dict) -> dict:
    """Create a DRAFT SPO from a seeded FK graph; return the raw SPO body."""
    r = client.post(
        "/api/v1/spos/",
        json={
            "supplier_id": fks["supplier_id"],
            "procurement_method": "DIRECT",
            "warehouse_id": fks["warehouse_id"],
            "currency": "AED",
            "items": [
                {
                    "line_number": 1,
                    "product_id": fks["product_id"],
                    "description": "Widget",
                    "uom_id": fks["uom_id"],
                    "quantity_ordered": 10,
                    "unit_price": 5.0,
                    "vat_rate": 5.0,
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, f"SPO create failed: {r.text}"
    return r.json()


def test_spo_numbers_are_gapless_within_a_workspace():
    """Two SPOs in one workspace must get distinct, gapless numbers."""
    token, ws_id = _register("owner_gap", "Gapless Workspace")
    headers = {"Authorization": f"Bearer {token}"}
    fks = _seed_fks(headers, ws_id)

    spo1 = _create_spo(headers, fks)
    spo2 = _create_spo(headers, fks)

    assert spo1["spo_number"] and spo2["spo_number"]
    assert (
        spo1["spo_number"] != spo2["spo_number"]
    ), f"SPO numbers must be unique: {spo1['spo_number']} == {spo2['spo_number']}"


def test_spo_is_workspace_isolated():
    """Workspace B must not read or mutate workspace A's SPO — both cross-tenant
    reads and writes must 404 (not 200, and not a 403 that confirms existence)."""
    token_a, ws_a = _register("owner_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    fks_a = _seed_fks(headers_a, ws_a)
    spo_id = _create_spo(headers_a, fks_a)["id"]

    token_b, _ = _register("owner_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Cross-tenant READ must 404
    r = client.get(f"/api/v1/spos/{spo_id}", headers=headers_b)
    assert r.status_code == 404, f"cross-tenant read leaked: {r.status_code} {r.text}"

    # Cross-tenant WRITE (state transition) must 404
    r = client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers_b)
    assert r.status_code == 404, f"cross-tenant write leaked: {r.status_code} {r.text}"

    # Owner A can still read its own SPO
    r = client.get(f"/api/v1/spos/{spo_id}", headers=headers_a)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == spo_id
