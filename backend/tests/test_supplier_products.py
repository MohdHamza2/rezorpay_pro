"""Wave 31 Item 2.4 — SupplierProduct link CRUD tests.

Covers: create happy path + response shape, duplicate → 409, foreign
supplier/product → 404, soft-deleted supplier/product → 404, blank and
whitespace supplier_sku → 422, negative lead_time_days / moq → 422,
list scoping (supplier + workspace), delete happy path + 404s, link
creation independent of supplier status (ACTIVE/INACTIVE/HOLD), and
product detail retrieval unaffected by links.

Follows the suite's standard harness: sync ``TestClient`` against a real
PostgreSQL ``_test`` database, module-scoped schema create/drop.
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


def _supplier(headers, workspace_id, tag):
    suffix = uuid.uuid4().hex[:6]
    r = client.post(
        f"/api/v1/suppliers/?workspace_id={workspace_id}",
        json={
            "name": f"SUP-{tag}",
            "email": f"sup-{tag}-{suffix}@example.com",
            "currency": "AED",
            "supplier_code": f"SUP-{tag}-{suffix}",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), f"supplier: {r.text}"
    return r.json()["data"]["id"]


def _product(headers, workspace_id, tag):
    suffix = uuid.uuid4().hex[:6]
    q = f"?workspace_id={workspace_id}"
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
    return r.json()["data"]["id"]


def _link(headers, supplier_id, body):
    return client.post(
        f"/api/v1/suppliers/{supplier_id}/products", json=body, headers=headers
    )


def _set_supplier_status(supplier_id, status_value):
    async def _update():
        async with TestingSessionLocal() as session:
            from app.models.supplier import Supplier

            row = await session.get(Supplier, uuid.UUID(str(supplier_id)))
            row.status = status_value
            await session.commit()

    asyncio.run(_update())


def _soft_delete(model_name, row_id):
    async def _update():
        async with TestingSessionLocal() as session:
            from datetime import datetime, timezone

            if model_name == "supplier":
                from app.models.supplier import Supplier as Model
            else:
                from app.models.product import Product as Model

            row = await session.get(Model, uuid.UUID(str(row_id)))
            row.deleted_at = datetime.now(timezone.utc)
            await session.commit()

    asyncio.run(_update())


def test_create_happy_path_and_shape():
    token, ws = _register("splink")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C1")
    product_id = _product(headers, ws, "C1")

    r = _link(
        headers,
        supplier_id,
        {
            "product_id": product_id,
            "supplier_sku": "ACME-W-001",
            "lead_time_days": 7,
            "moq": "10.00",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["id"]
    assert data["workspace_id"] == ws
    assert data["supplier_id"] == supplier_id
    assert data["product_id"] == product_id
    assert data["supplier_sku"] == "ACME-W-001"
    assert data["lead_time_days"] == 7
    assert float(data["moq"]) == 10.00
    assert data["created_at"]


def test_create_minimal_body_preserves_nulls():
    token, ws = _register("splinkmin")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C2")
    product_id = _product(headers, ws, "C2")

    r = _link(headers, supplier_id, {"product_id": product_id})
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["supplier_sku"] is None
    assert data["lead_time_days"] is None
    assert data["moq"] is None


def test_duplicate_link_conflicts():
    token, ws = _register("spdup")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C3")
    product_id = _product(headers, ws, "C3")
    body = {"product_id": product_id, "supplier_sku": "DUP-1"}

    r = _link(headers, supplier_id, body)
    assert r.status_code == 201, r.text
    r = _link(headers, supplier_id, body)
    assert r.status_code == 409, r.text


def test_foreign_supplier_or_product_404():
    token, ws = _register("spforeign")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C4")
    product_id = _product(headers, ws, "C4")

    r = _link(headers, str(uuid.uuid4()), {"product_id": product_id})
    assert r.status_code == 404, r.text

    r = _link(headers, supplier_id, {"product_id": str(uuid.uuid4())})
    assert r.status_code == 404, r.text


def test_soft_deleted_supplier_or_product_404():
    token, ws = _register("spdeleted")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C5")
    product_id = _product(headers, ws, "C5")

    _soft_delete("supplier", supplier_id)
    r = _link(headers, supplier_id, {"product_id": product_id})
    assert r.status_code == 404, r.text

    supplier_id = _supplier(headers, ws, "C5b")
    _soft_delete("product", product_id)
    r = _link(headers, supplier_id, {"product_id": product_id})
    assert r.status_code == 404, r.text


def test_blank_and_whitespace_sku_422():
    token, ws = _register("spsku")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C6")
    product_id = _product(headers, ws, "C6")

    r = _link(headers, supplier_id, {"product_id": product_id, "supplier_sku": ""})
    assert r.status_code == 422, r.text

    r = _link(headers, supplier_id, {"product_id": product_id, "supplier_sku": "   "})
    assert r.status_code == 422, r.text


def test_negative_lead_and_moq_422():
    token, ws = _register("spneg")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C7")
    product_id = _product(headers, ws, "C7")

    r = _link(headers, supplier_id, {"product_id": product_id, "lead_time_days": -1})
    assert r.status_code == 422, r.text

    r = _link(headers, supplier_id, {"product_id": product_id, "moq": "-5"})
    assert r.status_code == 422, r.text


def test_list_returns_only_requested_supplier_links():
    token, ws = _register("splist")
    headers = {"Authorization": f"Bearer {token}"}
    sup_a = _supplier(headers, ws, "C8a")
    sup_b = _supplier(headers, ws, "C8b")
    prod_a = _product(headers, ws, "C8a")
    prod_b = _product(headers, ws, "C8b")

    assert _link(headers, sup_a, {"product_id": prod_a}).status_code == 201
    assert _link(headers, sup_a, {"product_id": prod_b}).status_code == 201
    assert _link(headers, sup_b, {"product_id": prod_a}).status_code == 201

    r = client.get(f"/api/v1/suppliers/{sup_a}/products", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 2
    assert {row["product_id"] for row in rows} == {prod_a, prod_b}
    assert all(row["supplier_id"] == sup_a for row in rows)

    r = client.get(f"/api/v1/suppliers/{sup_b}/products", headers=headers)
    assert len(r.json()["data"]) == 1


def test_list_is_workspace_isolated():
    token_a, _ = _register("splist_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b, _ = _register("splist_b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me_a = client.get("/auth/me", headers=headers_a).json()["data"]
    sup_a = _supplier(headers_a, me_a["workspace_id"], "C9")
    prod_a = _product(headers_a, me_a["workspace_id"], "C9")
    assert _link(headers_a, sup_a, {"product_id": prod_a}).status_code == 201

    # Cross-tenant supplier id must 404, never leak.
    r = client.get(f"/api/v1/suppliers/{sup_a}/products", headers=headers_b)
    assert r.status_code == 404, r.text

    # Own workspace starts empty.
    me_b = client.get("/auth/me", headers=headers_b).json()["data"]
    sup_b = _supplier(headers_b, me_b["workspace_id"], "C9b")
    r = client.get(f"/api/v1/suppliers/{sup_b}/products", headers=headers_b)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


def test_delete_happy_path():
    token, ws = _register("spdel")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C10")
    product_id = _product(headers, ws, "C10")
    assert _link(headers, supplier_id, {"product_id": product_id}).status_code == 201

    r = client.delete(
        f"/api/v1/suppliers/{supplier_id}/products/{product_id}", headers=headers
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/suppliers/{supplier_id}/products", headers=headers)
    assert r.json()["data"] == []

    # Supplier and product themselves survive the link delete.
    r = client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert r.status_code == 200, r.text


def test_delete_nonexistent_or_foreign_404():
    token, ws = _register("spdel404")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C11")
    product_id = _product(headers, ws, "C11")

    r = client.delete(
        f"/api/v1/suppliers/{supplier_id}/products/{product_id}", headers=headers
    )
    assert r.status_code == 404, r.text

    r = client.delete(
        f"/api/v1/suppliers/{str(uuid.uuid4())}/products/{product_id}",
        headers=headers,
    )
    assert r.status_code == 404, r.text

    r = client.delete(
        f"/api/v1/suppliers/{supplier_id}/products/{str(uuid.uuid4())}",
        headers=headers,
    )
    assert r.status_code == 404, r.text


def test_links_independent_of_supplier_status():
    token, ws = _register("spstatus")
    headers = {"Authorization": f"Bearer {token}"}
    for status_value in ("ACTIVE", "INACTIVE", "HOLD"):
        supplier_id = _supplier(headers, ws, f"C12-{status_value[:2]}")
        product_id = _product(headers, ws, f"C12-{status_value[:2]}")
        _set_supplier_status(supplier_id, status_value)
        r = _link(headers, supplier_id, {"product_id": product_id})
        assert r.status_code == 201, f"{status_value}: {r.text}"


def _set_supplier_status(supplier_id, status_value):
    async def _update():
        async with TestingSessionLocal() as session:
            from app.models.supplier import Supplier

            row = await session.get(Supplier, uuid.UUID(str(supplier_id)))
            row.status = status_value
            await session.commit()

    asyncio.run(_update())


def test_product_detail_unaffected_by_links():
    token, ws = _register("spdetail")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = _supplier(headers, ws, "C13")
    product_id = _product(headers, ws, "C13")
    assert _link(headers, supplier_id, {"product_id": product_id}).status_code == 201

    r = client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == product_id
