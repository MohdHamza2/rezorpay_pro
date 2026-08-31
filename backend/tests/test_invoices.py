"""WP-A FTA tax invoice API tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test`` (same URL
derivation as ``test_multi_tenant_isolation.py``). Never SQLite.
"""

import asyncio
import sys
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

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

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

VALID_TRN = "100123456789012"
MUTATED_TRN = "100987654321098"
GARBAGE_TAX_ID = "NOT-A-TRN-16CHARS+"
SELLER_ADDRESS = "Warehouse 12, Al Quoz, Dubai"
BUYER_ADDRESS = "Plot 4, Mussafah, Abu Dhabi"
MUTATED_ADDRESS = "New Plot, DIP, Dubai"


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


def _set_workspace_fta(
    headers: dict, trn: str = VALID_TRN, address: str = SELLER_ADDRESS
) -> None:
    r = client.put(
        "/api/v1/workspaces/me",
        json={"trn": trn, "address": address},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def _invoice_payload(client_id: str, items: list[dict], **extra) -> dict:
    body = {
        "client_id": client_id,
        "issue_date": "2026-08-26",
        "due_date": "2026-09-26",
        "items": items,
    }
    body.update(extra)
    return body


def _create_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(client_id, items, **extra),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


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


def test_omit_tax_rate_inherits_workspace_default_5_percent():
    token, _ = _register("tax_inherit", "Tax Inherit WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "10", "unit_price": "100.00"}],
    )
    line = data["items"][0]
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    assert _dec(line["line_net"]) == Decimal("1000.00")
    assert _dec(line["tax_amount"]) == Decimal("50.00")
    assert _dec(data["tax_amount"]) == Decimal("50.00")
    assert _dec(data["subtotal"]) == Decimal("1000.00")
    assert _dec(data["total_amount"]) == Decimal("1050.00")


def test_explicit_tax_rate_zero_stays_zero():
    token, _ = _register("tax_zero", "Tax Zero WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [
            {
                "description": "Zero-rated",
                "quantity": "2",
                "unit_price": "50.00",
                "tax_rate": "0",
            }
        ],
    )
    line = data["items"][0]
    assert _dec(line["tax_rate"]) == Decimal("0")
    assert _dec(line["tax_amount"]) == Decimal("0.00")
    assert _dec(data["tax_amount"]) == Decimal("0.00")
    assert _dec(data["total_amount"]) == Decimal("100.00")


def test_line_money_round_half_up_and_header_identity():
    token, _ = _register("money_rnd", "Money WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [
            {
                "description": "Fils rounding",
                "quantity": "3",
                "unit_price": "1.11",
                "tax_rate": "5",
            }
        ],
    )
    line_net = _money(Decimal("3") * Decimal("1.11"))
    line_vat = _money(line_net * Decimal("5") / Decimal("100"))
    line = data["items"][0]
    assert _dec(line["line_net"]) == line_net
    assert _dec(line["tax_amount"]) == line_vat
    assert _dec(data["subtotal"]) + _dec(data["tax_amount"]) == _dec(
        data["total_amount"]
    )
    assert _dec(data["subtotal"]) + _dec(data["tax_amount"]) == _dec(
        line["total_price"]
    )


def test_line_discount_percent_vat_on_net():
    token, _ = _register("disc_pct", "Disc WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [
            {
                "description": "Discounted",
                "quantity": "2",
                "unit_price": "100.00",
                "tax_rate": "5",
                "discount_percent": "10",
            }
        ],
    )
    line = data["items"][0]
    assert _dec(line["line_net"]) == Decimal("180.00")
    assert _dec(line["tax_amount"]) == Decimal("9.00")
    assert _dec(line["total_price"]) == Decimal("189.00")
    assert _dec(data["subtotal"]) == Decimal("180.00")


def test_both_discount_fields_422():
    token, _ = _register("disc_xor", "XOR WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_id,
            [
                {
                    "description": "Bad",
                    "quantity": "1",
                    "unit_price": "10",
                    "discount_percent": "5",
                    "discount_amount": "1",
                }
            ],
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_product_id_copies_catalog_and_allows_override():
    token, _ = _register("prod_copy", "Catalog WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    product = _create_catalog_product(
        headers, name="NYM 3x2.5", sku="NYM-325", price="12.50"
    )
    data = _create_invoice(
        headers,
        client_id,
        [{"product_id": product["id"], "quantity": "4"}],
    )
    line = data["items"][0]
    assert line["description"] == "NYM 3x2.5"
    assert line["sku_snapshot"] == "NYM-325"
    assert line["uom_id"] == product["uom_id"]
    assert line["product_id"] == product["id"]
    assert _dec(line["unit_price"]) == Decimal("12.50")
    assert _dec(line["tax_rate"]) == Decimal("5.00")
    assert _dec(line["line_net"]) == Decimal("50.00")

    overridden = _create_invoice(
        headers,
        client_id,
        [
            {
                "product_id": product["id"],
                "quantity": "1",
                "description": "Site extra NYM",
            }
        ],
    )
    assert overridden["items"][0]["description"] == "Site extra NYM"
    assert overridden["items"][0]["sku_snapshot"] == "NYM-325"


def test_product_id_other_workspace_404_and_inactive_400():
    token_a, _ = _register("prod_a", "WS A")
    headers_a = _headers(token_a)
    product = _create_catalog_product(headers_a)

    token_b, _ = _register("prod_b", "WS B")
    headers_b = _headers(token_b)
    client_b = _create_client(headers_b)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_b, [{"product_id": product["id"], "quantity": "1"}]
        ),
        headers=headers_b,
    )
    assert r.status_code == 404, r.text

    inactive = _create_catalog_product(
        headers_a, name="Old SKU", sku=f"OLD-{uuid.uuid4().hex[:6]}"
    )
    r = client.put(
        f"/api/v1/products/{inactive['id']}",
        json={"is_active": False},
        headers=headers_a,
    )
    assert r.status_code == 200, r.text
    client_a = _create_client(headers_a)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_a, [{"product_id": inactive["id"], "quantity": "1"}]
        ),
        headers=headers_a,
    )
    assert r.status_code == 400, r.text


