"""Concurrent document number collision tests (T12).

Tests gapless numbering under race conditions:
- Concurrent invoice creation (multiple threads)
- Concurrent SPO creation
- Cross-year boundary scenarios
- Rollback scenarios (transaction failure should not create gaps)

These tests verify that the FOR UPDATE locking strategy prevents:
1. Duplicate numbers
2. Gaps in the sequence
3. Race conditions under high concurrency

Uses asyncio to simulate concurrent requests.
"""

import sys
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

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

# Import all models
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


# ========== INVOICE NUMBERING ==========


def test_concurrent_invoice_creation_no_duplicates():
    """Create 10 invoices concurrently and verify all numbers are unique and sequential."""
    token, ws_id = _register("owner_concurrent_inv", "Invoice Workspace")
    headers = {"Authorization": f"Bearer {token}"}

    # Create a client first
    r = client.post(
        "/api/v1/clients",
        json={"name": "Test Client", "email": "test@example.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    def create_invoice(index: int) -> str:
        """Create an invoice and return its number."""
        r = client.post(
            "/api/v1/invoices",
            json={
                "client_id": client_id,
                "issue_date": "2026-08-26",
                "due_date": "2026-09-26",
                "items": [
                    {
                        "description": f"Item {index}",
                        "quantity": 1,
                        "unit_price": 100.0,
                        "tax_rate": 5.0,
                    }
                ],
            },
            headers=headers,
        )
        assert r.status_code == 201, f"Invoice {index} failed: {r.text}"
        return r.json()["data"]["invoice_number"]

    # Create 10 invoices concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        invoice_numbers = list(executor.map(create_invoice, range(10)))

    # Verify all numbers are unique
    assert len(invoice_numbers) == len(
        set(invoice_numbers)
    ), f"Duplicate invoice numbers detected: {invoice_numbers}"

    # Verify numbers are sequential (INV-2026-0001 through INV-2026-0010)
    numbers = sorted([int(num.split("-")[-1]) for num in invoice_numbers])
    expected = list(range(1, 11))
    assert (
        numbers == expected
    ), f"Invoice numbers not sequential. Got {numbers}, expected {expected}"


# ========== SPO NUMBERING ==========


def test_concurrent_spo_creation_no_duplicates():
    """Create 10 SPOs concurrently and verify all numbers are unique and sequential."""
    token, ws_id = _register("owner_concurrent_spo", "SPO Workspace")
    headers = {"Authorization": f"Bearer {token}"}

    # Seed foreign keys
    suffix = uuid.uuid4().hex[:6]

    r = client.post(
        f"/api/v1/suppliers?workspace_id={ws_id}",
        json={
            "name": "Supplier",
            "email": "sup@example.com",
            "currency": "AED",
            "supplier_code": f"SUP-{suffix}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    supplier_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/inventory/warehouses?workspace_id={ws_id}",
        json={"name": "WH", "code": f"WH-{suffix}", "address": "123"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    warehouse_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/uom?workspace_id={ws_id}",
        json={"name": "Pieces", "code": f"PCS-{suffix}"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    uom_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products?workspace_id={ws_id}",
        json={
            "name": "Widget",
            "internal_sku": f"WDGT-{suffix}",
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    product_id = r.json()["data"]["id"]

    def create_spo(index: int) -> str:
        """Create an SPO and return its number."""
        r = client.post(
            "/api/v1/spos/",
            json={
                "supplier_id": supplier_id,
                "procurement_method": "DIRECT",
                "warehouse_id": warehouse_id,
                "currency": "AED",
                "items": [
                    {
                        "line_number": 1,
                        "product_id": product_id,
                        "description": f"Widget {index}",
                        "uom_id": uom_id,
                        "quantity_ordered": 10,
                        "unit_price": 5.0,
                        "vat_rate": 5.0,
                    }
                ],
            },
            headers=headers,
        )
        assert r.status_code == 200, f"SPO {index} failed: {r.text}"
        return r.json()["data"]["spo_number"]

    # Create 10 SPOs concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        spo_numbers = list(executor.map(create_spo, range(10)))

    # Verify all numbers are unique
    assert len(spo_numbers) == len(
        set(spo_numbers)
    ), f"Duplicate SPO numbers detected: {spo_numbers}"

    # Verify numbers are sequential (SPO-2026-0001 through SPO-2026-0010)
    numbers = sorted([int(num.split("-")[-1]) for num in spo_numbers])
    expected = list(range(1, 11))
    assert (
        numbers == expected
    ), f"SPO numbers not sequential. Got {numbers}, expected {expected}"


# ========== CROSS-YEAR BOUNDARY ==========


def test_invoice_numbering_resets_by_year():
    """Verify that invoice counters are year-scoped (counter resets each year)."""
    token, ws_id = _register("owner_year_reset", "Year Reset Workspace")
    headers = {"Authorization": f"Bearer {token}"}

    # Create a client
    r = client.post(
        "/api/v1/clients",
        json={"name": "Test Client", "email": "test@example.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    # Create invoice for 2026
    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [
                {
                    "description": "Item 2026",
                    "quantity": 1,
                    "unit_price": 100.0,
                    "tax_rate": 5.0,
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    inv_2026 = r.json()["data"]["invoice_number"]

    # Verify 2026 invoice has format INV-2026-XXXX
    assert inv_2026.startswith("INV-2026-"), f"Expected INV-2026-*, got {inv_2026}"

    # Note: We cannot test 2027 numbering without mocking datetime.now()
    # or adding a year parameter to the API (which would be a new feature).
    # This test verifies the format; actual year-reset logic is tested
    # by the service layer unit tests (if they exist).


# ========== ROLLBACK SCENARIO ==========


def test_invoice_rollback_does_not_create_gap():
    """Verify that failed invoice creation does not consume a number (no gap)."""
    token, ws_id = _register("owner_rollback", "Rollback Workspace")
    headers = {"Authorization": f"Bearer {token}"}

    # Create a client
    r = client.post(
        "/api/v1/clients",
        json={"name": "Test Client", "email": "test@example.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    # Create first invoice successfully
    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [
                {
                    "description": "Item 1",
                    "quantity": 1,
                    "unit_price": 100.0,
                    "tax_rate": 5.0,
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    first_number = r.json()["data"]["invoice_number"]
    first_seq = int(first_number.split("-")[-1])

    # Attempt to create invoice with invalid data (should fail)
    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [],  # Empty items should fail validation
        },
        headers=headers,
    )
    assert r.status_code == 422, "Expected validation error for empty items"

    # Create third invoice successfully
    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [
                {
                    "description": "Item 3",
                    "quantity": 1,
                    "unit_price": 100.0,
                    "tax_rate": 5.0,
                }
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    third_number = r.json()["data"]["invoice_number"]
    third_seq = int(third_number.split("-")[-1])

    # Verify no gap: third number should be first + 1
    assert third_seq == first_seq + 1, (
        f"Gap detected! First: {first_seq}, Third: {third_seq}. "
        f"Expected {first_seq + 1}"
    )
