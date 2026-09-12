"""Wave 31 Item 2.1 — D-22 landed cost allocation tests.

Locked architecture: `architecture/wave-landed-cost-addendum.md`.
Covers:
- DRAFT allocation creation on GRN item add (per-line 2dp, MANUAL factor gate)
- Inline items + landed cost on POST /grns (§7.1)
- Capitalization at disposition for accepted quantities only (D-22-01/02)
- Idempotency: no duplicate capitalization, uq_landed_cost_source enforced (D-22-06)
- Supplier invoice matching is validation-only, never auto-capitalizes (D-22-03)
- Landed cost never touches balance_due (D-22-07)
- AP aging landed cost aggregates
- Workspace isolation
"""

import asyncio
import sys
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.landed_cost import LandedCostAllocation, LandedCostStatus

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

    asyncio.run(_setup())
    yield

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_teardown())


def _auth():
    email = f"lc_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "Landed Cost Tester",
            "workspace_name": "LC Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login", json={"email": email, "password": "securepassword123"}
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["data"]["workspace_id"]


def _base_entities(headers, workspace_id, tag):
    """Create supplier/warehouse/bin/uom/product. Returns ids dict."""
    r = client.post(
        f"/api/v1/suppliers/?workspace_id={workspace_id}",
        headers=headers,
        json={
            "name": f"LC-SUP-{tag}",
            "email": f"lc-{tag}@example.com",
            "currency": "AED",
            "supplier_code": f"LC-{tag}",
        },
    )
    assert r.status_code in (200, 201), r.text
    supplier_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses/?workspace_id={workspace_id}",
        headers=headers,
        json={"name": f"LC-WH-{tag}", "code": f"LCWH-{tag}", "address": "Dubai"},
    )
    assert r.status_code in (200, 201), r.text
    warehouse_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        headers=headers,
        json={"code": f"LCBIN-{tag}"},
    )
    assert r.status_code in (200, 201), r.text

    r = client.post(
        f"/api/v1/products/uom/?workspace_id={workspace_id}",
        headers=headers,
        json={"name": "Pieces", "code": f"LCU-{tag}"},
    )
    assert r.status_code in (200, 201), r.text
    uom_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/?workspace_id={workspace_id}",
        headers=headers,
        json={
            "name": f"LC-PROD-{tag}",
            "internal_sku": f"LC-SKU-{tag}",
            "base_uom_id": uom_id,
        },
    )
    assert r.status_code in (200, 201), r.text
    product_id = r.json()["data"]["id"]
    return {
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "uom_id": uom_id,
        "product_id": product_id,
    }


def _spo(headers, workspace_id, ids, lines):
    """Create + approve + send + acknowledge an SPO. Returns (spo_id, spo_item_ids)."""
    r = client.post(
        f"/api/v1/spos/?workspace_id={workspace_id}",
        headers=headers,
        json={
            "supplier_id": ids["supplier_id"],
            "warehouse_id": ids["warehouse_id"],
            "procurement_method": "DIRECT",
            "currency": "AED",
            "items": lines,
        },
    )
    assert r.status_code in (200, 201), r.text
    spo_id = r.json()["data"]["id"]
    spo_item_ids = [it["id"] for it in r.json()["data"]["items"]]
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    ack = {
        "lines": {
            sid: {
                "quantity_confirmed": ln["quantity_ordered"],
                "unit_price": ln["unit_price"],
            }
            for sid, ln in zip(spo_item_ids, lines)
        }
    }
    r = client.post(
        f"/api/v1/spos/{spo_id}/items/acknowledge", json=ack, headers=headers
    )
    assert r.status_code in (200, 201), r.text
    return spo_id, spo_item_ids


def _grn_with_item(headers, ids, spo_id, spo_item_id, qty, lc_items=None):
    """Create GRN, receive, add one item (optionally with landed cost)."""
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
        "internal_sku": "LC-SKU",
        "description": "LC Widget",
        "uom_id": ids["uom_id"],
        "quantity_received": qty,
    }
    if lc_items is not None:
        payload["landed_cost_items"] = lc_items
    r = client.post(f"/api/v1/grns/{grn_id}/items", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    grn_item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)
    return grn_id, grn_item_id


