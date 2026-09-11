"""
AR Aging Service — Wave 29 (Phase 6), historical engine added Wave 30 item 1.2.

Workspace-wide AR aging, a symmetric counterpart to
`supplier_payment_service.ap_aging` (AP aging, Wave 22).

Locked semantics (see `architecture/wave-reports-dashboard-addendum.md` §2.3):
- Rows = currently-open invoices: `status IN AR_STATUSES` (SENT, PARTIALLY_PAID,
  OVERDUE), `deleted_at IS NULL`, `balance_due > 0` — exactly mirroring the AP
  open set (`open_ap_invoices` applies the same `balance_due > 0` guard).
- `as_of` resolves to the literal provided date (or today); a future date is
  rejected with 422. `as_of` moves bucket boundaries / `days_overdue` only —
  it does NOT reconstruct historical balances or lifecycle status.
- Bucketing reuses the live `aging_buckets` / `_bucket_key` helpers from
  `credit_control_service` — no second implementation of the aging rules.

Historical balance-reconstruction mode (Wave 30 item 1.2, `historical=True`):
- `as_of` reconstructs the outstanding balance from payment / credit-note /
  tax-debit-note history instead of using the live `balance_due`.
- This is a *balance reconstruction*, NOT a point-in-time lifecycle snapshot:
  it uses today's status (current-history eligibility), not the invoice's status
  on `as_of`. An invoice that was DRAFT on `as_of` but SENT today can be included;
  an invoice that was SENT on `as_of` but voided today is excluded. The app has
  no cancellation/lifecycle timestamp, so historical status cannot be dated.
- Reconstruction scope: invoices issued on/before `as_of` (`issue_date <= as_of`),
  not deleted before `as_of`, and in a billing lifecycle that can be open today
  (SENT / PARTIALLY_PAID / PAID / OVERDUE). DRAFT and CANCELLED are excluded
  because there is no cancellation timestamp to date the historical snapshot.
- balance_as_of = max(0, total_amount − Σ SUCCESS payments `<= as_of`
  − Σ ISSUED credit notes `<= as_of` + Σ ISSUED tax debit notes `<= as_of`).
- Rows with `balance_due > 0` are kept; this naturally includes invoices that
  are PAID today but were outstanding at a past `as_of`, and excludes invoices
  created after `as_of`.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_note import CreditNote, CreditNoteStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentMethod, PDCStatus, PaymentStatus
from app.models.tax_debit_note import TaxDebitNote, TaxDebitNoteStatus
from app.schemas.common import ErrorCode
from app.services.credit_control_service import (
    AR_STATUSES,
    _bucket_key,
    aging_buckets,
    utc_today,
)
from app.services.customer_po_support import raise_error
from app.services.line_money import money

ZERO = Decimal("0.00")

HISTORICAL_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)


@dataclass
class _ReconstructedInvoice:
    id: uuid.UUID
    client_id: uuid.UUID
    invoice_number: str
    issue_date: date
    due_date: date
    balance_due: Decimal


async def _open_ar_invoices(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    client_id: Optional[uuid.UUID] = None,
) -> list[Invoice]:
    """Open AR = open-status invoices with a balance (mirror of AP open set).

    `Invoice.balance_due` is a computed property (`total - paid - credited +
    debited`), so the `balance_due > 0` guard cannot be expressed in SQL —
    apply it post-load, exactly mirroring the AP open-set semantics.
    """
    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(AR_STATUSES),
        )
    )
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    invoices = (await session.execute(stmt)).scalars().all()
    return [inv for inv in invoices if inv.balance_due > ZERO]


async def _client_names(
    session: AsyncSession, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Client]:
    if not ids:
        return {}
    result = await session.execute(
        select(Client).where(Client.workspace_id == workspace_id, Client.id.in_(ids))
    )
    return {c.id: c for c in result.scalars().all()}


def _payment_date_at_or_before(p: Payment, as_of: date) -> bool:
    """True when a payment was received on or before `as_of` (UTC calendar day)."""
    value = p.payment_date
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        value = value.date()
    return value <= as_of


def _end_of_as_of(as_of: date) -> datetime:
    """End-of-day UTC boundary for `as_of` (exclusive of the next day)."""
    return datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)


async def _pdc_outstanding_by_invoice(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    invoice_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, Decimal]]:
    """Pre-aggregate PDC Outstanding (RECEIVED + DEPOSITED) per invoice.

    Returns a mapping: invoice_id -> (count, amount) for PDC payments with
    pdc_status IN (RECEIVED, DEPOSITED). Invoices with no PDC payments are
    not present in the result; callers should default to (0, ZERO).

    This pre-aggregation avoids row multiplication when joining to invoices.
    """
    if not invoice_ids:
        return {}
    stmt = (
        select(
            Payment.invoice_id,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), ZERO),
        )
        .where(
            Payment.invoice_id.in_(invoice_ids),
            Payment.payment_method == PaymentMethod.PDC,
            Payment.pdc_status.in_([PDCStatus.RECEIVED, PDCStatus.DEPOSITED]),
        )
        .group_by(Payment.invoice_id)
    )
    result = await session.execute(stmt)
    return {row[0]: (row[1], row[2]) for row in result.all()}


async def _reconstruct_open_invoices(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    as_of: date,
    client_id: Optional[uuid.UUID] = None,
) -> list[_ReconstructedInvoice]:
    """Point-in-time reconstruction of outstanding balances as of `as_of`.

    Historical engine (Wave 30 item 1.2): instead of trusting the live
    `balance_due`, re-derive each invoice's balance from the payment /
    credit-note / tax-debit-note ledger cut off at `as_of`:

        balance_as_of =
            max(0, total_amount
                − Σ ISSUED credit notes with issue_date <= as_of
                + Σ ISSUED tax debit notes with issue_date <= as_of
                − Σ SUCCESS payments received on/before as_of)

    Only invoices that existed (issued and not yet deleted) as of `as_of`
    participate; invoices created after `as_of` are excluded even if they are
    open today. Invoices fully paid before `as_of` reconstruct to zero and are
    dropped, matching the live "balance_due > 0" open-set guard.
    """
    stmt = (
        select(Invoice)
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.issue_date <= as_of,
            Invoice.status.in_(HISTORICAL_STATUSES),
            or_(
                Invoice.deleted_at.is_(None),
                Invoice.deleted_at > _end_of_as_of(as_of),
            ),
        )
        .order_by(Invoice.issue_date, Invoice.invoice_number)
    )
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    invoices = (await session.execute(stmt)).scalars().all()
    if not invoices:
        return []

    ids = [inv.id for inv in invoices]

    credit_stmt = (
        select(
            CreditNote.invoice_id,
            func.coalesce(func.sum(CreditNote.total_amount), ZERO),
        )
        .where(
            CreditNote.invoice_id.in_(ids),
            CreditNote.status == CreditNoteStatus.ISSUED,
            CreditNote.issue_date <= as_of,
            CreditNote.deleted_at.is_(None),
        )
        .group_by(CreditNote.invoice_id)
    )
    credited_by_invoice = {
        invoice_id: amount
        for invoice_id, amount in (await session.execute(credit_stmt)).all()
    }

    debit_stmt = (
        select(
            TaxDebitNote.invoice_id,
            func.coalesce(func.sum(TaxDebitNote.total_amount), ZERO),
        )
        .where(
            TaxDebitNote.invoice_id.in_(ids),
            TaxDebitNote.status == TaxDebitNoteStatus.ISSUED,
            TaxDebitNote.issue_date <= as_of,
            TaxDebitNote.deleted_at.is_(None),
        )
        .group_by(TaxDebitNote.invoice_id)
    )
    debited_by_invoice = {
        invoice_id: amount
        for invoice_id, amount in (await session.execute(debit_stmt)).all()
    }

    payment_stmt = (
        select(Payment)
        .where(
            Payment.invoice_id.in_(ids),
            Payment.status == PaymentStatus.SUCCESS,
        )
        .order_by(Payment.payment_date)
    )
    payments = (await session.execute(payment_stmt)).scalars().all()
    paid_by_invoice: dict[uuid.UUID, Decimal] = {invoice_id: ZERO for invoice_id in ids}
    for p in payments:
        if _payment_date_at_or_before(p, as_of):
            paid_by_invoice[p.invoice_id] = money(
                paid_by_invoice[p.invoice_id] + (p.amount or ZERO)
            )

    rows: list[_ReconstructedInvoice] = []
    for inv in invoices:
        balance_as_of = money(
            inv.total_amount
            - credited_by_invoice.get(inv.id, ZERO)
            + debited_by_invoice.get(inv.id, ZERO)
            - paid_by_invoice.get(inv.id, ZERO)
        )
        if balance_as_of > ZERO:
            rows.append(
                _ReconstructedInvoice(
                    id=inv.id,
                    client_id=inv.client_id,
                    invoice_number=inv.invoice_number,
                    issue_date=inv.issue_date,
                    due_date=inv.due_date,
                    balance_due=balance_as_of,
                )
            )
    return rows


async def ar_aging(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    as_of: Optional[date] = None,
    client_id: Optional[uuid.UUID] = None,
    view: str = "summary",
    historical: bool = False,
) -> dict:
    """AR aging report: summary | detail | by_customer.

    `historical=True` switches to the Wave 30 item 1.2 point-in-time engine —
    balances are reconstructed from ledger history as of `as_of`, so a past
    `as_of` shows the exposure exactly as it stood then (including invoices
    since fully paid, and excluding invoices issued after `as_of`).
    """
    resolved = as_of or utc_today()
    if resolved > utc_today():
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "as_of cannot be after today",
            "as_of",
        )

    if client_id is not None and view == "by_customer":
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "client_id cannot be combined with view=by_customer",
            "client_id",
        )

    if historical:
        invoices = await _reconstruct_open_invoices(
            session, workspace_id, resolved, client_id
        )
    else:
        invoices = await _open_ar_invoices(session, workspace_id, client_id)

    # Pre-aggregate PDC Outstanding per invoice to avoid row multiplication
    invoice_ids = [inv.id for inv in invoices]
    pdc_by_invoice = await _pdc_outstanding_by_invoice(
        session, workspace_id, invoice_ids
    )

    buckets = aging_buckets(invoices, resolved)
    outstanding = money(sum((inv.balance_due for inv in invoices), ZERO))

    # Compute PDC Outstanding aggregates
    total_pdc_count = 0
    total_pdc_amount = ZERO
    for inv in invoices:
        cnt, amt = pdc_by_invoice.get(inv.id, (0, ZERO))
        total_pdc_count += cnt
        total_pdc_amount = money(total_pdc_amount + amt)

    if view == "detail":
        clients = await _client_names(
            session, workspace_id, [inv.client_id for inv in invoices]
        )
        rows = [
            {
                "client_id": inv.client_id,
                "client_name": (
                    clients.get(inv.client_id).name
                    if clients.get(inv.client_id)
                    else ""
                ),
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "issue_date": inv.issue_date,
                "due_date": inv.due_date,
                "days_overdue": max(0, (resolved - inv.due_date).days),
                "balance_due": inv.balance_due,
                "bucket": _bucket_key((resolved - inv.due_date).days),
                "pdc_outstanding_count": pdc_by_invoice.get(inv.id, (0, ZERO))[0],
                "pdc_outstanding_amount": pdc_by_invoice.get(inv.id, (0, ZERO))[1],
            }
            for inv in invoices
        ]
        return {
            "as_of": resolved,
            "total_outstanding": outstanding,
            "buckets": buckets,
            "invoices": rows,
            "pdc_outstanding_count": total_pdc_count,
            "pdc_outstanding_amount": total_pdc_amount,
        }

    if view == "by_customer":
        per_client: dict[uuid.UUID, list[Invoice]] = {}
        for inv in invoices:
            per_client.setdefault(inv.client_id, []).append(inv)
        clients = await _client_names(session, workspace_id, list(per_client.keys()))
        rows = []
        for cid, invs in per_client.items():
            cli = clients.get(cid)
            # Per-client PDC aggregate
            client_pdc_count = 0
            client_pdc_amount = ZERO
            for inv in invs:
                cnt, amt = pdc_by_invoice.get(inv.id, (0, ZERO))
                client_pdc_count += cnt
                client_pdc_amount = money(client_pdc_amount + amt)
            rows.append(
                {
                    "client": {
                        "id": cid,
                        "name": cli.name if cli else "",
                    },
                    "total_outstanding": money(
                        sum((i.balance_due for i in invs), ZERO)
                    ),
                    "buckets": aging_buckets(invs, resolved),
                    "pdc_outstanding_count": client_pdc_count,
                    "pdc_outstanding_amount": client_pdc_amount,
                }
            )
        rows.sort(key=lambda r: r["client"]["name"])
        return {
            "as_of": resolved,
            "total_outstanding": outstanding,
            "buckets": buckets,
            "customers": rows,
            "pdc_outstanding_count": total_pdc_count,
            "pdc_outstanding_amount": total_pdc_amount,
        }

    client_ids = {inv.client_id for inv in invoices}
    return {
        "as_of": resolved,
        "client_count": len(client_ids),
        "invoice_count": len(invoices),
        "total_outstanding": outstanding,
        "buckets": buckets,
        "pdc_outstanding_count": total_pdc_count,
        "pdc_outstanding_amount": total_pdc_amount,
    }
