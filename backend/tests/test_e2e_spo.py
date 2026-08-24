import pytest
import uuid
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_session
from app.config import get_settings
from app.models.spo import SPOStatus
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


def get_auth_token():
    test_email = f"spo_tester_{uuid.uuid4().hex[:8]}@example.com"
    register_data = {
        "email": test_email,
        "password": "securepassword123",
        "name": "SPO Tester",
        "workspace_name": "SPO Workspace",
    }
    r = client.post("/auth/register", json=register_data)
    if r.status_code != 201:
        # maybe already exists or something, just login
        r = client.post(
            "/auth/login", json={"email": test_email, "password": "securepassword123"}
        )
    return r.json()["data"]["access_token"]


def test_e2e_spo_flow():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Get workspace ID
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    user_data = r.json()["data"]
    workspace_id = user_data["workspace_id"]

    # Generate UUIDs
    product_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    warehouse_id = str(uuid.uuid4())
    supplier_id = str(uuid.uuid4())

    # Insert FK records directly
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
    assert r_supp.status_code == 200, f"Supplier creation failed: {r_supp.text}"
    supplier_id = r_supp.json()["data"]["id"]

    r_wh = client.post(
        f"/api/v1/inventory/warehouses/?workspace_id={workspace_id}",
        json={"name": "WH", "code": "WH1", "address": "123"},
        headers=headers,
    )
    assert r_wh.status_code == 200, f"Warehouse creation failed: {r_wh.text}"
    warehouse_id = r_wh.json()["data"]["id"]

    r_uom = client.post(
        f"/api/v1/products/uom/?workspace_id={workspace_id}",
        json={"name": "UOM", "code": "UOM1"},
        headers=headers,
    )
    assert r_uom.status_code == 200, f"UOM creation failed: {r_uom.text}"
    uom_id = r_uom.json()["data"]["id"]

    r_prod = client.post(
        f"/api/v1/products/?workspace_id={workspace_id}",
        json={
            "name": "PROD",
            "internal_sku": "PROD1",
            "type": "GOODS",
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert r_prod.status_code == 200, f"Product creation failed: {r_prod.text}"
    product_id = r_prod.json()["data"]["id"]

    # 2. Award -> SPO (Create DRAFT SPO)
    spo_data = {
        "supplier_id": supplier_id,
        "procurement_method": "DIRECT",
        "warehouse_id": warehouse_id,
        "currency": "AED",
        "items": [
            {
                "product_id": product_id,
                "description": "Widget A",
                "uom_id": uom_id,
                "quantity_ordered": 100,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    }

    r = client.post(
        f"/api/v1/spos/?workspace_id={workspace_id}", json=spo_data, headers=headers
    )
    assert r.status_code == 200, f"Failed to create SPO: {r.text}"
    spo_id = r.json()["data"]["id"]
    item_id = r.json()["data"]["items"][0]["id"]

    # 3. Submit Approval
    r = client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == SPOStatus.PENDING_APPROVAL.value

    # 4. Approve
    r = client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == SPOStatus.APPROVED.value

    # 5. Send
    r = client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == SPOStatus.SENT.value

    # 6. Partial Ack with price amendment
    ack_data = {
        "lines": {
            item_id: {
                "quantity_confirmed": 90,  # partial ack
                "unit_price": 55.0,  # price amendment (changed from 50)
            }
        }
    }
    r = client.post(
        f"/api/v1/spos/{spo_id}/items/acknowledge", json=ack_data, headers=headers
    )
    assert r.status_code == 200, f"Ack failed: {r.text}"
    assert r.json()["data"]["status"] == SPOStatus.PARTIALLY_ACKNOWLEDGED.value
    assert r.json()["data"]["items"][0]["price_amendment_pending"] is True

    # 7. Short close remainder (cancel the remaining 10)
    r = client.post(
        f"/api/v1/spos/{spo_id}/cancel?reason=Short%20closing%20remainder",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == SPOStatus.CANCELLED.value
