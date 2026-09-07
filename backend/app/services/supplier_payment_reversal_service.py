"""AP payment reversal — a SUCCESS CHEQUE/CASH/BANK payment that bounces at the bank.

Wave 25 (Phase 4 leftover). MVP records non-PDC payments SUCCESS on receipt
("cleared on receipt"). If the bank later refuses the cheque or recalls the
transfer, the AP the payment consumed must be restored: `status -> FAILED` and
the exact inverse of `SupplierPaymentService._settle_invoice` runs inside the
row lock. Amount / method / `payment_date` / reference / bank are never
rewritten. Already-reversed payments are a 200 no-op; PDC payments use their
own machine and a CLEARED PDC is terminal (mirror AR).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import NoReturn

from fastapi import status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.payment import PaymentMethod, PaymentStatus
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from app.models.supplier_payment import SupplierPayment
from app.models.user import User, UserRole
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error
from app.services.line_money import money

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

REVERSIBLE_INVOICE_STATUSES = (
    SupplierInvoiceStatus.APPROVED,
    SupplierInvoiceStatus.PARTIALLY_PAID,
    SupplierInvoiceStatus.PAID,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may reverse a payment",
        )


def _invalid_state(message: str) -> NoReturn:
    raise_error(status.HTTP_403_FORBIDDEN, ErrorCode.INVALID_STATE, message)


class SupplierPaymentReversalService:
    @staticmethod
    async def _lock_invoice(
        session: AsyncSession, workspace_id: uuid.UUID, invoice_id: uuid.UUID
    ) -> SupplierInvoice:
        result = await session.execute(
            select(SupplierInvoice)
            .where(SupplierInvoice.id == invoice_id)
            .where(SupplierInvoice.workspace_id == workspace_id)
            .with_for_update()
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Supplier invoice not found or not in workspace",
            )
        return invoice

    @staticmethod
    async def _lock_payment(
        session: AsyncSession, invoice_id: uuid.UUID, payment_id: uuid.UUID
    ) -> SupplierPayment:
        result = await session.execute(
            select(SupplierPayment)
            .where(SupplierPayment.id == payment_id)
            .where(SupplierPayment.supplier_invoice_id == invoice_id)
            .with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Supplier payment not found for this invoice",
            )
        return payment

    @classmethod
    async def reverse_payment(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> SupplierPayment:
        invoice = await cls._lock_invoice(session, workspace_id, invoice_id)
        payment = await cls._lock_payment(session, invoice.id, payment_id)
        _require_owner_admin(user)
        if payment.payment_method == PaymentMethod.PDC:
            _invalid_state(
                "PDC payments use the PDC lifecycle; they cannot be reversed"
            )
        if payment.status == PaymentStatus.FAILED:
            return payment
        if payment.status != PaymentStatus.SUCCESS:
            _invalid_state("Only SUCCESS payments can be reversed")
        if invoice.status not in REVERSIBLE_INVOICE_STATUSES:
            _invalid_state("The invoice is not open; it cannot be reversed")
        if payment.amount > invoice.amount_paid:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.PAYMENT_EXCEEDS_BALANCE,
                f"Payment amount ({payment.amount}) exceeds amount paid "
                f"({invoice.amount_paid}). Cannot reverse.",
            )
        payment.status = PaymentStatus.FAILED
        payment.updated_at = _now()
        await session.flush()
        cls._reverse_settlement(invoice, payment.amount)
        logger.info(
            "supplier_payment_reversed",
            extra={
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
            },
        )
        return payment

    @staticmethod
    def _reverse_settlement(invoice: SupplierInvoice, amount: Decimal) -> None:
        """Inverse of `SupplierPaymentService._settle_invoice`.

        Called inside the row lock when a SUCCESS payment is reversed. AP is
        restored (`amount_paid -= amount; balance_due += amount`) and the
        invoice steps back from PAID -> PARTIALLY_PAID -> APPROVED.
        `amount_paid` never goes negative — the caller guards
        `amount <= amount_paid`.
        """
        invoice.amount_paid = money(invoice.amount_paid - amount)
        invoice.balance_due = money(invoice.balance_due + amount)
        invoice.updated_at = _now()
        if invoice.balance_due > ZERO:
            invoice.paid_at = None
            if invoice.status == SupplierInvoiceStatus.PAID:
                invoice.status = SupplierInvoiceStatus.PARTIALLY_PAID
            if (
                invoice.status == SupplierInvoiceStatus.PARTIALLY_PAID
                and invoice.amount_paid == ZERO
            ):
                invoice.status = SupplierInvoiceStatus.APPROVED


supplier_payment_reversal_service = SupplierPaymentReversalService()
