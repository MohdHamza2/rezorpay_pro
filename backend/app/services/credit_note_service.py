"""Tax credit-note lifecycle: remaining caps, issue posts AR, no /apply."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.credit_note import CreditNote, CreditNoteReason, CreditNoteStatus
from app.models.credit_note_event import CreditNoteEventType
from app.models.credit_status_event import CreditEventReason
from app.models.invoice import Invoice
from app.models.invoice_event import InvoiceEventType
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.services.audit_service import AuditService
from app.services.credit_control_service import CreditControlService
from app.services.credit_note_number import CreditNoteNumberService
from app.services.credit_note_support import (
    ZERO,
    add_lines,
    assert_cn_remaining,
    assert_draft,
    credit_increment,
    freeze_snapshots,
    issued_header_total,
    load_invoice_with_payments,
    load_parent_invoice,
    lock_client,
    log_event,
    now,
    replace_items,
    serialize,
    serialize_list_item,
    utc_today,
)
from app.services.customer_po_support import raise_error
from app.services.invoice_service import InvoiceService
from app.services.line_money import money


class CreditNoteService:
    """DRAFT CRUD plus ISSUED AR post. Never CREDIT_HOLD on issue."""

    serialize = staticmethod(serialize)
    serialize_list_item = staticmethod(serialize_list_item)

    @staticmethod
    async def get_visible(
        session: AsyncSession,
        cn_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[CreditNote]:
        query = (
            select(CreditNote)
            .options(selectinload(CreditNote.items))
            .where(CreditNote.id == cn_id)
            .where(CreditNote.workspace_id == workspace_id)
            .where(CreditNote.deleted_at.is_(None))
        )
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def wrapped(cls, session: AsyncSession, cn: CreditNote):
        loaded = await cls.get_visible(session, cn.id, cn.workspace_id)
        return serialize(loaded or cn)

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        invoice_id: uuid.UUID,
        reason: CreditNoteReason,
        reason_notes: Optional[str] = None,
        issue_date: Optional[date] = None,
        items: Optional[List[dict]] = None,
    ) -> CreditNote:
        number = await CreditNoteNumberService.generate_credit_note_number(
            session, workspace_id
        )
        invoice = await load_parent_invoice(
            session, invoice_id, workspace_id, for_update=True
        )
        cn = CreditNote(
            workspace_id=workspace_id,
            client_id=invoice.client_id,
            invoice_id=invoice.id,
            credit_note_number=number,
            status=CreditNoteStatus.DRAFT,
            currency=invoice.currency,
            issue_date=issue_date or utc_today(),
            reason=reason,
            reason_notes=reason_notes,
            subtotal=ZERO,
            tax_amount=ZERO,
            total_amount=ZERO,
            created_at=now(),
            updated_at=now(),
        )
        session.add(cn)
        await session.flush()
        built = await add_lines(session, cn, invoice, items or [])
        await log_event(
            session,
            cn,
            user_id,
            CreditNoteEventType.CN_CREATED,
            None,
            CreditNoteStatus.DRAFT.value,
            {"items_count": len(built)},
        )
        return cn

    @classmethod
    async def update_draft(
        cls,
        session: AsyncSession,
        cn: CreditNote,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> CreditNote:
        assert_draft(cn)
        for field, value in patch.items():
            setattr(cn, field, value)
        invoice = await load_parent_invoice(
            session, cn.invoice_id, cn.workspace_id, for_update=True
        )
        if items is not None:
            await replace_items(session, cn)
            await add_lines(session, cn, invoice, items)
        cn.updated_at = now()
        await log_event(
            session,
            cn,
            user_id,
            CreditNoteEventType.CN_UPDATED,
            CreditNoteStatus.DRAFT.value,
            CreditNoteStatus.DRAFT.value,
            {"changed": list(patch.keys()) + (["items"] if items is not None else [])},
        )
        return cn

    @staticmethod
    async def soft_delete(cn: CreditNote) -> None:
        assert_draft(cn)
        cn.deleted_at = now()
        cn.updated_at = now()

    @classmethod
    async def issue(
        cls,
        session: AsyncSession,
        cn: CreditNote,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> CreditNote:
        if cn.status == CreditNoteStatus.ISSUED:
            return cn
        if cn.status != CreditNoteStatus.DRAFT:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot issue credit note with status '{cn.status.value}'.",
            )
        invoice = await load_parent_invoice(
            session, cn.invoice_id, workspace_id, for_update=True
        )
        await assert_cn_remaining(session, cn, invoice)
        await freeze_snapshots(session, cn, invoice)
        invoice = await load_invoice_with_payments(session, invoice.id, workspace_id)
        await cls._post_ar(session, cn, invoice, user_id, workspace_id)
        return cn

    @classmethod
    async def _post_ar(
        cls,
        session: AsyncSession,
        cn: CreditNote,
        invoice: Invoice,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        paid = invoice.amount_paid
        old_credited = invoice.amount_credited or ZERO
        net_before = money(invoice.total_amount - old_credited)
        increment = credit_increment(paid, net_before, cn.total_amount)
        previous = cn.status.value
        cn.status = CreditNoteStatus.ISSUED
        cn.updated_at = now()
        await session.flush()
        invoice.amount_credited = await issued_header_total(session, invoice.id)
        client = await lock_client(session, invoice.client_id, workspace_id)
        client.credit_balance = money((client.credit_balance or ZERO) + increment)
        client.updated_at = now()
        await cls._sync_invoice_status(session, invoice, user_id, cn)
        await log_event(
            session,
            cn,
            user_id,
            CreditNoteEventType.CN_ISSUED,
            previous,
            CreditNoteStatus.ISSUED.value,
            {"total": str(cn.total_amount)},
        )
        workspace = await session.get(Workspace, workspace_id)
        if workspace is not None:
            await CreditControlService.evaluate(
                session, client, workspace, user_id, CreditEventReason.EVALUATE
            )

    @staticmethod
    async def _sync_invoice_status(
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        cn: CreditNote,
    ) -> None:
        old_status = invoice.status
        new_status = InvoiceService.determine_status_from_balance(invoice)
        if new_status != old_status:
            invoice.status = new_status
            invoice.updated_at = now()
            await AuditService.log_status_changed(
                session=session,
                invoice_id=invoice.id,
                user_id=user_id,
                previous_status=old_status.value,
                new_status=new_status.value,
                reason="credit_note_issued",
            )
        await AuditService.log_event(
            session=session,
            invoice_id=invoice.id,
            event_type=InvoiceEventType.CREDIT_NOTE_ISSUED,
            user_id=user_id,
            previous_status=old_status.value,
            new_status=invoice.status.value,
            metadata={
                "credit_note_id": str(cn.id),
                "credit_note_number": cn.credit_note_number,
                "total": str(cn.total_amount),
            },
        )

    @staticmethod
    def list_filters(
        workspace_id: uuid.UUID,
        status_filter: Optional[CreditNoteStatus],
        client_id: Optional[uuid.UUID],
        invoice_id: Optional[uuid.UUID],
        search: Optional[str],
    ):
        query = (
            select(CreditNote)
            .where(CreditNote.workspace_id == workspace_id)
            .where(CreditNote.deleted_at.is_(None))
        )
        if status_filter is not None:
            query = query.where(CreditNote.status == status_filter)
        if client_id is not None:
            query = query.where(CreditNote.client_id == client_id)
        if invoice_id is not None:
            query = query.where(CreditNote.invoice_id == invoice_id)
        if search:
            query = query.where(CreditNote.credit_note_number.ilike(f"%{search}%"))
        return query
