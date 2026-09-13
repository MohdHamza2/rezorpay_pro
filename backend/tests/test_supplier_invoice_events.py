"""Wave 31 Item 2.6 — supplier-invoice event/history tests.

Covers: CREATED/MATCH_SUBMITTED/MATCHED/DISCREPANCY/DISCREPANCY_RESOLVED/
APPROVED/PARTIALLY_PAID/PAID/PAYMENT_REVERSED/DEBIT_NOTE_APPLIED emission,
actor attribution, previous/new statuses, compact reference metadata,
chronological ordering, empty history, cross-tenant 404, failed operations
leaving no rows, idempotent replay producing no duplicate event set,
PDC-record silence, and event immutability (no mutation API).
"""

import asyncio
import sys
import uuid
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

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from app.models.supplier_invoice_event import SupplierInvoiceEvent

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


def register_and_token(tag="ap_ev"):
    email = f"{tag}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AP Events Tester",
            "workspace_name": "AP Events Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    data = me.json()["data"]
    return token, data["workspace_id"], data["id"]


def create_supplier(token, name, code):
    r = client.post(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {token}"},
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


def _dt(d):
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)


def seed_invoice(
    workspace_id,
    supplier_id,
    number,
    total_amount,
    status=SupplierInvoiceStatus.APPROVED,
    amount_paid=Decimal("0.00"),
):
    total_amount = Decimal(str(total_amount))

    async def insert():
        async with TestingSessionLocal() as session:
            invoice = SupplierInvoice(
                workspace_id=workspace_id,
                supplier_id=supplier_id,
                supplier_invoice_number=number,
                invoice_date=_dt(date.today() - timedelta(days=3)),
                due_date=_dt(date.today() + timedelta(days=15)),
                currency="AED",
                subtotal=total_amount,
                discount_amount=Decimal("0.00"),
                vat_amount=Decimal("0.00"),
                total_amount=total_amount,
                amount_paid=amount_paid,
                balance_due=total_amount - amount_paid,
                status=status,
                three_way_match_status="PASSED",
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def audit_log(token, invoice_id):
    r = client.get(
        f"/api/v1/supplier-invoices/{invoice_id}/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def create_chain(
    token,
    workspace_id,
    tag,
    qty_ordered=100,
    qty_accept=100,
    billed_qty=100,
    inv_number="EV-INV-1",
):
    """Supplier→UOM→product→warehouse→SPO→ack→GRN→accept→supplier invoice."""
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, f"EvCo {tag}", f"EV-{tag}")
    r = client.post(
        "/api/v1/products/uom",
        headers=headers,
        json={"name": "Pieces", "code": f"EVU-{tag}"},
    )
    uom_id = r.json()["data"]["id"]
    r = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": f"EvWidget {tag}",
            "internal_sku": f"EVW-{tag}",
            "description": "event widget",
            "base_uom_id": uom_id,
        },
    )
    product_id = r.json()["data"]["id"]
    r = client.post(
        "/api/v1/inventory/warehouses",
        headers=headers,
        json={"name": f"EvWH {tag}", "code": f"EVWH-{tag}", "address": "Dubai"},
    )
    warehouse_id = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        headers=headers,
        json={"code": "EVBIN1"},
    )
    assert r.status_code in (200, 201), r.text

    r = client.post(
        f"/api/v1/spos?workspace_id={workspace_id}",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "procurement_method": "DIRECT",
            "currency": "AED",
            "expected_delivery_date": "2026-12-01T00:00:00Z",
            "items": [
                {
                    "line_number": 1,
                    "product_id": product_id,
                    "description": "EvWidget",
                    "quantity_ordered": qty_ordered,
                    "uom_id": uom_id,
                    "unit_price": 50.0,
                    "vat_rate": 5.0,
                    "vat_amount": 250.0,
                    "total_price": 5250.0,
                    "currency": "AED",
                }
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    spo_id = r.json()["data"]["id"]
    spo_item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/spos/{spo_id}/submit-approval", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/approve", headers=headers)
    client.post(f"/api/v1/spos/{spo_id}/send", headers=headers)
    r = client.post(
        f"/api/v1/spos/{spo_id}/items/acknowledge",
        headers=headers,
        json={
            "lines": {
                spo_item_id: {"quantity_confirmed": qty_ordered, "unit_price": 50.0}
            }
        },
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "received_date": "2026-08-23T00:00:00Z",
            "spo_id": spo_id,
        },
    )
    assert r.status_code in (200, 201), r.text
    grn_id = r.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)
    r = client.post(
        f"/api/v1/grns/{grn_id}/items",
        headers=headers,
        json={
            "spo_item_id": spo_item_id,
            "product_id": product_id,
            "internal_sku": f"EVW-{tag}",
            "description": "EvWidget",
            "uom_id": uom_id,
            "quantity_received": qty_ordered,
        },
    )
    assert r.status_code in (200, 201), r.text
    grn_item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)
    damaged = qty_ordered - qty_accept
    r = client.post(
        f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition",
        headers=headers,
        json={
            "quantity_accepted": qty_accept,
            "quantity_damaged": damaged,
            "quantity_rejected": 0,
            "damage_reason": "Bent surfaces on units" if damaged else "",
        },
    )
    assert r.status_code == 200, r.text

    line_total = round(billed_qty * 50.0, 2)
    line_vat = round(line_total * 0.05, 2)
    r = client.post(
        "/api/v1/supplier-invoices",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "supplier_invoice_number": inv_number,
            "invoice_date": "2026-08-23T00:00:00Z",
            "due_date": "2026-09-23T00:00:00Z",
            "currency": "AED",
            "subtotal": line_total,
            "discount_amount": 0,
            "vat_amount": line_vat,
            "total_amount": round(line_total + line_vat, 2),
            "primary_spo_id": spo_id,
            "items": [
                {
                    "spo_item_id": spo_item_id,
                    "grn_item_id": grn_item_id,
                    "product_id": product_id,
                    "description": "EvWidget",
                    "quantity": billed_qty,
                    "uom_id": uom_id,
                    "unit_price": 50.0,
                    "vat_rate": 5.0,
                    "vat_amount": line_vat,
                    "total_price": round(line_total + line_vat, 2),
                    "currency": "AED",
                }
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_create_emits_created_with_actor():
    token, workspace_id, user_id = register_and_token("ev_create")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvCreate", "EVC-001")
    r = client.post(
        "/api/v1/supplier-invoices",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "supplier_invoice_number": "EV-CREATE-1",
            "invoice_date": "2026-08-23T00:00:00Z",
            "due_date": "2026-09-23T00:00:00Z",
            "currency": "AED",
            "subtotal": 1000.0,
            "discount_amount": 0,
            "vat_amount": 50.0,
            "total_amount": 1050.0,
            "items": [],
        },
    )
    assert r.status_code in (200, 201), r.text
    inv_id = r.json()["data"]["id"]

    rows = audit_log(token, inv_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "CREATED"
    assert row["previous_status"] is None
    assert row["new_status"] == "RECEIVED"
    assert row["actor_id"] == user_id
    assert row["workspace_id"] == workspace_id
    assert row["metadata_log"]["supplier_invoice_number"] == "EV-CREATE-1"
    assert float(row["metadata_log"]["total_amount"]) == 1050.00


def test_match_submit_then_matched_sequence():
    token, workspace_id, _ = register_and_token("ev_match")
    inv_id = create_chain(token, workspace_id, "M1")
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/submit-matching",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "MATCHED"

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == ["CREATED", "MATCH_SUBMITTED", "MATCHED"]
    submitted, matched = rows[1], rows[2]
    assert (submitted["previous_status"], submitted["new_status"]) == (
        "RECEIVED",
        "PENDING_MATCHING",
    )
    assert (matched["previous_status"], matched["new_status"]) == (
        "PENDING_MATCHING",
        "MATCHED",
    )
    assert matched["metadata_log"]["match_result"] == "PASSED"


def test_discrepancy_path_and_resolve_notes():
    token, workspace_id, _ = register_and_token("ev_disc")
    # Bill more than the accepted quantity to force a discrepancy.
    inv_id = create_chain(token, workspace_id, "D1", billed_qty=120)
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/submit-matching",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["data"]["status"] == "DISCREPANCY"

    long_notes = "N" * 250
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/resolve-discrepancy",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": long_notes},
    )
    assert r.status_code == 200, r.text

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == [
        "CREATED",
        "MATCH_SUBMITTED",
        "DISCREPANCY",
        "DISCREPANCY_RESOLVED",
    ]
    resolved = rows[3]
    assert (resolved["previous_status"], resolved["new_status"]) == (
        "DISCREPANCY",
        "APPROVED",
    )
    # Notes truncated to the 200-char bound inside compact metadata.
    assert resolved["metadata_log"]["notes"] == "N" * 200


