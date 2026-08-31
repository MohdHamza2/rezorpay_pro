"""Credit HOLD / exposure / aging. WP-A — no Celery, no admin override."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import NoReturn, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_status_event import (
    CreditEventReason,
    CreditStatus,
    CreditStatusEvent,
)
from app.models.invoice import Invoice, InvoiceStatus
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode, ErrorDetail
from app.services.line_money import money

logger = logging.getLogger(__name__)

AR_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.OVERDUE,
)
FLIP_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID)
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class CreditSnapshot:
    status: CreditStatus
    exposure: Decimal
    effective_limit: Decimal
    oldest_overdue_days: Optional[int]
    credit_limit: Optional[Decimal]
    payment_terms_days: int


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def due_date_from_terms(issue_date: date, payment_terms_days: int) -> date:
    return issue_date + timedelta(days=payment_terms_days)


def effective_limit(client: Client, workspace: Workspace) -> Decimal:
    if client.credit_limit is not None:
        return money(client.credit_limit)
    return money(workspace.credit_limit_default)


def decide_status(
    exposure: Decimal,
    limit: Decimal,
    oldest_overdue_days: Optional[int],
    warning_days: int,
    hold_days: int,
) -> CreditStatus:
    if exposure > limit:
        return CreditStatus.HOLD
    if oldest_overdue_days is not None and oldest_overdue_days > hold_days:
        return CreditStatus.HOLD
    if oldest_overdue_days is not None and oldest_overdue_days > warning_days:
        return CreditStatus.WARNING
    return CreditStatus.ACTIVE


def assert_warning_not_after_hold(warning_days: int, hold_days: int) -> None:
    if warning_days > hold_days:
        _raise(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "credit_warning_days must be less than or equal to credit_hold_days",
            "credit_warning_days",
        )


def _raise(
    http_status: int, code: str, message: str, field: Optional[str] = None
) -> NoReturn:
    raise HTTPException(
        status_code=http_status,
        detail=ErrorDetail(code=code, message=message, field=field).model_dump(),
    )


def _exposure(invoices: Sequence[Invoice]) -> Decimal:
    return money(sum((inv.balance_due for inv in invoices), ZERO))


def _oldest_overdue_days(invoices: Sequence[Invoice], today: date) -> Optional[int]:
    dates = [
        inv.due_date
        for inv in invoices
        if inv.due_date < today and inv.balance_due > ZERO
    ]
    if not dates:
        return None
    return (today - min(dates)).days


def _bucket_key(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "days_1_30"
    if days_overdue <= 60:
        return "days_31_60"
    if days_overdue <= 90:
        return "days_61_90"
    return "days_90_plus"


def aging_buckets(invoices: Sequence[Invoice], today: date) -> dict[str, Decimal]:
    buckets = {
        "current": ZERO,
        "days_1_30": ZERO,
        "days_31_60": ZERO,
        "days_61_90": ZERO,
        "days_90_plus": ZERO,
    }
    for inv in invoices:
        key = _bucket_key((today - inv.due_date).days)
        buckets[key] = money(buckets[key] + inv.balance_due)
    return buckets


def should_mark_overdue(invoice: Invoice, today: Optional[date] = None) -> bool:
    today = today or utc_today()
    if invoice.deleted_at is not None:
        return False
    if invoice.status not in AR_STATUSES:
        return False
    if invoice.due_date >= today:
        return False
    return invoice.balance_due > ZERO


class CreditControlService:
    """Exposure SUM, evaluate, persist, HOLD assert, overdue on-read."""

    @staticmethod
    async def open_ar_invoices(
        session: AsyncSession, workspace_id: uuid.UUID, client_id: uuid.UUID
    ) -> list[Invoice]:
        result = await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.payments))
            .where(Invoice.workspace_id == workspace_id)
            .where(Invoice.client_id == client_id)
            .where(Invoice.deleted_at.is_(None))
            .where(Invoice.status.in_(AR_STATUSES))
        )
        return list(result.scalars().all())

    @classmethod
    async def snapshot(
        cls, session: AsyncSession, client: Client, workspace: Workspace
    ) -> CreditSnapshot:
        invoices = await cls.open_ar_invoices(session, workspace.id, client.id)
        exposure = _exposure(invoices)
        limit = effective_limit(client, workspace)
        oldest = _oldest_overdue_days(invoices, utc_today())
        status_value = decide_status(
            exposure,
            limit,
            oldest,
            workspace.credit_warning_days,
            workspace.credit_hold_days,
        )
        return CreditSnapshot(
            status=status_value,
            exposure=exposure,
            effective_limit=limit,
            oldest_overdue_days=oldest,
            credit_limit=client.credit_limit,
            payment_terms_days=client.payment_terms_days,
        )

    @classmethod
    async def evaluate(
        cls,
        session: AsyncSession,
        client: Client,
        workspace: Workspace,
        user_id: Optional[uuid.UUID],
        reason: CreditEventReason,
    ) -> CreditSnapshot:
        await cls.apply_overdue_client(session, workspace.id, client.id)
        snap = await cls.snapshot(session, client, workspace)
        if client.credit_status != snap.status:
            await cls._persist_change(session, client, workspace, snap, user_id, reason)
        return snap

    @classmethod
    async def _persist_change(
        cls,
        session: AsyncSession,
        client: Client,
        workspace: Workspace,
        snap: CreditSnapshot,
        user_id: Optional[uuid.UUID],
        reason: CreditEventReason,
    ) -> None:
        previous = client.credit_status
        event = CreditStatusEvent(
            client_id=client.id,
            workspace_id=workspace.id,
            previous_status=previous.value,
            new_status=snap.status.value,
            exposure=snap.exposure,
            effective_limit=snap.effective_limit,
            oldest_overdue_days=snap.oldest_overdue_days,
            reason=reason,
            changed_by=user_id,
            metadata_log={},
            timestamp=_now(),
        )
        session.add(event)
        client.credit_status = snap.status
        client.credit_status_changed_at = _now()
        client.credit_status_changed_by = user_id
        logger.info(
            "credit_status_changed",
            extra={
                "client_id": str(client.id),
                "previous": previous.value,
                "new": snap.status.value,
                "reason": reason.value,
            },
        )

    @classmethod
    async def lock_client(
        cls, session: AsyncSession, client_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Optional[Client]:
        result = await session.execute(
            select(Client)
            .where(Client.id == client_id)
            .where(Client.workspace_id == workspace_id)
            .where(Client.deleted_at.is_(None))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @classmethod
    async def assert_not_hold(
        cls,
        session: AsyncSession,
        client: Client,
        workspace: Workspace,
        user_id: Optional[uuid.UUID],
        reason: CreditEventReason,
    ) -> CreditSnapshot:
        locked = await cls.lock_client(session, client.id, workspace.id)
        if locked is None:
            _raise(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found")
        snap = await cls.evaluate(session, locked, workspace, user_id, reason)
        if snap.status == CreditStatus.HOLD:
            _raise(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.CREDIT_HOLD,
                (
                    "Client is on credit HOLD "
                    f"(exposure {snap.exposure} exceeds effective limit "
                    f"{snap.effective_limit})"
                    if snap.exposure > snap.effective_limit
                    else (
                        "Client is on credit HOLD "
                        f"(oldest overdue {snap.oldest_overdue_days} days)"
                    )
                ),
                "client.credit_status",
            )
        return snap

    @classmethod
    async def aging(
        cls, session: AsyncSession, client: Client, workspace: Workspace
    ) -> dict:
        invoices = await cls.open_ar_invoices(session, workspace.id, client.id)
        today = utc_today()
        snap = await cls.snapshot(session, client, workspace)
        return {
            "credit_status": snap.status,
            "credit_limit": snap.credit_limit,
            "effective_credit_limit": snap.effective_limit,
            "payment_terms_days": snap.payment_terms_days,
            "exposure": snap.exposure,
            "oldest_overdue_days": snap.oldest_overdue_days,
            "buckets": aging_buckets(invoices, today),
        }

    @staticmethod
    def _past_due_select(
        workspace_id: uuid.UUID, client_id: Optional[uuid.UUID] = None
    ):
        query = (
            select(Invoice)
            .options(selectinload(Invoice.payments))
            .where(Invoice.workspace_id == workspace_id)
            .where(Invoice.deleted_at.is_(None))
            .where(Invoice.status.in_(FLIP_STATUSES))
            .where(Invoice.due_date < utc_today())
        )
        if client_id is not None:
            query = query.where(Invoice.client_id == client_id)
        return query

    @staticmethod
    def _flip_past_due(invoices: Sequence[Invoice]) -> int:
        flipped = 0
        for invoice in invoices:
            if invoice.balance_due > ZERO:
                invoice.status = InvoiceStatus.OVERDUE
                invoice.updated_at = _now()
                flipped += 1
        return flipped

    @staticmethod
    async def apply_overdue_invoice(session: AsyncSession, invoice: Invoice) -> bool:
        if invoice.status not in FLIP_STATUSES:
            return False
        await session.refresh(invoice, ["payments"])
        if not should_mark_overdue(invoice):
            return False
        invoice.status = InvoiceStatus.OVERDUE
        invoice.updated_at = _now()
        return True

    @classmethod
    async def apply_overdue_client(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> int:
        result = await session.execute(cls._past_due_select(workspace_id, client_id))
        return cls._flip_past_due(list(result.scalars().all()))

    @classmethod
    async def apply_overdue_workspace(
        cls, session: AsyncSession, workspace_id: uuid.UUID
    ) -> int:
        result = await session.execute(cls._past_due_select(workspace_id))
        return cls._flip_past_due(list(result.scalars().all()))

    @staticmethod
    async def load_client(
        session: AsyncSession, client_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Optional[Client]:
        result = await session.execute(
            select(Client)
            .where(Client.id == client_id)
            .where(Client.workspace_id == workspace_id)
            .where(Client.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()
