import pytest
import uuid
import sys
import asyncio
from httpx import AsyncClient

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_session
from app.config import get_settings
from app.models.spo import SPOStatus
from app.models.grn import GRNStatus
from app.models import *

settings = get_settings()

TEST_DATABASE_URL = settings.DATABASE_URL.replace("invoicesaas", "invoicesaas_test")
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def override_get_session():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    import asyncio
    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
    asyncio.run(_setup())
    yield
    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
    asyncio.run(_teardown())


def get_auth_token():
    test_email = f"grn_e2e_{uuid.uuid4().hex[:8]}@example.com"
    register_data = {
        "email": test_email,
        "password": "securepassword123",
        "name": "GRN E2E Tester",
        "workspace_name": "GRN E2E Workspace"
    }
    r = client.post("/auth/register", json=register_data)
    if r.status_code != 201:
        r = client.post("/auth/login", json={"email": test_email, "password": "securepassword123"})
    return r.json()["data"]["access_token"]


def test_e2e_grn_complex_flow():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get workspace ID
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    user_data = r.json()["data"]
    workspace_id = user_data["workspace_id"]
    
    # Create Entities
    r_supp = client.post(f"/api/v1/suppliers/?workspace_id={workspace_id}", json={"name": "SUP", "email": "sup@example.com", "currency": "AED", "supplier_code": "SUP1"}, headers=headers)
    supplier_id = r_supp.json()["data"]["id"]
    
    r_wh = client.post(f"/api/v1/inventory/warehouses/?workspace_id={workspace_id}", json={"name": "WH", "code": "WH1", "address": "123"}, headers=headers)
    warehouse_id = r_wh.json()["data"]["id"]
    
    # Create bin via API (endpoint now exists)
    r_bin = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        json={"code": "BIN1"},
        headers=headers,
    )
    assert r_bin.status_code in (200, 201), r_bin.json()
    
    r_uom = client.post(f"/api/v1/products/uom/?workspace_id={workspace_id}", json={"name": "UOM", "code": "UOM1"}, headers=headers)
    uom_id = r_uom.json()["data"]["id"]
    
    r_prod = client.post(f"/api/v1/products/?workspace_id={workspace_id}", json={"name": "PROD", "internal_sku": "PROD1", "type": "GOODS", "base_uom_id": uom_id}, headers=headers)
    product_id = r_prod.json()["data"]["id"]

    # 1. Create SPO (Qty 100)
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
                "line_number": 1
            }
        ]
    }
    
    r = client.post(f"/api/v1/spos/?workspace_id={workspace_id}", json=spo_data, headers=headers)
    assert r.status_code == 200, r.text
    spo_id = r.json()["id"]
    spo_item_id = r.json()["items"][0]["id"]
    
    # Submit, Approve, Send
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    
    # Acknowledge (Confirm all 100)
    ack_data = {
        "lines": {
            spo_item_id: {
                "quantity_confirmed": 100,
                "unit_price": 50.0
            }
        }
    }
    r = client.post(f"/api/v1/spos/{spo_id}/items/acknowledge", json=ack_data, headers=headers)
    assert r.json()["status"] == SPOStatus.ACKNOWLEDGED.value

    # 2. GRN TRANCHE 1
    grn_create_data = {
        "supplier_id": supplier_id,
        "spo_id": spo_id,
        "warehouse_id": warehouse_id,
        "received_date": "2026-08-20"
    }
    r_grn1 = client.post("/api/v1/grns", json=grn_create_data, headers=headers)
    assert r_grn1.status_code == 201, r_grn1.text
    grn1_id = r_grn1.json()["data"]["id"]
    
    client.post(f"/api/v1/grns/{grn1_id}/start-receiving", headers=headers)
    
    item_data = {
        "spo_item_id": spo_item_id,
        "product_id": product_id,
        "internal_sku": "PROD1",
        "description": "Widget A",
        "uom_id": uom_id,
        "quantity_received": 50
    }
    r_item1 = client.post(f"/api/v1/grns/{grn1_id}/items", json=item_data, headers=headers)
    grn1_item_id = r_item1.json()["data"]["items"][0]["id"]
    
    client.post(f"/api/v1/grns/{grn1_id}/stage-for-inspection", headers=headers)
    
    disp1 = {
        "quantity_accepted": 40,
        "quantity_damaged": 5,
        "quantity_rejected": 5,
        "damage_reason": "Scratched surfaces on 5 units",
        "rejection_reason": "Broken completely on 5 units"
    }
    r_disp1 = client.post(f"/api/v1/grns/{grn1_id}/items/{grn1_item_id}/disposition", json=disp1, headers=headers)
    assert r_disp1.status_code == 200, r_disp1.text
    
    # 3. GRN TRANCHE 2
    r_grn2 = client.post("/api/v1/grns", json=grn_create_data, headers=headers)
    grn2_id = r_grn2.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn2_id}/start-receiving", headers=headers)
    
    item_data["quantity_received"] = 50
    r_item2 = client.post(f"/api/v1/grns/{grn2_id}/items", json=item_data, headers=headers)
    grn2_item_id = r_item2.json()["data"]["items"][0]["id"]
    
    client.post(f"/api/v1/grns/{grn2_id}/stage-for-inspection", headers=headers)
    
    disp2 = {
        "quantity_accepted": 45,
        "quantity_damaged": 5,
        "quantity_rejected": 0,
        "damage_reason": "Slight bends on 5 units",
        "rejection_reason": ""
    }
    r_disp2 = client.post(f"/api/v1/grns/{grn2_id}/items/{grn2_item_id}/disposition", json=disp2, headers=headers)
    assert r_disp2.status_code == 200, r_disp2.text

    # 4. SPO Reconciliation Verify
    r_spo = client.get(f"/api/v1/spos/{spo_id}", headers=headers)
    assert r_spo.status_code == 200
    spo_item = r_spo.json()["items"][0]
    
    assert float(spo_item["quantity_received"]) == 100.0
    assert float(spo_item["quantity_accepted"]) == 85.0
    assert float(spo_item["quantity_damaged_rejected"]) == 15.0