def test_adhoc_line_without_product_id_201():
    token, _ = _register("adhoc", "Adhoc WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [{"description": "Cutting charge", "quantity": "1", "unit_price": "25.00"}],
    )
    assert data["items"][0]["product_id"] is None
    assert data["items"][0]["sku_snapshot"] is None
    assert _dec(data["items"][0]["tax_rate"]) == Decimal("5.00")


def test_send_without_workspace_trn_400_stays_draft():
    token, _ = _register("no_trn", "No TRN WS")
    headers = _headers(token)
    _set_workspace_fta(headers, trn="", address=SELLER_ADDRESS)
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["code"] == "FTA_SEND_BLOCKED"
    assert err["field"] == "workspace.trn"
    got = client.get(f"/api/v1/invoices/{inv['id']}", headers=headers)
    assert got.json()["data"]["status"] == "DRAFT"


def test_send_invalid_trn_400():
    token, _ = _register("bad_trn", "Bad TRN WS")
    headers = _headers(token)
    _set_workspace_fta(headers, trn="200123456789012", address=SELLER_ADDRESS)
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "FTA_SEND_BLOCKED"
    assert r.json()["error"]["field"] == "workspace.trn"

    _set_workspace_fta(headers, trn="100123", address=SELLER_ADDRESS)
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["field"] == "workspace.trn"


def test_send_without_workspace_address_400():
    token, _ = _register("no_addr", "No Addr WS")
    headers = _headers(token)
    _set_workspace_fta(headers, trn=VALID_TRN, address="  ")
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "FTA_SEND_BLOCKED"
    assert r.json()["error"]["field"] == "workspace.address"


