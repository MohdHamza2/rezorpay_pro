"""Wave 27 — WhatsApp comms + webhook tests (addendum §6).

Covers: TEXT/DOCUMENT/AR_STATEMENT happy paths via a spy provider (recipient
authority: document recipient derived from Client phone, never the payload),
dry-run never dials a provider, provider errors persist FAILED for resend,
idempotency (replay same row / 409 conflict / expired key refresh), resend
gating (FAILED->SENT, SENT no-op, AR_STATEMENT regenerated with stored params),
lifecycle gates (INVOICE/QUOTATION), recipient + TEXT linked-entity validation,
RBAC, no-HTTTP guarantee, webhook challenge/413/401, status promotion with
idempotent repeats, phone_number_id mismatch, inbound dedup race, media
handling, unknown-contact matching, no-routing drop, transaction rollback
both-or-neither, cross-workspace isolation, list filters + pagination.
"""

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.auth.utils import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.client import Client  # noqa: E402
from app.models.enquiry import Enquiry  # noqa: E402
from app.models.invoice import Invoice, InvoiceStatus  # noqa: E402
from app.models.quotation import Quotation, QuotationStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.whatsapp_message import (  # noqa: E402
    WhatsAppDirection,
    WhatsAppIdempotencyKey,
    WhatsAppMessage,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
)
from app.services.enquiry_service import EnquiryService  # noqa: E402
from app.services.providers import ProviderResult, whatsapp_provider  # noqa: E402
from app.services.whatsapp_service import WhatsAppService  # noqa: E402

logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)

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

PHONE = "+971501234567"
BAD_PHONE = "0501234567"  # bare local number — never guessed, never derivable


class _SpyProvider:
    """Records every provider call; returns synthetic ids. Swapped into
    ``WhatsAppService.provider`` so no HTTP is ever dialed."""

    def __init__(self, upload_ok=True, send_ok=True):
        self.upload_ok = upload_ok
        self.send_ok = send_ok
        self.calls = []  # ("upload", filename, pdf_bytes) / ("send", to, payload)

    async def upload_media(self, phone_number_id, filename, pdf_bytes):
        self.calls.append(("upload", filename, pdf_bytes))
        if not self.upload_ok:
            return ProviderResult.failure(
                "http_500",
                provider_code="500",
                provider_category="GraphMethodException",
            )
        return ProviderResult.success(f"media_{uuid.uuid4().hex[:12]}")

    async def send_message(self, phone_number_id, to_number, payload):
        self.calls.append(("send", to_number, payload))
        if not self.send_ok:
            return ProviderResult.failure(
                "http_500",
                provider_code="500",
                provider_category="GraphServerException",
            )
        return ProviderResult.success(f"wamid_{uuid.uuid4().hex[:12]}")


@contextlib.contextmanager
def _provider(spy):
    WhatsAppService.provider = spy
    try:
        yield
    finally:
        WhatsAppService.provider = whatsapp_provider


@contextlib.contextmanager
def _settings(**changes):
    originals = {k: getattr(settings, k) for k in changes}
    for k, v in changes.items():
        setattr(settings, k, v)
    try:
        yield
    finally:
        for k, v in originals.items():
            setattr(settings, k, v)


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


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_token():
    email = f"wa_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "WA Tester",
            "workspace_name": "WA Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers=_headers(token))
    return token, me.json()["data"]["workspace_id"]


def _count(model, **kwargs) -> int:
    async def _c():
        async with TestingSessionLocal() as session:
            stmt = select(func.count()).select_from(model)
            for k, v in kwargs.items():
                stmt = stmt.where(getattr(model, k) == v)
            return (await session.execute(stmt)).scalar() or 0

    return asyncio.run(_c())


