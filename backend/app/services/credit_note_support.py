"""Credit-note helpers: remaining qty/header, frozen lines, snapshots, events."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_note import CreditNote, CreditNoteStatus
from app.models.credit_note_event import CreditNoteEvent, CreditNoteEventType
from app.models.credit_note_item import CreditNoteItem
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.tax_debit_note import TaxDebitNote, TaxDebitNoteStatus
from app.models.tax_debit_note import TaxDebitNoteItem
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error
from app.services.invoice_service import (
    _freeze_snapshots,
    _load_send_context,
    _resolve_kind,
)
from app.services.line_money import apply_line_money, money

ZERO = Decimal("0.00")
ALLOWED_PARENT = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)
MONEY_FIELDS = ("unit_price", "discount_amount")
RATE_FIELDS = ("tax_rate", "discount_percent")


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def assert_draft(cn: CreditNote) -> None:
    if cn.status != CreditNoteStatus.DRAFT:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot modify credit note with status '{cn.status.value}'. "
            "Only DRAFT credit notes can be edited or deleted.",
        )


async def log_event(
    session: AsyncSession,
    cn: CreditNote,
    user_id: uuid.UUID,
    event_type: CreditNoteEventType,
    previous_status: Optional[str],
    new_status: str,
    metadata: Optional[dict],
) -> None:
    session.add(
        CreditNoteEvent(
            credit_note_id=cn.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user_id,
            metadata_log=metadata or {},
            timestamp=now(),
        )
    )


async def load_parent_invoice(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Invoice:
    query = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found")
    if invoice.status not in ALLOWED_PARENT:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            "Credit notes require a SENT, PARTIALLY_PAID, PAID, or OVERDUE invoice.",
            "invoice_id",
        )
    return invoice


async def load_invoice_items(
    session: AsyncSession, invoice_id: uuid.UUID
) -> Dict[uuid.UUID, InvoiceItem]:
    result = await session.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)
    )
    return {item.id: item for item in result.scalars().all()}


async def issued_qty_map(
    session: AsyncSession, invoice_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(CreditNoteItem.invoice_item_id, func.sum(CreditNoteItem.quantity))
        .join(CreditNote)
        .where(CreditNote.invoice_id == invoice_id)
        .where(CreditNote.status == CreditNoteStatus.ISSUED)
        .where(CreditNote.deleted_at.is_(None))
        .group_by(CreditNoteItem.invoice_item_id)
    )
    return {row[0]: dec(row[1] or 0) for row in result.all()}


async def tdn_issued_qty_map(
    session: AsyncSession, invoice_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(TaxDebitNoteItem.invoice_item_id, func.sum(TaxDebitNoteItem.quantity))
        .join(TaxDebitNote)
        .where(TaxDebitNote.invoice_id == invoice_id)
        .where(TaxDebitNote.status == TaxDebitNoteStatus.ISSUED)
        .where(TaxDebitNote.deleted_at.is_(None))
        .group_by(TaxDebitNoteItem.invoice_item_id)
    )
    return {row[0]: dec(row[1] or 0) for row in result.all()}


async def issued_header_total(session: AsyncSession, invoice_id: uuid.UUID) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(CreditNote.total_amount), 0))
        .where(CreditNote.invoice_id == invoice_id)
        .where(CreditNote.status == CreditNoteStatus.ISSUED)
        .where(CreditNote.deleted_at.is_(None))
    )
    return money(dec(result.scalar() or 0))


async def tdn_issued_header_total(
    session: AsyncSession, invoice_id: uuid.UUID
) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(TaxDebitNote.total_amount), 0))
        .where(TaxDebitNote.invoice_id == invoice_id)
        .where(TaxDebitNote.status == TaxDebitNoteStatus.ISSUED)
        .where(TaxDebitNote.deleted_at.is_(None))
    )
    return money(dec(result.scalar() or 0))


def remaining_qty(
    item: InvoiceItem,
    cn_qty_map: Dict[uuid.UUID, Decimal],
    tdn_qty_map: Dict[uuid.UUID, Decimal],
) -> Decimal:
    used = cn_qty_map.get(item.id, ZERO)
    added = tdn_qty_map.get(item.id, ZERO)
    return money(dec(item.quantity) + added - used)


def assert_header_remaining(cn_total: Decimal, remaining: Decimal) -> None:
    if cn_total > remaining:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.CREDIT_EXCEEDS_REMAINING,
            "Credit note total exceeds remaining invoice amount",
            "total_amount",
        )


def assert_qty_remaining(quantity: Decimal, remaining: Decimal) -> None:
    if quantity > remaining:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "Quantity exceeds remaining invoice line quantity",
            "quantity",
        )


def assert_frozen(body: dict, item: InvoiceItem) -> None:
    for field in MONEY_FIELDS:
        if body.get(field) is None:
            continue
        if money(dec(body[field])) != money(dec(getattr(item, field))):
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                f"{field} must match the invoice line",
                field,
            )
    for field in RATE_FIELDS:
        if body.get(field) is None:
            continue
        if dec(body[field]) != dec(getattr(item, field)):
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                f"{field} must match the invoice line",
                field,
            )


def build_item(
    cn_id: uuid.UUID, invoice_item: InvoiceItem, quantity: Decimal
) -> CreditNoteItem:
    item = CreditNoteItem(
        credit_note_id=cn_id,
        invoice_item_id=invoice_item.id,
        product_id=invoice_item.product_id,
        uom_id=invoice_item.uom_id,
        sku_snapshot=invoice_item.sku_snapshot,
        description=invoice_item.description,
        quantity=quantity,
        unit_price=invoice_item.unit_price,
        tax_rate=invoice_item.tax_rate,
        discount_percent=invoice_item.discount_percent,
        discount_amount=invoice_item.discount_amount,
        line_net=ZERO,
        tax_amount=ZERO,
        total_price=ZERO,
        created_at=now(),
        updated_at=now(),
    )
    apply_line_money(item)
    return item


def apply_totals(cn: CreditNote, items: Sequence[CreditNoteItem]) -> None:
    subtotal = sum((item.line_net for item in items), ZERO)
    tax_amount = sum((item.tax_amount for item in items), ZERO)
    cn.subtotal = money(subtotal)
    cn.tax_amount = money(tax_amount)
    cn.total_amount = money(subtotal + tax_amount)
    cn.updated_at = now()


async def replace_items(session: AsyncSession, cn: CreditNote) -> None:
    await session.execute(
        delete(CreditNoteItem).where(CreditNoteItem.credit_note_id == cn.id)
    )
    await session.flush()


async def add_lines(
    session: AsyncSession,
    cn: CreditNote,
    invoice: Invoice,
    items: List[dict],
) -> List[CreditNoteItem]:
    if not items:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "At least one line is required",
        )
    invoice_items = await load_invoice_items(session, invoice.id)
    qty_map = await issued_qty_map(session, invoice.id)
    tdn_qty_map = await tdn_issued_qty_map(session, invoice.id)
    seen: set[uuid.UUID] = set()
    built: List[CreditNoteItem] = []
    for body in items:
        inv_item = _resolve_invoice_item(body, invoice_items)
        if inv_item.id in seen:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Duplicate invoice_item_id on credit note",
                "invoice_item_id",
            )
        seen.add(inv_item.id)
        assert_frozen(body, inv_item)
        quantity = dec(body["quantity"])
        assert_qty_remaining(quantity, remaining_qty(inv_item, qty_map, tdn_qty_map))
        built.append(build_item(cn.id, inv_item, quantity))
    apply_totals(cn, built)
    tdn_total = await tdn_issued_header_total(session, invoice.id)
    remaining = money(
        dec(invoice.total_amount)
        + tdn_total
        - await issued_header_total(session, invoice.id)
    )
    assert_header_remaining(cn.total_amount, remaining)
    for item in built:
        session.add(item)
    await session.flush()
    return built


async def assert_cn_remaining(
    session: AsyncSession, cn: CreditNote, invoice: Invoice
) -> None:
    items = list(cn.items or [])
    if not items:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "At least one line is required",
        )
    tdn_total = await tdn_issued_header_total(session, invoice.id)
    remaining = money(
        dec(invoice.total_amount)
        + tdn_total
        - await issued_header_total(session, invoice.id)
    )
    assert_header_remaining(cn.total_amount, remaining)
    invoice_items = await load_invoice_items(session, invoice.id)
    qty_map = await issued_qty_map(session, invoice.id)
    tdn_qty_map = await tdn_issued_qty_map(session, invoice.id)
    seen: set[uuid.UUID] = set()
    for item in items:
        inv_item = invoice_items.get(item.invoice_item_id)
        if inv_item is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "invoice_item_id does not belong to the parent invoice",
                "invoice_item_id",
            )
        if item.invoice_item_id in seen:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Duplicate invoice_item_id on credit note",
                "invoice_item_id",
            )
        seen.add(item.invoice_item_id)
        assert_qty_remaining(
            dec(item.quantity), remaining_qty(inv_item, qty_map, tdn_qty_map)
        )


def _resolve_invoice_item(
    body: dict, invoice_items: Dict[uuid.UUID, InvoiceItem]
) -> InvoiceItem:
    item_id = body.get("invoice_item_id")
    if item_id is None:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "invoice_item_id is required",
            "invoice_item_id",
        )
    inv_item = invoice_items.get(item_id)
    if inv_item is None:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "invoice_item_id does not belong to the parent invoice",
            "invoice_item_id",
        )
    return inv_item


async def freeze_snapshots(
    session: AsyncSession, cn: CreditNote, invoice: Invoice
) -> None:
    cn.original_invoice_number = invoice.invoice_number
    cn.original_issue_date = invoice.issue_date
    if invoice.seller_name_snapshot:
        cn.invoice_kind = invoice.invoice_kind
        cn.seller_trn_snapshot = invoice.seller_trn_snapshot
        cn.seller_name_snapshot = invoice.seller_name_snapshot
        cn.seller_address_snapshot = invoice.seller_address_snapshot
        cn.buyer_trn_snapshot = invoice.buyer_trn_snapshot
        cn.buyer_name_snapshot = invoice.buyer_name_snapshot
        cn.buyer_address_snapshot = invoice.buyer_address_snapshot
        return
    workspace, client, _items = await _load_send_context(session, invoice)
    kind = invoice.invoice_kind or _resolve_kind(client, invoice.total_amount)
    _freeze_snapshots(cn, workspace, client, kind)


async def lock_client(
    session: AsyncSession, client_id: uuid.UUID, workspace_id: uuid.UUID
) -> Client:
    result = await session.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
        .with_for_update()
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found")
    return client


def credit_increment(paid: Decimal, net_before: Decimal, cn_total: Decimal) -> Decimal:
    unpaid_before = money(max(ZERO, net_before - paid))
    return money(max(ZERO, cn_total - unpaid_before))


def serialize(cn: CreditNote):
    from app.schemas.credit_notes import CreditNoteResponse

    return CreditNoteResponse.model_validate(cn)


def serialize_list_item(cn: CreditNote):
    from app.schemas.credit_notes import CreditNoteListItem

    return CreditNoteListItem.model_validate(cn)


async def load_invoice_with_payments(
    session: AsyncSession, invoice_id: uuid.UUID, workspace_id: uuid.UUID
) -> Invoice:
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
    )
    return result.scalar_one()
