"""Wave 28 — UAE VAT Compliance Pack export tests (addendum §7).

Covers: zip integrity (7 entries, headers, manifest), per-line VAT math,
summary output/input with CN/TDN netting, excluded statuses, OVERDUE inclusion,
period guards, OWNER/ADMIN RBAC, JSON mirror, business-date-not-created_at,
no-TRN tolerance, workspace isolation, non-AED supplier invoices (listed but
never aggregated), and GST business-date rendering of supplier invoice_date.
"""

import asyncio
import csv
import io
import json
import sys
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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
from app.models.credit_note import (
    CreditNote,
    CreditNoteReason,
    CreditNoteStatus,
)  # noqa: E402
from app.models.credit_note_item import CreditNoteItem  # noqa: E402
from app.models.invoice import Invoice, InvoiceStatus  # noqa: E402
from app.models.invoice_item import InvoiceItem  # noqa: E402
from app.models.supplier_invoice import (  # noqa: E402
    SupplierInvoice,
    SupplierInvoiceStatus,
)
from app.models.tax_debit_note import (  # noqa: E402
    TaxDebitNote,
    TaxDebitNoteItem,
    TaxDebitNoteStatus,
)
from app.models.user import User, UserRole  # noqa: E402
from app.services.line_money import money  # noqa: E402

ZERO = Decimal("0.00")

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

    asyncio.run(_setup())
    yield

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_teardown())


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_token():
    email = f"vat_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "VAT Tester",
            "workspace_name": "VAT Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login", json={"email": email, "password": "securepassword123"}
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["data"]["workspace_id"]


def member_token(workspace_id):
    email = f"vat_member_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="VAT Member",
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


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _item(
    description="Widget",
    quantity=1.00,
    unit_price=100.00,
    tax_rate=5.00,
    discount_amount=0.00,
    line_net=None,
    tax_amount=None,
):
    net = _dec(line_net if line_net is not None else quantity * unit_price)
    tax = _dec(
        tax_amount
        if tax_amount is not None
        else money(net * _dec(tax_rate) / Decimal("100"))
    )
    return {
        "description": description,
        "quantity": _dec(quantity),
        "unit_price": _dec(unit_price),
        "tax_rate": _dec(tax_rate),
        "discount_amount": _dec(discount_amount),
        "line_net": net,
        "tax_amount": tax,
        "total_price": money(net + tax),
    }


def seed_client(workspace_id, name="Acme", tax_id="AE1000000002"):
    async def _insert():
        async with TestingSessionLocal() as session:
            entity = Client(
                workspace_id=uuid.UUID(workspace_id), name=name, tax_id=tax_id
            )
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity.id

    return asyncio.run(_insert())


