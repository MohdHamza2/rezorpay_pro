import pytest
import uuid
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_session
from app.config import get_settings
from app.models.supplier_invoice import SupplierInvoiceStatus, MatchResult
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
    test_email = f"match_e2e_{uuid.uuid4().hex[:8]}@example.com"
    register_data = {
        "email": test_email,
        "password": "securepassword123",
        "name": "Match E2E Tester",
        "workspace_name": "Match E2E Workspace"
    }
    r = client.post("/auth/register", json=register_data)
    if r.status_code != 201:
        r = client.post("/auth/login", json={"email": test_email, "password": "securepassword123"})
    return r.json()["data"]["access_token"]


def test_3way_match_engine():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    me_r = client.get("/auth/me", headers=headers)
    workspace_id = me_r.json()["data"]["workspace_id"]
    
    # 1. Create Supplier
    supplier_r = client.post("/api/v1/suppliers", headers=headers, json={
        "name": "Acme Corp",
        "supplier_code": "ACME-001",
        "email": "vendor@acme.com",
        "currency": "AED",
        "status": "ACTIVE"
    })
    assert supplier_r.status_code in (200, 201), supplier_r.json()
    supplier_id = supplier_r.json()["data"]["id"]

    # 3. Create UOM
    uom_r = client.post("/api/v1/products/uom", headers=headers, json={
        "name": "Pieces",
        "code": "PCS"
    })
    assert uom_r.status_code in (200, 201), uom_r.json()
    uom_id = uom_r.json()["data"]["id"]

    # 2. Create Product
    product_r = client.post("/api/v1/products", headers=headers, json={
        "name": "Widget X",
        "internal_sku": "WIDGET-X",
        "description": "A widget",
        "base_currency": "AED",
        "base_uom_id": uom_id
    })
    assert product_r.status_code in (200, 201), product_r.json()
    product_id = product_r.json()["data"]["id"]
    
    # 4. Create Warehouse
    warehouse_r = client.post("/api/v1/inventory/warehouses", headers=headers, json={
        "name": "Main Warehouse",
        "code": "MAIN-01",
        "address": "Dubai"
    })
    assert warehouse_r.status_code in (200, 201), warehouse_r.json()
    warehouse_id = warehouse_r.json()["data"]["id"]
    # Create bin via API (endpoint now exists)
    r_bin = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        json={"code": "BIN1"},
        headers=headers,
    )
    assert r_bin.status_code in (200, 201), r_bin.json()


    # 5. Create SPO
    spo_r = client.post(f"/api/v1/spos?workspace_id={workspace_id}", headers=headers, json={
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "procurement_method": "DIRECT",
        "currency": "AED",
        "expected_delivery_date": "2026-12-01T00:00:00Z",
        "items": [
            {
                "line_number": 1,
                "product_id": product_id,
                "description": "Widget X",
                "quantity_ordered": 1000,
                "uom_id": uom_id,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "vat_amount": 2500.0,
                "total_price": 52500.0,
                "currency": "AED"
            }
        ]
    })
    print("SPO:", spo_r.json())
    assert spo_r.status_code in (200, 201), spo_r.json()
    spo_id = spo_r.json().get("data", spo_r.json()).get("id", spo_r.json().get("id"))
    spo_item_id = spo_r.json().get("data", spo_r.json())["items"][0]["id"]
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    
    # Approve and Send SPO
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/acknowledge", headers=headers)

    # 6. Create GRN & Accept (We accepted 980, damaged 20)
    grn_r = client.post("/api/v1/grns", headers=headers, json={
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "procurement_method": "DIRECT",
        "delivery_reference": "DEL-123",
        "received_date": "2026-08-23T00:00:00Z",
        "spo_id": spo_id
    })
    assert grn_r.status_code in (200, 201), grn_r.json()
    grn_id = grn_r.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    
    # Add GRN Item (We received 1000)
    grn_item_r = client.post(f"/api/v1/grns/{grn_id}/items", headers=headers, json={
        "spo_item_id": spo_item_id,
        "line_number": 1,
                "product_id": product_id,
        "internal_sku": "WIDGET-X",
        "description": "Widget X",
        "uom_id": uom_id,
        "quantity_received": 1000
    })
    assert grn_item_r.status_code in (200, 201), grn_item_r.json()
    grn_item_id = grn_item_r.json().get("data", grn_item_r.json())["items"][0]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)
    disp1 = {"quantity_accepted": 980, "quantity_damaged": 20, "quantity_rejected": 0, "damage_reason": "Bent surfaces on 20 units"}
    disp_r = client.post(f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition", json=disp1, headers=headers)
    assert disp_r.status_code == 200, disp_r.json()
    
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)
    
    
    
    # Disposition: 980 Accepted, 20 Damaged
    client.post(f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition", headers=headers, json={
        "quantity_accepted": 980,
        "quantity_damaged": 20,
        "quantity_rejected": 0,
        "damage_reason": "Broken in transit"
    })
    
    # 7. Create Supplier Invoice (Supplier bills for 1000 at 50 AED)
    inv_r = client.post("/api/v1/supplier-invoices", headers=headers, json={
        "supplier_id": supplier_id,
        "supplier_invoice_number": "INV-10025",
        "invoice_date": "2026-08-23T00:00:00Z",
        "due_date": "2026-09-23T00:00:00Z",
        "currency": "AED",
        "subtotal": 50000.0,
        "discount_amount": 0,
        "vat_amount": 2500.0,
        "total_amount": 52500.0,
        "primary_spo_id": spo_id,
        "items": [
            {
                "spo_item_id": spo_item_id,
                "grn_item_id": grn_item_id,
                "line_number": 1,
                "product_id": product_id,
                "description": "Widget X",
                "quantity": 1000,
                "uom_id": uom_id,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "vat_amount": 2500.0,
                "total_price": 52500.0,
                "currency": "AED"
            }
        ]
    })
    assert inv_r.status_code in (200, 201), inv_r.json()
    inv_id = inv_r.json()["data"]["id"]
    
    # 8. Submit Matching - Should Fail on Qty (1000 billed > 980 accepted)
    match_r = client.post(f"/api/v1/supplier-invoices/{inv_id}/submit-matching", headers=headers)
    assert match_r.status_code == 200
    matched_inv = match_r.json()["data"]
    
    assert matched_inv["status"] == "DISCREPANCY"
    assert matched_inv["three_way_match_status"] == "FAILED_QTY"
    assert float(matched_inv["items"][0]["variance_quantity"]) == 20.0
    
    # 9. Try to approve directly - Should be blocked by INV-6.1
    approve_fail = client.post(f"/api/v1/supplier-invoices/{inv_id}/approve", headers=headers)
    assert approve_fail.status_code == 400
    assert "Only MATCHED invoices" in approve_fail.json()["error"]["message"]
    
    # 10. Authorized Override
    resolve_r = client.post(f"/api/v1/supplier-invoices/{inv_id}/resolve-discrepancy", headers=headers, json={
        "notes": "Approved paying full invoice, supplier is sending replacement 20 next week."
    })
    assert resolve_r.status_code == 200
    resolved_inv = resolve_r.json()["data"]
    
    assert resolved_inv["status"] == "APPROVED"
    assert resolved_inv["three_way_match_notes"] == "Approved paying full invoice, supplier is sending replacement 20 next week."
    print("E2E 3-Way Match Test Passed!")