def test_approve_emits_approved():
    token, workspace_id, user_id = register_and_token("ev_appr")
    inv_id = create_chain(token, workspace_id, "A1")
    client.post(
        f"/api/v1/supplier-invoices/{inv_id}/submit-matching",
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    rows = audit_log(token, inv_id)
    assert rows[-1]["event_type"] == "APPROVED"
    assert (rows[-1]["previous_status"], rows[-1]["new_status"]) == (
        "MATCHED",
        "APPROVED",
    )
    assert rows[-1]["actor_id"] == user_id


def test_partial_then_full_payment_events():
    token, workspace_id, _ = register_and_token("ev_pay")
    supplier_id = create_supplier(token, "EvPay", "EVP-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-PAY-1", 10000)

    r = post_payment(token, inv_id, 4000, "ev-pay-1")
    assert r.status_code == 200, r.text
    pid1 = r.json()["data"]["id"]
    r = post_payment(token, inv_id, 6000, "ev-pay-2")
    assert r.status_code == 200, r.text

    rows = audit_log(token, inv_id)
    # Seeded directly: no CREATED row; exactly the two settlement events.
    assert [x["event_type"] for x in rows] == ["PARTIALLY_PAID", "PAID"]
    assert rows[0]["metadata_log"]["supplier_payment_id"] == str(pid1)
    assert rows[0]["metadata_log"]["amount"] == "4000"
    assert (rows[0]["previous_status"], rows[0]["new_status"]) == (
        "APPROVED",
        "PARTIALLY_PAID",
    )
    assert (rows[1]["previous_status"], rows[1]["new_status"]) == (
        "PARTIALLY_PAID",
        "PAID",
    )


def post_payment(token, invoice_id, amount, idem_key, method="BANK_TRANSFER", **extra):
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idem_key,
    }
    body = {
        "supplier_invoice_id": str(invoice_id),
        "amount": amount,
        "payment_method": method,
        **extra,
    }
    return client.post("/api/v1/supplier-payments", headers=headers, json=body)