def seed_invoice(
    workspace_id,
    client_id,
    number,
    issue_date,
    items,
    status="SENT",
    seller_trn="AE1000000001",
    buyer_trn="AE1000000002",
    invoice_kind="STANDARD",
    created_at=None,
):
    if items and "total_price" not in items[0]:
        items = [dict(_item(**item)) for item in items]
    subtotal = money(sum((i["line_net"] for i in items), ZERO))
    tax = money(sum((i["tax_amount"] for i in items), ZERO))
    total = money(subtotal + tax)
    now = datetime.now(timezone.utc)

    async def _insert_with_ids():
        async with TestingSessionLocal() as session:
            invoice = Invoice(
                workspace_id=uuid.UUID(workspace_id),
                client_id=client_id,
                invoice_number=number,
                currency="AED",
                subtotal=subtotal,
                tax_amount=tax,
                total_amount=total,
                status=InvoiceStatus(status),
                issue_date=issue_date,
                supply_date=issue_date,
                due_date=issue_date + timedelta(days=30),
                invoice_kind=invoice_kind,
                seller_trn_snapshot=seller_trn,
                buyer_trn_snapshot=buyer_trn,
                created_at=created_at or now,
                updated_at=now,
            )
            session.add(invoice)
            await session.flush()
            item_ids = []
            for item in items:
                row = InvoiceItem(
                    invoice_id=invoice.id,
                    description=item["description"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    tax_rate=item["tax_rate"],
                    discount_amount=item["discount_amount"],
                    line_net=item["line_net"],
                    tax_amount=item["tax_amount"],
                    total_price=item["total_price"],
                )
                session.add(row)
                await session.flush()
                item_ids.append(str(row.id))
            await session.commit()
            return invoice.id, invoice.invoice_number, item_ids

    return asyncio.run(_insert_with_ids())


def seed_credit_note(
    workspace_id,
    client_id,
    invoice_id,
    invoice_item_id,
    number,
    issue_date,
    items,
    status="ISSUED",
    buyer_trn="AE1000000002",
):
    if items and "total_price" not in items[0]:
        items = [dict(_item(**item)) for item in items]
    subtotal = money(sum((i["line_net"] for i in items), ZERO))
    tax = money(sum((i["tax_amount"] for i in items), ZERO))
    total = money(subtotal + tax)

    async def _insert():
        async with TestingSessionLocal() as session:
            note = CreditNote(
                workspace_id=uuid.UUID(workspace_id),
                client_id=client_id,
                invoice_id=invoice_id,
                credit_note_number=number,
                status=CreditNoteStatus(status),
                currency="AED",
                issue_date=issue_date,
                reason=CreditNoteReason.SALES_RETURN,
                subtotal=subtotal,
                tax_amount=tax,
                total_amount=total,
                invoice_kind="STANDARD",
                buyer_trn_snapshot=buyer_trn,
            )
            session.add(note)
            await session.flush()
            for item in items:
                session.add(
                    CreditNoteItem(
                        credit_note_id=note.id,
                        invoice_item_id=invoice_item_id,
                        description=item["description"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        tax_rate=item["tax_rate"],
                        discount_amount=item["discount_amount"],
                        line_net=item["line_net"],
                        tax_amount=item["tax_amount"],
                        total_price=item["total_price"],
                    )
                )
            await session.commit()

    asyncio.run(_insert())


def seed_tax_debit_note(
    workspace_id,
    client_id,
    invoice_id,
    invoice_item_id,
    number,
    issue_date,
    items,
    status="ISSUED",
    buyer_trn="AE1000000002",
):
    if items and "total_price" not in items[0]:
        items = [dict(_item(**item)) for item in items]
    subtotal = money(sum((i["line_net"] for i in items), ZERO))
    tax = money(sum((i["tax_amount"] for i in items), ZERO))
    total = money(subtotal + tax)

    async def _insert():
        async with TestingSessionLocal() as session:
            note = TaxDebitNote(
                workspace_id=uuid.UUID(workspace_id),
                client_id=client_id,
                invoice_id=invoice_id,
                debit_note_number=number,
                status=TaxDebitNoteStatus(status),
                currency="AED",
                issue_date=issue_date,
                reason="INVOICE_ERROR",
                subtotal=subtotal,
                tax_amount=tax,
                total_amount=total,
                invoice_kind="STANDARD",
                buyer_trn_snapshot=buyer_trn,
            )
            session.add(note)
            await session.flush()
            for item in items:
                session.add(
                    TaxDebitNoteItem(
                        tax_debit_note_id=note.id,
                        invoice_item_id=invoice_item_id,
                        description=item["description"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        tax_rate=item["tax_rate"],
                        discount_percent=_dec(0.00),
                        tax_amount=item["tax_amount"],
                        total_price=item["total_price"],
                    )
                )
            await session.commit()

    asyncio.run(_insert())


_catalog = {}


def ensure_catalog(token, workspace_id):
    if workspace_id in _catalog:
        return _catalog[workspace_id]
    headers = _headers(token)
    uom_r = client.post(
        "/api/v1/products/uom",
        headers=headers,
        json={"name": "Pieces", "code": f"PCS{uuid.uuid4().hex[:4].upper()}"},
    )
    assert uom_r.status_code in (200, 201), uom_r.text
    uom_id = uom_r.json()["data"]["id"]
    product_r = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "VAT Widget",
            "internal_sku": f"VAT{uuid.uuid4().hex[:8]}",
            "base_uom_id": uom_id,
        },
    )
    assert product_r.status_code in (200, 201), product_r.text
    product_id = product_r.json()["data"]["id"]
    supplier_r = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "name": "VAT Supplier Co",
            "supplier_code": f"VSUP{uuid.uuid4().hex[:4].upper()}",
            "email": "sup@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert supplier_r.status_code in (200, 201), supplier_r.text
    supplier_id = supplier_r.json()["data"]["id"]
    entry = {
        "uom_id": uom_id,
        "product_id": product_id,
        "supplier_id": supplier_id,
    }
    _catalog[workspace_id] = entry
    return entry


def create_supplier_invoice(
    token,
    workspace_id,
    number,
    invoice_date,
    currency="AED",
    net=60.00,
    vat_rate=5.00,
    vat_amount=None,
):
    catalog = ensure_catalog(token, workspace_id)
    net = _dec(net)
    vat = _dec(
        vat_amount if vat_amount is not None else money(net * _dec(vat_rate) / 100)
    )
    total = money(net + vat)
    body = {
        "supplier_id": catalog["supplier_id"],
        "supplier_invoice_number": number,
        "invoice_date": invoice_date.isoformat(),
        "due_date": (invoice_date + timedelta(days=30)).isoformat(),
        "currency": currency,
        "subtotal": str(net),
        "discount_amount": "0.00",
        "vat_amount": str(vat),
        "total_amount": str(total),
        "items": [
            {
                "product_id": catalog["product_id"],
                "description": f"Item {number}",
                "quantity": "1.0000",
                "uom_id": catalog["uom_id"],
                "unit_price": str(net),
                "vat_rate": str(_dec(vat_rate)),
                "vat_amount": str(vat),
                "total_price": str(total),
                "currency": currency,
            }
        ],
    }
    r = client.post("/api/v1/supplier-invoices", headers=_headers(token), json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def set_supplier_invoice_status(supplier_invoice_id, status):
    async def _update():
        async with TestingSessionLocal() as session:
            invoice = await session.get(SupplierInvoice, uuid.UUID(supplier_invoice_id))
            invoice.status = SupplierInvoiceStatus(status)
            await session.commit()

    asyncio.run(_update())


def unzip(response):
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def get_csv(token, period_from="2026-09-01", period_to="2026-09-30"):
    return client.get(
        f"/api/v1/reports/vat-compliance?from={period_from}&to={period_to}",
        headers=_headers(token),
    )


def get_json(token, period_from="2026-09-01", period_to="2026-09-30"):
    return client.get(
        f"/api/v1/reports/vat-compliance?from={period_from}&to={period_to}&format=json",
        headers=_headers(token),
    )


def test_1_csv_zip_integrity():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(workspace_id, client_id, "VAT-INV-001", date(2026, 9, 5), [_item()])

    r = get_csv(token)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert (
        'filename="vat-compliance-2026-09-01_to_2026-09-30.zip"'
        in r.headers["content-disposition"]
    )
    content = unzip(r)
    assert sorted(content.keys()) == [
        "credit_notes.csv",
        "invoice_lines.csv",
        "manifest.json",
        "purchase_invoices.csv",
        "sales_invoices.csv",
        "tax_debit_notes.csv",
        "vat_summary.csv",
    ]
    for text in content.values():
        if text.endswith(".csv"):
            assert content[text].strip().splitlines()[0], text
    manifest = json.loads(content["manifest.json"])
    assert manifest["generator"] == "InvoiceSaaS VAT Compliance Pack"
    assert manifest["period"] == {"from": "2026-09-01", "to": "2026-09-30"}
    assert manifest["currency"] == "AED"
    assert manifest["org"]["trn"] is not None
    assert manifest["warnings"]["non_aed_supplier_invoices"] == []
    assert sorted(manifest["files"]) == [
        "credit_notes.csv",
        "invoice_lines.csv",
        "purchase_invoices.csv",
        "sales_invoices.csv",
        "tax_debit_notes.csv",
        "vat_summary.csv",
    ]


def test_2_per_line_vat_math():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-INV-002",
        date(2026, 9, 5),
        [_item(description="Five", unit_price=100.00, tax_rate=5.00)],
    )
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-INV-003",
        date(2026, 9, 6),
        [_item(description="Zero", unit_price=50.00, tax_rate=0.00)],
    )

    content = unzip(get_csv(token))
    lines = parse_csv(content["invoice_lines.csv"])
    assert len(lines) == 2
    five = next(row for row in lines if row["description"] == "Five")
    assert five["line_net"] == "100.00"
    assert five["tax_amount"] == "5.00"
    assert five["tax_rate"] == "5.00"
    assert five["total_price"] == "105.00"
    zero = next(row for row in lines if row["description"] == "Zero")
    assert zero["line_net"] == "50.00"
    assert zero["tax_amount"] == "0.00"
    assert zero["tax_rate"] == "0.00"


