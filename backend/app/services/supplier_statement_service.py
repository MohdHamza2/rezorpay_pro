"""Generated supplier AP statement (the AP ledger). Read-only. No ledger table."""

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

from app.models.payment import PaymentStatus
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from app.models.supplier_payment import SupplierPayment
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.schemas.supplier_statements import (
    DOC_TYPE_LABELS,
    SupplierStatementDocType,
)
from app.services.ar_statement_service import (
    assert_activity_cap,
    validate_statement_dates,
)
from app.services.customer_po_support import raise_error
from app.services.line_money import money
from app.services.supplier_payment_service import (
    ap_aging_buckets,
    supplier_payment_service,
)

logger = logging.getLogger(__name__)

INCLUDE_STATUSES = (
    SupplierInvoiceStatus.APPROVED,
    SupplierInvoiceStatus.PARTIALLY_PAID,
    SupplierInvoiceStatus.PAID,
)
PAYMENT_STATUSES = (PaymentStatus.SUCCESS, PaymentStatus.PENDING)
ACTIVITY_ORDER = {
    SupplierStatementDocType.SUPPLIER_INVOICE: 0,
    SupplierStatementDocType.SUPPLIER_PAYMENT: 1,
    SupplierStatementDocType.SUPPLIER_PAYMENT_PENDING: 2,
}
ZERO = Decimal("0.00")


def payment_on(payment: SupplierPayment) -> date:
    value = payment.payment_date
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    return value


def in_period(value: date, start: date, end: date) -> bool:
    return start <= value <= end


def method_value(payment: SupplierPayment) -> Optional[str]:
    method = payment.payment_method
    if method is None:
        return None
    return method.value if hasattr(method, "value") else str(method)


def opening_debit_credit(opening: Decimal) -> tuple[Decimal, Decimal]:
    if opening > ZERO:
        return money(opening), ZERO
    if opening < ZERO:
        return ZERO, money(-opening)
    return ZERO, ZERO


def activity_sort_key(line: dict) -> tuple:
    return (
        line["date"],
        ACTIVITY_ORDER[line["doc_type"]],
        line["number"] or "",
    )


def labelled_line(
    *,
    on: date,
    doc_type: SupplierStatementDocType,
    number: Optional[str],
    reference: Optional[str],
    payment_method: Optional[str],
    payment_status: Optional[str],
    cleared_cash: Optional[bool],
    pending_amount: Decimal,
    debit: Decimal,
    credit: Decimal,
) -> dict:
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


def invoice_activity(invoice: SupplierInvoice) -> dict:
    return labelled_line(
        on=invoice.invoice_date.date(),
        doc_type=SupplierStatementDocType.SUPPLIER_INVOICE,
        number=invoice.supplier_invoice_number,
        reference=invoice.our_reference,
        payment_method=None,
        payment_status=None,
        cleared_cash=None,
        pending_amount=ZERO,
        debit=invoice.total_amount,
        credit=ZERO,
    )


def payment_activity(payment: SupplierPayment) -> dict:
    pending = payment.status == PaymentStatus.PENDING
    amount = money(payment.amount)
    return labelled_line(
        on=payment_on(payment),
        doc_type=(
            SupplierStatementDocType.SUPPLIER_PAYMENT_PENDING
            if pending
            else SupplierStatementDocType.SUPPLIER_PAYMENT
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


def collect_activity(
    invoices: Sequence[SupplierInvoice],
    payments: Sequence[SupplierPayment],
    start: date,
    end: date,
) -> list[dict]:
    rows = []
    for invoice in invoices:
        if in_period(invoice.invoice_date.date(), start, end):
            rows.append(invoice_activity(invoice))
    for payment in payments:
        if in_period(payment_on(payment), start, end):
            rows.append(payment_activity(payment))
    return rows


def reconstruct_opening(
    invoices: Sequence[SupplierInvoice],
    payments: Sequence[SupplierPayment],
    start: date,
) -> Decimal:
    billed = sum(
        (inv.total_amount for inv in invoices if inv.invoice_date.date() < start),
        ZERO,
    )
    paid = sum(
        (
            p.amount
            for p in payments
            if p.status == PaymentStatus.SUCCESS and payment_on(p) < start
        ),
        ZERO,
    )
    return money(billed - paid)


def period_totals(
    invoices: Sequence[SupplierInvoice],
    payments: Sequence[SupplierPayment],
    start: date,
    end: date,
) -> dict:
    billed = sum(
        (
            inv.total_amount
            for inv in invoices
            if in_period(inv.invoice_date.date(), start, end)
        ),
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
        "pending": money(pending),
    }


def assemble_lines(opening: Decimal, start: date, activity: list[dict]) -> tuple:
    debit, credit = opening_debit_credit(opening)
    opening_row = labelled_line(
        on=start,
        doc_type=SupplierStatementDocType.OPENING,
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


class SupplierStatementService:
    @staticmethod
    async def _require_supplier(
        session: AsyncSession, supplier_id: UUID, workspace_id: UUID
    ) -> Supplier:
        result = await session.execute(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.workspace_id == workspace_id,
            )
        )
        supplier = result.scalar_one_or_none()
        if supplier is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Supplier not found"
            )
        return supplier

    @staticmethod
    async def _load_include_set(
        session: AsyncSession, workspace_id: UUID, supplier_id: UUID
    ) -> list[SupplierInvoice]:
        result = await session.execute(
            select(SupplierInvoice)
            .where(SupplierInvoice.workspace_id == workspace_id)
            .where(SupplierInvoice.supplier_id == supplier_id)
            .where(SupplierInvoice.status.in_(INCLUDE_STATUSES))
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_payments(
        session: AsyncSession, invoice_ids: Sequence[uuid.UUID]
    ) -> list[SupplierPayment]:
        if not invoice_ids:
            return []
        result = await session.execute(
            select(SupplierPayment)
            .where(SupplierPayment.supplier_invoice_id.in_(invoice_ids))
            .where(SupplierPayment.status.in_(PAYMENT_STATUSES))
        )
        return list(result.scalars().all())

    @classmethod
    async def get_statement(
        cls,
        session: AsyncSession,
        workspace: Workspace,
        supplier_id: UUID,
        period_from: date,
        period_to: date,
        as_of: Optional[date],
        actor_id: Optional[UUID] = None,
    ) -> dict:
        resolved = validate_statement_dates(period_from, period_to, as_of)
        supplier = await cls._require_supplier(session, supplier_id, workspace.id)
        invoices = await cls._load_include_set(session, workspace.id, supplier.id)
        invoice_ids = [inv.id for inv in invoices]
        payments = await cls._load_payments(session, invoice_ids)
        opening = reconstruct_opening(invoices, payments, period_from)
        activity = collect_activity(invoices, payments, period_from, period_to)
        assert_activity_cap(len(activity))
        lines, closing = assemble_lines(opening, period_from, activity)
        totals = period_totals(invoices, payments, period_from, period_to)
        totals["closing_running"] = closing
        open_ap = await supplier_payment_service.open_ap_invoices(
            session, workspace.id, supplier.id
        )
        footer = {
            "amount_due_now": money(sum((inv.balance_due for inv in open_ap), ZERO)),
            "aging": {
                "as_of": resolved,
                "buckets": ap_aging_buckets(open_ap, resolved),
            },
        }
        logger.info(
            "supplier_statement_generated",
            extra={
                "supplier_id": str(supplier.id),
                "user_id": str(actor_id) if actor_id else None,
                "activity_lines": len(activity),
            },
        )
        return {
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "supplier_code": supplier.supplier_code,
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


supplier_statement_service = SupplierStatementService()
