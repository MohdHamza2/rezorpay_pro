"""Wave 23 — supplier debit note tests.

Covers: manual create→issue→apply (balance_due reduction only, no PAID flip),
apply guards (DRAFT, double-apply 409, over-balance, supplier mismatch, foreign
invoice, payable-status gate), cancel rules, and the dispatch auto-SDN from a
purchase return.
"""

import asyncio
import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

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
from app.models.supplier_invoice import (  # noqa: E402
    SupplierInvoice,
    SupplierInvoiceStatus,
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


def register_and_token():
    email = f"sdn_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "SDN Tester",
            "workspace_name": "SDN Workspace",
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


def create_supplier(token, code=None):
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "name": "DNCo",
            "supplier_code": code or f"DN{uuid.uuid4().hex[:4]}",
            "email": "dn@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def seed_invoice(
    workspace_id,
    supplier_id,
    number,
    total,
    *,
    status=SupplierInvoiceStatus.APPROVED,
    amount_paid=Decimal("0"),
):
    def _dt(d):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)

    total = Decimal(str(total))

    async def insert():
        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=uuid.UUID(supplier_id),
                supplier_invoice_number=number,
                invoice_date=_dt(date.today() - timedelta(days=3)),
                due_date=_dt(date.today() + timedelta(days=15)),
                currency="AED",
                total_amount=total,
                amount_paid=Decimal(str(amount_paid)),
                balance_due=total - Decimal(str(amount_paid)),
                status=(
                    status.value
                    if isinstance(status, SupplierInvoiceStatus)
                    else status
                ),
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return str(invoice.id)

    return asyncio.run(insert())


def create_note(
    token, supplier_id, amount, reason="Manual credit note", issue_date=None
):
    return client.post(
        "/api/v1/supplier-debit-notes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "supplier_id": supplier_id,
            "amount": amount,
            "reason": reason,
            "issue_date": issue_date or date.today().isoformat(),
        },
    )


def require_issued(token, note_id):
    r = client.post(
        f"/api/v1/supplier-debit-notes/{note_id}/issue",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def apply_note(token, note_id, invoice_id):
    return client.post(
        f"/api/v1/supplier-debit-notes/{note_id}/apply",
        json={"supplier_invoice_id": invoice_id},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _balance_due(invoice_id: str) -> Decimal:
    async with TestingSessionLocal() as session:
        inv = await session.get(SupplierInvoice, uuid.UUID(invoice_id))
        return Decimal(inv.balance_due)


async def _invoice_status(invoice_id: str) -> str:
    async with TestingSessionLocal() as session:
        inv = await session.get(SupplierInvoice, uuid.UUID(invoice_id))
        return inv.status.value


def test_manual_create_issue_apply_reduces_balance_only():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "DN-INV-1", 1000)

    r = create_note(token, supplier_id, "300")
    assert r.status_code == 201, r.text
    note = r.json()["data"]
    assert note["status"] == "DRAFT"
    assert note["source_type"] == "MANUAL"
    assert re.match(r"^SDN-\d{4}-\d{4}$", note["dn_number"])

    issued = require_issued(token, note["id"])
    assert issued["status"] == "ISSUED"

    applied = apply_note(token, note["id"], invoice_id)
    assert applied.status_code == 200, applied.text
    data = applied.json()["data"]
    assert data["status"] == "APPLIED"
    assert data["applied_invoice_id"] == invoice_id
    assert data["applied_at"] is not None

    assert asyncio.run(_balance_due(invoice_id)) == Decimal("700.00")
    assert asyncio.run(_invoice_status(invoice_id)) == "APPROVED"


def test_apply_exact_balance_leaves_status_approved():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "DN-INV-2", 500)

    note = create_note(token, supplier_id, "500").json()["data"]
    require_issued(token, note["id"])
    applied = apply_note(token, note["id"], invoice_id)
    assert applied.status_code == 200, applied.text

    assert asyncio.run(_balance_due(invoice_id)) == Decimal("0.00")
    assert asyncio.run(_invoice_status(invoice_id)) == "APPROVED"
    assert applied.json()["data"]["status"] == "APPLIED"