def _allocations(grn_item_id):
    async def _fetch():
        async with TestingSessionLocal() as session:
            result = await session.execute(
                select(LandedCostAllocation).where(
                    LandedCostAllocation.grn_item_id == uuid.UUID(str(grn_item_id))
                )
            )
            rows = result.scalars().all()
            return [
                {
                    "component_type": r.component_type,
                    "amount": r.amount,
                    "currency": r.currency,
                    "allocation_basis": r.allocation_basis,
                    "allocation_factor": r.allocation_factor,
                    "status": r.status,
                    "workspace_id": r.workspace_id,
                    "source_document_type": r.source_document_type,
                    "source_document_id": r.source_document_id,
                    "source_line_id": r.source_line_id,
                    "capitalized_at": r.capitalized_at,
                }
                for r in rows
            ]

    return asyncio.run(_fetch())


def _disposition(headers, grn_id, grn_item_id, accepted, damaged, rejected):
    payload = {
        "quantity_accepted": accepted,
        "quantity_damaged": damaged,
        "quantity_rejected": rejected,
    }
    if damaged:
        payload["damage_reason"] = "Damaged in transit, scratched units"
    if rejected:
        payload["rejection_reason"] = "Rejected: broken beyond repair use"
    return client.post(
        f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition",
        json=payload,
        headers=headers,
    )


def test_create_item_with_landed_cost_creates_draft_rows_2dp():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T1")
    spo_id, (spo_item_id,) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "LC Widget",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 100,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    )
    grn_id, grn_item_id = _grn_with_item(
        headers,
        ids,
        spo_id,
        spo_item_id,
        100,
        lc_items=[
            {
                "component_type": "FREIGHT",
                "amount": "5000.00",
                "allocation_basis": "QUANTITY",
            },
            {
                "component_type": "CUSTOMS",
                "amount": "1000.006",
                "allocation_basis": "VALUE",
            },
        ],
    )
    rows = _allocations(grn_item_id)
    assert len(rows) == 2
    by_comp = {r["component_type"]: r for r in rows}
    assert by_comp["FREIGHT"]["amount"] == Decimal("5000.00")
    assert by_comp["CUSTOMS"]["amount"] == Decimal("1000.01")  # per-line 2dp
    for r in rows:
        assert r["status"] == LandedCostStatus.DRAFT
        assert r["currency"] == "AED"
        assert str(r["workspace_id"]) == workspace_id
        assert r["source_document_type"] == "GRN"
        assert str(r["source_document_id"]) == grn_id
        assert r["source_line_id"] is not None
        assert r["capitalized_at"] is None
    assert by_comp["FREIGHT"]["source_line_id"] != by_comp["CUSTOMS"]["source_line_id"]


def test_manual_basis_requires_factor():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T2")
    spo_id, (spo_item_id,) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "LC Widget",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 10,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    )
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
    grn_id = r.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    r = client.post(
        f"/api/v1/grns/{grn_id}/items",
        headers=headers,
        json={
            "spo_item_id": spo_item_id,
            "product_id": ids["product_id"],
            "internal_sku": "LC-SKU",
            "description": "LC Widget",
            "uom_id": ids["uom_id"],
            "quantity_received": 10,
            "landed_cost_items": [
                {
                    "component_type": "HANDLING",
                    "amount": "100.00",
                    "allocation_basis": "MANUAL",
                }
            ],
        },
    )
    assert r.status_code == 422, r.text


