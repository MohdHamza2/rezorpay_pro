"""Tax debit-note lifecycle: no caps, issue posts AR, reopens invoices."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice import Invoice
from app.models.invoice_event import InvoiceEventType
from app.models.tax_debit_note import (
    TaxDebitNote,
    TaxDebitNoteReason,
    TaxDebitNoteStatus,
)
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.services.audit_service import AuditService
from app.services.credit_control_service import CreditControlService
from app.models.credit_status_event import CreditEventReason
from app.services.credit_note_support import (
    tdn_issued_header_total,
    load_invoice_with_payments,
    load_parent_invoice,
    lock_client,
)
from app.services.tax_debit_note_number import TaxDebitNoteNumberService
from app.services.tax_debit_note_support import (
    ZERO,
    add_lines,
    assert_draft,
    freeze_snapshots,
    now,
    replace_items,
    serialize,
    serialize_detail,
)
from app.services.customer_po_support import raise_error
from app.services.invoice_service import InvoiceService
from app.services.line_money import money


def utc_today() -> date:
    return now().date()


class TaxDebitNoteService:
    """DRAFT CRUD plus ISSUED AR post."""

    serialize = staticmethod(serialize)
    serialize_detail = staticmethod(serialize_detail)

    @staticmethod
    async def get_visible(
        session: AsyncSession,
        tdn_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[TaxDebitNote]:
        query = (
            select(TaxDebitNote)
            .options(selectinload(TaxDebitNote.items))
            .where(TaxDebitNote.id == tdn_id)
            .where(TaxDebitNote.workspace_id == workspace_id)
            .where(TaxDebitNote.deleted_at.is_(None))
        )
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        invoice_id: uuid.UUID,
        reason: TaxDebitNoteReason,
        reason_notes: Optional[str] = None,
        issue_date: Optional[date] = None,
        items: Optional[List[dict]] = None,
    ) -> TaxDebitNote:
        number = await TaxDebitNoteNumberService.generate_debit_note_number(
            session, workspace_id
        )
        invoice = await load_parent_invoice(
            session, invoice_id, workspace_id, for_update=True
        )
        tdn = TaxDebitNote(
            workspace_id=workspace_id,
            client_id=invoice.client_id,
            invoice_id=invoice.id,
            debit_note_number=number,
            status=TaxDebitNoteStatus.DRAFT,
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
        session.add(tdn)
        await session.flush()

        # Load invoice items to pass to add_lines
        from app.services.credit_note_support import load_invoice_items

        inv_items = await load_invoice_items(session, invoice.id)

        await add_lines(session, tdn, inv_items, items or [])
        return tdn

    @classmethod
    async def update_draft(
        cls,
        session: AsyncSession,
        tdn: TaxDebitNote,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> TaxDebitNote:
        assert_draft(tdn)
        for field, value in patch.items():
            setattr(tdn, field, value)

        if items is not None:
            invoice = await load_parent_invoice(
                session, tdn.invoice_id, tdn.workspace_id, for_update=True
            )
            from app.services.credit_note_support import load_invoice_items

            inv_items = await load_invoice_items(session, invoice.id)

            await replace_items(session, tdn)
            await add_lines(session, tdn, inv_items, items)

        tdn.updated_at = now()
        return tdn

    @staticmethod
    async def soft_delete(tdn: TaxDebitNote) -> None:
        assert_draft(tdn)
        tdn.deleted_at = now()
        tdn.updated_at = now()

    @classmethod
    async def issue(
        cls,
        session: AsyncSession,
        tdn: TaxDebitNote,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> TaxDebitNote:
        if tdn.status == TaxDebitNoteStatus.ISSUED:
            return tdn
        if tdn.status != TaxDebitNoteStatus.DRAFT:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot issue debit note with status '{tdn.status.value}'.",
            )
        invoice = await load_parent_invoice(
            session, tdn.invoice_id, workspace_id, for_update=True
        )

        if not getattr(tdn, "items", None):
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "At least one line is required to issue",
            )

        await freeze_snapshots(session, tdn, invoice)
        invoice = await load_invoice_with_payments(session, invoice.id, workspace_id)
        await cls._post_ar(session, tdn, invoice, user_id, workspace_id)
        return tdn

    @classmethod
    async def _post_ar(
        cls,
        session: AsyncSession,
        tdn: TaxDebitNote,
        invoice: Invoice,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        paid = invoice.amount_paid
        old_debited = invoice.amount_debited or ZERO
        old_credited = invoice.amount_credited or ZERO

        net_before = money(invoice.total_amount - old_credited + old_debited)

        def owing(net: Decimal) -> Decimal:
            return money(max(ZERO, -(net - paid)))

        unpark = money(
            max(ZERO, owing(net_before) - owing(net_before + tdn.total_amount))
        )

        tdn.status = TaxDebitNoteStatus.ISSUED
        tdn.updated_at = now()
        await session.flush()

        invoice.amount_debited = await tdn_issued_header_total(session, invoice.id)

        if unpark > 0:
            client = await lock_client(session, invoice.client_id, workspace_id)
            client.credit_balance = money(
                max(ZERO, (client.credit_balance or ZERO) - unpark)
            )
            client.updated_at = now()

        await cls._sync_invoice_status(session, invoice, user_id, tdn)

        workspace = await session.get(Workspace, workspace_id)
        if workspace is not None:
            # Re-evaluate hold status based on new balance_due
            client = await lock_client(session, invoice.client_id, workspace_id)
            await CreditControlService.evaluate(
                session, client, workspace, user_id, CreditEventReason.EVALUATE
            )

    @staticmethod
    async def _sync_invoice_status(
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        tdn: TaxDebitNote,
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
                reason="tax_debit_note_issued",
            )
        await AuditService.log_event(
            session=session,
            invoice_id=invoice.id,
            event_type=InvoiceEventType.DEBIT_NOTE_ISSUED,
            user_id=user_id,
            previous_status=old_status.value,
            new_status=invoice.status.value,
            metadata={
                "tax_debit_note_id": str(tdn.id),
                "debit_note_number": tdn.debit_note_number,
                "total": str(tdn.total_amount),
            },
        )

    @staticmethod
    def list_filters(
        workspace_id: uuid.UUID,
        status_filter: Optional[TaxDebitNoteStatus],
        client_id: Optional[uuid.UUID],
        invoice_id: Optional[uuid.UUID],
        search: Optional[str],
    ):
        query = (
            select(TaxDebitNote)
            .where(TaxDebitNote.workspace_id == workspace_id)
            .where(TaxDebitNote.deleted_at.is_(None))
        )
        if status_filter is not None:
            query = query.where(TaxDebitNote.status == status_filter)
        if client_id is not None:
            query = query.where(TaxDebitNote.client_id == client_id)
        if invoice_id is not None:
            query = query.where(TaxDebitNote.invoice_id == invoice_id)
        if search:
            query = query.where(TaxDebitNote.debit_note_number.ilike(f"%{search}%"))
        return query