def test_idempotent_replay_creates_no_duplicate_events():
    token, workspace_id, _ = register_and_token("ev_idem")
    supplier_id = create_supplier(token, "EvIdem", "EVI-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-IDEM-1", 10000)

    r1 = post_payment(token, inv_id, 4000, "ev-idem-key")
    r2 = post_payment(token, inv_id, 4000, "ev-idem-key")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == ["PARTIALLY_PAID"]


def test_pdc_record_silent_clear_emits():
    token, workspace_id, _ = register_and_token("ev_pdc")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvPdc", "EVPDC-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-PDC-1", 10000)

    r = post_payment(
        token,
        inv_id,
        4000,
        "ev-pdc-1",
        method="PDC",
        pdc_date=date.today().isoformat(),
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    assert audit_log(token, inv_id) == []

    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/payments/{pid}/pdc/deposit",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert audit_log(token, inv_id) == []

    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/payments/{pid}/pdc/clear",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == ["PARTIALLY_PAID"]
    assert rows[0]["metadata_log"]["supplier_payment_id"] == str(pid)


def test_reversal_emits_and_noop_reversal_silent():
    token, workspace_id, _ = register_and_token("ev_rev")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvRev", "EVR-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-REV-1", 10000)

    r = post_payment(token, inv_id, 4000, "ev-rev-1")
    pid = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/payments/{pid}/reverse",
        headers=headers,
        json={},
    )
    assert r.status_code == 200, r.text

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == ["PARTIALLY_PAID", "PAYMENT_REVERSED"]
    rev = rows[1]
    assert (rev["previous_status"], rev["new_status"]) == (
        "PARTIALLY_PAID",
        "APPROVED",
    )
    assert rev["metadata_log"]["supplier_payment_id"] == str(pid)

    # Reversing an already-FAILED payment is a no-op: no new event.
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/payments/{pid}/reverse",
        headers=headers,
        json={},
    )
    assert r.status_code == 200, r.text
    assert len(audit_log(token, inv_id)) == 2


def test_debit_note_apply_emits_without_status_change():
    token, workspace_id, _ = register_and_token("ev_dn")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvDn", "EVD-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-DN-1", 10000)

    r = client.post(
        "/api/v1/supplier-debit-notes",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "amount": 2000,
            "reason": "Damaged goods credit",
            "issue_date": date.today().isoformat(),
        },
    )
    assert r.status_code in (200, 201), r.text
    note_id = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/supplier-debit-notes/{note_id}/issue", json={}, headers=headers
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/supplier-debit-notes/{note_id}/apply",
        json={"supplier_invoice_id": str(inv_id)},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == ["DEBIT_NOTE_APPLIED"]
    row = rows[0]
    assert row["previous_status"] == row["new_status"] == "APPROVED"
    assert row["metadata_log"]["debit_note_id"] == str(note_id)
    assert float(row["metadata_log"]["amount"]) == 2000.00