def test_disposition_capitalizes_accepted_only():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T3")
    spo_id, (spo_a, spo_b) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "Line A",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 60,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            },
            {
                "product_id": ids["product_id"],
                "description": "Line B",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 40,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 2,
            },
        ],
    )
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
    grn_id = r.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    r = client.post(
        f"/api/v1/grns/{grn_id}/items",
        headers=headers,
        json={
            "spo_item_id": spo_a,
            "product_id": ids["product_id"],
            "internal_sku": "LC-SKU",
            "description": "Line A",
            "uom_id": ids["uom_id"],
            "quantity_received": 60,
            "landed_cost_items": [
                {
                    "component_type": "FREIGHT",
                    "amount": "2000.00",
                    "allocation_basis": "QUANTITY",
                }
            ],
        },
    )
    item_a = r.json()["data"]["items"][0]["id"]
    r = client.post(
        f"/api/v1/grns/{grn_id}/items",
        headers=headers,
        json={
            "spo_item_id": spo_b,
            "product_id": ids["product_id"],
            "internal_sku": "LC-SKU",
            "description": "Line B",
            "uom_id": ids["uom_id"],
            "quantity_received": 40,
        },
    )
    item_b = [it for it in r.json()["data"]["items"] if it["id"] != item_a][0]["id"]
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)

    r = _disposition(headers, grn_id, item_a, 50, 5, 5)
    assert r.status_code == 200, r.text
    rows = {it["id"]: it for it in r.json()["data"]["items"]}
    assert float(rows[item_a]["landed_cost_allocated"]) == 2000.00
    assert float(rows[item_a]["landed_cost_per_unit"]) == 40.00

    r = _disposition(headers, grn_id, item_b, 0, 0, 40)
    assert r.status_code == 200, r.text
    rows = {it["id"]: it for it in r.json()["data"]["items"]}
    assert float(rows[item_b]["landed_cost_allocated"]) == 0.00
    assert r.json()["data"]["status"] == "PARTIALLY_ACCEPTED"

    allocs_a = _allocations(item_a)
    assert len(allocs_a) == 1
    assert allocs_a[0]["status"] == LandedCostStatus.CAPITALIZED
    assert allocs_a[0]["capitalized_at"] is not None
    assert _allocations(item_b) == []


def test_no_double_capitalization_and_unique_source():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T4")
    spo_id, (spo_item_id,) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "LC Widget",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 20,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    )
    grn_id, grn_item_id = _grn_with_item(
        headers,
        ids,
        spo_id,
        spo_item_id,
        20,
        lc_items=[{"component_type": "INSURANCE", "amount": "400.00"}],
    )
    r = _disposition(headers, grn_id, grn_item_id, 20, 0, 0)
    assert r.status_code == 200, r.text
    assert len(_allocations(grn_item_id)) == 1

    # Second disposition attempt is rejected by the status guard: no reprocessing.
    r = _disposition(headers, grn_id, grn_item_id, 20, 0, 0)
    assert r.status_code == 400, r.text
    assert len(_allocations(grn_item_id)) == 1

    # The idempotency constraint rejects an exact source duplicate.
    async def _duplicate():
        async with TestingSessionLocal() as session:
            existing = (
                (
                    await session.execute(
                        select(LandedCostAllocation).where(
                            LandedCostAllocation.grn_item_id
                            == uuid.UUID(str(grn_item_id))
                        )
                    )
                )
                .scalars()
                .first()
            )
            dup = LandedCostAllocation(
                workspace_id=existing.workspace_id,
                grn_id=existing.grn_id,
                grn_item_id=existing.grn_item_id,
                spo_item_id=existing.spo_item_id,
                component_type="FREIGHT",
                amount=Decimal("1.00"),
                currency="AED",
                allocation_basis="QUANTITY",
                allocation_factor=Decimal("1.0"),
                source_document_type=existing.source_document_type,
                source_document_id=existing.source_document_id,
                source_line_id=existing.source_line_id,
                status=LandedCostStatus.DRAFT,
                created_by=existing.created_by,
            )
            session.add(dup)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return True
            return False

    assert asyncio.run(_duplicate()) is True
    assert len(_allocations(grn_item_id)) == 1


