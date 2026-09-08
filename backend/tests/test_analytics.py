"""Wave 30 — BI analytics report tests.

Covers: revenue buckets (day/week/month + inclusive window), sales by customer
grouping + decimals, sales by product (sku fallback, product name), cashflow
(inflows = AR receipts, outflows = AP payments, net), period guards (from>to,
>366 days), OWNER/ADMIN RBAC (MEMBER -> 403), status exclusion (DRAFT/CANCELLED),
deleted invoice exclusion, and multi-workspace isolation.
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

from app.auth.utils import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.client import Client  # noqa: E402
from app.models.invoice import Invoice, InvoiceStatus  # noqa: E402
from app.models.invoice_item import InvoiceItem  # noqa: E402
from app.models.payment import Payment, PaymentMethod, PaymentStatus  # noqa: E402
from app.models.product import Product, UnitOfMeasure  # noqa: E402
from app.models.supplier_payment import SupplierPayment  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.line_money import money  # noqa: E402

ZERO = Decimal("0.00")


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


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
    email = f"analytics_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "Analytics Tester",
            "workspace_name": "Analytics Workspace",
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
    email = f"analytics_member_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert():
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="Analytics Member",
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


def seed_product(workspace_id, name="Widget", sku="SKU-100", uom="PCS"):
    async def _insert():
        async with TestingSessionLocal() as session:
            existing = (
                (
                    await session.execute(
                        select(UnitOfMeasure).where(
                            UnitOfMeasure.workspace_id == uuid.UUID(workspace_id),
                            UnitOfMeasure.code == uom,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is None:
                existing = UnitOfMeasure(
                    workspace_id=uuid.UUID(workspace_id), code=uom, name=uom
                )
                session.add(existing)
                await session.flush()
            product = Product(
                workspace_id=uuid.UUID(workspace_id),
                internal_sku=sku,
                name=name,
                base_uom_id=existing.id,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
            return product.id

    return asyncio.run(_insert())


def _line(description, qty, price, tax_rate=0.00, product_id=None, sku=None):
    net = money(Decimal(str(qty)) * Decimal(str(price)))
    tax = money(net * Decimal(str(tax_rate)) / Decimal("100"))
    return {
        "invoice_id": None,
        "product_id": product_id,
        "sku_snapshot": sku,
        "description": description,
        "quantity": Decimal(str(qty)),
        "unit_price": Decimal(str(price)),
        "tax_rate": Decimal(str(tax_rate)),
        "discount_amount": ZERO,
        "discount_percent": ZERO,
        "line_net": net,
        "tax_amount": tax,
        "total_price": money(net + tax),
    }


def seed_invoice(
    workspace_id,
    client_id,
    number,
    issue_date,
    lines,
    status="SENT",
    deleted_at=None,
):
    subtotal = money(sum((line["line_net"] for line in lines), ZERO))
    tax = money(sum((line["tax_amount"] for line in lines), ZERO))
    total = money(subtotal + tax)
    now = datetime.now(timezone.utc)

    async def _insert():
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
                deleted_at=deleted_at,
                created_at=now,
                updated_at=now,
            )
            session.add(invoice)
            await session.flush()
            for idx, line in enumerate(lines):
                row = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=line["product_id"],
                    sku_snapshot=line["sku_snapshot"],
                    description=f"{line['description']}-{idx}",
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    tax_rate=line["tax_rate"],
                    discount_amount=line["discount_amount"],
                    discount_percent=line["discount_percent"],
                    line_net=line["line_net"],
                    tax_amount=line["tax_amount"],
                    total_price=line["total_price"],
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            await session.commit()
            return invoice.id

    return asyncio.run(_insert())


def seed_client(workspace_id, name="Alpha Ltd"):
    async def _insert():
        async with TestingSessionLocal() as session:
            entity = Client(workspace_id=uuid.UUID(workspace_id), name=name)
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity.id

    return asyncio.run(_insert())


def seed_ar_payment(invoice_id, amount, payment_date, status=PaymentStatus.SUCCESS):
    async def _insert():
        async with TestingSessionLocal() as session:
            payment = Payment(
                invoice_id=invoice_id,
                amount=Decimal(str(amount)),
                payment_date=payment_date,
                payment_method=PaymentMethod.BANK_TRANSFER,
                status=status,
            )
            session.add(payment)
            await session.commit()

    asyncio.run(_insert())


def seed_ap_payment(
    workspace_id,
    amount,
    payment_date,
    supplier_id,
    status=PaymentStatus.SUCCESS,
    currency="AED",
):
    async def _insert():
        async with TestingSessionLocal() as session:
            from app.models.supplier_invoice import SupplierInvoice
            from app.models.user import User

            user = (
                (
                    await session.execute(
                        select(User).where(User.workspace_id == uuid.UUID(workspace_id))
                    )
                )
                .scalars()
                .first()
            )
            inv = SupplierInvoice(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=supplier_id,
                supplier_invoice_number=f"AP-{uuid.uuid4().hex[:6].upper()}",
                invoice_date=payment_date.date(),
                due_date=payment_date.date() + timedelta(days=30),
                currency=currency,
                subtotal=Decimal(str(amount)),
                tax_amount=ZERO,
                total_amount=Decimal(str(amount)),
            )
            session.add(inv)
            await session.flush()
            payment = SupplierPayment(
                workspace_id=uuid.UUID(workspace_id),
                supplier_id=supplier_id,
                supplier_invoice_id=inv.id,
                amount=Decimal(str(amount)),
                payment_date=payment_date,
                payment_method=PaymentMethod.BANK_TRANSFER,
                status=status,
                created_by=user.id if user else None,
            )
            session.add(payment)
            await session.commit()

    asyncio.run(_insert())


def seed_supplier(workspace_id, name="Supp Co"):
    async def _insert():
        async with TestingSessionLocal() as session:
            from app.models.supplier import Supplier

            supplier = Supplier(
                workspace_id=uuid.UUID(workspace_id),
                supplier_code=f"SUP-{uuid.uuid4().hex[:6].upper()}",
                name=name,
            )
            session.add(supplier)
            await session.commit()
            await session.refresh(supplier)
            return supplier.id

    return asyncio.run(_insert())


def test_revenue_day_buckets():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Rev Corp")
    line = _line("Widget", 2, 100.00, tax_rate=5.00)
    seed_invoice(workspace_id, client_id, "REV-1", date(2026, 9, 1), [line])
    seed_invoice(workspace_id, client_id, "REV-2", date(2026, 9, 3), [line])

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-09-01", "to": "2026-09-03"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["from"] == "2026-09-01"
    assert data["to"] == "2026-09-03"
    assert data["interval"] == "day"
    rows = {row["period"]: row for row in data["rows"]}
    assert _dec(rows["2026-09-01"]["total_amount"]) == _dec(210.00)
    assert rows["2026-09-01"]["invoice_count"] == 1
    assert _dec(rows["2026-09-02"]["total_amount"]) == _dec(0.00)  # empty bucket filled
    assert _dec(rows["2026-09-03"]["total_amount"]) == _dec(210.00)


def test_revenue_month_and_week_interval():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Bucket Co")
    line = _line("Widget", 1, 100.00)
    seed_invoice(workspace_id, client_id, "BUC-1", date(2026, 9, 5), [line])
    seed_invoice(workspace_id, client_id, "BUC-2", date(2026, 10, 7), [line])

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-09-01", "to": "2026-10-31", "interval": "month"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    rows = {row["period"]: row for row in r.json()["data"]["rows"]}
    assert _dec(rows["2026-09"]["total_amount"]) == _dec(100.00)
    assert _dec(rows["2026-10"]["total_amount"]) == _dec(100.00)

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-09-01", "to": "2026-09-30", "interval": "week"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    assert any(
        _dec(row["total_amount"]) == _dec(100.00) for row in r.json()["data"]["rows"]
    )


def test_sales_by_customer():
    token, workspace_id = register_and_token()
    c_a = seed_client(workspace_id, "ABC Trading")
    c_b = seed_client(workspace_id, "Zeta Shops")
    ln_a = _line("Widget", 1, 250.00)
    ln_b = _line("Gadget", 1, 100.00)
    seed_invoice(workspace_id, c_a, "SC-A-1", date(2026, 9, 1), [ln_a])
    seed_invoice(workspace_id, c_a, "SC-A-2", date(2026, 9, 2), [ln_a])
    seed_invoice(workspace_id, c_b, "SC-B-1", date(2026, 9, 1), [ln_b])

    r = client.get(
        "/api/v1/reports/analytics/sales-by-customer",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    rows = {row["client_name"]: row for row in r.json()["data"]["rows"]}
    assert rows["ABC Trading"]["invoice_count"] == 2
    assert _dec(rows["ABC Trading"]["total_amount"]) == _dec(500.00)
    assert _dec(rows["Zeta Shops"]["total_amount"]) == _dec(100.00)


def test_sales_by_product_and_sku_fallback():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Prod Client")
    product_id = seed_product(workspace_id, name="Cable 4mm", sku="CBL-4")
    ln_prod = _line("Cable 4mm", 10, 15.00, product_id=product_id, sku="CBL-4")
    ln_adhoc = _line("Adhoc Item", 2, 50.00, sku="NO-SKU")
    seed_invoice(workspace_id, client_id, "SP-1", date(2026, 9, 1), [ln_prod, ln_adhoc])

    r = client.get(
        "/api/v1/reports/analytics/sales-by-product",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    rows = {row["product_name"]: row for row in r.json()["data"]["rows"]}
    assert _dec(rows["Cable 4mm"]["quantity"]) == _dec(10.00)
    assert _dec(rows["Cable 4mm"]["line_net"]) == _dec(150.00)
    assert _dec(rows["Cable 4mm"]["total_price"]) == _dec(150.00)
    assert rows["Cable 4mm"]["product_id"] == str(product_id)
    adhoc = next(row for row in r.json()["data"]["rows"] if row["sku"] == "NO-SKU")
    assert adhoc["product_id"] is None
    assert _dec(adhoc["total_price"]) == _dec(100.00)


def test_cashflow_inflows_outflows_net():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Cash Client")
    supplier_id = seed_supplier(workspace_id, "Cash Supplier")
    line = _line("Widget", 1, 500.00)
    inv_id = seed_invoice(workspace_id, client_id, "CFL-1", date(2026, 9, 1), [line])
    seed_ar_payment(
        inv_id,
        300.00,
        datetime(2026, 9, 5, tzinfo=timezone.utc),
        status=PaymentStatus.SUCCESS,
    )
    seed_ar_payment(
        inv_id,
        200.00,
        datetime(2026, 9, 14, tzinfo=timezone.utc),
        status=PaymentStatus.SUCCESS,
    )
    seed_ar_payment(
        inv_id,
        500.00,
        datetime(2026, 9, 20, tzinfo=timezone.utc),
        status=PaymentStatus.FAILED,
    )

    seed_ap_payment(
        workspace_id,
        700.00,
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        supplier_id,
        status=PaymentStatus.SUCCESS,
    )

    r = client.get(
        "/api/v1/reports/analytics/cashflow",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["non_aed_payments_excluded"] == 0
    rows = {row["period"]: row for row in data["rows"]}
    assert _dec(rows["2026-09-05"]["inflows"]) == _dec(300.00)
    assert _dec(rows["2026-09-10"]["outflows"]) == _dec(700.00)
    assert _dec(rows["2026-09-14"]["inflows"]) == _dec(200.00)
    assert _dec(rows["2026-09-05"]["net"]) == _dec(300.00)
    total_in = sum(_dec(row["inflows"]) for row in data["rows"])
    total_out = sum(_dec(row["outflows"]) for row in data["rows"])
    assert _dec(total_in) == _dec(500.00)  # FAILED payment excluded
    assert _dec(total_out) == _dec(700.00)


def test_cashflow_excludes_non_aed_supplier_payments():
    """Non-AED supplier payments must not be summed into the AED cashflow."""
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Mixed Client")
    supplier_id = seed_supplier(workspace_id, "Mixed Supplier")
    line = _line("Widget", 1, 1000.00)
    inv_id = seed_invoice(workspace_id, client_id, "MIX-1", date(2026, 9, 1), [line])
    seed_ar_payment(
        inv_id,
        1000.00,
        datetime(2026, 9, 5, tzinfo=timezone.utc),
        status=PaymentStatus.SUCCESS,
    )
    seed_ap_payment(
        workspace_id,
        300.00,
        datetime(2026, 9, 8, tzinfo=timezone.utc),
        supplier_id,
        status=PaymentStatus.SUCCESS,
        currency="AED",
    )
    seed_ap_payment(
        workspace_id,
        500.00,
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        supplier_id,
        status=PaymentStatus.SUCCESS,
        currency="USD",
    )

    r = client.get(
        "/api/v1/reports/analytics/cashflow",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    rows = {row["period"]: row for row in data["rows"]}
    assert data["non_aed_payments_excluded"] == 1
    assert _dec(rows["2026-09-08"]["outflows"]) == _dec(300.00)
    assert rows["2026-09-10"]["outflows"] == "0.00"  # USD supplier payment excluded
    total_out = sum(_dec(row["outflows"]) for row in data["rows"])
    assert _dec(total_out) == _dec(300.00)
    assert _dec(rows["2026-09-08"]["net"]) == _dec(-300.00)


def test_period_guards():
    token, workspace_id = register_and_token()

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-10-01", "to": "2026-09-01"},
        headers=_headers(token),
    )
    assert r.status_code == 422, r.json()

    r = client.get(
        "/api/v1/reports/analytics/cashflow",
        params={"from": "2026-01-01", "to": "2027-01-05"},
        headers=_headers(token),
    )
    assert r.status_code == 422, r.json()


def test_member_forbidden():
    token, workspace_id = register_and_token()
    member = member_token(workspace_id)
    client_id = seed_client(workspace_id, "RBAC Co")
    line = _line("Widget", 1, 10.00)
    seed_invoice(workspace_id, client_id, "RBAC-1", date(2026, 9, 1), [line])

    r = client.get(
        "/api/v1/reports/analytics/sales-by-customer",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(member),
    )
    assert r.status_code == 403, r.json()
    assert r.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_status_and_deleted_exclusion():
    token, workspace_id = register_and_token()
    client_id = seed_client(workspace_id, "Excl Co")
    line = _line("Widget", 1, 100.00)
    seed_invoice(
        workspace_id, client_id, "EXC-DRAFT", date(2026, 9, 1), [line], status="DRAFT"
    )
    seed_invoice(
        workspace_id,
        client_id,
        "EXC-CANCEL",
        date(2026, 9, 2),
        [line],
        status="CANCELLED",
    )
    seed_invoice(
        workspace_id,
        client_id,
        "EXC-DEL",
        date(2026, 9, 3),
        [line],
        deleted_at=datetime.now(timezone.utc),
    )
    seed_invoice(workspace_id, client_id, "EXC-OK", date(2026, 9, 4), [line])

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.json()
    total = sum(_dec(row["total_amount"]) for row in r.json()["data"]["rows"])
    assert _dec(total) == _dec(100.00)


def test_multi_workspace_isolation():
    token_a, workspace_a = register_and_token()
    token_b, workspace_b = register_and_token()
    client_b = seed_client(workspace_b, "Other WS Customer")
    line = _line("Widget", 1, 400.00)
    seed_invoice(workspace_b, client_b, "ISO-1", date(2026, 9, 1), [line])

    r = client.get(
        "/api/v1/reports/analytics/sales-by-customer",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token_a),
    )
    assert r.status_code == 200, r.json()
    assert r.json()["data"]["rows"] == []

    r = client.get(
        "/api/v1/reports/analytics/revenue",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_headers(token_b),
    )
    assert sum(_dec(row["total_amount"]) for row in r.json()["data"]["rows"]) == _dec(
        400.00
    )
