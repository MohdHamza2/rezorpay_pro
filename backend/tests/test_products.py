"""WP-1 Product Master API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test`` (same URL
derivation as ``test_multi_tenant_isolation.py``). Never SQLite.
"""

import asyncio
import sys
import uuid
from decimal import Decimal
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.schemas.products import (
    ProductCreate,
    ProductPriceCreate,
    ProductUOMConversionCreate,
    ProductUpdate,
)

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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _assert_pagination(body: dict) -> None:
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "items" not in body
    pagination = body["pagination"]
    for key in ("total", "page", "per_page", "pages", "has_next", "has_prev"):
        assert key in pagination


def _create_uom(headers: dict, code: str | None = None, name: str = "Metres") -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {"name": name, "code": code or f"UOM-{suffix}"}
    r = client.post("/api/v1/products/uom", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_product(
    headers: dict, uom_id: str, sku: str | None = None, name: str = "Cable"
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": name,
        "internal_sku": sku or f"ELE-{suffix}",
        "base_uom_id": uom_id,
    }
    r = client.post("/api/v1/products", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _create_client(headers: dict, name: str = "Dealer") -> str:
    r = client.post(
        "/api/v1/clients",
        json={"name": name, "email": f"{uuid.uuid4().hex[:8]}@ex.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


# ---------- Category / Brand / UOM CRUD ----------


def test_category_crud_soft_delete_and_list():
    token, _ = _register("cat_owner", "Cat WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products/categories",
        json={"name": "Cables", "description": "Power cables"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    cat_id = r.json()["data"]["id"]

    r = client.get(f"/api/v1/products/categories/{cat_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Cables"

    r = client.put(
        f"/api/v1/products/categories/{cat_id}",
        json={"name": "XLPE Cables"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "XLPE Cables"

    r = client.get("/api/v1/products/categories", headers=headers)
    _assert_pagination(r.json())
    assert any(row["id"] == cat_id for row in r.json()["data"])

    r = client.delete(f"/api/v1/products/categories/{cat_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "data": None}

    r = client.get("/api/v1/products/categories", headers=headers)
    assert all(row["id"] != cat_id for row in r.json()["data"])

    r = client.get(f"/api/v1/products/categories/{cat_id}", headers=headers)
    assert r.status_code == 404


def test_brand_crud_soft_delete():
    token, _ = _register("brand_owner", "Brand WS")
    headers = _headers(token)
    r = client.post("/api/v1/products/brands", json={"name": "Ducab"}, headers=headers)
    assert r.status_code == 201, r.text
    brand_id = r.json()["data"]["id"]

    r = client.get(f"/api/v1/products/brands/{brand_id}", headers=headers)
    assert r.status_code == 200
    r = client.put(
        f"/api/v1/products/brands/{brand_id}",
        json={"description": "UAE cable brand"},
        headers=headers,
    )
    assert r.status_code == 200
    r = client.delete(f"/api/v1/products/brands/{brand_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"] is None
    r = client.get(f"/api/v1/products/brands/{brand_id}", headers=headers)
    assert r.status_code == 404
    r = client.get("/api/v1/products/brands", headers=headers)
    _assert_pagination(r.json())
    assert all(row["id"] != brand_id for row in r.json()["data"])


def test_uom_crud_soft_delete():
    token, _ = _register("uom_owner", "UOM WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products/uom", json={"name": "Pieces", "code": "PCS"}, headers=headers
    )
    assert r.status_code == 201, r.text
    uom_id = r.json()["data"]["id"]
    r = client.get(f"/api/v1/products/uom/{uom_id}", headers=headers)
    assert r.status_code == 200
    r = client.put(
        f"/api/v1/products/uom/{uom_id}", json={"name": "Piece"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Piece"
    r = client.delete(f"/api/v1/products/uom/{uom_id}", headers=headers)
    assert r.status_code == 200
    r = client.get(f"/api/v1/products/uom/{uom_id}", headers=headers)
    assert r.status_code == 404
    r = client.get("/api/v1/products/uom", headers=headers)
    _assert_pagination(r.json())
    assert all(row["id"] != uom_id for row in r.json()["data"])


def test_category_circular_and_self_parent_400():
    token, _ = _register("cat_cycle", "Cat Cycle WS")
    headers = _headers(token)
    root = client.post(
        "/api/v1/products/categories", json={"name": "Root"}, headers=headers
    )
    assert root.status_code == 201, root.text
    root_id = root.json()["data"]["id"]
    child = client.post(
        "/api/v1/products/categories",
        json={"name": "Child", "parent_id": root_id},
        headers=headers,
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["data"]["id"]

    r = client.put(
        f"/api/v1/products/categories/{root_id}",
        json={"parent_id": child_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    r = client.put(
        f"/api/v1/products/categories/{root_id}",
        json={"parent_id": root_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_category_parent_walk_ignores_deleted_ancestor():
    token, _ = _register("cat_anc", "Cat Anc WS")
    headers = _headers(token)
    a = client.post("/api/v1/products/categories", json={"name": "A"}, headers=headers)
    assert a.status_code == 201, a.text
    a_id = a.json()["data"]["id"]
    b = client.post(
        "/api/v1/products/categories",
        json={"name": "B", "parent_id": a_id},
        headers=headers,
    )
    assert b.status_code == 201, b.text
    b_id = b.json()["data"]["id"]
    c = client.post(
        "/api/v1/products/categories",
        json={"name": "C", "parent_id": b_id},
        headers=headers,
    )
    assert c.status_code == 201, c.text
    c_id = c.json()["data"]["id"]

    r = client.delete(f"/api/v1/products/categories/{b_id}", headers=headers)
    assert r.status_code == 200, r.text

    d = client.post(
        "/api/v1/products/categories",
        json={"name": "D", "parent_id": c_id},
        headers=headers,
    )
    assert d.status_code == 201, d.text


def test_duplicate_category_name_409():
    token, _ = _register("dup_cat", "Dup Cat WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products/categories", json={"name": "Switchgear"}, headers=headers
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/products/categories", json={"name": "Switchgear"}, headers=headers
    )
    assert r.status_code == 409, r.text


def test_duplicate_brand_name_409():
    token, _ = _register("dup_brand", "Dup Brand WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products/brands", json={"name": "Ducab Dup"}, headers=headers
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/products/brands", json={"name": "Ducab Dup"}, headers=headers
    )
    assert r.status_code == 409, r.text


def test_duplicate_uom_code_409():
    token, _ = _register("dup_uom", "Dup UOM WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products/uom", json={"name": "Metre", "code": "MTR"}, headers=headers
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/products/uom", json={"name": "Meter", "code": "MTR"}, headers=headers
    )
    assert r.status_code == 409, r.text


# ---------- Product ----------


def test_product_create_missing_base_uom_422():
    token, _ = _register("no_uom", "No UOM WS")
    headers = _headers(token)
    r = client.post(
        "/api/v1/products",
        json={"name": "Widget", "internal_sku": "W-1"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_duplicate_live_sku_409():
    token, _ = _register("dup_sku", "Dup SKU WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    _create_product(headers, uom_id, sku=sku)
    r = client.post(
        "/api/v1/products",
        json={"name": "Other", "internal_sku": sku, "base_uom_id": uom_id},
        headers=headers,
    )
    assert r.status_code == 409, r.text


def test_product_create_foreign_uom_404():
    token_a, _ = _register("prod_a_uom", "WS A")
    token_b, _ = _register("prod_b_uom", "WS B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    uom_b = _create_uom(headers_b, code="PCS-B")
    r = client.post(
        "/api/v1/products",
        json={"name": "Widget", "internal_sku": "W-X", "base_uom_id": uom_b},
        headers=headers_a,
    )
    assert r.status_code in (400, 404), r.text


def test_product_put_rejects_extra_keys_422():
    token, _ = _register("put_extra", "Put Extra WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    r = client.put(
        f"/api/v1/products/{product['id']}",
        json={"name": "Cable", "hs_code": "8544.49"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_product_create_rejects_extra_keys_422():
    token, _ = _register("extra_keys", "Extra WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    r = client.post(
        "/api/v1/products",
        json={
            "name": "Cable",
            "internal_sku": "ELE-X",
            "base_uom_id": uom_id,
            "hs_code": "8544.49",
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_product_tax_rate_omitted_is_null():
    token, _ = _register("tax_null", "Tax Null WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    r = client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tax_rate"] is None


def test_product_list_includes_inactive_without_filter():
    token, _ = _register("inactive_list", "Inactive List WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id, name="Inactive SKU")
    pid = product["id"]
    r = client.put(
        f"/api/v1/products/{pid}", json={"is_active": False}, headers=headers
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/products", headers=headers)
    assert r.status_code == 200, r.text
    ids = [row["id"] for row in r.json()["data"]]
    assert pid in ids


def test_product_list_pagination_and_search():
    token, _ = _register("list_prod", "List WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    sku = f"ELE-CBL-{uuid.uuid4().hex[:6]}"
    _create_product(headers, uom_id, sku=sku, name="4-core 10mm XLPE")
    for i in range(3):
        _create_product(headers, uom_id, sku=f"FILL-{i}-{uuid.uuid4().hex[:4]}")

    r = client.get("/api/v1/products?page=1&per_page=2", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_pagination(body)
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["per_page"] == 2
    assert body["pagination"]["total"] >= 4
    assert len(body["data"]) == 2
    assert body["pagination"]["has_next"] is True

    r = client.get(f"/api/v1/products?search={sku}", headers=headers)
    assert r.status_code == 200, r.text
    skus = [row["internal_sku"] for row in r.json()["data"]]
    assert sku in skus


def test_product_put_and_put_after_delete_404():
    token, _ = _register("put_prod", "Put WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    product_id = product["id"]

    r = client.put(
        f"/api/v1/products/{product_id}",
        json={"name": "Updated cable", "is_active": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Updated cable"
    assert r.json()["data"]["is_active"] is False

    r = client.delete(f"/api/v1/products/{product_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None

    r = client.put(
        f"/api/v1/products/{product_id}", json={"name": "Ghost"}, headers=headers
    )
    assert r.status_code == 404, r.text
    r = client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert r.status_code == 404, r.text


def test_mpn_reusable_after_product_soft_delete():
    token, _ = _register("mpn_reuse", "MPN Reuse WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    pid = product["id"]
    mpn = f"MPN-{uuid.uuid4().hex[:8]}"
    ident = client.post(
        f"/api/v1/products/{pid}/identifiers",
        json={"type": "MPN", "value": mpn},
        headers=headers,
    )
    assert ident.status_code == 201, ident.text
    ident_id = ident.json()["data"]["id"]

    r = client.delete(f"/api/v1/products/{pid}", headers=headers)
    assert r.status_code == 200, r.text

    r = client.delete(f"/api/v1/products/{pid}/identifiers/{ident_id}", headers=headers)
    assert r.status_code == 404, r.text

    other = _create_product(headers, uom_id)
    r = client.post(
        f"/api/v1/products/{other['id']}/identifiers",
        json={"type": "MPN", "value": mpn},
        headers=headers,
    )
    assert r.status_code == 201, r.text


def test_product_soft_delete_excluded_from_list_sku_not_reusable():
    token, _ = _register("del_prod", "Del WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    sku = f"REUSE-{uuid.uuid4().hex[:6]}"
    product = _create_product(headers, uom_id, sku=sku)
    product_id = product["id"]

    r = client.delete(f"/api/v1/products/{product_id}", headers=headers)
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/products", headers=headers)
    _assert_pagination(r.json())
    assert all(row["id"] != product_id for row in r.json()["data"])

    r = client.post(
        "/api/v1/products",
        json={"name": "Again", "internal_sku": sku, "base_uom_id": uom_id},
        headers=headers,
    )
    assert r.status_code == 409, r.text


def test_product_detail_embeds_children_not_stock():
    token, _ = _register("detail_prod", "Detail WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    r = client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "identifiers" in data
    assert "conversions" in data
    assert "prices" in data
    assert "warehouse_stock" not in data
    assert "quantity_on_hand" not in data


# ---------- Identifiers ----------


def test_identifier_crud_allow_list_and_duplicate():
    token, _ = _register("ident", "Ident WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    pid = product["id"]

    for ident_type, value in (
        ("MPN", "DUC-4C10"),
        ("BARCODE", "1234567890123"),
        ("SUPPLIER_CODE", "SUP-99"),
    ):
        r = client.post(
            f"/api/v1/products/{pid}/identifiers",
            json={"type": ident_type, "value": value},
            headers=headers,
        )
        assert r.status_code == 201, r.text

    r = client.get(f"/api/v1/products/{pid}/identifiers", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert isinstance(r.json()["data"], list)
    assert "pagination" not in r.json()
    assert len(r.json()["data"]) == 3
    ident_id = r.json()["data"][0]["id"]

    r = client.post(
        f"/api/v1/products/{pid}/identifiers",
        json={"type": "FOO", "value": "X"},
        headers=headers,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/identifiers",
        json={"type": "INTERNAL_SKU", "value": "X"},
        headers=headers,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/identifiers",
        json={"type": "MPN", "value": "DUC-4C10"},
        headers=headers,
    )
    assert r.status_code == 409, r.text

    r = client.delete(f"/api/v1/products/{pid}/identifiers/{ident_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None


def test_same_mpn_on_two_live_products_409():
    token, _ = _register("mpn_two", "MPN Two WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    first = _create_product(headers, uom_id)
    second = _create_product(headers, uom_id)
    mpn = f"SHARED-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"/api/v1/products/{first['id']}/identifiers",
        json={"type": "MPN", "value": mpn},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"/api/v1/products/{second['id']}/identifiers",
        json={"type": "MPN", "value": mpn},
        headers=headers,
    )
    assert r.status_code == 409, r.text


# ---------- Conversions ----------


def test_conversion_factor_decimal_and_rules():
    token, _ = _register("conv", "Conv WS")
    headers = _headers(token)
    base_uom = _create_uom(headers, code="MTR", name="Metre")
    drum_uom = _create_uom(headers, code="DRM", name="Drum")
    product = _create_product(headers, base_uom)
    pid = product["id"]

    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": drum_uom, "conversion_factor": "500.000000"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert _dec(data["conversion_factor"]) == Decimal("500.000000")
    assert data["to_uom_id"] == drum_uom
    assert data["base_uom_id"] == base_uom
    conversion_id = data["id"]

    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": base_uom, "conversion_factor": "1"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": drum_uom, "conversion_factor": "0"},
        headers=headers,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={
            "to_uom_id": drum_uom,
            "conversion_factor": "10",
            "from_uom_id": base_uom,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": drum_uom, "conversion_factor": "250"},
        headers=headers,
    )
    assert r.status_code == 409, r.text

    r = client.get(f"/api/v1/products/{pid}/conversions", headers=headers)
    assert r.status_code == 200
    assert "pagination" not in r.json()

    r = client.delete(
        f"/api/v1/products/{pid}/conversions/{conversion_id}", headers=headers
    )
    assert r.status_code == 200
    assert r.json()["data"] is None


def test_put_base_uom_blocked_while_conversions_exist():
    token, _ = _register("base_lock", "Base Lock WS")
    headers = _headers(token)
    base_uom = _create_uom(headers, code="PCS")
    other_uom = _create_uom(headers, code="BOX")
    third_uom = _create_uom(headers, code="KG")
    product = _create_product(headers, base_uom)
    pid = product["id"]
    r = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": other_uom, "conversion_factor": "10"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    r = client.put(
        f"/api/v1/products/{pid}",
        json={"base_uom_id": third_uom},
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_uom_delete_blocked_when_live_conversion_references_it():
    token, _ = _register("uom_conv_block", "UOM Conv Block WS")
    headers = _headers(token)
    base_uom = _create_uom(headers, code="PCS")
    box_uom = _create_uom(headers, code="BOX")
    product = _create_product(headers, base_uom)
    r = client.post(
        f"/api/v1/products/{product['id']}/conversions",
        json={"to_uom_id": box_uom, "conversion_factor": "10"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/api/v1/products/uom/{box_uom}", headers=headers)
    assert r.status_code == 400, r.text


def test_uom_delete_blocked_when_product_references_it():
    token, _ = _register("uom_block", "UOM Block WS")
    headers = _headers(token)
    uom_id = _create_uom(headers, code="MTR")
    _create_product(headers, uom_id)
    r = client.delete(f"/api/v1/products/uom/{uom_id}", headers=headers)
    assert r.status_code == 400, r.text


# ---------- Prices ----------


def test_price_rules():
    token_a, _ = _register("price_a", "Price A")
    token_b, _ = _register("price_b", "Price B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    uom_id = _create_uom(headers_a)
    product = _create_product(headers_a, uom_id)
    pid = product["id"]
    client_a = _create_client(headers_a)
    client_b = _create_client(headers_b)

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "DEFAULT_SALES", "price": "12.50"},
        headers=headers_a,
    )
    assert r.status_code == 201, r.text
    assert _dec(r.json()["data"]["price"]) == Decimal("12.50")
    assert r.json()["data"]["currency"] == "AED"
    price_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "DEFAULT_SALES", "price": "9.00"},
        headers=headers_a,
    )
    assert r.status_code == 409, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "DEFAULT_SALES", "price": "9.00", "currency": "USD"},
        headers=headers_a,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "TIER_1", "price": "11.00"},
        headers=headers_a,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={
            "price_type": "TIER_1",
            "price": "11.00",
            "min_quantity": "10.00",
        },
        headers=headers_a,
    )
    assert r.status_code == 201, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={
            "price_type": "TIER_1",
            "price": "10.00",
            "min_quantity": "10.00",
        },
        headers=headers_a,
    )
    assert r.status_code == 409, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "CUSTOMER_SPECIFIC", "price": "8.00"},
        headers=headers_a,
    )
    assert r.status_code == 422, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={
            "price_type": "CUSTOMER_SPECIFIC",
            "price": "8.00",
            "client_id": client_b,
        },
        headers=headers_a,
    )
    assert r.status_code == 404, r.text

    r = client.post(
        f"/api/v1/products/{pid}/prices",
        json={
            "price_type": "CUSTOMER_SPECIFIC",
            "price": "8.00",
            "client_id": client_a,
        },
        headers=headers_a,
    )
    assert r.status_code == 201, r.text

    r = client.get(f"/api/v1/products/{pid}/prices", headers=headers_a)
    assert r.status_code == 200
    assert "pagination" not in r.json()

    r = client.delete(f"/api/v1/products/{pid}/prices/{price_id}", headers=headers_a)
    assert r.status_code == 200
    assert r.json()["data"] is None


# ---------- Isolation ----------


def test_workspace_b_cannot_access_workspace_a_product_or_children():
    token_a, ws_a = _register("iso_a", "Iso A")
    token_b, _ = _register("iso_b", "Iso B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    spoof = f"?workspace_id={ws_a}"
    base_uom = _create_uom(headers_a, code="MTR")
    drum_uom = _create_uom(headers_a, code="DRM")
    product = _create_product(headers_a, base_uom)
    pid = product["id"]

    cat = client.post(
        "/api/v1/products/categories", json={"name": "Iso Cat"}, headers=headers_a
    )
    assert cat.status_code == 201, cat.text
    cat_id = cat.json()["data"]["id"]
    brand = client.post(
        "/api/v1/products/brands", json={"name": "Iso Brand"}, headers=headers_a
    )
    assert brand.status_code == 201, brand.text
    brand_id = brand.json()["data"]["id"]

    ident = client.post(
        f"/api/v1/products/{pid}/identifiers",
        json={"type": "EAN", "value": "4006381333931"},
        headers=headers_a,
    )
    assert ident.status_code == 201, ident.text
    ident_id = ident.json()["data"]["id"]

    conv = client.post(
        f"/api/v1/products/{pid}/conversions",
        json={"to_uom_id": drum_uom, "conversion_factor": "500"},
        headers=headers_a,
    )
    assert conv.status_code == 201, conv.text
    conv_id = conv.json()["data"]["id"]

    price = client.post(
        f"/api/v1/products/{pid}/prices",
        json={"price_type": "DEFAULT_SALES", "price": "15.00"},
        headers=headers_a,
    )
    assert price.status_code == 201, price.text
    price_id = price.json()["data"]["id"]

    assert (
        client.get(f"/api/v1/products/{pid}{spoof}", headers=headers_b).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/products/{pid}{spoof}",
            json={"name": "HACK"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/products/{pid}{spoof}", headers=headers_b).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/products/{pid}/identifiers{spoof}", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/products/{pid}/identifiers/{ident_id}{spoof}",
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/products/{pid}/conversions", headers=headers_b).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/products/{pid}/conversions/{conv_id}", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/products/{pid}/prices", headers=headers_b).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/products/{pid}/prices/{price_id}", headers=headers_b
        ).status_code
        == 404
    )

    assert (
        client.post(
            f"/api/v1/products/{pid}/identifiers{spoof}",
            json={"type": "MPN", "value": "HACK-MPN"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/products/{pid}/conversions{spoof}",
            json={"to_uom_id": drum_uom, "conversion_factor": "2"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/products/{pid}/prices{spoof}",
            json={"price_type": "DEFAULT_SALES", "price": "1.00"},
            headers=headers_b,
        ).status_code
        == 404
    )

    for path in (
        f"/api/v1/products/categories/{cat_id}{spoof}",
        f"/api/v1/products/brands/{brand_id}{spoof}",
        f"/api/v1/products/uom/{base_uom}{spoof}",
    ):
        assert client.get(path, headers=headers_b).status_code == 404
        assert (
            client.put(path, json={"name": "HACK"}, headers=headers_b).status_code
            == 404
        )
        assert client.delete(path, headers=headers_b).status_code == 404


# ---------- Schema money types ----------


def test_schema_fields_are_not_float():
    for model in (
        ProductCreate,
        ProductUpdate,
        ProductPriceCreate,
        ProductUOMConversionCreate,
    ):
        for name, field in model.model_fields.items():
            annotation = field.annotation
            assert annotation is not float, f"{model.__name__}.{name} is float"
            assert float not in get_args(
                annotation
            ), f"{model.__name__}.{name} allows float"