def test_3_summary_netting():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    _, _, item_ids = seed_invoice(
        workspace_id,
        client_id,
        "VAT-INV-004",
        date(2026, 9, 5),
        [_item(unit_price=100.00, tax_rate=5.00)],
    )
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-INV-005",
        date(2026, 9, 6),
        [_item(unit_price=50.00, tax_rate=0.00)],
    )
    seed_credit_note(
        workspace_id,
        client_id,
        uuid.UUID(_first_invoice_id(workspace_id, "VAT-INV-004")),
        uuid.UUID(item_ids[0]),
        "VAT-CN-001",
        date(2026, 9, 7),
        [_item(unit_price=20.00, tax_rate=5.00)],
    )
    seed_tax_debit_note(
        workspace_id,
        client_id,
        uuid.UUID(_first_invoice_id(workspace_id, "VAT-INV-004")),
        uuid.UUID(item_ids[0]),
        "VAT-TDN-001",
        date(2026, 9, 8),
        [_item(unit_price=20.00, tax_rate=5.00)],
    )
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-001",
        datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
    )

    content = unzip(get_csv(token))
    rows = parse_csv(content["vat_summary.csv"])
    output5 = next(
        r for r in rows if r["direction"] == "output" and r["tax_rate"] == "5.00"
    )
    output0 = next(
        r for r in rows if r["direction"] == "output" and r["tax_rate"] == "0.00"
    )
    input5 = next(
        r for r in rows if r["direction"] == "input" and r["tax_rate"] == "5.00"
    )
    assert output5["taxable_amount"] == "100.00"
    assert output5["vat_amount"] == "5.00"
    assert output0["taxable_amount"] == "50.00"
    assert output0["vat_amount"] == "0.00"
    assert input5["taxable_amount"] == "60.00"
    assert input5["vat_amount"] == "3.00"
    assert output5["count"] == "3"
    manifest = json.loads(content["manifest.json"])
    assert manifest["summary"]["output_tax"] == "5.00"
    assert manifest["summary"]["input_tax"] == "3.00"
    assert manifest["summary"]["net_tax"] == "2.00"


