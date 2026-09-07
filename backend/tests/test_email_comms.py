"""Wave 26 — Email Engine (Resend) tests.

Covers: happy-path send (provider id captured), dry-run never dials a
provider (simulated=True + resend_message_id None), provider failure 502 with
the FAILED row persisted for resend, idempotency (same key returns the same
row), manual resend gating (FAILED->SENT, SENT no-op), linked-entity rules
(valid/cross-workspace/AR_STATEMENT reference/unsupported type), MEMBER RBAC,
webhook events (secret, delivered/bounced + idempotent repeats, unknown id),
list filters + pagination, and cross-workspace isolation 404 (never 403).
"""

import asyncio
import logging
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.email_log import EmailLog, EmailStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.auth.utils import hash_password  # noqa: E402
from app.services.email_service import EmailService  # noqa: E402
from app.services.providers import ProviderResult, resend_provider  # noqa: E402

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


class _FakeSuccess:
    async def send(self, from_email, to_email, subject, body_html, bcc=None):
        return ProviderResult.success(f"res_{uuid.uuid4().hex}")


class _FakeFail:
    async def send(self, from_email, to_email, subject, body_html, bcc=None):
        return ProviderResult.failure("http_500")


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
    email = f"email_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "Email Tester",
            "workspace_name": "Email Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["data"]["workspace_id"]


def send_email(token, to_email="to@example.com", idem_key=None, subject="Test subject"):
    body = {
        "to_email": to_email,
        "subject": subject,
        "body_html": "<p>Hello</p>",
    }
    headers = _headers(token)
    if idem_key:
        headers["Idempotency-Key"] = idem_key
    return client.post("/api/v1/comms/emails", headers=headers, json=body)


