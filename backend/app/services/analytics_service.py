"""Wave 30 — BI aggregations service.

Locked semantics (see `architecture/wave-reports-dashboard-addendum.md` §5 and
`.planning/AUDIT.md` §2.1 item 1.1):

- **Revenue** = invoiced amounts (subtotal / tax / total) of non-cancelled,
  non-draft AR invoices, bucketed by `issue_date` into day/week/month periods.
  Reuses the VAT compliance status filter (`OUTPUT_INVOICE_STATUSES`).
  Invoice `deleted_at IS NULL`.
- **Sales by customer** = same invoice population grouped by `client_id`.
- **Sales by product** = invoice *items* across the same invoice population,
  grouped by `product_id` (null product → `sku_snapshot`; fallback description).
- **Cashflow** = successful AR receipts (payments JOIN invoices, status=SUCCESS)
  minus successful AP payments (`supplier_payments`, status=SUCCESS), bucketed
  by `payment_date` (GST business date). Net = inflows − outflows.

Reading model only (GET, rate-limited, OWNER/ADMIN) — mirrors `reports.py`.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.supplier_payment import SupplierPayment
from app.services.ar_statement_service import (
    assert_from_not_after_to,
    assert_range_not_too_long,
)
from app.services.line_money import money
from app.services.vat_compliance_service import OUTPUT_INVOICE_STATUSES, business_date

ZERO = Decimal("0.00")
Interval = Literal["day", "week", "month"]


def _period_floor(value: date, interval: Interval) -> str:
    """Period bucket key: day → ISO date, week → ISO `YYYY-Www`, month → `YYYY-MM`."""
    if interval == "day":
        return value.isoformat()
    if interval == "month":
        return f"{value.year:04d}-{value.month:02d}"
    # week: Monday-anchored ISO week key (same label reused by helpers)
    iso = value.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def _week_start(value: date) -> date:
    return value - timedelta(days=value.isocalendar()[2] - 1)


def _bucket_windows(
    period_from: date, period_to: date, interval: Interval
) -> list[str]:
    """Ordered period keys covering the inclusive [from, to] window."""
    keys: list[str] = []
    cursor = period_from
    if interval == "month":
        cursor = period_from.replace(day=1)
        while cursor <= period_to:
            keys.append(_period_floor(cursor, interval))
            year = cursor.year + (1 if cursor.month == 12 else 0)
            month = 1 if cursor.month == 12 else cursor.month + 1
            cursor = date(year, month, 1)
        return keys
    if interval == "week":
        cursor = _week_start(period_from)
        while cursor <= period_to:
            keys.append(_period_floor(cursor, interval))
            cursor += timedelta(days=7)
        return keys
    while cursor <= period_to:
        keys.append(_period_floor(cursor, interval))
        cursor += timedelta(days=1)
    return keys


def resolve_period(period_from: date, period_to: date) -> None:
    assert_from_not_after_to(period_from, period_to)
    assert_range_not_too_long(period_from, period_to)


async def revenue(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    period_from: date,
    period_to: date,
    interval: Interval = "day",
) -> dict:
    """Invoiced revenue by period bucket (subtotal/tax/total)."""
    resolve_period(period_from, period_to)
    invoices = (
        (
            await session.execute(
                select(Invoice).where(
                    Invoice.workspace_id == workspace_id,
                    Invoice.deleted_at.is_(None),
                    Invoice.status.in_(OUTPUT_INVOICE_STATUSES),
                    Invoice.issue_date >= period_from,
                    Invoice.issue_date <= period_to,
                )
            )
        )
        .scalars()
        .all()
    )

    buckets = {
        key: [ZERO, ZERO, ZERO, 0]
        for key in _bucket_windows(period_from, period_to, interval)
    }
    for inv in invoices:
        bucket = buckets[_period_floor(inv.issue_date, interval)]
        bucket[0] += inv.subtotal
        bucket[1] += inv.tax_amount
        bucket[2] += inv.total_amount
        bucket[3] += 1
    rows = [
        {
            "period": key,
            "invoice_count": int(bucket[3]),
            "subtotal": money(bucket[0]),
            "tax_amount": money(bucket[1]),
            "total_amount": money(bucket[2]),
        }
        for key, bucket in buckets.items()
    ]
    return {
        "from": period_from,
        "to": period_to,
        "interval": interval,
        "currency": "AED",
        "rows": rows,
    }


async def sales_by_customer(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    period_from: date,
    period_to: date,
) -> dict:
    """Invoiced sales grouped by customer."""
    resolve_period(period_from, period_to)
    invoices = (
        (
            await session.execute(
                select(Invoice)
                .options(selectinload(Invoice.client))
                .where(
                    Invoice.workspace_id == workspace_id,
                    Invoice.deleted_at.is_(None),
                    Invoice.status.in_(OUTPUT_INVOICE_STATUSES),
                    Invoice.issue_date >= period_from,
                    Invoice.issue_date <= period_to,
                )
            )
        )
        .scalars()
        .all()
    )

    per_client: dict[uuid.UUID, list[Invoice]] = {}
    for inv in invoices:
        per_client.setdefault(inv.client_id, []).append(inv)

    client_ids = list(per_client.keys())
    clients: dict[uuid.UUID, Client] = {}
    if client_ids:
        result = await session.execute(
            select(Client).where(
                Client.workspace_id == workspace_id, Client.id.in_(client_ids)
            )
        )
        clients = {c.id: c for c in result.scalars().all()}

    rows = []
    for cid, invs in per_client.items():
        client = clients.get(cid)
        rows.append(
            {
                "client_id": cid,
                "client_name": client.name if client else "",
                "invoice_count": len(invs),
                "subtotal": money(sum((i.subtotal for i in invs), ZERO)),
                "tax_amount": money(sum((i.tax_amount for i in invs), ZERO)),
                "total_amount": money(sum((i.total_amount for i in invs), ZERO)),
            }
        )
    rows.sort(key=lambda r: r["client_name"].lower())
    return {
        "from": period_from,
        "to": period_to,
        "currency": "AED",
        "rows": rows,
    }


async def sales_by_product(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    period_from: date,
    period_to: date,
) -> dict:
    """Invoiced line items grouped by product (sku fallback)."""
    resolve_period(period_from, period_to)
    result = await session.execute(
        select(InvoiceItem, Invoice)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(OUTPUT_INVOICE_STATUSES),
            Invoice.issue_date >= period_from,
            Invoice.issue_date <= period_to,
        )
    )
    pairs = result.all()

    product_ids = {item.product_id for item, _ in pairs if item.product_id is not None}
    products: dict[uuid.UUID, Product] = {}
    if product_ids:
        presult = await session.execute(
            select(Product).where(Product.id.in_(product_ids))
        )
        products = {p.id: p for p in presult.scalars().all()}

    keyed: dict[tuple, dict] = {}
    for item, _ in pairs:
        product = products.get(item.product_id) if item.product_id else None
        key: tuple = (
            item.product_id or uuid.UUID(int=0),
            product.name if product else (item.sku_snapshot or ""),
            item.sku_snapshot or "",
        )
        group = keyed.setdefault(
            key,
            {
                "quantity": ZERO,
                "line_net": ZERO,
                "tax_amount": ZERO,
                "total_price": ZERO,
            },
        )
        group["quantity"] += item.quantity
        group["line_net"] += item.line_net
        group["tax_amount"] += item.tax_amount
        group["total_price"] += item.total_price

    rows = [
        {
            "product_id": None if key[0] == uuid.UUID(int=0) else key[0],
            "product_name": key[1],
            "sku": key[2],
            "quantity": money(group["quantity"]),
            "line_net": money(group["line_net"]),
            "tax_amount": money(group["tax_amount"]),
            "total_price": money(group["total_price"]),
        }
        for key, group in sorted(keyed.items(), key=lambda kv: kv[0][1].lower())
    ]
    return {
        "from": period_from,
        "to": period_to,
        "currency": "AED",
        "rows": rows,
    }


async def _ar_receipts(
    session: AsyncSession, workspace_id: uuid.UUID, period_from: date, period_to: date
) -> dict[str, Decimal]:
    """Successful AR receipts (Payments JOIN invoices), keyed by GST business date."""
    result = await session.execute(
        select(Payment, Invoice)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.deleted_at.is_(None),
            Payment.status == PaymentStatus.SUCCESS,
        )
    )
    totals: dict[str, Decimal] = {}
    for payment, _ in result.all():
        when = (
            payment.payment_date
            if isinstance(payment.payment_date, datetime)
            else datetime.combine(payment.payment_date, datetime.min.time())
        )
        day = business_date(when)
        if period_from <= day <= period_to:
            totals[day.isoformat()] = totals.get(day.isoformat(), ZERO) + payment.amount
    return totals


async def _ap_payments(
    session: AsyncSession, workspace_id: uuid.UUID, period_from: date, period_to: date
) -> dict[str, Decimal]:
    """Successful AP payments, keyed by GST business date."""
    result = await session.execute(
        select(SupplierPayment).where(
            SupplierPayment.workspace_id == workspace_id,
            SupplierPayment.status == PaymentStatus.SUCCESS,
        )
    )
    totals: dict[str, Decimal] = {}
    for payment in result.scalars().all():
        when = (
            payment.payment_date
            if isinstance(payment.payment_date, datetime)
            else datetime.combine(payment.payment_date, datetime.min.time())
        )
        day = business_date(when)
        if period_from <= day <= period_to:
            totals[day.isoformat()] = totals.get(day.isoformat(), ZERO) + payment.amount
    return totals


async def cashflow(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    period_from: date,
    period_to: date,
    interval: Interval = "day",
) -> dict:
    """Cash inflow (AR receipts) vs outflow (AP payments) by period."""
    resolve_period(period_from, period_to)
    receipts = await _ar_receipts(session, workspace_id, period_from, period_to)
    payments = await _ap_payments(session, workspace_id, period_from, period_to)

    inflow_buckets = {
        key: ZERO for key in _bucket_windows(period_from, period_to, interval)
    }
    outflow_buckets = {
        key: ZERO for key in _bucket_windows(period_from, period_to, interval)
    }
    for day, amount in receipts.items():
        inflow_buckets[_period_floor(date.fromisoformat(day), interval)] += amount
    for day, amount in payments.items():
        outflow_buckets[_period_floor(date.fromisoformat(day), interval)] += amount

    rows = [
        {
            "period": key,
            "inflows": money(inflow_buckets[key]),
            "outflows": money(outflow_buckets[key]),
            "net": money(inflow_buckets[key] - outflow_buckets[key]),
        }
        for key in inflow_buckets
    ]
    return {
        "from": period_from,
        "to": period_to,
        "interval": interval,
        "currency": "AED",
        "rows": rows,
    }