def test_apply_guards():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "DN-INV-3", 1000)

    # DRAFT cannot apply
    draft = create_note(token, supplier_id, "100").json()["data"]
    r = apply_note(token, draft["id"], invoice_id)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STATE"

    # over balance
    big = create_note(token, supplier_id, "2000").json()["data"]
    require_issued(token, big["id"])
    r = apply_note(token, big["id"], invoice_id)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "DEBIT_NOTE_EXCEEDS_BALANCE"

    # double apply
    ok = create_note(token, supplier_id, "200").json()["data"]
    require_issued(token, ok["id"])
    assert apply_note(token, ok["id"], invoice_id).status_code == 200
    r = apply_note(token, ok["id"], invoice_id)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"

    # supplier mismatch
    other_supplier = create_supplier(token, "OPP")
    other_invoice = seed_invoice(workspace_id, other_supplier, "DN-INV-4", 900)
    note = create_note(token, supplier_id, "50").json()["data"]
    require_issued(token, note["id"])
    r = apply_note(token, note["id"], other_invoice)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STATE"

    # foreign invoice → 404
    token_b, ws_b = register_and_token()
    foreign_sup = create_supplier(token_b)
    foreign_inv = seed_invoice(ws_b, foreign_sup, "DN-INV-F", 800)
    r = apply_note(token, note["id"], foreign_inv)
    assert r.status_code == 404, r.text

    # MATCHED (non-payable) invoice gate
    sent_inv = seed_invoice(
        workspace_id,
        supplier_id,
        "DN-INV-5",
        700,
        status=SupplierInvoiceStatus.MATCHED,
    )
    note2 = create_note(token, supplier_id, "30").json()["data"]
    require_issued(token, note2["id"])
    r = apply_note(token, note2["id"], sent_inv)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_cancel_rules():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    invoice_id = seed_invoice(workspace_id, supplier_id, "DN-INV-6", 1000)
    headers = {"Authorization": f"Bearer {token}"}

    # cancel a DRAFT
    draft = create_note(token, supplier_id, "40").json()["data"]
    r = client.post(
        f"/api/v1/supplier-debit-notes/{draft['id']}/cancel",
        json={},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "CANCELLED"
    assert r.json()["data"]["cancelled_at"] is not None

    # cancel an ISSUED
    issued = create_note(token, supplier_id, "60").json()["data"]
    require_issued(token, issued["id"])
    r = client.post(
        f"/api/v1/supplier-debit-notes/{issued['id']}/cancel",
        json={},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "CANCELLED"

    # cannot cancel an APPLIED note
    applied = create_note(token, supplier_id, "80").json()["data"]
    require_issued(token, applied["id"])
    apply_note(token, applied["id"], invoice_id)
    r = client.post(
        f"/api/v1/supplier-debit-notes/{applied['id']}/cancel",
        json={},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STATE"

    # applying a cancelled note is invalid
    note = create_note(token, supplier_id, "90").json()["data"]
    require_issued(token, note["id"])
    client.post(
        f"/api/v1/supplier-debit-notes/{note['id']}/cancel",
        json={},
        headers=headers,
    )
    r = apply_note(token, note["id"], invoice_id)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_dispatch_auto_sdn():
    token, _ = register_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    sup = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "name": "AutoCo",
            "supplier_code": f"AUT{uuid.uuid4().hex[:4]}",
            "email": "a@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    ).json()["data"]
    wh = client.post(
        "/api/v1/inventory/warehouses",
        headers=headers,
        json={"name": "WH", "code": "WH", "address": "x"},
    ).json()["data"]
    client.post(
        f"/api/v1/inventory/warehouses/{wh['id']}/bins",
        headers=headers,
        json={"code": "B1"},
    )
    uom = client.post(
        "/api/v1/products/uom",
        headers=headers,
        json={"name": "UOM", "code": "UOM"},
    ).json()["data"]
    prod = client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "P", "internal_sku": "SKU", "base_uom_id": uom["id"]},
    ).json()["data"]

    spo = client.post(
        "/api/v1/spos",
        headers=headers,
        json={
            "supplier_id": sup["id"],
            "procurement_method": "DIRECT",
            "warehouse_id": wh["id"],
            "currency": "AED",
            "items": [
                {
                    "product_id": prod["id"],
                    "description": "W",
                    "uom_id": uom["id"],
                    "quantity_ordered": 10,
                    "unit_price": 25.0,
                    "vat_rate": 0,
                    "line_number": 1,
                }
            ],
        },
    ).json()["data"]
    spo_item_id = spo["items"][0]["id"]
    for action in ("submit-approval", "approve", "send"):
        client.post(f"/api/v1/spos/{spo['id']}/{action}", headers=headers)
    client.post(
        f"/api/v1/spos/{spo['id']}/items/acknowledge",
        headers=headers,
        json={"lines": {spo_item_id: {"quantity_confirmed": 10, "unit_price": 25.0}}},
    )

    grn = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": sup["id"],
            "spo_id": spo["id"],
            "warehouse_id": wh["id"],
            "received_date": "2026-09-05",
        },
    ).json()["data"]
    client.post(f"/api/v1/grns/{grn['id']}/start-receiving", headers=headers)
    gi = client.post(
        f"/api/v1/grns/{grn['id']}/items",
        headers=headers,
        json={
            "spo_item_id": spo_item_id,
            "product_id": prod["id"],
            "internal_sku": "SKU",
            "description": "W",
            "uom_id": uom["id"],
            "quantity_received": 10,
        },
    ).json()["data"]["items"][0]
    client.post(f"/api/v1/grns/{grn['id']}/stage-for-inspection", headers=headers)
    client.post(
        f"/api/v1/grns/{grn['id']}/items/{gi['id']}/disposition",
        headers=headers,
        json={"quantity_accepted": 10, "quantity_damaged": 0, "quantity_rejected": 0},
    )

    pr = client.post(
        "/api/v1/purchase-returns",
        headers=headers,
        json={
            "supplier_id": sup["id"],
            "grn_id": grn["id"],
            "return_date": "2026-09-06",
            "reason": "Returning surplus goods",
            "items": [
                {
                    "grn_item_id": gi["id"],
                    "quantity": 4,
                    "unit_price": 25.0,
                    "return_type": "EXCESS",
                }
            ],
        },
    ).json()["data"]

    client.post(
        f"/api/v1/purchase-returns/{pr['id']}/submit-for-supplier-approval",
        json={},
        headers=headers,
    )
    client.post(
        f"/api/v1/purchase-returns/{pr['id']}/approve", json={}, headers=headers
    )
    dispatched = client.post(
        f"/api/v1/purchase-returns/{pr['id']}/dispatch", json={}, headers=headers
    )
    assert dispatched.status_code == 200, dispatched.text

    notes = client.get(
        f"/api/v1/supplier-debit-notes?purchase_return_id={pr['id']}",
        headers=headers,
    ).json()["data"]
    assert len(notes) == 1
    note = notes[0]
    assert note["status"] == "ISSUED"
    assert note["source_type"] == "PURCHASE_RETURN"
    assert note["amount"] == "100.00"
    assert note["purchase_return_id"] == pr["id"]


def test_list_filters_and_sequence():
    token, workspace_id = register_and_token()
    supplier_id = create_supplier(token)
    seed_invoice(workspace_id, supplier_id, "DN-INV-7", 1000)
    headers = {"Authorization": f"Bearer {token}"}

    n1 = create_note(token, supplier_id, "100").json()["data"]
    n2 = create_note(token, supplier_id, "200").json()["data"]

    lst = client.get(
        f"/api/v1/supplier-debit-notes?supplier_id={supplier_id}",
        headers=headers,
    ).json()["data"]
    assert [n["id"] for n in lst] == [n2["id"], n1["id"]]
    assert {"100.00", "200.00"} == {n["amount"] for n in lst}

    year = datetime.now(timezone.utc).year
    assert n1["dn_number"] == f"SDN-{year}-0001"
    assert n2["dn_number"] == f"SDN-{year}-0002"

    got = client.get(f"/api/v1/supplier-debit-notes/{n1['id']}", headers=headers)
    assert got.status_code == 200 and got.json()["data"]["id"] == n1["id"]

    missing = client.get(
        f"/api/v1/supplier-debit-notes/{uuid.uuid4()}", headers=headers
    )
    assert missing.status_code == 404
