"""Wave 30 item 1.3 — statement export (PDF/CSV) tests.

Sync TestClient against real PostgreSQL ``invoicesaas_test``. Never SQLite.

Covers (locked addendum §2.5): AR + AP CSV/PDF, exact deterministic
filenames, CSV block structure, no-recalculation equality with the JSON
statement, workspace isolation 404, MEMBER access, format/date validation,
deterministic output.
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

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
from app.models.user import User, UserRole
from app.services.credit_control_service import utc_today

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

VALID_TRN = "100123456789012"
SELLER_ADDRESS = "Warehouse 12, Al Quoz, Dubai"


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def _set_workspace(headers: dict, **fields) -> None:
    body = {
        "trn": VALID_TRN,
        "address": SELLER_ADDRESS,
        "credit_limit_default": "100000.00",
    }
    body.update(fields)
    r = client.put("/api/v1/workspaces/me", json=body, headers=headers)
    assert r.status_code == 200, r.text


def _create_client(headers: dict, name: str = "Dealer", **extra) -> str:
    payload = {
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@ex.com",
        **extra,
    }
    r = client.post("/api/v1/clients", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _line(qty: str = "1", price: str = "100.00", **extra) -> dict:
    item = {
        "description": "NYM cable",
        "quantity": qty,
        "unit_price": price,
        "tax_rate": extra.pop("tax_rate", "0"),
    }
    item.update(extra)
    return item


def _sent_invoice(headers: dict, client_id: str, items: list[dict], **extra) -> dict:
    today = utc_today()
    body = {
        "client_id": client_id,
        "issue_date": extra.pop("issue_date", today.isoformat()),
        "due_date": extra.pop("due_date", (today + timedelta(days=30)).isoformat()),
        "items": items,
    }
    body.update(extra)
    r = client.post("/api/v1/invoices", json=body, headers=headers)
    assert r.status_code == 201, r.text
    sent = client.post(
        f"/api/v1/invoices/{r.json()['data']['id']}/send", json={}, headers=headers
    )
    assert sent.status_code == 200, sent.text
    return sent.json()["data"]


def _ar_ready() -> tuple[dict, str, str]:
    token, workspace_id = _register("exp_ar", "Export AR WS")
    headers = _headers(token)
    _set_workspace(headers)
    client_id = _create_client(headers, credit_limit="100000.00")
    return headers, client_id, workspace_id


def _create_supplier(token: str, name: str, code: str) -> str:
    r = client.post(
        "/api/v1/suppliers",
        headers=_headers(token),
        json={
            "name": name,
            "supplier_code": code,
            "email": f"{code.lower()}@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.json()
    return r.json()["data"]["id"]


def _seed_supplier_invoice(
    workspace_id: str, supplier_id: str, number: str, total: str, days_ago: int
) -> str:
    def _dt(d: date):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    invoice_date = date.today() - timedelta(days=days_ago)
    due = date.today() + timedelta(days=15)

    async def insert():
        from app.models.supplier_invoice import SupplierInvoice

        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=uuid.UUID(supplier_id),
                supplier_invoice_number=number,
                invoice_date=_dt(invoice_date),
                due_date=_dt(due),
                currency="AED",
                total_amount=Decimal(total),
                amount_paid=Decimal("0.00"),
                balance_due=Decimal(total),
                status="APPROVED",
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def _ap_ready() -> tuple[dict, str]:
    token, workspace_id = _register("exp_ap", "Export AP WS")
    _set_workspace(_headers(token))
    supplier_id = _create_supplier(token, "Export Co", "EXP-001")
    _seed_supplier_invoice(workspace_id, supplier_id, "EXP-INV-1", "1500.00", 3)
    return _headers(token), supplier_id


def _ar_export(headers, client_id: str, from_iso, to_iso, fmt: str, as_of=None):
    params = {"from": str(from_iso), "to": str(to_iso), "format": fmt}
    if as_of is not None:
        params["as_of"] = str(as_of)
    return client.get(
        f"/api/v1/clients/{client_id}/statement/export",
        headers=headers,
        params=params,
    )


def _ap_export(headers, supplier_id: str, from_iso, to_iso, fmt: str, as_of=None):
    params = {"from": str(from_iso), "to": str(to_iso), "format": fmt}
    if as_of is not None:
        params["as_of"] = str(as_of)
    return client.get(
        f"/api/v1/suppliers/{supplier_id}/statement/export",
        headers=headers,
        params=params,
    )


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


def _rows_by_label(text: str) -> dict[str, str]:
    labels = {
        "Statement Type",
        "Entity ID",
        "Entity Name",
        "Workspace",
        "Workspace TRN",
        "Currency",
        "Period From",
        "Period To",
        "As Of",
        "Total Billed",
        "Total Paid",
        "Total Credited",
        "Total Debited",
        "Total Pending",
        "Closing Balance",
        "Amount Due Now",
        "Credit Balance",
        "Aging Current",
        "Aging 1-30 Days",
        "Aging 31-60 Days",
        "Aging 61-90 Days",
        "Aging 90+ Days",
    }
    out: dict[str, str] = {}
    for line in text.split("\r\n"):
        if "," not in line:
            continue
        label, value = line.split(",", 1)
        if label in labels:
            out[label] = value
    return out


def test_ar_csv_structure_and_filename():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    sent = _sent_invoice(headers, client_id, [_line(price="100.00")])
    assert _dec(sent["total_amount"]) == Decimal("100.00")

    r = _ar_export(headers, client_id, today, today, "csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    expected = (
        f'attachment; filename="ar-statement-{client_id}-'
        f'{today.isoformat()}_to_{today.isoformat()}.csv"'
    )
    assert r.headers["content-disposition"] == expected

    body = r.content
    assert body.startswith(b"\xef\xbb\xbf")
    lines = body.decode("utf-8-sig").split("\r\n")

    # Block 0 — metadata, exact order
    assert lines[0] == "Statement Type,AR_STATEMENT"
    assert lines[1] == f"Entity ID,{client_id}"
    assert lines[2] == "Entity Name,Dealer"
    assert lines[3] == "Workspace,Export AR WS"
    assert lines[4] == f"Workspace TRN,{VALID_TRN}"
    assert lines[5] == "Currency,AED"
    assert lines[6] == f"Period From,{today.isoformat()}"
    assert lines[7] == f"Period To,{today.isoformat()}"
    assert lines[8] == f"As Of,{today.isoformat()}"

    # Block 1 — activity table
    assert lines[9] == ""
    assert (
        lines[10]
        == "Date,Type,Number,Reference,Payment Method,Payment Status,Pending,Debit,Credit,Balance"
    )
    assert "Opening balance" in lines[11]
    invoice_row = next(line for line in lines if f",{sent['invoice_number']}," in line)
    assert "Tax Invoice" in invoice_row

    labels = _rows_by_label(body.decode("utf-8-sig"))
    assert labels["Total Billed"] == "100.00"
    assert labels["Total Paid"] == "0.00"
    assert labels["Total Credited"] == "0.00"
    assert labels["Total Debited"] == "0.00"
    assert labels["Total Pending"] == "0.00"
    assert labels["Closing Balance"] == "100.00"
    assert labels["Amount Due Now"] == "100.00"
    assert labels["Credit Balance"] == "0.00"
    assert labels["Aging Current"] == "100.00"
    assert labels["Aging 1-30 Days"] == "0.00"
    assert labels["Aging 31-60 Days"] == "0.00"
    assert labels["Aging 61-90 Days"] == "0.00"
    assert labels["Aging 90+ Days"] == "0.00"


def test_ar_csv_equals_json_statement_numbers():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    _sent_invoice(headers, client_id, [_line(price="250.00")])

    json_r = client.get(
        f"/api/v1/clients/{client_id}/ar-statement",
        headers=headers,
        params={"from": today.isoformat(), "to": today.isoformat()},
    )
    assert json_r.status_code == 200, json_r.text
    data = json_r.json()["data"]

    r = _ar_export(headers, client_id, today, today, "csv")
    assert r.status_code == 200, r.text
    labels = _rows_by_label(r.content.decode("utf-8-sig"))
    json_labels = {
        "Closing Balance": str(data["totals"]["closing_running"]),
        "Amount Due Now": str(data["amount_due_now"]),
        "Credit Balance": str(data["credit_balance"]),
        "Aging Current": str(data["aging"]["buckets"]["current"]),
    }
    for label, expected in json_labels.items():
        assert labels[label] == expected, f"{label}: csv vs json mismatch"


def test_ar_pdf():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    _sent_invoice(headers, client_id, [_line(price="100.00")])

    r = _ar_export(headers, client_id, today, today, "pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    expected = (
        f'attachment; filename="ar-statement-{client_id}-'
        f'{today.isoformat()}_to_{today.isoformat()}.pdf"'
    )
    assert r.headers["content-disposition"] == expected


def test_ap_csv_structure_and_filename():
    headers, supplier_id = _ap_ready()
    today = date.today()
    from_iso = (today - timedelta(days=7)).isoformat()
    to_iso = (today + timedelta(days=7)).isoformat()

    r = _ap_export(headers, supplier_id, from_iso, to_iso, "csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    expected = (
        f'attachment; filename="ap-statement-{supplier_id}-'
        f'{from_iso}_to_{to_iso}.csv"'
    )
    assert r.headers["content-disposition"] == expected

    text = r.content.decode("utf-8-sig")
    assert r.content.startswith(b"\xef\xbb\xbf")
    lines = text.split("\r\n")
    assert lines[0] == "Statement Type,AP_STATEMENT"
    assert lines[1] == f"Entity ID,{supplier_id}"
    assert lines[2] == "Entity Name,Export Co"
    assert lines[5] == "Currency,AED"
    assert (
        lines[10]
        == "Date,Type,Number,Reference,Payment Method,Payment Status,Pending,Debit,Credit,Balance"
    )
    assert "Opening balance" in lines[11]

    labels = _rows_by_label(text)
    assert labels["Total Billed"] == "1500.00"
    assert labels["Closing Balance"] == "1500.00"
    assert "Total Debited" not in labels
    assert "Credit Balance" not in labels
    assert labels["Aging Current"] == "1500.00"


def test_ap_pdf():
    headers, supplier_id = _ap_ready()
    today = date.today()
    from_iso = (today - timedelta(days=7)).isoformat()
    to_iso = (today + timedelta(days=7)).isoformat()

    r = _ap_export(headers, supplier_id, from_iso, to_iso, "pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    expected = (
        f'attachment; filename="ap-statement-{supplier_id}-'
        f'{from_iso}_to_{to_iso}.pdf"'
    )
    assert r.headers["content-disposition"] == expected


def test_export_cross_workspace_404():
    headers_a, client_id, _workspace_id = _ar_ready()
    token_b, _ = _register("exp_iso_b", "Export Iso B")
    headers_b = _headers(token_b)
    _set_workspace(headers_b)
    today = utc_today().isoformat()

    ar = _ar_export(headers_b, client_id, today, today, "csv")
    assert ar.status_code == 404, ar.text
    assert ar.status_code != 403
    assert ar.json()["error"]["code"] == "NOT_FOUND"

    token_b2, _ = _register("exp_iso_b2", "Export Iso B2")
    headers_b2 = _headers(token_b2)
    _set_workspace(headers_b2)
    supplier_b = _create_supplier(token_b2, "For Co", "FOR-001")
    ap = _ap_export(headers_a, supplier_b, today, today, "pdf")
    assert ap.status_code == 404, ap.text
    assert ap.status_code != 403


def test_member_can_export_ar():
    headers, client_id, workspace_id = _ar_ready()
    today = utc_today()
    client_id = _create_client(headers, name="Member Dealer", credit_limit="1000.00")
    _sent_invoice(headers, client_id, [_line(price="50.00")])

    member = _member_token(workspace_id)
    r = _ar_export(_headers(member), client_id, today, today, "csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")


def test_format_validation_422():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    r = _ar_export(headers, client_id, today, today, "pizza")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_query_validation_422():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    inverted = _ar_export(headers, client_id, "2026-06-01", "2026-01-01", "csv")
    assert inverted.status_code == 422, inverted.text
    assert inverted.json()["error"]["code"] == "VALIDATION_ERROR"
    future = (utc_today() + timedelta(days=1)).isoformat()
    future_as_of = _ar_export(headers, client_id, today, today, "csv", as_of=future)
    assert future_as_of.status_code == 422, future_as_of.text
    assert future_as_of.json()["error"]["code"] == "VALIDATION_ERROR"

    token2, workspace2 = _register("exp_ap_guard", "Export AP Guard")
    headers2 = _headers(token2)
    supplier_id = _create_supplier(token2, "Guard Co", "GRD-001")
    ap_inverted = _ap_export(
        headers2,
        supplier_id,
        (today + timedelta(days=2)).isoformat(),
        today.isoformat(),
        "csv",
    )
    assert ap_inverted.status_code == 422, ap_inverted.text
    assert ap_inverted.json()["error"]["code"] == "VALIDATION_ERROR"
    ap_future = _ap_export(
        headers2,
        supplier_id,
        (today - timedelta(days=1)).isoformat(),
        today.isoformat(),
        "csv",
        as_of=future,
    )
    assert ap_future.status_code == 422, ap_future.text


def test_csv_export_is_deterministic():
    headers, client_id, _workspace_id = _ar_ready()
    today = utc_today()
    _sent_invoice(headers, client_id, [_line(price="75.00")])

    a = _ar_export(headers, client_id, today, today, "csv")
    b = _ar_export(headers, client_id, today, today, "csv")
    assert a.status_code == 200 and b.status_code == 200
    assert a.content == b.content


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))
