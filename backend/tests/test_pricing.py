"""WP-A volume / customer pricing (addendum §9). PostgreSQL `_test` only."""

import asyncio
import json
import shutil
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.auth.utils import hash_password
from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.product import ProductPrice
from app.models.user import User, UserRole
from app.schemas.products import ResolvedPriceResponse

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def _create_client(headers: dict, name: str = "Dealer") -> str:
    r = client.post(
        "/api/v1/clients",
        json={"name": name, "email": f"{uuid.uuid4().hex[:8]}@ex.com"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_product(headers: dict, *, is_active: bool = True) -> dict:
    uom = client.post(
        "/api/v1/products/uom",
        json={"name": "Metres", "code": f"MTR-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert uom.status_code == 201, uom.text
    r = client.post(
        "/api/v1/products",
        json={
            "name": "NYM cable",
            "internal_sku": f"ELE-{uuid.uuid4().hex[:8]}",
            "base_uom_id": uom.json()["data"]["id"],
            "is_active": is_active,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _add_price(headers: dict, product_id: str, payload: dict) -> dict:
    r = client.post(
        f"/api/v1/products/{product_id}/prices", json=payload, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _seed_volume(headers: dict, client_a: str) -> dict:
    product = _create_product(headers)
    pid = product["id"]
    _add_price(headers, pid, {"price_type": "DEFAULT_SALES", "price": "100.00"})
    _add_price(
        headers, pid, {"price_type": "TIER_1", "price": "90.00", "min_quantity": "10"}
    )
    _add_price(
        headers,
        pid,
        {
            "price_type": "CUSTOMER_SPECIFIC",
            "price": "80.00",
            "client_id": client_a,
            "min_quantity": "1",
        },
    )
    return product


def _ready(prefix: str) -> tuple[dict, str, str, dict]:
    token, workspace_id = _register(prefix, f"{prefix} WS")
    headers = _headers(token)
    client_a = _create_client(headers, "Client A")
    client_b = _create_client(headers, "Client B")
    product = _seed_volume(headers, client_a)
    return headers, client_a, client_b, product


def _omit(product_id: str, quantity: str) -> dict:
    return {"product_id": product_id, "quantity": quantity}


def _post_invoice(headers: dict, client_id: str, items: list[dict]):
    return client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-08-26",
            "due_date": "2026-09-26",
            "items": items,
        },
        headers=headers,
    )


def _invoice_price(headers: dict, client_id: str, items: list[dict]) -> Decimal:
    r = _post_invoice(headers, client_id, items)
    assert r.status_code == 201, r.text
    return _dec(r.json()["data"]["items"][0]["unit_price"])


QUOTE_PATH = "/api/v1/quotations"
LPO_PATH = "/api/v1/customer-purchase-orders"


def _post_doc(headers: dict, path: str, client_id: str, items: list[dict]):
    return client.post(
        path, json={"client_id": client_id, "items": items}, headers=headers
    )


def _preview(headers: dict, product_id: str, qty: str, client_id: str | None = None):
    params: dict[str, str] = {"quantity": qty}
    if client_id is not None:
        params["client_id"] = client_id
    return client.get(
        f"/api/v1/products/{product_id}/resolved-price", params=params, headers=headers
    )


def _wipe_to_list(headers: dict, product_id: str, price: str = "1.00") -> None:
    listed = client.get(f"/api/v1/products/{product_id}/prices", headers=headers)
    assert listed.status_code == 200, listed.text
    for row in listed.json()["data"]:
        gone = client.delete(
            f"/api/v1/products/{product_id}/prices/{row['id']}", headers=headers
        )
        assert gone.status_code == 200, gone.text
    _add_price(headers, product_id, {"price_type": "DEFAULT_SALES", "price": price})


def _member_token(workspace_id: str) -> str:
    email = f"mem_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert() -> None:
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="Member",
                    role=UserRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(_insert())
    r = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


def test_invoice_a_customer_beats_tier():
    headers, client_a, _, product = _ready("px_a")
    pid = product["id"]
    assert _invoice_price(headers, client_a, [_omit(pid, "1")]) == Decimal("80.00")
    assert _invoice_price(headers, client_a, [_omit(pid, "10")]) == Decimal("80.00")


def test_invoice_b_tier_then_list():
    headers, _, client_b, product = _ready("px_b")
    pid = product["id"]
    assert _invoice_price(headers, client_b, [_omit(pid, "10")]) == Decimal("90.00")
    assert _invoice_price(headers, client_b, [_omit(pid, "1")]) == Decimal("100.00")


def test_explicit_unit_price_wins():
    headers, client_a, _, product = _ready("px_exp")
    price = _invoice_price(
        headers,
        client_a,
        [{"product_id": product["id"], "quantity": "10", "unit_price": "12.50"}],
    )
    assert price == Decimal("12.50")


def test_no_list_price_and_adhoc_requires_price():
    token, _ = _register("px_none", "No Price WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    bare = _create_product(headers)
    missing = _post_invoice(headers, client_id, [_omit(bare["id"], "1")])
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["code"] == "NO_LIST_PRICE"
    assert missing.json()["error"]["field"] == "product_id"
    adhoc = _post_invoice(
        headers, client_id, [{"description": "Cutting", "quantity": "1"}]
    )
    assert adhoc.status_code == 422, adhoc.text


def test_other_workspace_product_and_preview_client_404():
    headers_a, _, _, product = _ready("px_iso_a")
    token_b, _ = _register("px_iso_b", "Iso B WS")
    headers_b = _headers(token_b)
    client_b = _create_client(headers_b)
    inv = _post_invoice(headers_b, client_b, [_omit(product["id"], "1")])
    assert inv.status_code == 404, inv.text
    preview = _preview(headers_a, product["id"], "1", client_b)
    assert preview.status_code == 404, preview.text
    assert preview.json()["error"]["code"] == "NOT_FOUND"


def test_inactive_add_and_preview_400():
    headers, client_a, _, product = _ready("px_dead")
    off = client.put(
        f"/api/v1/products/{product['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert off.status_code == 200, off.text
    line = [_omit(product["id"], "1")]
    inv = _post_invoice(headers, client_a, line)
    assert inv.status_code == 400, inv.text
    quote = _post_doc(headers, QUOTE_PATH, client_a, line)
    assert quote.status_code == 400, quote.text
    lpo = _post_doc(headers, LPO_PATH, client_a, line)
    assert lpo.status_code == 400, lpo.text
    preview = _preview(headers, product["id"], "1", client_a)
    assert preview.status_code == 400, preview.text
    assert preview.json()["error"]["code"] == "VALIDATION_ERROR"
    assert preview.json()["error"]["field"] == "product_id"


def test_quotation_and_lpo_create_put_same_precedence():
    headers, client_a, client_b, product = _ready("px_docs")
    pid = product["id"]
    quote = _post_doc(headers, QUOTE_PATH, client_a, [_omit(pid, "1")])
    assert quote.status_code == 201, quote.text
    assert _dec(quote.json()["data"]["items"][0]["unit_price"]) == Decimal("80.00")
    put_q = client.put(
        f"/api/v1/quotations/{quote.json()['data']['id']}",
        json={"items": [_omit(pid, "10")]},
        headers=headers,
    )
    assert put_q.status_code == 200, put_q.text
    got_q = client.get(
        f"/api/v1/quotations/{quote.json()['data']['id']}", headers=headers
    )
    assert got_q.status_code == 200, got_q.text
    assert _dec(got_q.json()["data"]["items"][0]["quantity"]) == Decimal("10.00")
    assert _dec(got_q.json()["data"]["items"][0]["unit_price"]) == Decimal("80.00")
    lpo = _post_doc(headers, LPO_PATH, client_b, [_omit(pid, "10")])
    assert lpo.status_code == 201, lpo.text
    assert _dec(lpo.json()["data"]["items"][0]["unit_price"]) == Decimal("90.00")
    lid = lpo.json()["data"]["id"]
    put_l = client.put(
        f"/api/v1/customer-purchase-orders/{lid}",
        json={"items": [_omit(pid, "1")]},
        headers=headers,
    )
    assert put_l.status_code == 200, put_l.text
    got_l = client.get(f"/api/v1/customer-purchase-orders/{lid}", headers=headers)
    assert got_l.status_code == 200, got_l.text
    assert _dec(got_l.json()["data"]["items"][0]["quantity"]) == Decimal("1.00")
    assert _dec(got_l.json()["data"]["items"][0]["unit_price"]) == Decimal("100.00")


def test_quote_convert_and_lpo_invoice_keep_frozen_price():
    headers, client_a, _, product = _ready("px_freeze")
    pid = product["id"]
    quote = _post_doc(headers, QUOTE_PATH, client_a, [_omit(pid, "10")])
    assert quote.status_code == 201, quote.text
    qid = quote.json()["data"]["id"]
    assert _dec(quote.json()["data"]["items"][0]["unit_price"]) == Decimal("80.00")
    assert (
        client.post(
            f"/api/v1/quotations/{qid}/send", json={}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/quotations/{qid}/accept", headers=headers).status_code
        == 200
    )
    lpo = _post_doc(headers, LPO_PATH, client_a, [_omit(pid, "10")])
    assert lpo.status_code == 201, lpo.text
    lid = lpo.json()["data"]["id"]
    rec = client.post(
        f"/api/v1/customer-purchase-orders/{lid}/receive", json={}, headers=headers
    )
    assert rec.status_code == 200, rec.text
    _wipe_to_list(headers, pid, "1.00")
    converted = client.post(
        f"/api/v1/quotations/{qid}/convert-to-invoice", headers=headers
    )
    assert converted.status_code == 201, converted.text
    assert _dec(converted.json()["data"]["items"][0]["unit_price"]) == Decimal("80.00")
    child = client.post(
        f"/api/v1/customer-purchase-orders/{lid}/invoices", json={}, headers=headers
    )
    assert child.status_code == 201, child.text
    assert _dec(child.json()["data"]["items"][0]["unit_price"]) == Decimal("80.00")


def test_preview_winning_price_hides_other_clients():
    headers, client_a, client_b, product = _ready("px_prev")
    pid = product["id"]
    a10 = _preview(headers, pid, "10", client_a)
    assert a10.status_code == 200, a10.text
    data_a = a10.json()["data"]
    assert _dec(data_a["unit_price"]) == Decimal("80.00")
    assert data_a["price_type"] == "CUSTOMER_SPECIFIC"
    blob = json.dumps(data_a, default=str)
    assert client_b not in blob
    b10 = _preview(headers, pid, "10", client_b)
    assert b10.status_code == 200, b10.text
    data_b = b10.json()["data"]
    assert _dec(data_b["unit_price"]) == Decimal("90.00")
    assert data_b["price_type"] == "TIER_1"
    none = _preview(headers, pid, "10")
    assert none.status_code == 200, none.text
    assert _dec(none.json()["data"]["unit_price"]) == Decimal("90.00")
    assert none.json()["data"]["client_id"] is None
    zero = _preview(headers, pid, "0", client_a)
    assert zero.status_code == 422, zero.text
    assert zero.json()["error"]["field"] == "quantity"


def test_workspace_b_resolved_price_404():
    headers_a, _, _, product = _ready("px_ws_a")
    token_b, _ = _register("px_ws_b", "WS B")
    r = _preview(_headers(token_b), product["id"], "1")
    assert r.status_code == 404, r.text


def test_member_dealer_book_and_client_b_invoice():
    token, workspace_id = _register("px_mem", "Member WS")
    headers = _headers(token)
    client_a = _create_client(headers, "Client A")
    client_b = _create_client(headers, "Client B")
    product = _seed_volume(headers, client_a)
    _add_price(
        headers,
        product["id"],
        {
            "price_type": "CUSTOMER_SPECIFIC",
            "price": "50.00",
            "client_id": client_b,
            "min_quantity": "100",
        },
    )
    member = _headers(_member_token(workspace_id))
    listed = client.get(f"/api/v1/products/{product['id']}/prices", headers=member)
    assert listed.status_code == 200, listed.text
    dealers = {
        row["client_id"]
        for row in listed.json()["data"]
        if row["price_type"] == "CUSTOMER_SPECIFIC"
    }
    assert client_a in dealers and client_b in dealers
    price = _invoice_price(member, client_b, [_omit(product["id"], "10")])
    assert price == Decimal("90.00")


def test_customer_highest_min_and_usd_debris_ignored():
    headers, client_a, _, product = _ready("px_min")
    pid = product["id"]
    _add_price(
        headers,
        pid,
        {
            "price_type": "CUSTOMER_SPECIFIC",
            "price": "70.00",
            "client_id": client_a,
            "min_quantity": "50",
        },
    )
    assert _invoice_price(headers, client_a, [_omit(pid, "10")]) == Decimal("80.00")
    assert _invoice_price(headers, client_a, [_omit(pid, "50")]) == Decimal("70.00")
    token, workspace_id = _register("px_usd", "USD debris WS")
    h2 = _headers(token)
    dealer = _create_client(h2, "Dealer")
    sku = _create_product(h2)
    _add_price(h2, sku["id"], {"price_type": "DEFAULT_SALES", "price": "100.00"})

    async def _debris() -> None:
        async with TestingSessionLocal() as session:
            session.add(
                ProductPrice(
                    workspace_id=uuid.UUID(workspace_id),
                    product_id=uuid.UUID(sku["id"]),
                    price_type="CUSTOMER_SPECIFIC",
                    currency="USD",
                    price=Decimal("1.00"),
                    client_id=uuid.UUID(dealer),
                    min_quantity=Decimal("1"),
                )
            )
            await session.commit()

    asyncio.run(_debris())
    assert _invoice_price(h2, dealer, [_omit(sku["id"], "1")]) == Decimal("100.00")


def test_schema_not_float_and_alembic_head():
    for name, field in ResolvedPriceResponse.model_fields.items():
        annotation = field.annotation
        assert annotation is not float, f"{name} is float"
        assert float not in get_args(annotation), f"{name} allows float"
    alembic_bin = shutil.which("alembic")
    assert alembic_bin, "alembic CLI not found"

    def _alembic(*args: str) -> str:
        run = subprocess.run(
            [alembic_bin, *args], cwd=BACKEND_DIR, capture_output=True, text=True
        )
        assert run.returncode == 0, run.stdout + run.stderr
        return run.stdout + run.stderr

    assert "b8d5f0c3a216" in _alembic("heads")
    assert "No new upgrade operations detected" in _alembic("check")
