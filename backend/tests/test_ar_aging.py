"""Wave 29 AR — aging report tests.

Covers: bucket placement, totals/outstanding invariants, detail rows,
by-customer aggregation, per-client filter, as_of guards, status/balance/
deleted exclusion, multi-workspace isolation, no-clamping past as_of.
Mirrors `test_ap_aging.py` (Wave 22).
"""

import asyncio
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
    email = f"ar_age_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "AR Aging Tester",
            "workspace_name": "AR Aging Workspace",
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


def create_client(token, name):
    r = client.post(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.json()
    return r.json()["data"]["id"]


def seed_invoice(
    workspace_id,
    client_id,
    number,
    total,
    due_shift_days,
    status="SENT",
    credited=None,
    deleted_at=None,
    issue_date=None,
    due_date=None,
):
    wrt = datetime.now(timezone.utc).date()
    issue = issue_date if issue_date is not None else wrt
    due = due_date if due_date is not None else issue + timedelta(days=due_shift_days)

    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.invoice import Invoice

            invoice = Invoice(
                workspace_id=workspace_id,
                client_id=client_id,
                invoice_number=number,
                currency="AED",
                subtotal=Decimal(str(total)),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal(str(total)),
                amount_credited=credited if credited is not None else Decimal("0.00"),
                status=status,
                issue_date=issue,
                supply_date=issue,
                due_date=due,
                deleted_at=deleted_at,
            )
            session.add(invoice)
            await session.commit()
            await session.refresh(invoice)
            return invoice.id

    return asyncio.run(insert())


def test_aging_summary_buckets():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Age Corp")
    # due today+5 (current), today-5, today-40, today-70, today-120
    for i, shift in enumerate((5, -5, -40, -70, -120)):
        seed_invoice(workspace_id, client_id, f"AR-INV-{i}", 1000, shift)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["client_count"] == 1
    assert data["invoice_count"] == 5
    assert float(data["total_outstanding"]) == 5000.00
    assert float(data["buckets"]["current"]) == 1000.00
    assert float(data["buckets"]["days_1_30"]) == 1000.00
    assert float(data["buckets"]["days_31_60"]) == 1000.00
    assert float(data["buckets"]["days_61_90"]) == 1000.00
    assert float(data["buckets"]["days_90_plus"]) == 1000.00


def test_aging_detail_rows():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Detail Corp")
    late_id = seed_invoice(workspace_id, client_id, "DET-INV-1", 2000, -40)

    r = client.get(
        "/api/v1/ar-aging/detail", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    row = next(x for x in data["invoices"] if x["invoice_id"] == str(late_id))
    assert row["bucket"] == "days_31_60"
    assert row["days_overdue"] == 40
    assert float(row["balance_due"]) == 2000.0
    assert row["client_name"] == "Detail Corp"


def test_aging_by_customer():
    token, workspace_id = register_and_token()
    c_a = create_client(token, "Alpha Ltd")
    c_b = create_client(token, "Beta Ltd")
    seed_invoice(workspace_id, c_a, "ALP-INV-1", 1500, -10)
    seed_invoice(workspace_id, c_a, "ALP-INV-2", 500, -10)
    seed_invoice(workspace_id, c_b, "BET-INV-1", 800, 0)

    r = client.get(
        "/api/v1/ar-aging/by-customer", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert float(data["total_outstanding"]) == 2800.0
    rows = data["customers"]
    assert len(rows) == 2
    by_name = {row["client"]["name"]: row for row in rows}
    assert float(by_name["Alpha Ltd"]["total_outstanding"]) == 2000.0
    assert float(by_name["Beta Ltd"]["total_outstanding"]) == 800.0
    assert float(by_name["Alpha Ltd"]["buckets"]["days_1_30"]) == 2000.0


def test_aging_client_filter():
    token, workspace_id = register_and_token()
    c_a = create_client(token, "Filter A")
    c_b = create_client(token, "Filter B")
    seed_invoice(workspace_id, c_a, "FIL-A-INV", 1000, -5)
    seed_invoice(workspace_id, c_b, "FIL-B-INV", 4000, -5)

    r = client.get(
        f"/api/v1/ar-aging?client_id={c_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 1000.0


def test_aging_as_of_future_rejected():
    token, _ = register_and_token()
    future = (date.today() + timedelta(days=2)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?as_of={future}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def test_aging_by_customer_rejects_client_id():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Conf Co")
    seed_invoice(workspace_id, client_id, "CON-INV-1", 1000, -5)

    r = client.get(
        f"/api/v1/ar-aging/by-customer?client_id={client_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def test_aging_status_exclusion():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Status Co")
    seed_invoice(workspace_id, client_id, "EX-DRAFT", 1000, -5, status="DRAFT")
    seed_invoice(workspace_id, client_id, "EX-PAID", 1000, -5, status="PAID")
    seed_invoice(workspace_id, client_id, "EX-CANCEL", 1000, -5, status="CANCELLED")
    seed_invoice(workspace_id, client_id, "EX-OPEN", 5000, -5)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 5000.0


def test_aging_deleted_excluded():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Del Co")
    seed_invoice(
        workspace_id,
        client_id,
        "DEL-INV-1",
        1000,
        -5,
        deleted_at=datetime.now(timezone.utc),
    )

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0


def test_aging_multi_workspace_isolation():
    token_a, workspace_a = register_and_token()
    token_b, workspace_b = register_and_token()
    client_b = create_client(token_b, "Other WS Customer")
    seed_invoice(workspace_b, client_b, "OTHER-1", 9000, -5)

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token_b}"})
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 9000.0


def test_aging_zero_balance_excluded():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "Zero Co")
    seed_invoice(
        workspace_id,
        client_id,
        "ZERO-INV-1",
        1000,
        -5,
        status="SENT",
        credited=Decimal("1000.00"),
    )

    r = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0


def test_aging_past_as_of_honored_no_clamping():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "NoClamp Co")
    seed_invoice(workspace_id, client_id, "NOCLAMP-1", 1000, -35)

    today = date.today()
    past_as_of = (today - timedelta(days=20)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging/detail?as_of={past_as_of}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["as_of"] == past_as_of
    row = data["invoices"][0]
    assert row["days_overdue"] == 15
    assert row["bucket"] == "days_1_30"

    future = (today + timedelta(days=2)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?as_of={future}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.json()


def seed_payment(
    workspace_id, invoice_id, number, amount, payment_date, status="SUCCESS"
):
    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.payment import Payment, PaymentMethod

            payment = Payment(
                invoice_id=invoice_id,
                amount=Decimal(str(amount)),
                payment_date=payment_date,
                payment_method=PaymentMethod.BANK_TRANSFER,
                status=status,
                reference_number=number,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            return payment.id

    return asyncio.run(insert())


def seed_credit_note(
    workspace_id, client_id, invoice_id, number, total, issue_date, status="ISSUED"
):
    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.credit_note import (
                CreditNote,
                CreditNoteReason,
                CreditNoteStatus,
            )

            note = CreditNote(
                workspace_id=workspace_id,
                client_id=client_id,
                invoice_id=invoice_id,
                credit_note_number=number,
                status=CreditNoteStatus(status),
                issue_date=issue_date,
                reason=CreditNoteReason.OTHER,
                subtotal=Decimal(str(total)),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal(str(total)),
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note.id

    return asyncio.run(insert())


def seed_debit_note(
    workspace_id, client_id, invoice_id, number, total, issue_date, status="ISSUED"
):
    async def insert():
        async with TestingSessionLocal() as session:
            from app.models.tax_debit_note import (
                TaxDebitNote,
                TaxDebitNoteReason,
                TaxDebitNoteStatus,
            )

            note = TaxDebitNote(
                workspace_id=workspace_id,
                client_id=client_id,
                invoice_id=invoice_id,
                debit_note_number=number,
                status=TaxDebitNoteStatus(status),
                issue_date=issue_date,
                reason=TaxDebitNoteReason.OTHER,
                subtotal=Decimal(str(total)),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal(str(total)),
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note.id

    return asyncio.run(insert())


def test_historical_reconstructs_paid_invoice_at_past_as_of():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H Recon Co")
    today = date.today()
    inv_id = seed_invoice(
        workspace_id,
        client_id,
        "RECON-INV-1",
        1000,
        0,
        issue_date=today - timedelta(days=40),
    )

    paid_on = datetime.now(timezone.utc)
    seed_payment(workspace_id, inv_id, "PAY-RECON-1", 1000, paid_on)

    past = (today - timedelta(days=10)).isoformat()
    live = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    assert live.status_code == 200, live.json()
    assert live.json()["data"]["invoice_count"] == 0

    r = client.get(
        f"/api/v1/ar-aging?historical=true&as_of={past}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 1000.0
    assert float(data["buckets"]["days_1_30"]) == 1000.0


def test_historical_reconstructs_ignores_payment_after_as_of():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H After Co")
    today = date.today()
    inv_id = seed_invoice(
        workspace_id,
        client_id,
        "AFTER-INV-1",
        1000,
        5,
        issue_date=today - timedelta(days=60),
    )

    past = (today - timedelta(days=5)).isoformat()
    paid_later = datetime.combine(
        today, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=12)
    seed_payment(workspace_id, inv_id, "PAY-AFTER-1", 300, paid_later)

    r = client.get(
        f"/api/v1/ar-aging/detail?historical=true&as_of={past}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert len(data["invoices"]) == 1
    assert float(data["invoices"][0]["balance_due"]) == 1000.0

    today_iso = today.isoformat()
    r2 = client.get(
        f"/api/v1/ar-aging/detail?historical=true&as_of={today_iso}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.json()
    assert float(r2.json()["data"]["invoices"][0]["balance_due"]) == 700.0


def test_historical_credit_and_debit_notes_respect_as_of():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H Notes Co")
    today = date.today()
    inv_id = seed_invoice(
        workspace_id,
        client_id,
        "NOTES-INV-1",
        1000,
        10,
        issue_date=today - timedelta(days=90),
    )

    backing_day = today - timedelta(days=3)
    cred_on = backing_day - timedelta(days=1)
    debit_on = backing_day + timedelta(days=1)
    seed_credit_note(workspace_id, client_id, inv_id, "CN-H-1", 200, cred_on)
    seed_debit_note(workspace_id, client_id, inv_id, "TDN-H-1", 50, debit_on)

    snapshot = backing_day.isoformat()
    r = client.get(
        f"/api/v1/ar-aging/detail?historical=true&as_of={snapshot}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    rows = r.json()["data"]["invoices"]
    assert len(rows) == 1
    assert float(rows[0]["balance_due"]) == 800.0

    later = (backing_day + timedelta(days=2)).isoformat()
    r2 = client.get(
        f"/api/v1/ar-aging/detail?historical=true&as_of={later}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.json()
    assert float(r2.json()["data"]["invoices"][0]["balance_due"]) == 850.0


def test_historical_excludes_invoice_issued_after_as_of():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H Issued Co")
    seed_invoice(workspace_id, client_id, "LATE-INV-1", 1000, -5)

    today = date.today()
    past = (today - timedelta(days=2)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?historical=true&as_of={past}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 0
    assert float(data["total_outstanding"]) == 0.0


def test_historical_as_of_today_matches_live_set():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H Match Co")
    seed_invoice(workspace_id, client_id, "MATCH-A", 1000, -5)
    seed_invoice(workspace_id, client_id, "MATCH-B", 2000, -40)
    seed_invoice(workspace_id, client_id, "MATCH-DRAFT", 500, -5, status="DRAFT")

    today = date.today()

    live = client.get("/api/v1/ar-aging", headers={"Authorization": f"Bearer {token}"})
    hist = client.get(
        f"/api/v1/ar-aging?historical=true&as_of={today.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert live.status_code == 200 and hist.status_code == 200
    live_data, hist_data = live.json()["data"], hist.json()["data"]
    assert hist_data["invoice_count"] == live_data["invoice_count"] == 2
    assert (
        float(hist_data["total_outstanding"])
        == float(live_data["total_outstanding"])
        == 3000.0
    )


def test_historical_detail_rows_and_buckets():
    token, workspace_id = register_and_token()
    client_id = create_client(token, "H Detail Co")
    today = date.today()
    inv_id = seed_invoice(
        workspace_id,
        client_id,
        "HD-INV-1",
        1000,
        5,
        issue_date=today - timedelta(days=40),
    )

    past = (today - timedelta(days=20)).isoformat()
    seed_payment(
        workspace_id,
        inv_id,
        "PAY-HD",
        400,
        datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
    )

    r = client.get(
        f"/api/v1/ar-aging/detail?historical=true&as_of={past}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["as_of"] == past
    assert float(data["total_outstanding"]) == 1000.0
    row = data["invoices"][0]
    assert row["client_name"] == "H Detail Co"
    assert row["invoice_number"] == "HD-INV-1"
    assert row["days_overdue"] == 15
    assert row["bucket"] == "days_1_30"
    assert float(row["balance_due"]) == 1000.0


def test_historical_client_filter():
    token, workspace_id = register_and_token()
    c_a = create_client(token, "H Filt A")
    c_b = create_client(token, "H Filt B")
    today = date.today()
    seed_invoice(
        workspace_id,
        c_a,
        "HF-A-1",
        1000,
        -5,
        issue_date=today - timedelta(days=30),
    )
    seed_invoice(
        workspace_id,
        c_b,
        "HF-B-1",
        4000,
        -5,
        issue_date=today - timedelta(days=30),
    )

    past = (today - timedelta(days=1)).isoformat()
    r = client.get(
        f"/api/v1/ar-aging?historical=true&as_of={past}&client_id={c_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["invoice_count"] == 1
    assert float(data["total_outstanding"]) == 1000.0
