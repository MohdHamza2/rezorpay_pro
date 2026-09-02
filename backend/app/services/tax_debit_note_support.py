"""Tax Debit Note helpers: frozen lines, snapshots, events."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Sequence

from fastapi import status
from sqlalchemy import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice import Invoice
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
from app.services.line_money import money

ZERO = Decimal("0.00")
MONEY_FIELDS = ("unit_price", "discount_amount")
RATE_FIELDS = ("tax_rate", "discount_percent")


def now() -> datetime:
    return datetime.utcnow()


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def assert_draft(tdn: TaxDebitNote) -> None:
    if tdn.status != TaxDebitNoteStatus.DRAFT:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot modify tax debit note with status '{tdn.status.value}'. "
            "Only DRAFT debit notes can be edited or deleted.",
        )


def assert_frozen(body: dict, item: InvoiceItem) -> None:
    """Ensure money fields match invoice exactly."""
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
    tdn_id: uuid.UUID, invoice_item: InvoiceItem, quantity: Decimal
) -> TaxDebitNoteItem:
    item = TaxDebitNoteItem(
        tax_debit_note_id=tdn_id,
        invoice_item_id=invoice_item.id,
        product_id=invoice_item.product_id,
        internal_sku=invoice_item.sku_snapshot,
        description=invoice_item.description,
        quantity=quantity,
        unit_price=invoice_item.unit_price,
        tax_rate=invoice_item.tax_rate,
        discount_percent=invoice_item.discount_percent,
        tax_amount=ZERO,
        total_price=ZERO,
    )
    # Apply money logic (same as credit notes & invoices)
    item.tax_amount = money(
        quantity * item.unit_price * (item.tax_rate / Decimal("100"))
    )
    item.total_price = money((quantity * item.unit_price) + item.tax_amount)
    return item


def apply_totals(tdn: TaxDebitNote, items: Sequence[TaxDebitNoteItem]) -> None:
    subtotal = sum((money(item.quantity * item.unit_price) for item in items), ZERO)
    tax_amount = sum((item.tax_amount for item in items), ZERO)
    tdn.subtotal = money(subtotal)
    tdn.tax_amount = money(tax_amount)
    tdn.total_amount = money(subtotal + tax_amount)
    tdn.updated_at = now()


async def replace_items(session: AsyncSession, tdn: TaxDebitNote) -> None:
    await session.execute(
        delete(TaxDebitNoteItem).where(TaxDebitNoteItem.tax_debit_note_id == tdn.id)
    )
    await session.flush()


async def add_lines(
    session: AsyncSession,
    tdn: TaxDebitNote,
    invoice_items: Dict[uuid.UUID, InvoiceItem],
    items: List[dict],
) -> List[TaxDebitNoteItem]:
    if not items:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "At least one line is required",
        )
    seen: set[uuid.UUID] = set()
    built: List[TaxDebitNoteItem] = []
    for body in items:
        item_id = body.get("invoice_item_id")
        if item_id is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "invoice_item_id is required",
                "invoice_item_id",
            )
        inv_item = invoice_items.get(uuid.UUID(str(item_id)))
        if inv_item is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "invoice_item_id does not belong to the parent invoice",
                "invoice_item_id",
            )
        if inv_item.id in seen:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Duplicate invoice_item_id on tax debit note",
                "invoice_item_id",
            )
        seen.add(inv_item.id)
        assert_frozen(body, inv_item)
        quantity = dec(body["quantity"])
        if quantity <= 0:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Quantity must be greater than zero",
                "quantity",
            )
        built.append(build_item(tdn.id, inv_item, quantity))

    apply_totals(tdn, built)
    for item in built:
        session.add(item)
    await session.flush()
    return built


async def freeze_snapshots(
    session: AsyncSession, tdn: TaxDebitNote, invoice: Invoice
) -> None:
    tdn.original_invoice_number = invoice.invoice_number
    tdn.original_issue_date = invoice.issue_date
    if invoice.seller_name_snapshot:
        tdn.invoice_kind = invoice.invoice_kind
        tdn.seller_trn_snapshot = invoice.seller_trn_snapshot
        tdn.seller_name_snapshot = invoice.seller_name_snapshot
        tdn.seller_address_snapshot = invoice.seller_address_snapshot
        tdn.buyer_trn_snapshot = invoice.buyer_trn_snapshot
        tdn.buyer_name_snapshot = invoice.buyer_name_snapshot
        tdn.buyer_address_snapshot = invoice.buyer_address_snapshot
        return
    workspace, client, _items = await _load_send_context(session, invoice)
    kind = invoice.invoice_kind or _resolve_kind(client, invoice.total_amount)
    _freeze_snapshots(tdn, workspace, client, kind)


def serialize(tdn: TaxDebitNote):
    from app.schemas.tax_debit_notes import TaxDebitNoteResponse

    return TaxDebitNoteResponse.model_validate(tdn)


def serialize_detail(tdn: TaxDebitNote):
    from app.schemas.tax_debit_notes import TaxDebitNoteDetailResponse

    return TaxDebitNoteDetailResponse.model_validate(tdn)