def _supplier_invoice(
    headers, ids, spo_id, spo_item_id, grn_item_id, number, qty, total
):
    r = client.post(
        "/api/v1/supplier-invoices",
        headers=headers,
        json={
            "supplier_id": ids["supplier_id"],
            "supplier_invoice_number": number,
            "invoice_date": "2026-08-23T00:00:00Z",
            "due_date": "2026-09-23T00:00:00Z",
            "currency": "AED",
            "subtotal": 5000.0,
            "discount_amount": 0,
            "vat_amount": 250.0,
            "total_amount": total,
            "primary_spo_id": spo_id,
            "items": [
                {
                    "spo_item_id": spo_item_id,
                    "grn_item_id": grn_item_id,
                    "product_id": ids["product_id"],
                    "description": "LC Widget",
                    "quantity": qty,
                    "uom_id": ids["uom_id"],
                    "unit_price": 50.0,
                    "vat_rate": 5.0,
                    "vat_amount": 250.0,
                    "total_price": total,
                    "currency": "AED",
                }
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_supplier_matching_validates_without_capitalizing():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T5")
    spo_id, (spo_item_id,) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "LC Widget",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 100,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    )
    # Landed cost 50000 over 100 accepted units = 500/unit.
    grn_id, grn_item_id = _grn_with_item(
        headers,
        ids,
        spo_id,
        spo_item_id,
        100,
        lc_items=[{"component_type": "FREIGHT", "amount": "50000.00"}],
    )
    r = _disposition(headers, grn_id, grn_item_id, 100, 0, 0)
    assert r.status_code == 200, r.text

    # Invoice WITHOUT landed cost fails price validation...
    inv_nolc = _supplier_invoice(
        headers, ids, spo_id, spo_item_id, grn_item_id, "LC-INV-NOLC", 100, 52500.0
    )
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_nolc}/submit-matching", headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "DISCREPANCY"
    assert data["three_way_match_status"] == "FAILED_PRICE"
    # ...but validation never touches money or allocations.
    assert float(data["balance_due"]) == 52500.0
    assert len(_allocations(grn_item_id)) == 1
    assert _allocations(grn_item_id)[0]["status"] == LandedCostStatus.CAPITALIZED

    # Invoice WITH landed cost passes and still capitalizes nothing new.
    inv_lc = _supplier_invoice(
        headers, ids, spo_id, spo_item_id, grn_item_id, "LC-INV-WITHLC", 100, 102500.0
    )
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_lc}/submit-matching", headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["three_way_match_status"] == "PASSED", data
    assert data["status"] == "MATCHED"
    assert float(data["balance_due"]) == 102500.0
    assert len(_allocations(grn_item_id)) == 1

    # Approve the matched invoice, then check AP aging landed cost aggregates.
    r = client.post(f"/api/v1/supplier-invoices/{inv_lc}/approve", headers=headers)
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/ap-aging/detail", headers=headers)
    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    row = next(x for x in payload["invoices"] if x["supplier_invoice_id"] == inv_lc)
    assert row["landed_cost_outstanding_count"] == 1
    assert float(row["landed_cost_outstanding_amount"]) == 50000.0
    assert float(payload["landed_cost_outstanding_amount"]) == 50000.0
    # Landed cost is operational only: outstanding still equals balance_due.
    assert float(payload["total_outstanding"]) == 102500.0


def test_grn_create_with_inline_items_and_landed_cost():
    token, workspace_id = _auth()
    headers = {"Authorization": f"Bearer {token}"}
    ids = _base_entities(headers, workspace_id, "T6")
    spo_id, (spo_item_id,) = _spo(
        headers,
        workspace_id,
        ids,
        [
            {
                "product_id": ids["product_id"],
                "description": "LC Widget",
                "uom_id": ids["uom_id"],
                "quantity_ordered": 30,
                "unit_price": 50.0,
                "vat_rate": 5.0,
                "line_number": 1,
            }
        ],
    )
    r = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": ids["supplier_id"],
            "spo_id": spo_id,
            "warehouse_id": ids["warehouse_id"],
            "received_date": "2026-08-20",
            "items": [
                {
                    "spo_item_id": spo_item_id,
                    "product_id": ids["product_id"],
                    "internal_sku": "LC-SKU",
                    "description": "LC Widget",
                    "uom_id": ids["uom_id"],
                    "quantity_received": 30,
                    "landed_cost_items": [
                        {
                            "component_type": "BROKERAGE",
                            "amount": "300.00",
                            "allocation_basis": "MANUAL",
                            "allocation_factor": "0.5",
                        }
                    ],
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    rows = _allocations(items[0]["id"])
    assert len(rows) == 1
    assert rows[0]["component_type"] == "BROKERAGE"
    assert rows[0]["amount"] == Decimal("300.00")
    assert rows[0]["allocation_basis"] == "MANUAL"
    assert rows[0]["allocation_factor"] == Decimal("0.5")
    assert rows[0]["status"] == LandedCostStatus.DRAFT


def test_workspace_isolation():
    _auth()  # workspace A (may hold landed cost from other tests in this module)
    token_b, _ = _auth()  # fresh workspace B
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get("/api/v1/ap-aging", headers=headers_b)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data.get("landed_cost_outstanding_amount", 0.0)) == 0.0