def seed_client(workspace_id, phone=PHONE, name="ClientCo"):
    async def _seed():
        async with TestingSessionLocal() as session:
            row = Client(
                workspace_id=uuid.UUID(workspace_id),
                name=name,
                phone=phone,
                tax_id="1001234567000003",
                address="Dubai",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return str(row.id)

    return asyncio.run(_seed())


def seed_invoice(workspace_id, client_id, status="SENT", number=None):
    async def _seed():
        async with TestingSessionLocal() as session:
            row = Invoice(
                workspace_id=uuid.UUID(workspace_id),
                client_id=uuid.UUID(client_id),
                invoice_number=number or f"INV-2026-{uuid.uuid4().hex[:4]}",
                currency="AED",
                subtotal="100.00",
                tax_amount="5.00",
                total_amount="105.00",
                amount_credited="0.00",
                amount_debited="0.00",
                status=InvoiceStatus(status),
                issue_date=date(2026, 8, 1),
                supply_date=date(2026, 8, 1),
                due_date=date(2026, 9, 1),
                notes="Thanks",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return str(row.id)

    return asyncio.run(_seed())


def seed_quotation(workspace_id, client_id, status="SENT", valid_until=None):
    async def _seed():
        async with TestingSessionLocal() as session:
            row = Quotation(
                workspace_id=uuid.UUID(workspace_id),
                client_id=uuid.UUID(client_id),
                quotation_number=f"QTN-2026-{uuid.uuid4().hex[:4]}",
                currency="AED",
                subtotal="100.00",
                tax_amount="5.00",
                total_amount="105.00",
                status=QuotationStatus(status),
                quotation_date=date(2026, 8, 1),
                valid_until=valid_until or (date.today() + timedelta(days=30)),
                notes=None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return str(row.id)

    return asyncio.run(_seed())


def seed_message(
    workspace_id, wa_id=None, status="SENT", direction=WhatsAppDirection.OUTBOUND
):
    async def _seed():
        async with TestingSessionLocal() as session:
            row = WhatsAppMessage(
                workspace_id=uuid.UUID(workspace_id),
                direction=direction,
                message_type=WhatsAppMessageType.TEXT,
                message_body="seeded",
                whatsapp_message_id=wa_id,
                status=WhatsAppMessageStatus(status),
            )
            session.add(row)
            await session.commit()
            return str(row.id)

    return asyncio.run(_seed())


def seed_expired_key(workspace_id, key, fingerprint, message_id):
    async def _seed():
        async with TestingSessionLocal() as session:
            row = WhatsAppIdempotencyKey(
                workspace_id=uuid.UUID(workspace_id),
                key=key,
                request_fingerprint=fingerprint,
                message_id=uuid.UUID(message_id),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(row)
            await session.commit()

    asyncio.run(_seed())


def send_text(token, key, body="Hello there", to_number=PHONE, extra=None):
    payload = {"kind": "text", "to_number": to_number, "message_body": body}
    if extra:
        payload.update(extra)
    return client.post(
        "/api/v1/comms/whatsapp/messages",
        headers={**_headers(token), "Idempotency-Key": key},
        json=payload,
    )


def send_document(token, key, payload):
    return client.post(
        "/api/v1/comms/whatsapp/messages",
        headers={**_headers(token), "Idempotency-Key": key},
        json={"kind": "document", **payload},
    )


def create_supplier(token):
    r = client.post(
        "/api/v1/suppliers",
        headers=_headers(token),
        json={
            "name": "WA Supplier",
            "supplier_code": f"WAS{uuid.uuid4().hex[:4]}",
            "email": "sup@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _member_token(workspace_id):
    email = f"wamem_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="WA Member",
                    role=UserRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(_insert())
    login = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert login.status_code == 200, login.text
    return login.json()["data"]["access_token"]


def _sign(raw: bytes) -> str:
    return (
        "sha256="
        + hmac.new(
            settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
    )


def _webhook(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body, separators=(",", ":")).encode()
    return raw, _sign(raw)


def post_webhook(body, secret="appsecret"):
    raw, sig = _webhook(body)
    return client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw,
        headers={"X-Hub-Signature-256": sig},
    )


# ---------- send: TEXT ----------


def test_send_text_happy_path():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        r = send_text(token, "txt-happy-1")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["direction"] == "OUTBOUND"
    assert data["message_type"] == "TEXT"
    assert data["to_number"] == PHONE
    assert data["message_body"] == "Hello there"
    assert data["whatsapp_message_id"].startswith("wamid_")
    assert data["simulated"] is False
    assert data["sent_at"] is not None
    assert data["received_at"] is None
    assert spy.calls == [
        (
            "send",
            PHONE,
            {
                "messaging_product": "whatsapp",
                "to": PHONE,
                "type": "text",
                "text": {"body": "Hello there"},
            },
        )
    ]


# ---------- send: DOCUMENT ----------


def test_send_document_happy_path_recipient_derived():
    token, ws = register_and_token()
    client_id = seed_client(ws)
    invoice_id = seed_invoice(ws, client_id)
    spy = _SpyProvider()
    with _provider(spy):
        r = send_document(
            token,
            "doc-happy-1",
            {
                "document_type": "INVOICE",
                "document_id": invoice_id,
                "caption": "Thanks",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "SENT"
        assert data["message_type"] == "DOCUMENT"
        assert data["to_number"] == PHONE  # derived from Client.phone
        assert data["document_type"] == "INVOICE"
        assert data["document_filename"] is not None
        assert data["media_id"].startswith("media_")
        assert data["linked_entity_type"] == "INVOICE"
        assert data["linked_entity_id"] == invoice_id
        assert data["caption"] == "Thanks"
        assert len(spy.calls) == 2
        _, filename, pdf_bytes = spy.calls[0]
        assert filename == data["document_filename"]
        assert pdf_bytes[:5] == b"%PDF-"
        _, to_number, payload = spy.calls[1]
        assert to_number == PHONE
        assert payload["type"] == "document"
        assert payload["document"] == {
            "id": data["media_id"],
            "filename": filename,
            "caption": "Thanks",
        }


def test_send_ar_statement_happy_path():
    token, ws = register_and_token()
    client_id = seed_client(ws)
    seed_invoice(ws, client_id)
    spy = _SpyProvider()
    with _provider(spy):
        r = send_document(
            token,
            "doc-ar-1",
            {
                "document_type": "AR_STATEMENT",
                "client_id": client_id,
                "statement_from": "2026-08-01",
                "statement_to": "2026-08-31",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["message_type"] == "DOCUMENT"
    assert data["to_number"] == PHONE
    assert data["document_type"] == "AR_STATEMENT"
    assert data["statement_from"] == "2026-08-01"
    assert data["statement_to"] == "2026-08-31"
    assert data["linked_entity_type"] == "AR_STATEMENT"
    assert data["linked_entity_id"] == client_id
    assert data["document_filename"].startswith(
        "Account-Statement-2026-08-01_2026-08-31"
    )
    assert len(spy.calls) == 2
    assert spy.calls[0][1] == data["document_filename"]
    assert spy.calls[0][2][:5] == b"%PDF-"


# ---------- dry run ----------


def test_dry_run_default_never_hits_provider():
    token, _ = register_and_token()
    assert settings.COMMS_DRY_RUN is True
    assert not whatsapp_provider.enabled()

    import app.services.providers as providers_mod

    original = providers_mod.httpx.AsyncClient

    def _explode(*args, **kwargs):
        raise AssertionError("dry-run must not dial the provider")

    providers_mod.httpx.AsyncClient = _explode
    try:
        r = send_text(token, "dry-1")
    finally:
        providers_mod.httpx.AsyncClient = original
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["simulated"] is True
    assert data["whatsapp_message_id"] is None
    assert data["error_message"] is None


# ---------- provider failure ----------


def test_provider_error_persists_failed_for_resend():
    token, _ = register_and_token()
    spy = _SpyProvider(send_ok=False)
    with _provider(spy):
        r = send_text(token, "fail-1")
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "PROVIDER_ERROR"
    listed = client.get("/api/v1/comms/whatsapp/messages", headers=_headers(token))
    rows = [m for m in listed.json()["data"] if m["status"] == "FAILED"]
    assert len(rows) == 1
    assert rows[0]["error_message"] == "http_500"
    assert rows[0]["provider_error_code"] == "500"
    assert rows[0]["provider_error_category"] == "GraphServerException"
    assert rows[0]["whatsapp_message_id"] is None


def test_document_upload_failure_is_502_and_failed():
    token, ws = register_and_token()
    client_id = seed_client(ws)
    invoice_id = seed_invoice(ws, client_id)
    spy = _SpyProvider(upload_ok=False)
    with _provider(spy):
        r = send_document(
            token, "doc-fail-1", {"document_type": "INVOICE", "document_id": invoice_id}
        )
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "PROVIDER_ERROR"
    listed = client.get("/api/v1/comms/whatsapp/messages", headers=_headers(token))
    fail = [m for m in listed.json()["data"] if m["status"] == "FAILED"][0]
    assert fail["message_type"] == "DOCUMENT"
    assert fail["media_id"] is None
    assert len(spy.calls) == 1  # upload failed -> message never dispatched


# ---------- idempotency ----------


def test_idempotency_replay_same_message_provider_called_once():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        r1 = send_text(token, "idem-1", body="Same")
        r2 = send_text(token, "idem-1", body="Same")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    assert len(spy.calls) == 1  # replay never re-dispatches


def test_idempotency_conflict_same_key_different_request():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        r1 = send_text(token, "idem-conflict-1", body="Same")
        r2 = send_text(token, "idem-conflict-1", body="Different")
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(spy.calls) == 1  # conflicting request never reaches the provider


def test_idempotency_expired_key_allows_fresh_send():
    token, ws = register_and_token()
    dummy = seed_message(ws, status="FAILED")
    dummy_msg = client.get(
        f"/api/v1/comms/whatsapp/messages/{dummy}", headers=_headers(token)
    ).json()["data"]
    seed_expired_key(ws, "idem-exp-1", "old-fingerprint", dummy_msg["id"])
    spy = _SpyProvider()
    with _provider(spy):
        r = send_text(token, "idem-exp-1", body="Fresh")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "SENT"
    assert len(spy.calls) == 1  # expired reservation deleted, provider dialed once


# ---------- resend ----------


def test_resend_failed_to_sent_then_sent_is_noop():
    token, _ = register_and_token()
    spy = _SpyProvider(send_ok=False)
    with _provider(spy):
        r = send_text(token, "resend-1")
    assert r.status_code == 502, r.text
    message_id = client.get(
        "/api/v1/comms/whatsapp/messages",
        headers=_headers(token),
        params={"page": 1, "per_page": 50},
    ).json()["data"][0]["id"]

    spy2 = _SpyProvider()
    with _provider(spy2):
        rr = client.post(
            f"/api/v1/comms/whatsapp/messages/{message_id}/resend",
            headers=_headers(token),
        )
    assert rr.status_code == 200, rr.text
    assert rr.json()["data"]["status"] == "SENT"
    assert rr.json()["data"]["whatsapp_message_id"].startswith("wamid_")

    class _Zombie:
        async def send_message(self, *a, **kw):
            raise AssertionError("SENT message must not re-dispatch")

    with _provider(_Zombie()):
        noop = client.post(
            f"/api/v1/comms/whatsapp/messages/{message_id}/resend",
            headers=_headers(token),
        )
    assert noop.status_code == 200, noop.text
    assert noop.json()["data"]["status"] == "SENT"


def test_resend_ar_statement_rebuilds_with_stored_params():
    token, ws = register_and_token()
    client_id = seed_client(ws, phone=PHONE, name="ReprintCo")
    seed_invoice(ws, client_id)
    spy = _SpyProvider(send_ok=False)
    with _provider(spy):
        r = send_document(
            token,
            "resend-ar-1",
            {
                "document_type": "AR_STATEMENT",
                "client_id": client_id,
                "statement_from": "2026-08-01",
                "statement_to": "2026-08-31",
            },
        )
    assert r.status_code == 502, r.text
    first_filename = client.get(
        "/api/v1/comms/whatsapp/messages", headers=_headers(token)
    ).json()["data"][0]["document_filename"]

    spy2 = _SpyProvider()
    with _provider(spy2):
        message_id = client.get(
            "/api/v1/comms/whatsapp/messages", headers=_headers(token)
        ).json()["data"][0]["id"]
        rr = client.post(
            f"/api/v1/comms/whatsapp/messages/{message_id}/resend",
            headers=_headers(token),
        )
    assert rr.status_code == 200, rr.text
    assert rr.json()["data"]["status"] == "SENT"
    # Re-rendered with the SAME stored period -> same deterministic filename.
    assert rr.json()["data"]["document_filename"] == first_filename
    blob = next(c for c in spy2.calls if c[0] == "upload")
    assert blob[1] == first_filename
    assert blob[2][:5] == b"%PDF-"


# ---------- recipient authority ----------


def test_document_send_rejects_explicit_to_number():
    token, _ = register_and_token()
    r = send_document(
        token,
        "auth-1",
        {
            "document_type": "INVOICE",
            "document_id": str(uuid.uuid4()),
            "to_number": PHONE,
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_with_bare_phone_not_derivable():
    token, ws = register_and_token()
    client_id = seed_client(ws, phone=BAD_PHONE)
    invoice_id = seed_invoice(ws, client_id)
    spy = _SpyProvider()
    with _provider(spy):
        r = send_document(
            token, "auth-2", {"document_type": "INVOICE", "document_id": invoice_id}
        )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["field"] == "to_number"
    assert len(spy.calls) == 0


# ---------- lifecycle gates ----------


def test_invoice_lifecycle_gates():
    token, ws = register_and_token()
    client_id = seed_client(ws)
    draft_id = seed_invoice(ws, client_id, status="DRAFT")
    sent_id = seed_invoice(ws, client_id, status="SENT")
    spy = _SpyProvider()
    with _provider(spy):
        blocked = send_document(
            token, "gate-inv-1", {"document_type": "INVOICE", "document_id": draft_id}
        )
        ok = send_document(
            token, "gate-inv-2", {"document_type": "INVOICE", "document_id": sent_id}
        )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "INVALID_STATE"
    assert ok.status_code == 200, ok.text
    assert len(spy.calls) == 2


def test_quotation_lifecycle_gates_including_expiry():
    token, ws = register_and_token()
    client_id = seed_client(ws)
    expired_id = seed_quotation(
        ws, client_id, status="SENT", valid_until=date.today() - timedelta(days=1)
    )
    draft_id = seed_quotation(ws, client_id, status="DRAFT")
    accepted_id = seed_quotation(ws, client_id, status="ACCEPTED")
    spy = _SpyProvider()
    with _provider(spy):
        exp = send_document(
            token,
            "gate-qtn-1",
            {"document_type": "QUOTATION", "document_id": expired_id},
        )
        draft = send_document(
            token, "gate-qtn-2", {"document_type": "QUOTATION", "document_id": draft_id}
        )
        ok = send_document(
            token,
            "gate-qtn-3",
            {"document_type": "QUOTATION", "document_id": accepted_id},
        )
    assert exp.status_code == 403 and exp.json()["error"]["code"] == "INVALID_STATE"
    assert draft.status_code == 403 and draft.json()["error"]["code"] == "INVALID_STATE"
    assert ok.status_code == 200, ok.text


def test_document_not_found_404():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        r = send_document(
            token,
            "nf-1",
            {"document_type": "INVOICE", "document_id": str(uuid.uuid4())},
        )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert len(spy.calls) == 0


# ---------- TEXT linked-entity rules ----------


def test_text_linked_entity_valid_and_rules():
    token_a, _ = register_and_token()
    supplier_a = create_supplier(token_a)
    token_b, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        valid = send_text(
            token_a,
            "link-1",
            extra={"linked_entity_type": "SUPPLIER", "linked_entity_id": supplier_a},
        )
        cross = send_text(
            token_b,
            "link-2",
            extra={"linked_entity_type": "SUPPLIER", "linked_entity_id": supplier_a},
        )
        unsupported = send_text(
            token_a,
            "link-3",
            extra={
                "linked_entity_type": "WHATZIT",
                "linked_entity_id": str(uuid.uuid4()),
            },
        )
        type_only = send_text(
            token_a, "link-4", extra={"linked_entity_type": "SUPPLIER"}
        )
    assert valid.status_code == 200, valid.text
    assert valid.json()["data"]["linked_entity_type"] == "SUPPLIER"
    assert cross.status_code == 404, cross.text
    assert unsupported.status_code == 422, unsupported.text
    assert type_only.status_code == 422, type_only.text


def test_text_requires_to_and_body():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        no_to = client.post(
            "/api/v1/comms/whatsapp/messages",
            headers={**_headers(token), "Idempotency-Key": "txt-1"},
            json={"kind": "text", "message_body": "hi"},
        )
        no_body = client.post(
            "/api/v1/comms/whatsapp/messages",
            headers={**_headers(token), "Idempotency-Key": "txt-2"},
            json={"kind": "text", "to_number": PHONE},
        )
        bad_tel = client.post(
            "/api/v1/comms/whatsapp/messages",
            headers={**_headers(token), "Idempotency-Key": "txt-3"},
            json={"kind": "text", "to_number": "0123", "message_body": "hi"},
        )
    assert no_to.status_code == 422 and no_body.status_code == 422
    assert bad_tel.status_code == 422, bad_tel.text
    assert len(spy.calls) == 0


# ---------- RBAC + idempotency key required ----------


def test_member_blocked_and_reads_open():
    token, ws = register_and_token()
    member = _member_token(ws)
    spy = _SpyProvider()
    with _provider(spy):
        block = send_text(member, "mem-1")
    assert block.status_code == 403, block.text
    assert block.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    listed = client.get("/api/v1/comms/whatsapp/messages", headers=_headers(member))
    assert listed.status_code == 200, listed.text


def test_idempotency_key_header_required():
    token, _ = register_and_token()
    spy = _SpyProvider()
    with _provider(spy):
        r = client.post(
            "/api/v1/comms/whatsapp/messages",
            headers=_headers(token),
            json={"kind": "text", "to_number": PHONE, "message_body": "hi"},
        )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert len(spy.calls) == 0


# ---------- no HTTP guarantee ----------


def test_spy_provider_and_webhooks_never_dial_http():
    token, _ = register_and_token()
    import app.services.providers as providers_mod

    original = providers_mod.httpx.AsyncClient

    def _explode(*args, **kwargs):
        raise AssertionError("no real HTTP may be dialed in tests")

    providers_mod.httpx.AsyncClient = _explode
    try:
        spy = _SpyProvider()
        with _provider(spy):
            r = send_text(token, "noh-1")
        assert r.status_code == 200, r.text
        with _settings(WHATSAPP_APP_SECRET="sec"):
            resp = post_webhook(
                {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "changes": [
                                {
                                    "value": {
                                        "statuses": [
                                            {"id": "wamid_none", "status": "sent"}
                                        ]
                                    }
                                }
                            ]
                        }
                    ],
                }
            )
        assert resp.status_code == 200, resp.text
    finally:
        providers_mod.httpx.AsyncClient = original


# ---------- webhook: challenge / size / hmac ----------


def test_webhook_challenge_echo_and_mismatch():
    with _settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-tok"):
        ok = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-tok",
                "hub.challenge": "987654321",
            },
        )
        assert ok.status_code == 200, ok.text
        assert ok.text == "987654321"
        bad = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "1",
            },
        )
        assert bad.status_code == 403, bad.text
        assert bad.json()["error"]["code"] == "FORBIDDEN"


def test_webhook_body_size_cap_413_before_hmac():
    with _settings(WHATSAPP_WEBHOOK_MAX_BODY_BYTES=64):
        r = client.post(
            "/api/v1/webhooks/whatsapp",
            content=b'{"padding": "' + b"x" * 5000 + b'"}',
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_webhook_bad_hmac_401():
    with _settings(WHATSAPP_APP_SECRET="known"):
        r = client.post(
            "/api/v1/webhooks/whatsapp",
            content=b'{"object":"x"}',
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_webhook_missing_signature_401():
    with _settings(WHATSAPP_APP_SECRET="known"):
        r = client.post("/api/v1/webhooks/whatsapp", content=b'{"object":"x"}')
    assert r.status_code == 401, r.text


def test_webhook_unparseable_body_is_200():
    with _settings(WHATSAPP_APP_SECRET="sec"):
        raw = b"not-json"
        r = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw,
            headers={"X-Hub-Signature-256": _sign(raw)},
        )
    assert r.status_code == 200, r.text


# ---------- webhook: statuses ----------


def test_webhook_status_promotion_idempotent_and_terminal():
    token, ws = register_and_token()
    seed_message(ws, wa_id="wamid_status_1", status="SENT")
    with _settings(WHATSAPP_APP_SECRET="sec"):
        delivered = post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "e",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "metadata": {"phone_number_id": "999"},
                                    "statuses": [
                                        {"id": "wamid_status_1", "status": "delivered"}
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        )
        assert delivered.status_code == 200, delivered.text
        repeat = post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "999"},
                                    "statuses": [
                                        {"id": "wamid_status_1", "status": "delivered"}
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        )
        post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "999"},
                                    "statuses": [
                                        {"id": "wamid_status_1", "status": "read"}
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        )
        post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "999"},
                                    "statuses": [
                                        {"id": "wamid_status_1", "status": "failed"}
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        )
    row = client.get("/api/v1/comms/whatsapp/messages", headers=_headers(token)).json()[
        "data"
    ][0]
    assert row["status"] == "FAILED"
    assert row["delivered_at"] is not None
    assert row["read_at"] is not None
    assert row["error_message"] == "provider_webhook_failed"
    assert delivered.json()["status"] == "processed"
    assert repeat.json()["status"] == "processed"


def test_webhook_unknown_wamid_and_wrong_phone_id_are_noops():
    before = _count(WhatsAppMessage)
    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="myphone",
        WHATSAPP_INBOUND_WORKSPACE_ID="",
    ):
        unknown = post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "myphone"},
                                    "statuses": [
                                        {"id": "wamid_ghost", "status": "delivered"}
                                    ],
                                    "messages": [
                                        {
                                            "id": "wamid_ghost_msg",
                                            "from": PHONE,
                                            "type": "text",
                                            "text": {"body": "hi"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        )
        wrong_phone = post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "someone-else"},
                                    "messages": [
                                        {
                                            "id": "wamid_ghost2",
                                            "from": PHONE,
                                            "type": "text",
                                            "text": {"body": "hi"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        )
    assert unknown.status_code == 200 and wrong_phone.status_code == 200
    assert _count(WhatsAppMessage) == before  # nothing recorded


# ---------- webhook: inbound ----------


def _inbound_body(messages):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "pnid"},
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


def test_inbound_text_dedup_and_enquiry_creation():
    token, ws = register_and_token()
    seed_client(ws)  # canonical phone match
    body = _inbound_body(
        [
            {
                "id": "wamid_in_1",
                "from": PHONE,
                "timestamp": "1",
                "type": "text",
                "text": {"body": "I want 5 widgets"},
            }
        ]
    )
    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="pnid",
        WHATSAPP_INBOUND_WORKSPACE_ID=ws,
    ):
        r1 = post_webhook(body)
        r2 = post_webhook(body)  # exact duplicate -> fast-path dedup
    assert r1.status_code == 200 and r2.status_code == 200
    rows = [m for m in _rows(ws) if m["whatsapp_message_id"] == "wamid_in_1"]
    assert len(rows) == 1
    assert rows[0]["direction"] == "INBOUND"
    assert rows[0]["message_type"] == "TEXT"
    assert rows[0]["status"] == "RECEIVED"
    assert rows[0]["from_number"] == PHONE
    assert rows[0]["received_at"] is not None
    assert rows[0]["sent_at"] is None
    enquiries = _count(Enquiry, workspace_id=ws)
    assert enquiries == 1
    enq = _all_enquiries(ws)
    assert len(enq) == 1
    assert enq[0]["source"] == "WHATSAPP"
    assert enq[0]["contact_whatsapp"] == PHONE
    assert enq[0]["items_description"] == "I want 5 widgets"


def test_inbound_without_routing_is_dropped():
    before = _count(WhatsAppMessage)
    body = _inbound_body(
        [
            {
                "id": "wamid_in_noroute",
                "from": PHONE,
                "type": "text",
                "text": {"body": "hi"},
            }
        ]
    )
    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="pnid",
        WHATSAPP_INBOUND_WORKSPACE_ID="",
    ):
        r = post_webhook(body)
    assert r.status_code == 200, r.text
    assert _count(WhatsAppMessage) == before


def test_inbound_media_with_caption_is_text_without_is_media_only():
    token, ws = register_and_token()
    body = _inbound_body(
        [
            {
                "id": "wamid_in_media_cap",
                "from": PHONE,
                "type": "image",
                "image": {"caption": "Here is my BOQ"},
            },
            {
                "id": "wamid_in_media_raw",
                "from": PHONE,
                "type": "image",
                "image": {"id": "media_xyz"},
            },
        ]
    )
    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="pnid",
        WHATSAPP_INBOUND_WORKSPACE_ID=ws,
    ):
        r = post_webhook(body)
    assert r.status_code == 200, r.text
    cap = [m for m in _rows(ws) if m["whatsapp_message_id"] == "wamid_in_media_cap"]
    raw = [m for m in _rows(ws) if m["whatsapp_message_id"] == "wamid_in_media_raw"]
    assert cap[0]["message_type"] == "TEXT"
    assert cap[0]["message_body"] == "Here is my BOQ"
    assert raw[0]["message_type"] == "MEDIA"
    assert raw[0]["message_body"] is None
    # caption text -> Enquiry; media-only -> transport record, NO Enquiry
    assert len(_all_enquiries(ws, wa_id="wamid_in_media_cap")) == 1
    assert len(_all_enquiries(ws, wa_id="wamid_in_media_raw")) == 0


def test_inbound_unknown_contact_creates_unassigned_enquiry():
    token, ws = register_and_token()
    body = _inbound_body(
        [
            {
                "id": "wamid_in_unknown",
                "from": "+971999999999",
                "type": "text",
                "text": {"body": "quote for 10"},
            }
        ]
    )
    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="pnid",
        WHATSAPP_INBOUND_WORKSPACE_ID=ws,
    ):
        r = post_webhook(body)
    assert r.status_code == 200, r.text
    enq = _all_enquiries(ws, wa_id="wamid_in_unknown")
    assert len(enq) == 1
    assert enq[0]["client_id"] is None