def test_empty_history_returns_empty_list():
    token, workspace_id, _ = register_and_token("ev_empty")
    supplier_id = create_supplier(token, "EvEmpty", "EVE-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-EMPTY-1", 1000)
    assert audit_log(token, inv_id) == []


def test_cross_tenant_audit_log_404_and_no_leak():
    token_a, _, _ = register_and_token("ev_iso_a")
    token_b, _, _ = register_and_token("ev_iso_b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me_a = client.get("/auth/me", headers=headers_a).json()["data"]
    supplier_id = create_supplier(token_a, "EvIso", "EVISO-001")
    inv_id = seed_invoice(me_a["workspace_id"], supplier_id, "EV-ISO-1", 1000)
    post_payment(token_a, inv_id, 1000, "ev-iso-pay")

    r = client.get(f"/api/v1/supplier-invoices/{inv_id}/audit-log", headers=headers_b)
    assert r.status_code == 404, r.text
    # Tenant B has no rows at all.
    assert event_rows(token_b) == []


def event_rows(token):
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "data"
    ]

    async def fetch():
        async with TestingSessionLocal() as session:
            result = await session.execute(
                select(SupplierInvoiceEvent).where(
                    SupplierInvoiceEvent.workspace_id == me["workspace_id"]
                )
            )
            return list(result.scalars().all())

    return asyncio.run(fetch())


def test_failed_operations_leave_no_events():
    token, workspace_id, _ = register_and_token("ev_fail")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvFail", "EVF-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-FAIL-1", 10000)

    # Seeded APPROVED invoices cannot be approved again nor submitted.
    r = client.post(f"/api/v1/supplier-invoices/{inv_id}/approve", headers=headers)
    assert r.status_code == 400, r.text
    r = client.post(
        f"/api/v1/supplier-invoices/{inv_id}/submit-matching", headers=headers
    )
    assert r.status_code == 400, r.text
    # Overpayment is rejected.
    r = post_payment(token, inv_id, 20000, "ev-fail-pay")
    assert r.status_code == 400, r.text
    # Unknown invoice resolves to 404.
    r = client.post(
        f"/api/v1/supplier-invoices/{uuid.uuid4()}/resolve-discrepancy",
        headers=headers,
        json={"notes": "nope"},
    )
    assert r.status_code == 404, r.text

    assert audit_log(token, inv_id) == []


def test_event_api_has_no_mutation_paths():
    token, workspace_id, _ = register_and_token("ev_imm")
    headers = {"Authorization": f"Bearer {token}"}
    supplier_id = create_supplier(token, "EvImm", "EVI2-001")
    inv_id = seed_invoice(workspace_id, supplier_id, "EV-IMM-1", 1000)

    r = client.put(f"/api/v1/supplier-invoices/{inv_id}/audit-log", headers=headers)
    assert r.status_code == 405, r.text
    r = client.delete(f"/api/v1/supplier-invoices/{inv_id}/audit-log", headers=headers)
    assert r.status_code == 405, r.text
    assert audit_log(token, inv_id) == []


def test_full_lifecycle_event_sequence():
    token, workspace_id, user_id = register_and_token("ev_full")
    inv_id = create_chain(token, workspace_id, "FULL")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/supplier-invoices/{inv_id}/submit-matching", headers=headers)
    client.post(f"/api/v1/supplier-invoices/{inv_id}/approve", headers=headers)
    post_payment(token, inv_id, 2000, "ev-full-1")
    post_payment(token, inv_id, 3250, "ev-full-2")
    # Reverse the second (full-settling) payment back to partial.
    payments = client.get(
        f"/api/v1/supplier-payments?supplier_invoice_id={inv_id}", headers=headers
    ).json()["data"]
    # Paginated list shape: extract the SUCCESS payment for 3250.
    items = payments if isinstance(payments, list) else payments.get("items", [])
    pid = next(p["id"] for p in items if p["amount"] == "3250.00")
    client.post(
        f"/api/v1/supplier-invoices/{inv_id}/payments/{pid}/reverse",
        headers=headers,
        json={},
    )

    rows = audit_log(token, inv_id)
    assert [x["event_type"] for x in rows] == [
        "CREATED",
        "MATCH_SUBMITTED",
        "MATCHED",
        "APPROVED",
        "PARTIALLY_PAID",
        "PAID",
        "PAYMENT_REVERSED",
    ]
    assert all(x["actor_id"] == user_id for x in rows)
    created = [x["created_at"] for x in rows]
    assert created == sorted(created)
    assert rows[-1]["previous_status"] == "PAID"
    assert rows[-1]["new_status"] == "PARTIALLY_PAID"
