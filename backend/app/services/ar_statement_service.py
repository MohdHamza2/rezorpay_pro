"""Generated customer AR statement. Read-only. No Alembic, no ledger table."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_note import CreditNote, CreditNoteStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.workspace import Workspace
from app.schemas.ar_statements import DOC_TYPE_LABELS, StatementDocType
from app.schemas.common import ErrorCode
from app.services.credit_control_service import (
    CreditControlService,
    aging_buckets,
    utc_today,
)
from app.services.customer_po_support import raise_error
from app.services.line_money import money

logger = logging.getLogger(__name__)

INCLUDE_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)
PAYMENT_STATUSES = (PaymentStatus.SUCCESS, PaymentStatus.PENDING)
ACTIVITY_ORDER = {
    StatementDocType.TAX_INVOICE: 0,
    StatementDocType.PAYMENT: 1,
    StatementDocType.PAYMENT_PENDING: 2,
    StatementDocType.TAX_CREDIT_NOTE: 3,
}
ACTIVITY_LINE_CAP = 2000
MAX_RANGE_DAYS = 366
ZERO = Decimal("0.00")


def assert_from_not_after_to(period_from: date, period_to: date) -> None:
    """Reject inverted statement windows."""
    if period_from > period_to:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "from must be on or before to",
            "from",
        )


def assert_range_not_too_long(period_from: date, period_to: date) -> None:
    """Reject windows longer than 366 days."""
    if (period_to - period_from).days > MAX_RANGE_DAYS:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.DATE_RANGE_TOO_LONG,
            "Date range cannot exceed 366 days",
            "to",
        )


def assert_as_of_not_future(as_of: date) -> None:
    """Reject as_of after UTC today."""
    if as_of > utc_today():
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "as_of cannot be after today",
            "as_of",
        )


def validate_statement_dates(
    period_from: date, period_to: date, as_of: Optional[date]
) -> date:
    """Return resolved as_of after range checks."""
    resolved = as_of or utc_today()
    assert_from_not_after_to(period_from, period_to)
    assert_range_not_too_long(period_from, period_to)
    assert_as_of_not_future(resolved)
    return resolved


def assert_activity_cap(activity_count: int) -> None:
    """Refuse silently truncated statements."""
    if activity_count > ACTIVITY_LINE_CAP:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.STATEMENT_TOO_LARGE,
            "Statement has too many activity lines; shorten the date range",
            "to",
        )


def payment_on(payment: Payment) -> date:
    """Calendar date of a payment in UTC."""
    value = payment.payment_date
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    return value


def in_period(value: date, start: date, end: date) -> bool:
    """Inclusive [from, to] membership."""
    return start <= value <= end


def method_value(payment: Payment) -> Optional[str]:
    """Payment method label for JSON."""
    method = payment.payment_method
    if method is None:
        return None
    return method.value if hasattr(method, "value") else str(method)


def opening_debit_credit(opening: Decimal) -> tuple[Decimal, Decimal]:
    """Opening > 0 is a debit; negative opening is a credit."""
    if opening > ZERO:
        return money(opening), ZERO
    if opening < ZERO:
        return ZERO, money(-opening)
    return ZERO, ZERO


def activity_sort_key(line: dict) -> tuple:
    """Date ASC, type order, number ASC."""
    return (
        line["date"],
        ACTIVITY_ORDER[line["doc_type"]],
        line["number"] or "",
    )


def labelled_line(
    *,
    on: date,
    doc_type: StatementDocType,
    number: Optional[str],
    reference: Optional[str],
    payment_method: Optional[str],
    payment_status: Optional[str],
    cleared_cash: Optional[bool],
    pending_amount: Decimal,
    debit: Decimal,
    credit: Decimal,
) -> dict:
    """One statement row without running balance."""
    return {
        "date": on,
        "doc_type": doc_type,
        "doc_type_label": DOC_TYPE_LABELS[doc_type],
        "number": number,
        "reference": reference,
        "payment_method": payment_method,
        "payment_status": payment_status,
        "cleared_cash": cleared_cash,
        "pending_amount": money(pending_amount),
        "debit": money(debit),
        "credit": money(credit),
    }


def invoice_activity(invoice: Invoice) -> dict:
    """Tax Invoice debit for total_amount."""
    return labelled_line(
        on=invoice.issue_date,
        doc_type=StatementDocType.TAX_INVOICE,
        number=invoice.invoice_number,
        reference=None,
        payment_method=None,
        payment_status=None,
        cleared_cash=None,
        pending_amount=ZERO,
        debit=invoice.total_amount,
        credit=ZERO,
    )


def payment_activity(payment: Payment) -> dict:
    """SUCCESS is cleared cash; PENDING is memo-only."""
    pending = payment.status == PaymentStatus.PENDING
    amount = money(payment.amount)
    return labelled_line(
        on=payment_on(payment),
        doc_type=(
            StatementDocType.PAYMENT_PENDING if pending else StatementDocType.PAYMENT
        ),
        number=payment.reference_number,
        reference=None,
        payment_method=method_value(payment),
        payment_status=payment.status.value,
        cleared_cash=not pending,
        pending_amount=amount if pending else ZERO,
        debit=ZERO,
        credit=ZERO if pending else amount,
    )


def credit_note_activity(note: CreditNote, invoice_number: Optional[str]) -> dict:
    """Tax Credit Note credit; never labelled Payment."""
    return labelled_line(
        on=note.issue_date,
        doc_type=StatementDocType.TAX_CREDIT_NOTE,
        number=note.credit_note_number,
        reference=note.original_invoice_number or invoice_number,
        payment_method=None,
        payment_status=None,
        cleared_cash=None,
        pending_amount=ZERO,
        debit=ZERO,
        credit=note.total_amount,
    )


def collect_activity(
    invoices: Sequence[Invoice],
    payments: Sequence[Payment],
    notes: Sequence[CreditNote],
    numbers: dict[uuid.UUID, str],
    start: date,
    end: date,
) -> list[dict]:
    """Activity rows in [from, to], excluding opening."""
    rows: list[dict] = []
    for invoice in invoices:
        if in_period(invoice.issue_date, start, end):
            rows.append(invoice_activity(invoice))
    for payment in payments:
        if in_period(payment_on(payment), start, end):
            rows.append(payment_activity(payment))
    for note in notes:
        if in_period(note.issue_date, start, end):
            rows.append(credit_note_activity(note, numbers.get(note.invoice_id)))
    return rows


def reconstruct_opening(
    invoices: Sequence[Invoice],
    payments: Sequence[Payment],
    notes: Sequence[CreditNote],
    start: date,
) -> Decimal:
    """billed_before − paid_before − credited_before for dates < from."""
    billed = sum((inv.total_amount for inv in invoices if inv.issue_date < start), ZERO)
    paid = sum(
        (
            p.amount
            for p in payments
            if p.status == PaymentStatus.SUCCESS and payment_on(p) < start
        ),
        ZERO,
    )
    credited = sum((cn.total_amount for cn in notes if cn.issue_date < start), ZERO)
    return money(billed - paid - credited)


def period_totals(
    invoices: Sequence[Invoice],
    payments: Sequence[Payment],
    notes: Sequence[CreditNote],
    start: date,
    end: date,
) -> dict:
    """Period billed / SUCCESS paid / ISSUED credited / PENDING."""
    billed = sum(
        (inv.total_amount for inv in invoices if in_period(inv.issue_date, start, end)),
        ZERO,
    )
    paid = sum(
        (
            p.amount
            for p in payments
            if p.status == PaymentStatus.SUCCESS
            and in_period(payment_on(p), start, end)
        ),
        ZERO,
    )
    credited = sum(
        (cn.total_amount for cn in notes if in_period(cn.issue_date, start, end)),
        ZERO,
    )
    pending = sum(
        (
            p.amount
            for p in payments
            if p.status == PaymentStatus.PENDING
            and in_period(payment_on(p), start, end)
        ),
        ZERO,
    )
    return {
        "billed": money(billed),
        "paid": money(paid),
        "credited": money(credited),
        "pending": money(pending),
    }


def assemble_lines(opening: Decimal, start: date, activity: list[dict]) -> tuple:
    """Opening first, then sorted activity with running balances."""
    debit, credit = opening_debit_credit(opening)
    opening_row = labelled_line(
        on=start,
        doc_type=StatementDocType.OPENING,
        number=None,
        reference=None,
        payment_method=None,
        payment_status=None,
        cleared_cash=None,
        pending_amount=ZERO,
        debit=debit,
        credit=credit,
    )
    opening_row["running_balance"] = money(opening)
    sorted_activity = sorted(activity, key=activity_sort_key)
    running = money(opening)
    lines = [opening_row]
    for row in sorted_activity:
        running = money(running + row["debit"] - row["credit"])
        row["running_balance"] = running
        lines.append(row)
    return lines, running


def exposure_of(invoices: Sequence[Invoice]) -> Decimal:
    """Σ live balance_due of open AR."""
    return money(sum((inv.balance_due for inv in invoices), ZERO))


class ArStatementService:
    """Assemble a generated AR statement over live invoices / payments / CNs."""

    @staticmethod
    async def _require_client(
        session: AsyncSession, client_id: UUID, workspace_id: UUID
    ) -> Client:
        client = await CreditControlService.load_client(
            session, client_id, workspace_id
        )
        if client is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found"
            )
        return client

    @staticmethod
    async def _load_include_set(
        session: AsyncSession, workspace_id: UUID, client_id: UUID
    ) -> list[Invoice]:
        result = await session.execute(
            select(Invoice)
            .where(Invoice.workspace_id == workspace_id)
            .where(Invoice.client_id == client_id)
            .where(Invoice.deleted_at.is_(None))
            .where(Invoice.status.in_(INCLUDE_STATUSES))
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_payments(
        session: AsyncSession, invoice_ids: Sequence[uuid.UUID]
    ) -> list[Payment]:
        if not invoice_ids:
            return []
        result = await session.execute(
            select(Payment)
            .where(Payment.invoice_id.in_(invoice_ids))
            .where(Payment.status.in_(PAYMENT_STATUSES))
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_credit_notes(
        session: AsyncSession, workspace_id: UUID, invoice_ids: Sequence[uuid.UUID]
    ) -> list[CreditNote]:
        if not invoice_ids:
            return []
        result = await session.execute(
            select(CreditNote)
            .where(CreditNote.workspace_id == workspace_id)
            .where(CreditNote.invoice_id.in_(invoice_ids))
            .where(CreditNote.status == CreditNoteStatus.ISSUED)
            .where(CreditNote.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    @staticmethod
    async def _footer(
        session: AsyncSession, workspace: Workspace, client: Client, as_of: date
    ) -> dict:
        open_ar = await CreditControlService.open_ar_invoices(
            session, workspace.id, client.id
        )
        return {
            "amount_due_now": exposure_of(open_ar),
            "credit_balance": money(client.credit_balance or ZERO),
            "aging": {"as_of": as_of, "buckets": aging_buckets(open_ar, as_of)},
        }

    @classmethod
    async def get_statement(
        cls,
        session: AsyncSession,
        workspace: Workspace,
        client_id: UUID,
        period_from: date,
        period_to: date,
        as_of: Optional[date],
        actor_id: Optional[UUID] = None,
    ) -> dict:
        """Build JSON for GET /clients/{id}/ar-statement. Does not write rows."""
        resolved = validate_statement_dates(period_from, period_to, as_of)
        client = await cls._require_client(session, client_id, workspace.id)
        invoices = await cls._load_include_set(session, workspace.id, client.id)
        invoice_ids = [inv.id for inv in invoices]
        numbers = {inv.id: inv.invoice_number for inv in invoices}
        payments = await cls._load_payments(session, invoice_ids)
        notes = await cls._load_credit_notes(session, workspace.id, invoice_ids)
        opening = reconstruct_opening(invoices, payments, notes, period_from)
        activity = collect_activity(
            invoices, payments, notes, numbers, period_from, period_to
        )
        assert_activity_cap(len(activity))
        lines, closing = assemble_lines(opening, period_from, activity)
        totals = period_totals(invoices, payments, notes, period_from, period_to)
        totals["closing_running"] = closing
        footer = await cls._footer(session, workspace, client, resolved)
        logger.info(
            "ar_statement_generated",
            extra={
                "client_id": str(client.id),
                "user_id": str(actor_id) if actor_id else None,
                "activity_lines": len(activity),
            },
        )
        return {
            "client": {
                "id": client.id,
                "name": client.name,
                "tax_id": client.tax_id,
                "address": client.address,
            },
            "workspace": {
                "name": workspace.name,
                "trn": workspace.trn,
                "address": workspace.address,
            },
            "currency": "AED",
            "from": period_from,
            "to": period_to,
            "as_of": resolved,
            "opening_balance": opening,
            "lines": lines,
            "totals": totals,
            **footer,
        }
