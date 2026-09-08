import asyncio
import sys
import uuid
from decimal import Decimal
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
from app.models.enquiry import EnquiryStatus, EnquirySource

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


def _create_client(headers: dict, name: str = "Dealer", **extra) -> str:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_uom(headers: dict) -> str:
    r = client.post(
        "/api/v1/products/uom",
        json={"name": "Metres", "code": f"MTR-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_catalog_product(headers: dict) -> dict:
    uom_id = _create_uom(headers)
    product_body: dict[str, Any] = {
        "name": "Cable",
        "internal_sku": f"ELE-{uuid.uuid4().hex[:8]}",
        "base_uom_id": uom_id,
        "is_active": True,
    }
    r = client.post("/api/v1/products", json=product_body, headers=headers)
    assert r.status_code == 201, r.text
    product = r.json()["data"]
    pr = client.post(
        f"/api/v1/products/{product['id']}/prices",
        json={"price_type": "DEFAULT_SALES", "price": "10.0"},
        headers=headers,
    )
    assert pr.status_code == 201, pr.text
    product["uom_id"] = uom_id
    return product


def test_create_enquiry():
    token, _ = _register("enq_create", "Enq WS")
    headers = _headers(token)
    product = _create_catalog_product(headers)

    payload = {
        "source": EnquirySource.MANUAL.value,
        "contact_name": "Test Contact",
        "contact_phone": "+1234567890",
        "items_description": "We need some products",
        "items": [
            {
                "product_id": product["id"],
                "description": product["name"],
                "quantity_requested": "10",
                "uom_id": product["uom_id"],
            }
        ],
    }

    response = client.post("/api/v1/enquiries", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["enquiry_number"].startswith("ENQ-")
    assert data["status"] == EnquiryStatus.NEW.value
    assert data["source"] == EnquirySource.MANUAL.value
    assert data["contact_name"] == "Test Contact"
    assert len(data["items"]) == 1
    assert _dec(data["items"][0]["quantity_requested"]) == Decimal("10")


def test_update_enquiry():
    token, _ = _register("enq_update", "Enq Upd WS")
    headers = _headers(token)

    payload = {
        "source": EnquirySource.MANUAL.value,
        "contact_name": "Old Contact",
        "items": [],
    }
    create_response = client.post("/api/v1/enquiries", json=payload, headers=headers)
    enquiry_id = create_response.json()["id"]

    update_payload = {
        "contact_name": "Updated Contact",
        "notes": "Some notes added later",
    }

    response = client.put(
        f"/api/v1/enquiries/{enquiry_id}", json=update_payload, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["contact_name"] == "Updated Contact"
    assert data["notes"] == "Some notes added later"


def test_update_enquiry_status():
    token, _ = _register("enq_stat", "Enq Status WS")
    headers = _headers(token)

    payload = {
        "source": EnquirySource.MANUAL.value,
        "contact_name": "Test Contact",
        "items": [],
    }
    create_response = client.post("/api/v1/enquiries", json=payload, headers=headers)
    enquiry_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/enquiries/{enquiry_id}/status",
        json={"status": EnquiryStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == EnquiryStatus.IN_PROGRESS.value


def test_convert_enquiry_to_quotation():
    token, _ = _register("enq_conv", "Enq Conv WS")
    headers = _headers(token)
    client_id = _create_client(headers)

    payload = {
        "client_id": client_id,
        "source": EnquirySource.MANUAL.value,
        "items_description": "We need some products",
        "items": [],
    }

    create_response = client.post("/api/v1/enquiries", json=payload, headers=headers)
    enquiry_id = create_response.json()["id"]

    convert_response = client.post(
        f"/api/v1/enquiries/{enquiry_id}/convert", headers=headers
    )
    assert convert_response.status_code == 200

    quotation = convert_response.json()
    assert quotation["quotation_number"].startswith("QUO-")
    assert len(quotation["items"]) == 1
    assert quotation["items"][0]["description"] == "FROM ENQUIRY: We need some products"

    enq_response = client.get(f"/api/v1/enquiries/{enquiry_id}", headers=headers)
    assert enq_response.status_code == 200
    assert enq_response.json()["status"] == EnquiryStatus.QUOTED.value


def test_convert_enquiry_without_client_fails():
    token, _ = _register("enq_fail", "Enq Fail WS")
    headers = _headers(token)

    payload = {
        "source": EnquirySource.MANUAL.value,
        "items_description": "We need some products",
        "items": [],
    }
    create_response = client.post("/api/v1/enquiries", json=payload, headers=headers)
    enquiry_id = create_response.json()["id"]

    convert_response = client.post(
        f"/api/v1/enquiries/{enquiry_id}/convert", headers=headers
    )
    assert convert_response.status_code == 400
    assert convert_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_whatsapp_deduplication():
    token, _ = _register("enq_wa", "Enq WA WS")
    headers = _headers(token)

    payload = {
        "source": EnquirySource.WHATSAPP.value,
        "whatsapp_message_id": "wamid.HBgL",
        "items": [],
    }

    response1 = client.post("/api/v1/enquiries", json=payload, headers=headers)
    assert response1.status_code == 201

    response2 = client.post("/api/v1/enquiries", json=payload, headers=headers)
    assert response2.status_code == 201

    assert response1.json()["id"] == response2.json()["id"]


def test_list_enquiries_search_and_envelope():
    token, _ = _register("enq_list", "Enq List WS")
    headers = _headers(token)

    for i, name in enumerate(["Zeta Traders", "Acme Electrical"]):
        payload = {
            "source": EnquirySource.MANUAL.value,
            "contact_name": name,
            "contact_email": f"lead{i}@example.com",
            "items_description": f"Request batch {i}",
            "items": [],
        }
        r = client.post("/api/v1/enquiries", json=payload, headers=headers)
        assert r.status_code == 201, r.text

    r = client.get("/api/v1/enquiries", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["size"] == 20
    assert len(body["items"]) == 2

    hit = client.get("/api/v1/enquiries", params={"search": "Acme"}, headers=headers)
    assert hit.status_code == 200, hit.text
    hit_body = hit.json()
    assert hit_body["total"] == 1
    assert len(hit_body["items"]) == 1
    assert hit_body["items"][0]["contact_name"] == "Acme Electrical"

    scratch = client.get(
        "/api/v1/enquiries", params={"search": "nomatchzzz"}, headers=headers
    )
    assert scratch.status_code == 200, scratch.text
    assert scratch.json()["total"] == 0

    email_hit = client.get(
        "/api/v1/enquiries", params={"search": "lead0@"}, headers=headers
    )
    assert email_hit.status_code == 200, email_hit.text
    assert email_hit.json()["total"] == 1
    assert email_hit.json()["items"][0]["contact_name"] == "Zeta Traders"