def create_supplier(token, name="MailCo"):
    r = client.post(
        "/api/v1/suppliers",
        headers=_headers(token),
        json={
            "name": name,
            "supplier_code": f"ML{uuid.uuid4().hex[:4]}",
            "email": "mail@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def seed_email_row(
    workspace_id,
    resend_message_id=None,
    status="SENT",
    simulated=False,
):
    async def insert():
        async with TestingSessionLocal() as session:
            email = EmailLog(
                workspace_id=uuid.UUID(workspace_id),
                from_email="InvoiceSaaS <noreply@invoicesaas.example>",
                to_email="to@example.com",
                bcc=[],
                subject="Seeded",
                body_html="<p>x</p>",
                status=EmailStatus(status),
                resend_message_id=resend_message_id,
                simulated=simulated,
            )
            session.add(email)
            await session.commit()
            await session.refresh(email)
            return str(email.id)

    return asyncio.run(insert())


def _member_token(workspace_id: str) -> str:
    email = f"member_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="Email Member",
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


# ---------- send ----------


def test_send_happy_path_real_provider():
    token, _ = register_and_token()
    EmailService.provider = _FakeSuccess()
    try:
        r = send_email(token, idem_key="happy-1")
    finally:
        EmailService.provider = resend_provider
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["resend_message_id"].startswith("res_")
    assert data["simulated"] is False
    assert data["to_email"] == "to@example.com"
    assert data["subject"] == "Test subject"


def test_send_dry_run_default_never_hits_provider():
    token, _ = register_and_token()
    assert settings.COMMS_DRY_RUN is True
    assert not resend_provider.enabled()

    import app.services.providers as providers_mod

    original = providers_mod.httpx.AsyncClient

    def _explode(*args, **kwargs):  # any HTTP attempt fails the test
        raise AssertionError("dry-run must not dial the provider")

    providers_mod.httpx.AsyncClient = _explode
    try:
        r = send_email(token, idem_key="dry-1")
    finally:
        providers_mod.httpx.AsyncClient = original
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SENT"
    assert data["simulated"] is True
    assert data["resend_message_id"] is None
    assert data["error_message"] is None


def test_send_provider_error_persists_failed_for_resend():
    token, _ = register_and_token()
    EmailService.provider = _FakeFail()
    try:
        r = send_email(token, idem_key="fail-1")
    finally:
        EmailService.provider = resend_provider
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "PROVIDER_ERROR"
    # the FAILED row persists for manual resend
    listed = client.get("/api/v1/comms/emails", headers=_headers(token))
    assert listed.status_code == 200, listed.text
    rows = [e for e in listed.json()["data"] if e["status"] == "FAILED"]
    assert len(rows) == 1
    assert rows[0]["error_message"] == "http_500"


def test_send_idempotency_same_key_returns_same_email():
    token, _ = register_and_token()
    EmailService.provider = _FakeSuccess()
    try:
        r1 = send_email(token, idem_key="idem-1")
        r2 = send_email(token, idem_key="idem-1")
    finally:
        EmailService.provider = resend_provider
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    listed = client.get("/api/v1/comms/emails", headers=_headers(token))
    assert listed.json()["pagination"]["total"] == 1


# ---------- resend ----------


def test_resend_from_failed_to_sent_and_sent_is_noop():
    token, _ = register_and_token()
    EmailService.provider = _FakeFail()
    try:
        r = send_email(token, idem_key="resend-fail-1")
    finally:
        EmailService.provider = resend_provider
    assert r.status_code == 502, r.text
    listed = client.get("/api/v1/comms/emails", headers=_headers(token))
    original_id = listed.json()["data"][0]["id"]
    assert listed.json()["data"][0]["status"] == "FAILED"

    EmailService.provider = _FakeSuccess()
    try:
        rr = client.post(
            f"/api/v1/comms/emails/{original_id}/resend", headers=_headers(token)
        )
    finally:
        EmailService.provider = resend_provider
    assert rr.status_code == 200, rr.text
    assert rr.json()["data"]["status"] == "SENT"
    assert rr.json()["data"]["resend_message_id"].startswith("res_")

    sent = client.get(
        f"/api/v1/comms/emails/{original_id}", headers=_headers(token)
    ).json()["data"]
    assert sent["status"] == "SENT"

    class _Zombie:
        async def send(self, *a, **kw):
            raise AssertionError("SENT email must not re-dispatch")

    EmailService.provider = _Zombie()
    try:
        noop = client.post(
            f"/api/v1/comms/emails/{original_id}/resend", headers=_headers(token)
        )
    finally:
        EmailService.provider = resend_provider
    assert noop.status_code == 200, noop.text
    assert noop.json()["data"]["status"] == "SENT"


# ---------- linked entity ----------


def test_linked_entity_valid_and_reference_only():
    token, _ = register_and_token()
    supplier_id = create_supplier(token)
    EmailService.provider = _FakeSuccess()
    try:
        r = send_email(token, idem_key="link-sup-1")
        r2 = client.post(
            "/api/v1/comms/emails",
            headers={**_headers(token), "Idempotency-Key": "link-sup-2"},
            json={
                "to_email": "sup@example.com",
                "subject": "Linked",
                "body_html": "<p>x</p>",
                "linked_entity_type": "SUPPLIER",
                "linked_entity_id": supplier_id,
            },
        )
        r3 = client.post(
            "/api/v1/comms/emails",
            headers={**_headers(token), "Idempotency-Key": "link-ar-1"},
            json={
                "to_email": "ar@example.com",
                "subject": "AR",
                "body_html": "<p>x</p>",
                "linked_entity_type": "AR_STATEMENT",
                "linked_entity_id": str(uuid.uuid4()),
            },
        )
    finally:
        EmailService.provider = resend_provider
    assert r.status_code == 200, r.text  # no linked entity at all
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["linked_entity_type"] == "SUPPLIER"
    assert r3.status_code == 200, r3.text  # reference-only, no FK row checked


def test_linked_entity_bad_refs():
    token_b, _ = register_and_token()
    supplier_id = create_supplier(token_b)

    EmailService.provider = _FakeSuccess()
    try:
        # cross-workspace supplier
        token_a, _ = register_and_token()
        x = client.post(
            "/api/v1/comms/emails",
            headers={**_headers(token_a), "Idempotency-Key": "xt-1"},
            json={
                "to_email": "x@example.com",
                "subject": "x",
                "body_html": "<p>x</p>",
                "linked_entity_type": "SUPPLIER",
                "linked_entity_id": supplier_id,
            },
        )
        # unsupported type
        unsupported = client.post(
            "/api/v1/comms/emails",
            headers={**_headers(token_b), "Idempotency-Key": "xt-2"},
            json={
                "to_email": "x@example.com",
                "subject": "x",
                "body_html": "<p>x</p>",
                "linked_entity_type": "WHATZIT",
                "linked_entity_id": str(uuid.uuid4()),
            },
        )
        # type without id
        type_only = client.post(
            "/api/v1/comms/emails",
            headers={**_headers(token_b), "Idempotency-Key": "xt-3"},
            json={
                "to_email": "x@example.com",
                "subject": "x",
                "body_html": "<p>x</p>",
                "linked_entity_type": "SUPPLIER",
            },
        )
    finally:
        EmailService.provider = resend_provider
    assert x.status_code == 404, x.text
    assert x.json()["error"]["code"] == "NOT_FOUND"
    assert unsupported.status_code == 422, unsupported.text
    assert unsupported.json()["error"]["code"] == "VALIDATION_ERROR"
    assert type_only.status_code == 422, type_only.text


# ---------- RBAC ----------


def test_member_rbac_and_member_reads_open():
    token, workspace_id = register_and_token()
    member = _member_token(workspace_id)

    block = client.post(
        "/api/v1/comms/emails",
        headers={**_headers(member), "Idempotency-Key": "mem-1"},
        json={
            "to_email": "to@example.com",
            "subject": "s",
            "body_html": "<p>x</p>",
        },
    )
    assert block.status_code == 403, block.text
    assert block.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    listed = client.get("/api/v1/comms/emails", headers=_headers(member))
    assert listed.status_code == 200, listed.text
    email_id = seed_email_row(workspace_id)
    one = client.get(f"/api/v1/comms/emails/{email_id}", headers=_headers(member))
    assert one.status_code == 200, one.text
    assert one.json()["data"]["id"] == email_id


# ---------- webhook ----------


def test_webhook_secret_delivery_bounced_and_idempotent():
    token, workspace_id = register_and_token()
    seed_email_row(workspace_id, resend_message_id="res_wh_1", status="SENT")
    url = "/api/v1/webhooks/email"
    body = {"type": "email.delivered", "data": {"id": "res_wh_1"}}

    original = settings.RESEND_WEBHOOK_SECRET
    settings.RESEND_WEBHOOK_SECRET = "test-secret"
    bad_headers = {"Authorization": "Bearer wrong"}
    ok_headers = {"Authorization": "Bearer " + settings.RESEND_WEBHOOK_SECRET}
    try:
        bad = client.post(url, json=body, headers=bad_headers)
        assert bad.status_code == 401, bad.text

        ok = client.post(url, json=body, headers=ok_headers)
        assert ok.status_code == 200, ok.text
        delivered = ok.json()["data"]
        assert delivered["status"] == "DELIVERED"
        assert delivered["delivered_at"] is not None

        # idempotent repeat: same 200, same delivered_at
        r2 = client.post(url, json=body, headers=ok_headers)
        assert r2.status_code == 200, r2.text
        assert r2.json()["data"]["delivered_at"] == delivered["delivered_at"]

        # bounced after delivered
        bounced = client.post(
            url,
            json={"type": "email.bounced", "data": {"id": "res_wh_1"}},
            headers=ok_headers,
        )
        assert bounced.status_code == 200, bounced.text
        assert bounced.json()["data"]["status"] == "BOUNCED"

        # unknown resend_message_id -> 404
        unknown = client.post(
            url,
            json={"type": "email.delivered", "data": {"id": "res_zzz"}},
            headers=ok_headers,
        )
        assert unknown.status_code == 404, unknown.text
        assert unknown.json()["error"]["code"] == "NOT_FOUND"

        # informational events are a 200 no-op
        opened = client.post(
            url,
            json={"type": "email.opened", "data": {"id": "res_wh_1"}},
            headers=ok_headers,
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["data"]["status"] == "BOUNCED"
    finally:
        settings.RESEND_WEBHOOK_SECRET = original


# ---------- list + pagination ----------


def test_list_filters_and_pagination():
    token, workspace_id = register_and_token()
    for i, (status, mid) in enumerate(
        [("DELIVERED", "res_l1"), ("FAILED", "res_l2"), ("BOUNCED", "res_l3")]
    ):
        seed_email_row(workspace_id, resend_message_id=mid, status=status)

    all_rows = client.get("/api/v1/comms/emails", headers=_headers(token))
    assert all_rows.status_code == 200, all_rows.text
    assert all_rows.json()["pagination"]["total"] == 3

    bounced = client.get("/api/v1/comms/emails?status=BOUNCED", headers=_headers(token))
    assert bounced.json()["pagination"]["total"] == 1
    assert bounced.json()["data"][0]["status"] == "BOUNCED"

    page1 = client.get(
        "/api/v1/comms/emails?per_page=2&page=1", headers=_headers(token)
    ).json()
    assert page1["pagination"]["pages"] == 2
    assert page1["pagination"]["has_next"] is True
    assert page1["pagination"]["has_prev"] is False
    assert len(page1["data"]) == 2

    page2 = client.get(
        "/api/v1/comms/emails?per_page=2&page=2", headers=_headers(token)
    ).json()
    assert page2["pagination"]["has_next"] is False
    assert page2["pagination"]["has_prev"] is True

    bad_page = client.get("/api/v1/comms/emails?page=0", headers=_headers(token))
    assert bad_page.status_code == 422, bad_page.text


# ---------- isolation ----------


def test_isolation_cross_workspace_404():
    token_a, ws_a = register_and_token()
    email_id = seed_email_row(ws_a, resend_message_id="res_iso", status="SENT")
    token_b, _ = register_and_token()

    r = client.get(f"/api/v1/comms/emails/{email_id}", headers=_headers(token_b))
    assert r.status_code == 404, r.text
    listed = client.get("/api/v1/comms/emails", headers=_headers(token_b))
    assert listed.json()["data"] == []