def _first_invoice_id(workspace_id, number):
    async def _get():
        async with TestingSessionLocal() as session:
            result = await session.execute(
                select(Invoice).where(
                    Invoice.workspace_id == uuid.UUID(workspace_id),
                    Invoice.invoice_number == number,
                )
            )
            invoice = result.scalar_one_or_none()
            return str(invoice.id) if invoice else None

    return asyncio.run(_get())


def test_4_excluded_statuses_absent():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-DRAFT",
        date(2026, 9, 5),
        [_item()],
        status="DRAFT",
        invoice_kind=None,
    )
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-CANC",
        date(2026, 9, 5),
        [_item()],
        status="CANCELLED",
    )
    seed_invoice(
        workspace_id, client_id, "VAT-LIVE", date(2026, 9, 5), [_item()], status="SENT"
    )
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-OVER",
        date(2026, 9, 5),
        [_item()],
        status="OVERDUE",
    )
    _, _, item_ids = seed_invoice(
        workspace_id, client_id, "VAT-CNBASE", date(2026, 9, 5), [_item()]
    )
    seed_credit_note(
        workspace_id,
        client_id,
        _invoice_uuid(workspace_id, "VAT-CNBASE"),
        uuid.UUID(item_ids[0]),
        "VAT-CN-DRAFT",
        date(2026, 9, 6),
        [_item()],
        status="DRAFT",
    )
    seed_tax_debit_note(
        workspace_id,
        client_id,
        _invoice_uuid(workspace_id, "VAT-CNBASE"),
        uuid.UUID(item_ids[0]),
        "VAT-TDN-DRAFT",
        date(2026, 9, 6),
        [_item()],
        status="DRAFT",
    )
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-RECV",
        datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
    )
    appr = create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-APPR",
        datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
    )
    canc = create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-CANC",
        datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
    )
    set_supplier_invoice_status(appr, "APPROVED")
    set_supplier_invoice_status(canc, "CANCELLED")

    content = unzip(get_csv(token))
    sales = parse_csv(content["sales_invoices.csv"])
    numbers = {row["invoice_number"] for row in sales}
    assert "VAT-DRAFT" not in numbers
    assert "VAT-CANC" not in numbers
    assert "VAT-LIVE" in numbers
    assert "VAT-OVER" in numbers
    cns = parse_csv(content["credit_notes.csv"])
    cn_numbers = {row["credit_note_number"] for row in cns}
    assert "VAT-CN-DRAFT" not in cn_numbers
    tdns = parse_csv(content["tax_debit_notes.csv"])
    tdn_numbers = {row["debit_note_number"] for row in tdns}
    assert "VAT-TDN-DRAFT" not in tdn_numbers
    purchase = parse_csv(content["purchase_invoices.csv"])
    by_number = {row["supplier_invoice_number"]: row for row in purchase}
    assert "VAT-SI-RECV" in by_number
    assert "VAT-SI-APPR" in by_number
    assert "VAT-SI-CANC" not in by_number


