"""WP-A electrical catalogue spec columns (addendum §6).

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
Do not refactor ``test_products.py`` — helpers are duplicated here.
"""

import ast
import asyncio
import shutil
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Float, Integer, Numeric, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.product import Product
from app.schemas.products import ProductCreate, ProductResponse, ProductUpdate

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"
CREDIT_NOTES_REV = VERSIONS_DIR / "b8d5f0c3a216_add_credit_notes.py"
SPEC_FIELDS = ("amp_rating", "cable_size_mm2", "cores", "poles", "voltage")


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


def _create_uom(headers: dict, code: str | None = None, name: str = "Metres") -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {"name": name, "code": code or f"UOM-{suffix}"}
    r = client.post("/api/v1/products/uom", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_product(
    headers: dict,
    uom_id: str,
    sku: str | None = None,
    name: str = "Cable",
    extra: dict | None = None,
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": name,
        "internal_sku": sku or f"ELE-{suffix}",
        "base_uom_id": uom_id,
    }
    if extra:
        payload.update(extra)
    r = client.post("/api/v1/products", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _ids(body: dict) -> list[str]:
    return [row["id"] for row in body["data"]]


def test_create_without_specs_returns_null_keys():
    token, _ = _register("spec_wave3", "Spec Wave3 WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id, name="Wave3 SKU")
    assert product["id"]
    for key in SPEC_FIELDS:
        assert key in product
        assert product[key] is None

    r = client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    for key in SPEC_FIELDS:
        assert key in data
        assert data[key] is None

    empty_v = _create_product(
        headers, uom_id, extra={"voltage": "   "}, name="Empty voltage"
    )
    assert empty_v["voltage"] is None


def test_create_cable_breaker_and_fractional_mm2():
    token, _ = _register("spec_create", "Spec Create WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    cable = _create_product(
        headers,
        uom_id,
        sku=f"CBL-4C10-{uuid.uuid4().hex[:6]}",
        name="XLPE cable",
        extra={"cable_size_mm2": "10", "cores": 4},
    )
    assert _dec(cable["cable_size_mm2"]) == Decimal("10.00")
    assert cable["cores"] == 4
    assert cable["amp_rating"] is None

    breaker = _create_product(
        headers,
        uom_id,
        sku=f"MCB-63-3P-{uuid.uuid4().hex[:6]}",
        name="MCB breaker",
        extra={"amp_rating": "63", "poles": 3, "voltage": "230/400"},
    )
    assert _dec(breaker["amp_rating"]) == Decimal("63.00")
    assert breaker["poles"] == 3
    assert breaker["voltage"] == "230/400"

    mm15 = _create_product(
        headers,
        uom_id,
        extra={"cable_size_mm2": "1.5"},
        name="Fine strand",
    )
    mm25 = _create_product(
        headers,
        uom_id,
        extra={"cable_size_mm2": "2.5"},
        name="Twin and earth",
    )
    assert _dec(mm15["cable_size_mm2"]) == Decimal("1.50")
    assert _dec(mm25["cable_size_mm2"]) == Decimal("2.50")

    listed = client.get("/api/v1/products", headers=headers)
    assert listed.status_code == 200, listed.text
    by_id = {row["id"]: row for row in listed.json()["data"]}
    assert _dec(by_id[cable["id"]]["cable_size_mm2"]) == Decimal("10.00")
    assert by_id[cable["id"]]["cores"] == 4
    assert _dec(by_id[breaker["id"]]["amp_rating"]) == Decimal("63.00")
    assert by_id[breaker["id"]]["voltage"] == "230/400"


def test_unknown_keys_still_422_known_amp_ok():
    token, _ = _register("spec_extra", "Spec Extra WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id)
    base = {
        "name": "Cable",
        "internal_sku": f"ELE-{uuid.uuid4().hex[:6]}",
        "base_uom_id": uom_id,
    }
    r = client.post(
        "/api/v1/products", json={**base, "hs_code": "8544.49"}, headers=headers
    )
    assert r.status_code == 422, r.text
    r = client.post("/api/v1/products", json={**base, "specs": {}}, headers=headers)
    assert r.status_code == 422, r.text
    r = client.put(
        f"/api/v1/products/{product['id']}",
        json={"hs_code": "8544.49"},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    r = client.post(
        "/api/v1/products",
        json={
            **base,
            "internal_sku": f"AMP-{uuid.uuid4().hex[:6]}",
            "amp_rating": "63",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert _dec(r.json()["data"]["amp_rating"]) == Decimal("63.00")


def test_invalid_specs_are_422():
    token, _ = _register("spec_invalid", "Spec Invalid WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    base = {
        "name": "Bad spec",
        "internal_sku": f"BAD-{uuid.uuid4().hex[:6]}",
        "base_uom_id": uom_id,
    }
    cases = (
        {"amp_rating": "0"},
        {"amp_rating": "-1"},
        {"cores": 0},
        {"poles": 5},
        {"voltage": "230V"},
        {"voltage": "11kV"},
        {"voltage": "230 / 400"},
    )
    for extra in cases:
        sku = f"BAD-{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/api/v1/products",
            json={**base, "internal_sku": sku, **extra},
            headers=headers,
        )
        assert r.status_code == 422, f"{extra}: {r.text}"
        product = _create_product(headers, uom_id)
        r = client.put(f"/api/v1/products/{product['id']}", json=extra, headers=headers)
        assert r.status_code == 422, f"PUT {extra}: {r.text}"


def test_list_spec_filters_and_empty_intersection():
    token, _ = _register("spec_filter", "Spec Filter WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    cable = _create_product(
        headers,
        uom_id,
        name="Filter cable",
        extra={"cable_size_mm2": "10", "cores": 4},
    )
    breaker = _create_product(
        headers,
        uom_id,
        name="Filter breaker",
        extra={"amp_rating": "63", "poles": 3, "voltage": "230/400"},
    )
    r = client.get("/api/v1/products?cable_size_mm2=10&cores=4", headers=headers)
    assert r.status_code == 200, r.text
    ids = _ids(r.json())
    assert cable["id"] in ids
    assert breaker["id"] not in ids

    r = client.get("/api/v1/products?amp_rating=63&poles=3", headers=headers)
    assert r.status_code == 200, r.text
    ids = _ids(r.json())
    assert breaker["id"] in ids
    assert cable["id"] not in ids

    r = client.get(
        "/api/v1/products?cable_size_mm2=10&cores=4&amp_rating=63&poles=3",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


def test_accessory_excluded_from_amp_filter_omitted_lists_all():
    token, _ = _register("spec_access", "Spec Access WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    accessory = _create_product(headers, uom_id, name="Gland")
    breaker = _create_product(
        headers,
        uom_id,
        name="Access breaker",
        extra={"amp_rating": "63", "poles": 3},
    )
    r = client.get("/api/v1/products?amp_rating=63", headers=headers)
    assert r.status_code == 200, r.text
    ids = _ids(r.json())
    assert breaker["id"] in ids
    assert accessory["id"] not in ids

    r = client.get("/api/v1/products", headers=headers)
    assert r.status_code == 200, r.text
    ids = _ids(r.json())
    assert accessory["id"] in ids
    assert breaker["id"] in ids


def test_search_does_not_parse_mm2_or_amp():
    token, _ = _register("spec_search", "Spec Search WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    sku = f"CBL-XLPE-{uuid.uuid4().hex[:6]}"
    hidden = _create_product(
        headers,
        uom_id,
        sku=sku,
        name="XLPE drum",
        extra={"cable_size_mm2": "10", "cores": 4},
    )
    r = client.get(f"/api/v1/products?search={sku}", headers=headers)
    assert r.status_code == 200, r.text
    assert hidden["id"] in _ids(r.json())

    r = client.get("/api/v1/products?search=10mm", headers=headers)
    assert r.status_code == 200, r.text
    assert hidden["id"] not in _ids(r.json())


def test_put_null_clears_omit_leaves_value():
    token, _ = _register("spec_put", "Spec Put WS")
    headers = _headers(token)
    uom_id = _create_uom(headers)
    product = _create_product(headers, uom_id, extra={"amp_rating": "63", "poles": 3})
    pid = product["id"]
    r = client.put(
        f"/api/v1/products/{pid}", json={"name": "Still 63A"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert _dec(r.json()["data"]["amp_rating"]) == Decimal("63.00")
    assert r.json()["data"]["poles"] == 3
    assert r.json()["data"]["name"] == "Still 63A"

    r = client.put(
        f"/api/v1/products/{pid}", json={"amp_rating": None}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["amp_rating"] is None
    assert r.json()["data"]["poles"] == 3


def test_workspace_b_cannot_see_workspace_a_specs():
    token_a, ws_a = _register("spec_iso_a", "Spec Iso A")
    token_b, _ = _register("spec_iso_b", "Spec Iso B")
    headers_a = _headers(token_a)
    headers_b = _headers(token_b)
    spoof = f"?workspace_id={ws_a}"
    uom_a = _create_uom(headers_a)
    uom_b = _create_uom(headers_b)
    breaker = _create_product(
        headers_a,
        uom_a,
        name="Iso breaker",
        extra={"amp_rating": "63", "poles": 3},
    )
    pid = breaker["id"]
    _create_product(headers_b, uom_b, name="B accessory")

    get_r = client.get(f"/api/v1/products/{pid}{spoof}", headers=headers_b)
    assert get_r.status_code == 404, get_r.text
    assert get_r.status_code != 403
    put_r = client.put(
        f"/api/v1/products/{pid}{spoof}",
        json={"amp_rating": "10"},
        headers=headers_b,
    )
    assert put_r.status_code == 404, put_r.text
    assert put_r.status_code != 403

    listed = client.get("/api/v1/products?amp_rating=63", headers=headers_b)
    assert listed.status_code == 200, listed.text
    assert pid not in _ids(listed.json())


def test_spec_fields_are_not_float():
    for model in (ProductCreate, ProductUpdate, ProductResponse):
        for name in SPEC_FIELDS:
            annotation = model.model_fields[name].annotation
            assert annotation is not float, f"{model.__name__}.{name} is float"
            assert float not in get_args(
                annotation
            ), f"{model.__name__}.{name} allows float"
    columns = Product.__table__.c
    assert isinstance(columns.amp_rating.type, Numeric)
    assert isinstance(columns.cable_size_mm2.type, Numeric)
    assert isinstance(columns.cores.type, Integer)
    assert isinstance(columns.poles.type, Integer)
    assert isinstance(columns.voltage.type, String)
    for col in (
        columns.amp_rating,
        columns.cable_size_mm2,
        columns.cores,
        columns.poles,
        columns.voltage,
    ):
        assert not isinstance(col.type, Float)
        assert col.nullable is True
    model_src = (BACKEND_DIR / "app" / "models" / "product.py").read_text(
        encoding="utf-8"
    )
    schema_src = (BACKEND_DIR / "app" / "schemas" / "products.py").read_text(
        encoding="utf-8"
    )
    for src in (model_src, schema_src):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in {"float", "Float"}:
                raise AssertionError(f"float/Float name in AST: {src[:40]}")
            if isinstance(node, ast.Attribute) and node.attr == "Float":
                raise AssertionError("sqlalchemy.Float referenced")


def test_alembic_new_revision_parent_and_check():
    assert CREDIT_NOTES_REV.is_file()
    credit_src = CREDIT_NOTES_REV.read_text(encoding="utf-8")
    assert 'revision: str = "b8d5f0c3a216"' in credit_src
    assert 'down_revision: Union[str, None] = "a7c4e9d2b105"' in credit_src

    children: list[Path] = []
    for path in VERSIONS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        if 'down_revision: Union[str, None] = "b8d5f0c3a216"' in src:
            children.append(path)
    assert len(children) == 1, [p.name for p in children]
    new_src = children[0].read_text(encoding="utf-8")
    assert "amp_rating" in new_src
    assert "postgresql_where" in new_src
    rev_match = None
    for line in new_src.splitlines():
        if line.startswith("revision: str = "):
            rev_match = line.split("=", 1)[1].strip().strip("\"'")
            break
    assert rev_match and rev_match != "b8d5f0c3a216"

    alembic_bin = shutil.which("alembic")
    assert alembic_bin, "alembic CLI not found"
    heads = subprocess.run(
        [alembic_bin, "heads"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert heads.returncode == 0, heads.stdout + heads.stderr
    head_text = heads.stdout + heads.stderr
    assert rev_match in head_text
    assert "b8d5f0c3a216 (head)" not in head_text
    upgrade = subprocess.run(
        [alembic_bin, "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    check = subprocess.run(
        [alembic_bin, "check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    combined = check.stdout + check.stderr
    assert "No new upgrade operations detected" in combined
