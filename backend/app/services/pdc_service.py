"""PDC lifecycle transitions. Amount/method/dates are never rewritten."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import NoReturn

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_status_event import CreditEventReason
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentMethod, PaymentStatus, PDCStatus
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.services.credit_control_service import CreditControlService, utc_today
from app.services.customer_po_support import raise_error
from app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may change PDC status",
        )


def _invalid_state(message: str) -> NoReturn:
    raise_error(
        status.HTTP_403_FORBIDDEN,
        ErrorCode.INVALID_STATE,
        message,
        "pdc_status",
    )


def _require_pdc(payment: Payment) -> None:
    if payment.payment_method != PaymentMethod.PDC:
        _invalid_state("PDC actions apply only to PDC payments")


def _cleared_already(payment: Payment) -> bool:
    return payment.pdc_status == PDCStatus.CLEARED or (
        payment.status == PaymentStatus.SUCCESS
        and payment.payment_method == PaymentMethod.PDC
    )


def _assert_fits_balance(payment: Payment, invoice: Invoice) -> None:
    due = InvoiceService.calculate_balance_due(invoice)
    if payment.amount > due:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.PAYMENT_EXCEEDS_BALANCE,
            f"Payment amount ({payment.amount}) exceeds balance due ({due}). "
            "Overpayments are not allowed for MVP.",
        )


class PdcService:
    """RECEIVED → DEPOSITED → CLEARED | BOUNCED; RECEIVED → RETURNED."""

    @staticmethod
    async def _lock_invoice(
        session: AsyncSession, workspace_id: uuid.UUID, invoice_id: uuid.UUID
    ) -> Invoice:
        result = await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.payments))
            .where(Invoice.id == invoice_id)
            .where(Invoice.workspace_id == workspace_id)
            .with_for_update()
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found"
            )
        return invoice

    @staticmethod
    async def _lock_payment(
        session: AsyncSession, invoice_id: uuid.UUID, payment_id: uuid.UUID
    ) -> Payment:
        result = await session.execute(
            select(Payment)
            .where(Payment.id == payment_id)
            .where(Payment.invoice_id == invoice_id)
            .with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Payment not found"
            )
        return payment

    @classmethod
    async def _lock_pair(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
    ) -> tuple[Invoice, Payment]:
        invoice = await cls._lock_invoice(session, workspace_id, invoice_id)
        payment = await cls._lock_payment(session, invoice.id, payment_id)
        return invoice, payment

    @classmethod
    async def _ready(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> tuple[Invoice, Payment]:
        invoice, payment = await cls._lock_pair(
            session, workspace_id, invoice_id, payment_id
        )
        _require_owner_admin(user)
        _require_pdc(payment)
        return invoice, payment

    @classmethod
    async def _evaluate(
        cls, session: AsyncSession, invoice: Invoice, user_id: uuid.UUID
    ):
        workspace = await session.get(Workspace, invoice.workspace_id)
        client = await session.get(Client, invoice.client_id)
        if workspace is not None and client is not None:
            await CreditControlService.evaluate(
                session, client, workspace, user_id, CreditEventReason.PAYMENT
            )

    @classmethod
    async def deposit(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> Payment:
        invoice, payment = await cls._ready(
            session, workspace_id, invoice_id, payment_id, user
        )
        if (
            payment.pdc_status == PDCStatus.DEPOSITED
            and payment.status == PaymentStatus.PENDING
        ):
            return payment
        if _cleared_already(payment):
            _invalid_state("Cannot deposit a SUCCESS or CLEARED payment")
        if (
            payment.pdc_status != PDCStatus.RECEIVED
            or payment.status != PaymentStatus.PENDING
        ):
            _invalid_state("PDC must be RECEIVED before it can be deposited")
        if payment.pdc_date is None or payment.pdc_date > utc_today():
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot deposit before cheque date",
                "pdc_date",
            )
        payment.pdc_status = PDCStatus.DEPOSITED
        payment.updated_at = _now()
        logger.info(
            "pdc_deposited",
            extra={"payment_id": str(payment.id), "invoice_id": str(invoice.id)},
        )
        return payment

    @classmethod
    async def clear(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> Payment:
        invoice, payment = await cls._ready(
            session, workspace_id, invoice_id, payment_id, user
        )
        if _cleared_already(payment):
            return payment
        if payment.pdc_status != PDCStatus.DEPOSITED:
            _invalid_state("PDC must be DEPOSITED before it can be cleared")
        await session.refresh(invoice, ["payments"])
        _assert_fits_balance(payment, invoice)
        payment.status = PaymentStatus.SUCCESS
        payment.pdc_status = PDCStatus.CLEARED
        payment.updated_at = _now()
        await session.flush()
        await InvoiceService.update_status_from_payments(session, invoice, user.id)
        logger.info(
            "pdc_cleared",
            extra={"payment_id": str(payment.id), "invoice_id": str(invoice.id)},
        )
        return payment

    @classmethod
    async def bounce(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> Payment:
        invoice, payment = await cls._ready(
            session, workspace_id, invoice_id, payment_id, user
        )
        if payment.pdc_status == PDCStatus.BOUNCED:
            return payment
        if _cleared_already(payment):
            _invalid_state("Cannot bounce a SUCCESS or CLEARED payment")
        if payment.pdc_status != PDCStatus.DEPOSITED:
            _invalid_state("PDC must be DEPOSITED before it can be bounced")
        payment.status = PaymentStatus.FAILED
        payment.pdc_status = PDCStatus.BOUNCED
        payment.updated_at = _now()
        await cls._evaluate(session, invoice, user.id)
        logger.info(
            "pdc_bounced",
            extra={"payment_id": str(payment.id), "invoice_id": str(invoice.id)},
        )
        return payment

    @classmethod
    async def return_cheque(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        payment_id: uuid.UUID,
        user: User,
    ) -> Payment:
        _invoice, payment = await cls._ready(
            session, workspace_id, invoice_id, payment_id, user
        )
        if payment.pdc_status == PDCStatus.RETURNED:
            return payment
        if _cleared_already(payment):
            _invalid_state("Cannot return a SUCCESS or CLEARED payment")
        if (
            payment.pdc_status != PDCStatus.RECEIVED
            or payment.status != PaymentStatus.PENDING
        ):
            _invalid_state("PDC can only be returned from RECEIVED")
        payment.status = PaymentStatus.CANCELLED
        payment.pdc_status = PDCStatus.RETURNED
        payment.updated_at = _now()
        logger.info("pdc_returned", extra={"payment_id": str(payment.id)})
        return payment