def _invoice_uuid(workspace_id, number):
    value = _first_invoice_id(workspace_id, number)
    assert value is not None
    return uuid.UUID(value)


def test_5_overdue_included():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-OVERDUE",
        date(2026, 9, 10),
        [_item()],
        status="OVERDUE",
    )
    content = unzip(get_csv(token))
    sales = parse_csv(content["sales_invoices.csv"])
    assert any(row["invoice_number"] == "VAT-OVERDUE" for row in sales)
    lines = parse_csv(content["invoice_lines.csv"])
    assert any(row["invoice_number"] == "VAT-OVERDUE" for row in lines)


def test_6_period_bounds():
    token, _ = register_and_token()
    r = client.get(
        "/api/v1/reports/vat-compliance?from=2026-01-01&to=2027-01-03",
        headers=_headers(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "DATE_RANGE_TOO_LONG"
    r = client.get(
        "/api/v1/reports/vat-compliance?from=2026-09-30&to=2026-09-01",
        headers=_headers(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_7_rbac_member_forbidden():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(workspace_id, client_id, "VAT-RBAC", date(2026, 9, 5), [_item()])
    member = member_token(workspace_id)
    for response in (get_csv(member), get_json(member)):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_8_json_mirror():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-MIRR-1",
        date(2026, 9, 5),
        [_item(unit_price=100.00, tax_rate=5.00)],
    )
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-MIRR-2",
        date(2026, 9, 6),
        [_item(unit_price=50.00, tax_rate=0.00)],
    )
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-MIRR",
        datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
    )

    r = get_json(token)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    data = r.json()["data"]
    assert len(data["sales_invoices"]) == 2
    assert len(data["invoice_lines"]) == 2
    assert len(data["purchase_invoices"]) == 1

    content = unzip(get_csv(token))
    csv_lines = parse_csv(content["invoice_lines.csv"])
    csv_sales = parse_csv(content["sales_invoices.csv"])
    assert {row["invoice_number"] for row in csv_lines} == {
        s["invoice_number"] for s in data["sales_invoices"]
    }
    assert float(data["manifest"]["summary"]["output_tax"]) == pytest.approx(5.00)
    assert float(data["manifest"]["summary"]["input_tax"]) == pytest.approx(3.00)
    assert float(data["manifest"]["summary"]["net_tax"]) == pytest.approx(2.00)
    assert data["manifest"]["period"] == {"from": "2026-09-01", "to": "2026-09-30"}
    assert len(csv_sales) == len(data["sales_invoices"])


def test_9_business_date_not_created_at():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id)
    backdated = datetime(2025, 1, 1, tzinfo=timezone.utc)
    seed_invoice(
        workspace_id,
        client_id,
        "VAT-DATE-IN",
        date(2026, 9, 10),
        [_item()],
        created_at=backdated,
    )
    seed_invoice(workspace_id, client_id, "VAT-DATE-OUT", date(2025, 9, 10), [_item()])
    content = unzip(get_csv(token))
    sales = parse_csv(content["sales_invoices.csv"])
    numbers = {row["invoice_number"] for row in sales}
    assert "VAT-DATE-IN" in numbers
    assert "VAT-DATE-OUT" not in numbers