def test_webhook_requires_no_auth():
    with _settings(WHATSAPP_APP_SECRET="sec"):
        r = post_webhook(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "x"},
                                    "messages": [],
                                }
                            }
                        ]
                    }
                ],
            }
        )
    assert r.status_code == 200, r.text


# ---------- inbound: races + transaction integrity ----------


def test_concurrent_duplicate_webhook_lands_once():
    token, ws = register_and_token()
    body = json.dumps(
        _inbound_body(
            [
                {
                    "id": "wamid_race",
                    "from": PHONE,
                    "type": "text",
                    "text": {"body": "dup race"},
                }
            ]
        ),
        separators=(",", ":"),
    ).encode()

    async def _fire():
        async with TestingSessionLocal() as session:
            await WhatsAppService.apply_webhook_events(session, body)

    async def _dupe():
        # gather must be created INSIDE a running loop (3.11 semantics).
        await asyncio.gather(_fire(), _fire())

    with _settings(WHATSAPP_INBOUND_WORKSPACE_ID=ws):
        asyncio.run(_dupe())
    assert _count(WhatsAppMessage, whatsapp_message_id="wamid_race") == 1
    assert _count(Enquiry, whatsapp_message_id="wamid_race") == 1


def test_transaction_rollback_both_or_neither():
    token, ws = register_and_token()
    body = _inbound_body(
        [
            {
                "id": "wamid_rollback",
                "from": PHONE,
                "type": "text",
                "text": {"body": "boom"},
            }
        ]
    )
    orig = EnquiryService.create

    async def _boom(*a, **kw):
        raise RuntimeError("forced enquiry failure")

    with _settings(
        WHATSAPP_APP_SECRET="sec",
        WHATSAPP_PHONE_NUMBER_ID="pnid",
        WHATSAPP_INBOUND_WORKSPACE_ID=ws,
    ):
        EnquiryService.create = staticmethod(_boom)
        try:
            r = post_webhook(body)
        finally:
            EnquiryService.create = orig
    assert r.status_code == 200, r.text  # post-HMAC always 200
    assert _count(WhatsAppMessage, whatsapp_message_id="wamid_rollback") == 0
    assert _count(Enquiry, whatsapp_message_id="wamid_rollback") == 0


