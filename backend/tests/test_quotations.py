"""WP-A quotations API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.
"""

import asyncio
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.quotation import Quotation
from app.services.quotation_service import QuotationService

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

YEAR = datetime.now().year


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


def _utc_today():
    return datetime.now(timezone.utc).date()


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


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _create_client(headers: dict, name: str = "Dealer", **extra) -> str:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _adhoc_item(**extra) -> dict:
    item = {
        "description": "NYM 3x2.5 cable",
        "quantity": "10",
        "unit_price": "100.00",
    }
    item.update(extra)
    return item


def _quote_payload(client_id: str, items: list[dict], **extra) -> dict:
    body = {"client_id": client_id, "items": items}
    body.update(extra)
    return body


def _create_quote(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    r = client.post(
        "/api/v1/quotations",
        json=_quote_payload(client_id, items, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _send(headers: dict, quote_id: str):
    return client.post(f"/api/v1/quotations/{quote_id}/send", json={}, headers=headers)


def _accept(headers: dict, quote_id: str):
    return client.post(f"/api/v1/quotations/{quote_id}/accept", headers=headers)


def _reject(headers: dict, quote_id: str, reason: str | None = None):
    body = {} if reason is None else {"reason": reason}
    return client.post(
        f"/api/v1/quotations/{quote_id}/reject", json=body, headers=headers
    )


def _convert(headers: dict, quote_id: str):
    return client.post(
        f"/api/v1/quotations/{quote_id}/convert-to-invoice", headers=headers
    )


def _convert_lpo(headers: dict, quote_id: str, body: dict | None = None):
    return client.post(
        f"/api/v1/quotations/{quote_id}/convert-to-lpo",
        json=body or {},
        headers=headers,
    )


def _db_quote_status(quote_id: str) -> str:
    """Read status from PostgreSQL. Do not use GET — GET expires on-read."""

    async def _read() -> str:
        async with TestingSessionLocal() as session:
            result = await session.execute(
                select(Quotation.status).where(Quotation.id == uuid.UUID(quote_id))
            )
            value = result.scalar_one()
            return value.value if hasattr(value, "value") else str(value)

    return asyncio.run(_read())


def _create_uom(headers: dict) -> str:
    r = client.post(
        "/api/v1/products/uom",
        json={"name": "Metres", "code": f"MTR-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_catalog_product(
    headers: dict,
    *,
    name: str = "NYM cable",
    sku: str | None = None,
    tax_rate: str | None = "5.00",
    price: str = "12.50",
    is_active: bool = True,
) -> dict:
    uom_id = _create_uom(headers)
    product_body: dict[str, Any] = {
        "name": name,
        "internal_sku": sku or f"ELE-{uuid.uuid4().hex[:8]}",
        "base_uom_id": uom_id,
        "is_active": is_active,
    }
    if tax_rate is not None:
        product_body["tax_rate"] = tax_rate
    r = client.post("/api/v1/products", json=product_body, headers=headers)
    assert r.status_code == 201, r.text
    product = r.json()["data"]
    pr = client.post(
        f"/api/v1/products/{product['id']}/prices",
        json={"price_type": "DEFAULT_SALES", "price": price},
        headers=headers,
    )
    assert pr.status_code == 201, pr.text
    product["uom_id"] = uom_id
    product["list_price"] = price
    return product


def test_create_sequential_quotation_numbers():
    token, _ = _register("quo_num", "Quote Number WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    first = _create_quote(headers, client_id, [_adhoc_item()])
    second = _create_quote(headers, client_id, [_adhoc_item(description="Second")])
    assert first["quotation_number"] == f"QUO-{YEAR}-0001"
    assert second["quotation_number"] == f"QUO-{YEAR}-0002"
    assert first["status"] == "DRAFT"
    today = _utc_today()
    assert first["quotation_date"] == today.isoformat()
    assert first["valid_until"] == (today + timedelta(days=14)).isoformat()


def test_omit_tax_rate_inherits_workspace_default_5_percent():
    token, _ = _register("quo_tax", "Quote Tax WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_quote(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "10", "unit_price": "100.00"}],
    )
    line = data["items"][0]
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    assert _dec(line["line_net"]) == Decimal("1000.00")
    assert _dec(line["tax_amount"]) == Decimal("50.00")
    assert _dec(line["total_price"]) == Decimal("1050.00")
    assert _dec(data["subtotal"]) == Decimal("1000.00")
    assert _dec(data["tax_amount"]) == Decimal("50.00")
    assert _dec(data["total_amount"]) == Decimal("1050.00")


def test_xor_discounts_and_extra_key_and_non_aed():
    token, _ = _register("quo_xor", "Quote XOR WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    both = client.post(
        "/api/v1/quotations",
        json=_quote_payload(
            client_id,
            [
                {
                    "description": "Cable",
                    "quantity": "1",
                    "unit_price": "100",
                    "discount_percent": "10",
                    "discount_amount": "5",
                }
            ],
        ),
        headers=headers,
    )
    assert both.status_code == 422, both.text
    extra = client.post(
        "/api/v1/quotations",
        json=_quote_payload(
            client_id,
            [
                {
                    "description": "Cable",
                    "quantity": "1",
                    "unit_price": "100",
                    "hs_code": "8544",
                }
            ],
        ),
        headers=headers,
    )
    assert extra.status_code == 422, extra.text
    usd = client.post(
        "/api/v1/quotations",
        json=_quote_payload(
            client_id,
            [_adhoc_item()],
            currency="USD",
        ),
        headers=headers,
    )
    assert usd.status_code == 422, usd.text
    pct = _create_quote(
        headers,
        client_id,
        [
            {
                "description": "Cable",
                "quantity": "10",
                "unit_price": "100.00",
                "discount_percent": "10",
            }
        ],
    )
    assert _dec(pct["items"][0]["line_net"]) == Decimal("900.00")
    assert _dec(pct["items"][0]["tax_amount"]) == Decimal("45.00")
    assert _dec(pct["total_amount"]) == Decimal("945.00")


def test_product_id_copies_catalog_other_workspace_404_inactive_400_adhoc_201():
    token_a, _ = _register("quo_prod_a", "Quote Prod A")
    headers_a = _headers(token_a)
    client_id = _create_client(headers_a)
    product = _create_catalog_product(
        headers_a, name="NYM 3x1.5", sku="NYM-315", price="12.50"
    )
    quoted = _create_quote(
        headers_a,
        client_id,
        [{"product_id": product["id"], "quantity": "4", "unit_price": "20.00"}],
    )
    line = quoted["items"][0]
    assert line["product_id"] == product["id"]
    assert line["sku_snapshot"] == "NYM-315"
    assert line["description"] == "NYM 3x1.5"
    assert _dec(line["unit_price"]) == Decimal("20.00")
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    adhoc = _create_quote(headers_a, client_id, [_adhoc_item(description="Ad-hoc")])
    assert adhoc["items"][0]["product_id"] is None

    token_b, _ = _register("quo_prod_b", "Quote Prod B")
    headers_b = _headers(token_b)
    client_b = _create_client(headers_b)
    product_b = _create_catalog_product(headers_b, name="Other WS SKU")
    cross = client.post(
        "/api/v1/quotations",
        json=_quote_payload(
            client_id, [{"product_id": product_b["id"], "quantity": "1"}]
        ),
        headers=headers_a,
    )
    assert cross.status_code == 404, cross.text
    inactive = _create_catalog_product(headers_a, name="Dead SKU", is_active=False)
    dead = client.post(
        "/api/v1/quotations",
        json=_quote_payload(
            client_id, [{"product_id": inactive["id"], "quantity": "1"}]
        ),
        headers=headers_a,
    )
    assert dead.status_code == 400, dead.text
    msg = dead.json()["error"]["message"].lower()
    assert "quotation" in msg
    assert "invoice" not in msg
    foreign_client = client.post(
        "/api/v1/quotations",
        json=_quote_payload(client_b, [_adhoc_item()]),
        headers=headers_a,
    )
    assert foreign_client.status_code == 404, foreign_client.text


def test_put_delete_send_non_draft_403():
    token, _ = _register("quo_state", "Quote State WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    sent = _send(headers, quote["id"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["status"] == "SENT"
    put = client.put(
        f"/api/v1/quotations/{quote['id']}",
        json={"notes": "nope"},
        headers=headers,
    )
    assert put.status_code == 403, put.text
    assert put.json()["error"]["code"] == "INVALID_STATE"
    delete = client.delete(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert delete.status_code == 403, delete.text
    assert delete.json()["error"]["code"] == "INVALID_STATE"
    again = _send(headers, quote["id"])
    assert again.status_code == 403, again.text
    assert again.json()["error"]["code"] == "INVALID_STATE"


def test_isolation_workspace_b_404():
    token_a, _ = _register("quo_iso_a", "Quote Iso A")
    headers_a = _headers(token_a)
    client_id = _create_client(headers_a)
    quote = _create_quote(headers_a, client_id, [_adhoc_item()])
    token_b, _ = _register("quo_iso_b", "Quote Iso B")
    headers_b = _headers(token_b)
    qid = quote["id"]
    assert client.get(f"/api/v1/quotations/{qid}", headers=headers_b).status_code == 404
    assert (
        client.put(
            f"/api/v1/quotations/{qid}", json={"notes": "x"}, headers=headers_b
        ).status_code
        == 404
    )
    assert _send(headers_b, qid).status_code == 404
    assert _accept(headers_b, qid).status_code == 404
    assert _convert(headers_b, qid).status_code == 404
    assert _convert_lpo(headers_b, qid).status_code == 404


def test_send_does_not_require_workspace_trn():
    token, _ = _register("quo_no_trn", "Quote No TRN WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    sent = _send(headers, quote["id"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["status"] == "SENT"


def test_accept_convert_draft_invoice_frozen_prices():
    token, _ = _register("quo_conv", "Quote Convert WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    product = _create_catalog_product(headers, price="12.50")
    quote = _create_quote(
        headers,
        client_id,
        [
            {
                "product_id": product["id"],
                "quantity": "2",
                "unit_price": "20.00",
                "tax_rate": "5.00",
            }
        ],
        notes="Site visit included",
    )
    assert _send(headers, quote["id"]).status_code == 200
    accepted = _accept(headers, quote["id"])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "ACCEPTED"
    converted = _convert(headers, quote["id"])
    assert converted.status_code == 201, converted.text
    inv = converted.json()["data"]
    assert inv["status"] == "DRAFT"
    assert inv["quotation_id"] == quote["id"]
    assert inv["invoice_number"].startswith(f"INV-{YEAR}-")
    assert inv["invoice_kind"] is None
    assert inv["seller_trn_snapshot"] is None
    assert inv["buyer_trn_snapshot"] is None
    assert _dec(inv["items"][0]["unit_price"]) == Decimal("20.00")
    assert inv["items"][0]["quantity"] == quote["items"][0]["quantity"] or _dec(
        inv["items"][0]["quantity"]
    ) == Decimal("2.00")
    today = _utc_today()
    assert inv["issue_date"] == today.isoformat()
    assert inv["supply_date"] == today.isoformat()
    assert inv["due_date"] == (today + timedelta(days=30)).isoformat()
    assert inv["notes"].startswith(f"Converted from {quote['quotation_number']}.")
    got = client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["status"] == "CONVERTED"
    assert got.json()["data"]["converted_invoice_id"] == inv["id"]


def test_convert_twice_200_same_invoice():
    token, _ = _register("quo_idem", "Quote Idem WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    assert _accept(headers, quote["id"]).status_code == 200
    first = _convert(headers, quote["id"])
    assert first.status_code == 201, first.text
    invoice_id = first.json()["data"]["id"]
    second = _convert(headers, quote["id"])
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == invoice_id
    listed = client.get("/api/v1/invoices", headers=headers)
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json()["data"] if row["id"] == invoice_id]
    assert len(rows) == 1


def test_convert_from_sent_or_draft_403():
    token, _ = _register("quo_bad_conv", "Quote Bad Convert WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    draft = _create_quote(headers, client_id, [_adhoc_item()])
    r = _convert(headers, draft["id"])
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"
    assert _send(headers, draft["id"]).status_code == 200
    r = _convert(headers, draft["id"])
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_on_read_expiry_blocks_accept_and_convert():
    token, _ = _register("quo_exp", "Quote Expire WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    yesterday = (_utc_today() - timedelta(days=1)).isoformat()
    quote = _create_quote(
        headers,
        client_id,
        [_adhoc_item()],
        quotation_date=yesterday,
        valid_until=yesterday,
    )
    assert _send(headers, quote["id"]).status_code == 200
    got = client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["status"] == "EXPIRED"
    assert _accept(headers, quote["id"]).status_code == 403
    assert _accept(headers, quote["id"]).json()["error"]["code"] == "INVALID_STATE"
    conv = _convert(headers, quote["id"])
    assert conv.status_code == 403, conv.text
    assert conv.json()["error"]["code"] == "INVALID_STATE"


def test_accept_reject_convert_persist_expiry_without_prior_get():
    token, _ = _register("quo_exp_persist", "Quote Expire Persist WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    yesterday = (_utc_today() - timedelta(days=1)).isoformat()

    def _expired_sent() -> str:
        quote = _create_quote(
            headers,
            client_id,
            [_adhoc_item()],
            quotation_date=yesterday,
            valid_until=yesterday,
        )
        assert _send(headers, quote["id"]).status_code == 200
        assert _db_quote_status(quote["id"]) == "SENT"
        return quote["id"]

    accept_id = _expired_sent()
    acc = _accept(headers, accept_id)
    assert acc.status_code == 403, acc.text
    assert acc.json()["error"]["code"] == "INVALID_STATE"
    assert _db_quote_status(accept_id) == "EXPIRED"

    reject_id = _expired_sent()
    rej = _reject(headers, reject_id)
    assert rej.status_code == 403, rej.text
    assert rej.json()["error"]["code"] == "INVALID_STATE"
    assert _db_quote_status(reject_id) == "EXPIRED"

    convert_id = _expired_sent()
    conv = _convert(headers, convert_id)
    assert conv.status_code == 403, conv.text
    assert conv.json()["error"]["code"] == "INVALID_STATE"
    assert _db_quote_status(convert_id) == "EXPIRED"


def test_converted_invoice_hydration_is_workspace_scoped():
    token_a, workspace_a = _register("quo_hyd_a", "Quote Hydrate A")
    headers_a = _headers(token_a)
    client_id = _create_client(headers_a)
    quote = _create_quote(headers_a, client_id, [_adhoc_item()])
    assert _send(headers_a, quote["id"]).status_code == 200
    assert _accept(headers_a, quote["id"]).status_code == 200
    converted = _convert(headers_a, quote["id"])
    assert converted.status_code == 201, converted.text
    invoice_id = converted.json()["data"]["id"]
    quote_uuid = uuid.UUID(quote["id"])
    invoice_uuid = uuid.UUID(invoice_id)

    async def _map(workspace_id: str) -> dict:
        async with TestingSessionLocal() as session:
            return await QuotationService.map_converted_ids(
                session, [quote_uuid], uuid.UUID(workspace_id)
            )

    own = asyncio.run(_map(workspace_a))
    assert own.get(quote_uuid) == invoice_uuid
    _, workspace_b = _register("quo_hyd_b", "Quote Hydrate B")
    assert asyncio.run(_map(workspace_b)) == {}


def test_reject_then_convert_403():
    token, _ = _register("quo_rej", "Quote Reject WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    rejected = _reject(headers, quote["id"], reason="Price too high")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert rejected.json()["data"]["rejection_reason"] == "Price too high"
    conv = _convert(headers, quote["id"])
    assert conv.status_code == 403, conv.text
    assert conv.json()["error"]["code"] == "INVALID_STATE"


def test_convert_does_not_run_fta_send_quote_stays_converted():
    token, _ = _register("quo_fta", "Quote FTA WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    assert _accept(headers, quote["id"]).status_code == 200
    converted = _convert(headers, quote["id"])
    assert converted.status_code == 201, converted.text
    invoice_id = converted.json()["data"]["id"]
    send_inv = client.post(
        f"/api/v1/invoices/{invoice_id}/send", json={}, headers=headers
    )
    assert send_inv.status_code == 400, send_inv.text
    assert send_inv.json()["error"]["code"] == "FTA_SEND_BLOCKED"
    got = client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert got.json()["data"]["status"] == "CONVERTED"


def test_soft_delete_draft_404_number_not_reused():
    token, _ = _register("quo_del", "Quote Delete WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    first = _create_quote(headers, client_id, [_adhoc_item()])
    assert first["quotation_number"] == f"QUO-{YEAR}-0001"
    deleted = client.delete(f"/api/v1/quotations/{first['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    missing = client.get(f"/api/v1/quotations/{first['id']}", headers=headers)
    assert missing.status_code == 404, missing.text
    second = _create_quote(headers, client_id, [_adhoc_item(description="Next")])
    assert second["quotation_number"] == f"QUO-{YEAR}-0002"


def test_convert_after_invoice_soft_delete_409():
    token, _ = _register("quo_409", "Quote 409 WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    assert _accept(headers, quote["id"]).status_code == 200
    converted = _convert(headers, quote["id"])
    assert converted.status_code == 201, converted.text
    invoice_id = converted.json()["data"]["id"]
    deleted = client.delete(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    again = _convert(headers, quote["id"])
    assert again.status_code == 409, again.text
    err = again.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["field"] == "quotation_id"
    listed = client.get("/api/v1/invoices", headers=headers)
    assert listed.json()["data"] == []
    lpo = _convert_lpo(headers, quote["id"])
    assert lpo.status_code == 409, lpo.text
    assert lpo.json()["error"]["code"] == "CONFLICT"
    assert lpo.json()["error"]["field"] == "quotation_id"


def test_convert_to_lpo_then_invoice_409():
    token, _ = _register("quo_lpo_mutex", "Quote LPO Mutex WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    assert _accept(headers, quote["id"]).status_code == 200
    first = _convert_lpo(headers, quote["id"])
    assert first.status_code == 201, first.text
    lpo = first.json()["data"]
    assert lpo["status"] == "DRAFT"
    assert lpo["quotation_id"] == quote["id"]
    assert lpo["lpo_number"].startswith(f"LPO-{YEAR}-")
    second = _convert_lpo(headers, quote["id"])
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == lpo["id"]
    invoice = _convert(headers, quote["id"])
    assert invoice.status_code == 409, invoice.text
    assert invoice.json()["error"]["code"] == "CONFLICT"
    assert invoice.json()["error"]["field"] == "quotation_id"
    got = client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert got.json()["data"]["status"] == "CONVERTED"
    assert got.json()["data"]["converted_lpo_id"] == lpo["id"]
    assert got.json()["data"]["converted_invoice_id"] is None


def test_convert_to_invoice_then_lpo_409():
    token, _ = _register("quo_inv_mutex", "Quote INV Mutex WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    quote = _create_quote(headers, client_id, [_adhoc_item()])
    assert _send(headers, quote["id"]).status_code == 200
    assert _accept(headers, quote["id"]).status_code == 200
    invoice = _convert(headers, quote["id"])
    assert invoice.status_code == 201, invoice.text
    lpo = _convert_lpo(headers, quote["id"])
    assert lpo.status_code == 409, lpo.text
    assert lpo.json()["error"]["code"] == "CONFLICT"
    assert lpo.json()["error"]["field"] == "quotation_id"


def test_concurrent_quotation_numbers_unique():
    token, _ = _register("quo_race", "Quote Race WS")
    headers = _headers(token)
    client_id = _create_client(headers)

    def create_one(index: int) -> str:
        r = client.post(
            "/api/v1/quotations",
            json=_quote_payload(
                client_id,
                [
                    {
                        "description": f"Item {index}",
                        "quantity": "1",
                        "unit_price": "10.00",
                    }
                ],
            ),
            headers=headers,
        )
        assert r.status_code == 201, f"Quote {index} failed: {r.text}"
        return r.json()["data"]["quotation_number"]

    with ThreadPoolExecutor(max_workers=5) as executor:
        numbers = list(executor.map(create_one, range(10)))
    assert len(numbers) == len(set(numbers)), numbers
    seq = sorted(int(num.split("-")[-1]) for num in numbers)
    assert seq == list(range(1, 11)), seq
