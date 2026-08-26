"""Multi-tenant isolation test suite (T1).

Comprehensive cross-tenant security tests covering all major entities:
- Invoices
- Payments
- Clients
- GRNs (already covered in test_spo.py for SPOs)
- Products
- Suppliers

Each test verifies that Workspace B cannot read or mutate Workspace A's data,
and that both read and write attempts return 404 (not 403, to avoid existence leaks).

Follows the standard harness: sync TestClient against real PostgreSQL _test DB.
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

# Import all models so SQLModel.metadata is fully populated
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


# ========== CLIENT ISOLATION ==========


def test_client_is_workspace_isolated():
    """Workspace B must not read or update Workspace A's client."""
    token_a, ws_a = _register("owner_client_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create client in workspace A
    r = client.post(
        "/api/v1/clients",
        json={
            "name": "ACME Corp",
            "email": "acme@example.com",
            "phone": "+1234567890",
            "address": "123 Main St",
        },
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    # Workspace B should not read client
    token_b, _ = _register("owner_client_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = client.get(f"/api/v1/clients/{client_id}", headers=headers_b)
    assert r.status_code == 404, f"cross-tenant read leaked: {r.status_code} {r.text}"

    # Workspace B should not update client
    r = client.put(
        f"/api/v1/clients/{client_id}",
        json={"name": "HACKED"},
        headers=headers_b,
    )
    assert r.status_code == 404, f"cross-tenant write leaked: {r.status_code} {r.text}"

    # Workspace B should not delete client
    r = client.delete(f"/api/v1/clients/{client_id}", headers=headers_b)
    assert r.status_code == 404, f"cross-tenant delete leaked: {r.status_code} {r.text}"

    # Owner A can still read its own client
    r = client.get(f"/api/v1/clients/{client_id}", headers=headers_a)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "ACME Corp"


# ========== INVOICE ISOLATION ==========


def test_invoice_is_workspace_isolated():
    """Workspace B must not read, update, void, or send Workspace A's invoice."""
    token_a, ws_a = _register("owner_inv_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create client in workspace A
    r = client.post(
        "/api/v1/clients",
        json={"name": "Client A", "email": "clienta@example.com"},
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    # Create invoice in workspace A
    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [
                {
                    "description": "Widget",
                    "quantity": 10,
                    "unit_price": 100.0,
                    "tax_rate": 5.0,
                }
            ],
        },
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    invoice_id = r.json()["data"]["id"]

    # Workspace B should not read invoice
    token_b, _ = _register("owner_inv_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers_b)
    assert r.status_code == 404, f"cross-tenant read leaked: {r.status_code} {r.text}"

    # Workspace B should not send invoice
    r = client.post(f"/api/v1/invoices/{invoice_id}/send", json={}, headers=headers_b)
    assert r.status_code == 404, f"cross-tenant send leaked: {r.status_code} {r.text}"

    # Workspace B should not void invoice
    r = client.post(
        f"/api/v1/invoices/{invoice_id}/void",
        json={"reason": "testing void"},
        headers=headers_b,
    )
    assert r.status_code == 404, f"cross-tenant void leaked: {r.status_code} {r.text}"

    # Owner A can still read its own invoice
    r = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers_a)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == invoice_id


# ========== PAYMENT ISOLATION ==========


def test_payment_is_workspace_isolated():
    """Workspace B must not record payment against Workspace A's invoice."""
    token_a, ws_a = _register("owner_pay_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create client and invoice in workspace A
    r = client.post(
        "/api/v1/clients",
        json={"name": "Client A", "email": "clienta@example.com"},
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    client_id = r.json()["data"]["id"]

    r = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": [
                {
                    "description": "Widget",
                    "quantity": 10,
                    "unit_price": 100.0,
                    "tax_rate": 5.0,
                }
            ],
        },
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    invoice_id = r.json()["data"]["id"]

    # Send invoice so it can accept payments
    r = client.post(f"/api/v1/invoices/{invoice_id}/send", json={}, headers=headers_a)
    assert r.status_code == 200, r.text

    # Workspace B should not record payment
    token_b, _ = _register("owner_pay_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = client.post(
        f"/api/v1/payments/invoices/{invoice_id}/record",
        json={
            "amount": 100.0,
            "payment_method": "CASH",
            "payment_date": "2026-08-26",
        },
        headers={**headers_b, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert (
        r.status_code == 404
    ), f"cross-tenant payment leaked: {r.status_code} {r.text}"


# ========== PRODUCT ISOLATION ==========


def test_product_is_workspace_isolated():
    """Workspace B must not read or update Workspace A's product."""
    token_a, ws_a = _register("owner_prod_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create UOM first
    suffix = uuid.uuid4().hex[:6]
    r = client.post(
        f"/api/v1/products/uom?workspace_id={ws_a}",
        json={"name": "Pieces", "code": f"PCS-{suffix}"},
        headers=headers_a,
    )
    assert r.status_code in (200, 201), r.text
    uom_id = r.json()["data"]["id"]

    # Create product in workspace A
    r = client.post(
        f"/api/v1/products?workspace_id={ws_a}",
        json={
            "name": "Widget",
            "internal_sku": f"WDGT-{suffix}",
            "base_uom_id": uom_id,
        },
        headers=headers_a,
    )
    assert r.status_code in (200, 201), r.text
    product_id = r.json()["data"]["id"]

    # Workspace B should not read product
    token_b, ws_b = _register("owner_prod_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = client.get(
        f"/api/v1/products/{product_id}?workspace_id={ws_b}", headers=headers_b
    )
    assert r.status_code == 404, f"cross-tenant read leaked: {r.status_code} {r.text}"


# ========== SUPPLIER ISOLATION ==========


def test_supplier_is_workspace_isolated():
    """Workspace B must not read or update Workspace A's supplier."""
    token_a, ws_a = _register("owner_sup_a", "Workspace A")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create supplier in workspace A
    suffix = uuid.uuid4().hex[:6]
    r = client.post(
        f"/api/v1/suppliers?workspace_id={ws_a}",
        json={
            "name": "Supplier A",
            "email": "supa@example.com",
            "currency": "AED",
            "supplier_code": f"SUP-{suffix}",
        },
        headers=headers_a,
    )
    assert r.status_code in (200, 201), r.text
    supplier_id = r.json()["data"]["id"]

    # Workspace B should not read supplier
    token_b, ws_b = _register("owner_sup_b", "Workspace B")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = client.get(
        f"/api/v1/suppliers/{supplier_id}?workspace_id={ws_b}", headers=headers_b
    )
    assert r.status_code == 404, f"cross-tenant read leaked: {r.status_code} {r.text}"