# ---------- isolation / listing ----------


def test_cross_workspace_isolation_404_never_403():
    token_a, ws_a = register_and_token()
    msg_id = seed_message(ws_a, wa_id="wamid_iso", status="SENT")
    token_b, _ = register_and_token()
    r = client.get(
        f"/api/v1/comms/whatsapp/messages/{msg_id}", headers=_headers(token_b)
    )
    assert r.status_code == 404, r.text
    listed = client.get("/api/v1/comms/whatsapp/messages", headers=_headers(token_b))
    assert listed.json()["data"] == []


def test_list_filters_and_pagination():
    token, ws = register_and_token()
    seed_message(ws, wa_id="wamid_lf_sent", status="SENT")
    seed_message(ws, wa_id="wamid_lf_deliv", status="DELIVERED")
    seed_message(ws, wa_id="wamid_lf_fail", status="FAILED")

    delivered = client.get(
        "/api/v1/comms/whatsapp/messages?status=DELIVERED", headers=_headers(token)
    )
    assert delivered.json()["pagination"]["total"] == 1

    paged = client.get(
        "/api/v1/comms/whatsapp/messages?per_page=2&page=1", headers=_headers(token)
    )
    assert paged.json()["pagination"]["total"] == 3
    assert paged.json()["pagination"]["pages"] == 2
    assert paged.json()["pagination"]["has_next"] is True
    assert len(paged.json()["data"]) == 2

    bad = client.get("/api/v1/comms/whatsapp/messages?page=0", headers=_headers(token))
    assert bad.status_code == 422, bad.text


# ---------- internal helpers for DB assertions ----------


def _rows(workspace_id):
    async def _q():
        async with TestingSessionLocal() as session:
            result = await session.execute(
                select(WhatsAppMessage)
                .where(WhatsAppMessage.workspace_id == uuid.UUID(workspace_id))
                .order_by(WhatsAppMessage.created_at)
            )
            return [m.model_dump(mode="json") for m in result.scalars().all()]

    return asyncio.run(_q())


def _all_enquiries(workspace_id, wa_id=None):
    async def _q():
        async with TestingSessionLocal() as session:
            stmt = select(Enquiry).where(
                Enquiry.workspace_id == uuid.UUID(workspace_id)
            )
            if wa_id:
                stmt = stmt.where(Enquiry.whatsapp_message_id == wa_id)
            result = await session.execute(stmt)
            return [e.model_dump(mode="json") for e in result.scalars().all()]

    return asyncio.run(_q())
