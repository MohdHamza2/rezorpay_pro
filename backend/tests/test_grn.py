import pytest
import uuid
import sys
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlalchemy.pool import NullPool

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app
from app.database import get_session
from app.config import get_settings

# Import all models so SQLModel.metadata is fully populated before create_all
from app.models import *  # noqa: F401, F403

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


_MODULE_TOKEN: str = ""
_MODULE_WS_ID: str = ""


def _init_module_auth() -> None:
    """Register once per module; subsequent calls reuse cached token."""
    global _MODULE_TOKEN, _MODULE_WS_ID
    if _MODULE_TOKEN:
        return
    test_email = f"grn_tester_{uuid.uuid4().hex[:8]}@example.com"
    register_data = {
        "email": test_email,
        "password": "securepassword123",
        "name": "GRN Tester",
        "workspace_name": "GRN Workspace",
    }
    r = client.post("/auth/register", json=register_data)
    assert r.status_code == 201, f"Registration failed: {r.json()}"
    _MODULE_TOKEN = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {_MODULE_TOKEN}"})
    _MODULE_WS_ID = me.json()["data"]["workspace_id"]


def get_auth_token() -> str:
    _init_module_auth()
    return _MODULE_TOKEN


def get_workspace_id() -> str:
    _init_module_auth()
    return _MODULE_WS_ID


def test_grn_lifecycle():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    workspace_id = r.json()["data"]["workspace_id"]

    # Create dependencies
    r_supp = client.post(
        f"/api/v1/suppliers/?workspace_id={workspace_id}",
        json={
            "name": "SUP",
            "email": "sup@example.com",
            "currency": "AED",
            "supplier_code": "SUP1",
        },
        headers=headers,
    )
    assert r_supp.status_code in (200, 201), r_supp.json()
    supplier_id = r_supp.json()["data"]["id"]

    r_wh = client.post(
        f"/api/v1/inventory/warehouses/?workspace_id={workspace_id}",
        json={"name": "WH", "code": "WH1", "address": "123"},
        headers=headers,
    )
    assert r_wh.status_code in (200, 201), r_wh.json()
    warehouse_id = r_wh.json()["data"]["id"]

    # Create a bin in the warehouse (required for GRN stock posting)
    r_bin = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        json={"code": "BIN-A1"},
        headers=headers,
    )
    assert r_bin.status_code in (200, 201), r_bin.json()

    r_uom = client.post(
        f"/api/v1/products/uom/?workspace_id={workspace_id}",
        json={"name": "Pieces", "code": "PCS"},
        headers=headers,
    )
    assert r_uom.status_code in (200, 201), r_uom.json()
    uom_id = r_uom.json()["data"]["id"]

    r_prod = client.post(
        f"/api/v1/products/?workspace_id={workspace_id}",
        json={"name": "Widget", "internal_sku": "WDGT-001", "base_uom_id": uom_id},
        headers=headers,
    )
    assert r_prod.status_code in (200, 201), r_prod.json()
    product_id = r_prod.json()["data"]["id"]

    # Create SPO — router is at /api/v1/spos/
    spo_data = {
        "supplier_id": supplier_id,
        "procurement_method": "DIRECT",
        "warehouse_id": warehouse_id,
        "currency": "AED",
        "items": [
            {
                "line_number": 1,
                "product_id": product_id,
                "description": "Widget X",
                "uom_id": uom_id,
                "quantity_ordered": 10,
                "unit_price": 100,
            }
        ],
    }
    r_spo = client.post(
        f"/api/v1/spos/?workspace_id={workspace_id}", json=spo_data, headers=headers
    )
    assert r_spo.status_code in (200, 201), r_spo.json()
    spo_id = r_spo.json()["data"]["id"]
    spo_item_id = r_spo.json()["data"]["items"][0]["id"]

    # Advance SPO to SENT so GRN can be linked
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)

    # 1. Create GRN Draft
    grn_create_data = {
        "supplier_id": supplier_id,
        "spo_id": spo_id,
        "warehouse_id": warehouse_id,
        "received_date": "2026-08-20",
    }
    r_grn = client.post("/api/v1/grns", json=grn_create_data, headers=headers)
    assert r_grn.status_code == 201, r_grn.json()
    grn_id = r_grn.json()["data"]["id"]

    # 2. Start Receiving
    r_start = client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    assert r_start.status_code == 200, r_start.json()

    # 3. Add Item
    item_data = {
        "spo_item_id": spo_item_id,
        "product_id": product_id,
        "internal_sku": "WDGT-001",
        "description": "Widget X",
        "uom_id": uom_id,
        "quantity_received": 10,
    }
    r_item = client.post(
        f"/api/v1/grns/{grn_id}/items", json=item_data, headers=headers
    )
    assert r_item.status_code == 200, r_item.json()
    grn_item_id = r_item.json()["data"]["items"][0]["id"]

    # 4. Stage for Inspection
    r_stage = client.post(
        f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers
    )
    assert r_stage.status_code == 200, r_stage.json()

    # 5. Record Disposition
    disp_data = {
        "quantity_accepted": 8,
        "quantity_damaged": 1,
        "quantity_rejected": 1,
        "damage_reason": "Box was crushed during transit",
        "rejection_reason": "Wrong color delivered",
    }
    r_disp = client.post(
        f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition",
        json=disp_data,
        headers=headers,
    )
    assert r_disp.status_code == 200, r_disp.json()
    final_grn = r_disp.json()["data"]
    assert final_grn["stock_posted"] is True
    assert final_grn["status"] == "PARTIALLY_ACCEPTED"


def test_grn_cancellation():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = get_workspace_id()

    # Create supplier & warehouse
    r_supp = client.post(
        f"/api/v1/suppliers/?workspace_id={workspace_id}",
        json={
            "name": "SUP2",
            "email": "sup2@example.com",
            "currency": "AED",
            "supplier_code": "SUP2",
        },
        headers=headers,
    )
    assert r_supp.status_code in (200, 201), r_supp.json()
    supplier_id = r_supp.json()["data"]["id"]

    r_wh = client.post(
        f"/api/v1/inventory/warehouses/?workspace_id={workspace_id}",
        json={"name": "WH2", "code": "WH2", "address": "123"},
        headers=headers,
    )
    assert r_wh.status_code in (200, 201), r_wh.json()
    warehouse_id = r_wh.json()["data"]["id"]

    # Create GRN Draft (no SPO linked for simplicity)
    grn_create_data = {
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "received_date": "2026-08-20",
    }
    r_grn = client.post("/api/v1/grns", json=grn_create_data, headers=headers)
    assert r_grn.status_code == 201, r_grn.json()
    grn_id = r_grn.json()["data"]["id"]

    # Cancel GRN
    r_cancel = client.post(
        f"/api/v1/grns/{grn_id}/cancel",
        json={"reason": "Cancelled by user test"},
        headers=headers,
    )
    assert r_cancel.status_code == 200, r_cancel.json()
    assert r_cancel.json()["data"]["status"] == "CANCELLED"