def test_10_no_trn_tolerance():
    token, _ = register_and_token()
    r = get_json(token)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["manifest"]["org"]["trn"] == ""
    content = unzip(get_csv(token))
    manifest = json.loads(content["manifest.json"])
    assert manifest["org"]["trn"] == ""


def test_11_workspace_isolation():
    token_a, workspace_a = register_and_token()
    client_id_a = seed_client(workspace_a)
    seed_invoice(workspace_a, client_id_a, "VAT-ISO-A", date(2026, 9, 5), [_item()])
    token_b, _ = register_and_token()

    content_a = unzip(get_csv(token_a))
    assert len(parse_csv(content_a["sales_invoices.csv"])) == 1
    content_b = unzip(get_csv(token_b))
    assert parse_csv(content_b["sales_invoices.csv"]) == []
    r_b = get_json(token_b)
    assert r_b.status_code == 200, r_b.text
    assert r_b.json()["data"]["sales_invoices"] == []


def test_12_non_aed_supplier_invoices():
    token, workspace_id = register_and_token()
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-AED",
        datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
        net=60.00,
    )
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-USD",
        datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
        currency="USD",
        net=1000.00,
    )

    content = unzip(get_csv(token))
    purchase = parse_csv(content["purchase_invoices.csv"])
    by_number = {row["supplier_invoice_number"]: row for row in purchase}
    assert by_number["VAT-SI-AED"]["currency"] == "AED"
    assert by_number["VAT-SI-USD"]["currency"] == "USD"
    assert by_number["VAT-SI-USD"]["vat_amount"] == "50.00"
    manifest = json.loads(content["manifest.json"])
    assert manifest["warnings"]["non_aed_supplier_invoices"] == ["VAT-SI-USD"]
    summary = parse_csv(content["vat_summary.csv"])
    input_rows = [row for row in summary if row["direction"] == "input"]
    assert len(input_rows) == 1
    assert input_rows[0]["taxable_amount"] == "60.00"
    assert input_rows[0]["vat_amount"] == "3.00"
    assert manifest["summary"]["input_tax"] == "3.00"
    assert manifest["summary"]["net_tax"] == "-3.00"


def test_13_gst_business_date():
    token, workspace_id = register_and_token()
    # Instant 2026-08-31T20:30Z == 2026-09-01 00:30 +04:00 -> GST date 09-01.
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-GST1",
        datetime(2026, 8, 31, 20, 30, tzinfo=timezone.utc),
    )
    # 2026-09-01T23:00Z == 2026-09-02 03:00 +04:00 -> GST date 09-02.
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-GST2",
        datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc),
    )
    # 2026-08-31T18:00Z == 2026-08-31 22:00 +04:00 -> GST date 08-31 (out of window).
    create_supplier_invoice(
        token,
        workspace_id,
        "VAT-SI-GST3",
        datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc),
    )

    content = unzip(get_csv(token))
    purchase = parse_csv(content["purchase_invoices.csv"])
    by_number = {row["supplier_invoice_number"]: row for row in purchase}
    assert set(by_number) == {"VAT-SI-GST1", "VAT-SI-GST2"}
    assert by_number["VAT-SI-GST1"]["invoice_date"] == "2026-09-01"
    assert by_number["VAT-SI-GST2"]["invoice_date"] == "2026-09-02"

    r = get_json(token)
    data_numbers = {
        p["supplier_invoice_number"] for p in r.json()["data"]["purchase_invoices"]
    }
    assert data_numbers == {"VAT-SI-GST1", "VAT-SI-GST2"}