def test_standard_send_requires_buyer_trn_and_address():
    token, _ = _register("std_req", "Standard WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(headers)
    high = _create_invoice(
        headers,
        client_id,
        [{"description": "Panel", "quantity": "100", "unit_price": "120.00"}],
    )
    assert _dec(high["total_amount"]) > Decimal("10000.00")
    r = client.post(f"/api/v1/invoices/{high['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "FTA_SEND_BLOCKED"
    assert r.json()["error"]["field"] == "client.tax_id"

    b2b = _create_client(headers, name="B2B", tax_id=VALID_TRN)
    small = _create_invoice(
        headers,
        b2b,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    r = client.post(f"/api/v1/invoices/{small['id']}/send", json={}, headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["field"] == "client.address"


def test_simplified_send_succeeds_and_freezes_snapshots():
    token, _ = _register("simp_ok", "Simplified WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(headers, name="Cash buyer")
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "2", "unit_price": "100.00"}],
    )
    assert _dec(inv["total_amount"]) <= Decimal("10000.00")
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["invoice_kind"] == "SIMPLIFIED"
    assert data["seller_trn_snapshot"] == VALID_TRN
    assert data["seller_address_snapshot"] == SELLER_ADDRESS
    assert data["seller_name_snapshot"]
    assert data["buyer_name_snapshot"] == "Cash buyer"
    assert data["buyer_trn_snapshot"] is None
    assert data["amount_paid"] is not None
    assert data["balance_due"] is not None


def test_standard_send_succeeds_and_freezes_snapshots():
    token, _ = _register("std_ok", "Standard OK WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(
        headers, name="B2B Dealer", tax_id=VALID_TRN, address=BUYER_ADDRESS
    )
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10.00"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["invoice_kind"] == "STANDARD"
    assert data["seller_trn_snapshot"] == VALID_TRN
    assert data["seller_address_snapshot"] == SELLER_ADDRESS
    assert data["seller_name_snapshot"]
    assert data["buyer_trn_snapshot"] == VALID_TRN
    assert data["buyer_address_snapshot"] == BUYER_ADDRESS
    assert data["buyer_name_snapshot"] == "B2B Dealer"


def test_snapshots_immutable_after_send():
    token, _ = _register("snap_immut", "Snapshot WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(
        headers, name="B2B Dealer", tax_id=VALID_TRN, address=BUYER_ADDRESS
    )
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10.00"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    frozen = r.json()["data"]

    r = client.put(
        f"/api/v1/invoices/{inv['id']}",
        json={"notes": "should fail"},
        headers=headers,
    )
    assert r.status_code in (400, 403), r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"

    _set_workspace_fta(headers, trn=MUTATED_TRN, address=MUTATED_ADDRESS)
    r = client.put(
        f"/api/v1/clients/{client_id}",
        json={"tax_id": MUTATED_TRN, "address": MUTATED_ADDRESS, "name": "Renamed"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    got = client.get(f"/api/v1/invoices/{inv['id']}", headers=headers)
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["seller_trn_snapshot"] == frozen["seller_trn_snapshot"] == VALID_TRN
    assert data["seller_address_snapshot"] == frozen["seller_address_snapshot"]
    assert data["seller_name_snapshot"] == frozen["seller_name_snapshot"]
    assert data["buyer_trn_snapshot"] == frozen["buyer_trn_snapshot"] == VALID_TRN
    assert data["buyer_address_snapshot"] == frozen["buyer_address_snapshot"]
    assert data["buyer_name_snapshot"] == frozen["buyer_name_snapshot"]
    assert data["invoice_kind"] == "STANDARD"


def test_simplified_send_does_not_snapshot_invalid_tax_id():
    token, _ = _register("simp_junk", "Simplified Junk WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(
        headers, name="Cash buyer", tax_id=GARBAGE_TAX_ID, address=BUYER_ADDRESS
    )
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "2", "unit_price": "100.00"}],
    )
    assert _dec(inv["total_amount"]) <= Decimal("10000.00")
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["invoice_kind"] == "SIMPLIFIED"
    assert data["buyer_trn_snapshot"] is None
    assert data["seller_trn_snapshot"] == VALID_TRN
    assert GARBAGE_TAX_ID not in (data["buyer_trn_snapshot"] or "")


def test_put_non_draft_403_invalid_state():
    token, _ = _register("put_sent", "Put Sent WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.put(
        f"/api/v1/invoices/{inv['id']}",
        json={"notes": "should fail"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_item_extra_key_hs_code_422():
    token, _ = _register("extra_item", "Extra Item WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_id,
            [
                {
                    "description": "Cable",
                    "quantity": "1",
                    "unit_price": "10",
                    "hs_code": "8544.49",
                }
            ],
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_header_discount_amount_extra_key_422():
    token, _ = _register("hdr_disc", "Header Disc WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    body = _invoice_payload(
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    body["discount_amount"] = "50.00"
    r = client.post("/api/v1/invoices", json=body, headers=headers)
    assert r.status_code == 422, r.text


def test_supply_date_after_issue_date_422():
    token, _ = _register("supply_bad", "Supply WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_id,
            [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
            supply_date="2026-08-27",
            issue_date="2026-08-26",
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_supply_date_defaults_to_issue_date():
    token, _ = _register("supply_def", "Supply Def WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    data = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
    )
    assert data["supply_date"] == data["issue_date"]
    assert data["invoice_kind"] is None


def test_workspace_address_round_trip():
    token, _ = _register("ws_addr", "Addr WS")
    headers = _headers(token)
    r = client.put(
        "/api/v1/workspaces/me",
        json={"address": SELLER_ADDRESS, "trn": VALID_TRN},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["address"] == SELLER_ADDRESS
    got = client.get("/api/v1/workspaces/me", headers=headers)
    assert got.json()["data"]["address"] == SELLER_ADDRESS
    assert got.json()["data"]["trn"] == VALID_TRN


def test_overpayment_still_400():
    token, _ = _register("overpay", "Overpay WS")
    headers = _headers(token)
    _set_workspace_fta(headers)
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "Cable", "quantity": "1", "unit_price": "100.00"}],
    )
    r = client.post(f"/api/v1/invoices/{inv['id']}/send", json={}, headers=headers)
    assert r.status_code == 200, r.text
    total = _dec(r.json()["data"]["total_amount"])
    pay = client.post(
        f"/api/v1/invoices/{inv['id']}/payments",
        json={
            "amount": str(total + Decimal("1.00")),
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
        },
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert pay.status_code == 400, pay.text
    assert pay.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"


def test_draft_put_recalculates_line_math():
    token, _ = _register("put_math", "Put Math WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    inv = _create_invoice(
        headers,
        client_id,
        [{"description": "A", "quantity": "1", "unit_price": "10.00"}],
    )
    r = client.put(
        f"/api/v1/invoices/{inv['id']}",
        json={
            "items": [
                {
                    "description": "B",
                    "quantity": "2",
                    "unit_price": "10.00",
                    "tax_rate": "5",
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert _dec(data["subtotal"]) == Decimal("20.00")
    assert _dec(data["tax_amount"]) == Decimal("1.00")
    assert _dec(data["total_amount"]) == Decimal("21.00")


def test_usd_currency_422():
    token, _ = _register("usd_block", "USD WS")
    headers = _headers(token)
    client_id = _create_client(headers)
    r = client.post(
        "/api/v1/invoices",
        json=_invoice_payload(
            client_id,
            [{"description": "Cable", "quantity": "1", "unit_price": "10"}],
            currency="USD",
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text
