"""Supplier Debit Note Service — Wave 23 (Phase 4).

A supplier debit note is a credit against an APPROVED/ PARTIALLY_PAID supplier
invoice's `balance_due`. It NEVER changes `amount_paid`/`paid_at` and never
flips an invoice to PAID.

State machine:
    DRAFT → ISSUED → APPLIED      (APPLIED is permanent)
    DRAFT / ISSUED → CANCELLED

Apply runs in one transaction (FOR UPDATE on invoice + note): supplier match,
payable-status gate, amount <= balance_due, then reduce balance_due only.
A second apply on an APPLIED note is a 409 CONFLICT (no double reduction).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import status
from sqlalchemy import func, select

from app.models.supplier import Supplier
from app.models.supplier_debit_note import (
    SupplierDebitNote,
    SupplierDebitNoteStatus,
)
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from app.models.supplier_invoice_event import SupplierInvoiceEventType
from app.services.customer_po_support import raise_error
from app.services.supplier_invoice_events import emit_event
from app.services.line_money import money
from app.services.supplier_debit_note_number import SupplierDebitNoteNumberService
from app.schemas.common import ErrorCode
from app.schemas.supplier_debit_notes import SupplierDebitNoteCreate

ZERO = Decimal("0.00")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SupplierDebitNoteService:
    # ------------------------------------------------------------------ reads
    @staticmethod
    async def get(
        session, workspace_id: uuid.UUID, note_id: uuid.UUID
    ) -> Optional[SupplierDebitNote]:
        result = await session.execute(
            select(SupplierDebitNote).where(
                SupplierDebitNote.id == note_id,
                SupplierDebitNote.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session,
        workspace_id: uuid.UUID,
        supplier_id: Optional[uuid.UUID] = None,
        status_value: Optional[SupplierDebitNoteStatus] = None,
        purchase_return_id: Optional[uuid.UUID] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SupplierDebitNote], int]:
        stmt = select(SupplierDebitNote).where(
            SupplierDebitNote.workspace_id == workspace_id
        )
        if supplier_id is not None:
            stmt = stmt.where(SupplierDebitNote.supplier_id == supplier_id)
        if status_value is not None:
            stmt = stmt.where(SupplierDebitNote.status == status_value)
        if purchase_return_id is not None:
            stmt = stmt.where(
                SupplierDebitNote.purchase_return_id == purchase_return_id
            )

        count_result = await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        total = count_result.scalar()

        rows = (
            (
                await session.execute(
                    stmt.order_by(SupplierDebitNote.created_at.desc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------- create/issue
    @classmethod
    async def create(
        cls,
        session,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: SupplierDebitNoteCreate,
    ) -> SupplierDebitNote:
        supplier = await session.get(Supplier, data.supplier_id)
        if not supplier or supplier.workspace_id != workspace_id:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Supplier not found"
            )

        dn_number = await SupplierDebitNoteNumberService.generate_debit_note_number(
            session, workspace_id
        )
        note = SupplierDebitNote(
            workspace_id=workspace_id,
            supplier_id=data.supplier_id,
            dn_number=dn_number,
            amount=money(data.amount),
            status=SupplierDebitNoteStatus.DRAFT,
            source_type="MANUAL",
            issue_date=data.issue_date,
            reason=data.reason,
            created_by=user_id,
        )
        session.add(note)
        await session.flush()
        return note

    @classmethod
    async def issue(
        cls, session, workspace_id: uuid.UUID, note_id: uuid.UUID
    ) -> SupplierDebitNote:
        note = await cls._require_note(session, workspace_id, note_id, for_update=True)
        if note.status != SupplierDebitNoteStatus.DRAFT:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                f"Cannot issue a debit note in status {note.status.value}",
            )
        note.status = SupplierDebitNoteStatus.ISSUED
        note.updated_at = _now()
        await session.flush()
        return note

    # ------------------------------------------------------------------ apply
    @classmethod
    async def apply(
        cls,
        session,
        workspace_id: uuid.UUID,
        note_id: uuid.UUID,
        supplier_invoice_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SupplierDebitNote:
        note = await cls._require_note(session, workspace_id, note_id, for_update=True)
        if note.status == SupplierDebitNoteStatus.APPLIED:
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.CONFLICT,
                "Debit note already applied",
            )
        if note.status != SupplierDebitNoteStatus.ISSUED:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                f"Debit note must be ISSUED to apply (current status {note.status.value})",
            )

        result = await session.execute(
            select(SupplierInvoice)
            .where(
                SupplierInvoice.id == supplier_invoice_id,
                SupplierInvoice.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found"
            )

        if invoice.supplier_id != note.supplier_id:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "Debit note supplier must match invoice supplier",
            )

        if invoice.status not in (
            SupplierInvoiceStatus.APPROVED,
            SupplierInvoiceStatus.PARTIALLY_PAID,
        ):
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "Debit note can only be applied to an APPROVED or PARTIALLY_PAID invoice",
            )

        if note.amount > invoice.balance_due:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.DEBIT_NOTE_EXCEEDS_BALANCE,
                (
                    f"Debit note amount ({note.amount}) exceeds invoice balance due "
                    f"({invoice.balance_due})"
                ),
            )

        invoice.balance_due = money(invoice.balance_due - note.amount)
        invoice.updated_at = _now()

        note.status = SupplierDebitNoteStatus.APPLIED
        note.applied_invoice_id = invoice.id
        note.applied_at = _now()
        note.updated_at = _now()
        await session.flush()
        await emit_event(
            session,
            invoice.id,
            workspace_id,
            SupplierInvoiceEventType.DEBIT_NOTE_APPLIED,
            user_id,
            previous_status=invoice.status.value,
            new_status=invoice.status.value,
            metadata={
                "debit_note_id": str(note.id),
                "amount": str(note.amount),
            },
        )
        return note

    # ---------------------------------------------------------------- cancel
    @classmethod
    async def cancel(
        cls, session, workspace_id: uuid.UUID, note_id: uuid.UUID
    ) -> SupplierDebitNote:
        note = await cls._require_note(session, workspace_id, note_id, for_update=True)
        if note.status == SupplierDebitNoteStatus.APPLIED:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "Applied debit notes cannot be cancelled",
            )
        if note.status == SupplierDebitNoteStatus.CANCELLED:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "Debit note is already cancelled",
            )
        note.status = SupplierDebitNoteStatus.CANCELLED
        note.cancelled_at = _now()
        note.updated_at = _now()
        await session.flush()
        return note

    # --------------------------------------------------------------- helpers
    @staticmethod
    async def _require_note(
        session, workspace_id: uuid.UUID, note_id: uuid.UUID, for_update: bool
    ) -> SupplierDebitNote:
        stmt = select(SupplierDebitNote).where(
            SupplierDebitNote.id == note_id,
            SupplierDebitNote.workspace_id == workspace_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        note = result.scalar_one_or_none()
        if note is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Supplier debit note not found",
            )
        return note


supplier_debit_note_service = SupplierDebitNoteService()
