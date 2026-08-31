"""Quotation lifecycle: state machine, on-read expiry, convert via InvoiceService."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice import Invoice
from app.models.quotation import Quotation, QuotationStatus
from app.models.quotation_event import QuotationEventType
from app.models.quotation_item import QuotationItem
from app.schemas.common import ErrorCode
from app.services.invoice_service import AED, InvoiceService, _workspace_tax_rate
from app.services.quotation_number import QuotationNumberService
from app.services.quotation_support import (
    CONVERTIBLE,
    INVOICE_DUE_DAYS,
    VALIDITY_DAYS,
    add_items,
    assert_aed,
    assert_draft,
    assert_status,
    assert_validity,
    converted_notes,
    existing_converted_invoice,
    expire_locked,
    frozen_invoice_items,
    log_event,
    mark_expired,
    now,
    raise_error,
    recalculate,
    should_expire,
    utc_today,
)


class QuotationService:
    """State machine, expiry-on-read, isolation, convert-once."""

    @staticmethod
    def serialize(
        quotation: Quotation, converted_invoice_id: Optional[uuid.UUID] = None
    ):
        from app.schemas.quotations import QuotationResponse

        payload = QuotationResponse.model_validate(quotation)
        return payload.model_copy(update={"converted_invoice_id": converted_invoice_id})

    @staticmethod
    def serialize_list_item(
        quotation: Quotation, converted_invoice_id: Optional[uuid.UUID] = None
    ):
        from app.schemas.quotations import QuotationListItem

        payload = QuotationListItem.model_validate(quotation)
        return payload.model_copy(update={"converted_invoice_id": converted_invoice_id})

    @staticmethod
    async def map_converted_ids(
        session: AsyncSession,
        quotation_ids: Sequence[uuid.UUID],
        workspace_id: uuid.UUID,
    ) -> Dict[uuid.UUID, uuid.UUID]:
        if not quotation_ids:
            return {}
        result = await session.execute(
            select(Invoice.quotation_id, Invoice.id).where(
                Invoice.quotation_id.in_(list(quotation_ids)),
                Invoice.workspace_id == workspace_id,
            )
        )
        return {qid: iid for qid, iid in result.all() if qid is not None}

    @staticmethod
    async def get_visible(
        session: AsyncSession,
        quotation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[Quotation]:
        query = (
            select(Quotation)
            .options(selectinload(Quotation.items))
            .where(Quotation.id == quotation_id)
            .where(Quotation.workspace_id == workspace_id)
            .where(Quotation.deleted_at.is_(None))
        )
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def get_for_response(
        cls,
        session: AsyncSession,
        quotation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[Quotation]:
        quote = await cls.get_visible(session, quotation_id, workspace_id)
        if quote is None:
            return None
        if should_expire(quote):
            quote = await cls.get_visible(
                session, quotation_id, workspace_id, for_update=True
            )
            if quote is None:
                return None
            await mark_expired(session, quote, user_id)
        return quote

    @staticmethod
    async def expire_if_due(
        session: AsyncSession, quotation: Quotation, user_id: uuid.UUID
    ) -> bool:
        """On-read expiry. Router must commit when True, then 403 the action."""
        return await expire_locked(session, quotation, user_id)

    @classmethod
    async def expire_workspace_sent(
        cls, session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        today = utc_today()
        result = await session.execute(
            select(Quotation)
            .where(Quotation.workspace_id == workspace_id)
            .where(Quotation.status == QuotationStatus.SENT)
            .where(Quotation.valid_until < today)
            .where(Quotation.deleted_at.is_(None))
            .with_for_update()
        )
        for quote in result.scalars().all():
            await mark_expired(session, quote, user_id)

    @staticmethod
    async def create(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        quotation_date: Optional[date],
        valid_until: Optional[date],
        currency: str,
        notes: Optional[str],
        items: List[dict],
    ) -> Quotation:
        assert_aed(currency)
        q_date = quotation_date or utc_today()
        until = valid_until or (q_date + timedelta(days=VALIDITY_DAYS))
        assert_validity(q_date, until)
        default_tax = await _workspace_tax_rate(session, workspace_id)
        number = await QuotationNumberService.generate_quotation_number(
            session, workspace_id
        )
        quote = Quotation(
            workspace_id=workspace_id,
            client_id=client_id,
            quotation_number=number,
            currency=currency,
            status=QuotationStatus.DRAFT,
            quotation_date=q_date,
            valid_until=until,
            notes=notes,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            created_at=now(),
            updated_at=now(),
        )
        session.add(quote)
        await session.flush()
        await add_items(session, quote, workspace_id, default_tax, items)
        await recalculate(session, quote)
        await log_event(
            session,
            quote,
            user_id,
            QuotationEventType.QUOTATION_CREATED,
            None,
            QuotationStatus.DRAFT.value,
            {"items_count": len(items), "total": str(quote.total_amount)},
        )
        return quote

    @classmethod
    async def update_draft(
        cls,
        session: AsyncSession,
        quotation: Quotation,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> Quotation:
        assert_draft(quotation)
        if "currency" in patch:
            raw = patch["currency"]
            patch["currency"] = raw.value if hasattr(raw, "value") else raw
            assert_aed(patch["currency"])
        q_date = patch.get("quotation_date", quotation.quotation_date)
        until = patch.get("valid_until", quotation.valid_until)
        assert_validity(q_date, until)
        for field, value in patch.items():
            setattr(quotation, field, value)
        if items is not None:
            await session.execute(
                delete(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
            )
            await session.flush()
            default_tax = await _workspace_tax_rate(session, quotation.workspace_id)
            await add_items(
                session, quotation, quotation.workspace_id, default_tax, items
            )
        await recalculate(session, quotation)
        await log_event(
            session,
            quotation,
            user_id,
            QuotationEventType.QUOTATION_UPDATED,
            QuotationStatus.DRAFT.value,
            QuotationStatus.DRAFT.value,
            {"changed": list(patch.keys()) + (["items"] if items is not None else [])},
        )
        return quotation

    @staticmethod
    async def soft_delete(quotation: Quotation) -> None:
        assert_draft(quotation)
        quotation.deleted_at = now()
        quotation.updated_at = now()

    @classmethod
    async def send(
        cls, session: AsyncSession, quotation: Quotation, user_id: uuid.UUID
    ) -> Quotation:
        assert_draft(quotation)
        assert_aed(quotation.currency)
        if not quotation.items:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot send a quotation with no lines",
            )
        previous = quotation.status.value
        quotation.status = QuotationStatus.SENT
        quotation.updated_at = now()
        await log_event(
            session,
            quotation,
            user_id,
            QuotationEventType.QUOTATION_SENT,
            previous,
            QuotationStatus.SENT.value,
            None,
        )
        return quotation

    @classmethod
    async def accept(
        cls, session: AsyncSession, quotation: Quotation, user_id: uuid.UUID
    ) -> Quotation:
        await expire_locked(session, quotation, user_id)
        assert_status(quotation, QuotationStatus.SENT, "accept")
        previous = quotation.status.value
        quotation.status = QuotationStatus.ACCEPTED
        quotation.updated_at = now()
        await log_event(
            session,
            quotation,
            user_id,
            QuotationEventType.QUOTATION_ACCEPTED,
            previous,
            QuotationStatus.ACCEPTED.value,
            None,
        )
        return quotation

    @classmethod
    async def reject(
        cls,
        session: AsyncSession,
        quotation: Quotation,
        user_id: uuid.UUID,
        reason: Optional[str],
    ) -> Quotation:
        await expire_locked(session, quotation, user_id)
        assert_status(quotation, QuotationStatus.SENT, "reject")
        previous = quotation.status.value
        quotation.status = QuotationStatus.REJECTED
        quotation.rejection_reason = reason
        quotation.updated_at = now()
        await log_event(
            session,
            quotation,
            user_id,
            QuotationEventType.QUOTATION_REJECTED,
            previous,
            QuotationStatus.REJECTED.value,
            {"reason": (reason or "")[:200]},
        )
        return quotation

    @classmethod
    async def convert_to_invoice(
        cls,
        session: AsyncSession,
        quotation: Quotation,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Tuple[Invoice, bool]:
        """Return (invoice, created). created=False means idempotent 200."""
        await expire_locked(session, quotation, user_id)
        if quotation.status == QuotationStatus.CONVERTED:
            invoice = await existing_converted_invoice(session, quotation, workspace_id)
            return invoice, False
        if quotation.status != CONVERTIBLE:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot convert quotation with status '{quotation.status.value}'. "
                "Only ACCEPTED quotations can be converted.",
            )
        today = utc_today()
        invoice = await InvoiceService.create_invoice(
            session=session,
            workspace_id=workspace_id,
            client_id=quotation.client_id,
            user_id=user_id,
            issue_date=today,
            supply_date=today,
            due_date=today + timedelta(days=INVOICE_DUE_DAYS),
            currency=AED,
            notes=converted_notes(quotation),
            items=await frozen_invoice_items(session, workspace_id, quotation.items),
            quotation_id=quotation.id,
        )
        previous = quotation.status.value
        quotation.status = QuotationStatus.CONVERTED
        quotation.updated_at = now()
        await log_event(
            session,
            quotation,
            user_id,
            QuotationEventType.QUOTATION_CONVERTED,
            previous,
            QuotationStatus.CONVERTED.value,
            {"invoice_id": str(invoice.id)},
        )
        return invoice, True
