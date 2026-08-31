"""Delivery-note helpers: remaining qty, parent load, events, isolation."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.customer_purchase_order import (
    CustomerPurchaseOrder,
    CustomerPurchaseOrderStatus,
)
from app.models.customer_purchase_order_item import CustomerPurchaseOrderItem
from app.models.delivery_note import DeliveryNote, DeliveryNoteStatus
from app.models.delivery_note_event import DeliveryNoteEvent, DeliveryNoteEventType
from app.models.delivery_note_item import DeliveryNoteItem
from app.models.invoice import Invoice, InvoiceStatus
from app.models.product import Product
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error
from app.services.inventory_ledger import qty_dec, resolve_header_bin
from app.services.quotation_support import product_still_catalog

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
EDITABLE = DeliveryNoteStatus.DRAFT
LPO_SHIPPABLE = (
    CustomerPurchaseOrderStatus.RECEIVED,
    CustomerPurchaseOrderStatus.PARTIAL,
    CustomerPurchaseOrderStatus.INVOICED,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def assert_draft(dn: DeliveryNote) -> None:
    if dn.status != EDITABLE:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot modify delivery note with status '{dn.status.value}'. "
            "Only DRAFT delivery notes can be edited or deleted.",
        )


async def log_event(
    session: AsyncSession,
    dn: DeliveryNote,
    user_id: uuid.UUID,
    event_type: DeliveryNoteEventType,
    previous_status: Optional[str],
    new_status: str,
    metadata: Optional[dict],
) -> None:
    session.add(
        DeliveryNoteEvent(
            delivery_note_id=dn.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user_id,
            metadata_log=metadata or {},
            timestamp=now(),
        )
    )
    logger.info(
        "dn_event",
        extra={
            "dn_id": str(dn.id),
            "event_type": event_type.value,
            "status": new_status,
        },
    )


async def load_lpo(
    session: AsyncSession,
    lpo_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> CustomerPurchaseOrder:
    query = (
        select(CustomerPurchaseOrder)
        .options(selectinload(CustomerPurchaseOrder.items))
        .where(CustomerPurchaseOrder.id == lpo_id)
        .where(CustomerPurchaseOrder.workspace_id == workspace_id)
        .where(CustomerPurchaseOrder.deleted_at.is_(None))
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    lpo = result.scalar_one_or_none()
    if lpo is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "LPO not found")
    if lpo.status not in LPO_SHIPPABLE:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot create a delivery note for LPO status '{lpo.status.value}'.",
        )
    return lpo


async def load_invoice(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Invoice:
    query = (
        select(Invoice)
        .options(selectinload(Invoice.items))
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
    if invoice.status == InvoiceStatus.CANCELLED:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            "Cannot create a delivery note for a cancelled invoice.",
        )
    return invoice


async def confirmed_cpo_qty_map(
    session: AsyncSession, lpo_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(
            DeliveryNoteItem.customer_purchase_order_item_id,
            func.coalesce(func.sum(DeliveryNoteItem.quantity), ZERO),
        )
        .join(DeliveryNote, DeliveryNote.id == DeliveryNoteItem.delivery_note_id)
        .where(
            DeliveryNote.customer_purchase_order_id == lpo_id,
            DeliveryNote.status == DeliveryNoteStatus.CONFIRMED,
            DeliveryNote.deleted_at.is_(None),
            DeliveryNoteItem.customer_purchase_order_item_id.is_not(None),
        )
        .group_by(DeliveryNoteItem.customer_purchase_order_item_id)
    )
    return {item_id: qty_dec(qty) for item_id, qty in result.all() if item_id}


async def confirmed_invoice_qty_map(
    session: AsyncSession, invoice_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(
            DeliveryNoteItem.invoice_item_id,
            func.coalesce(func.sum(DeliveryNoteItem.quantity), ZERO),
        )
        .join(DeliveryNote, DeliveryNote.id == DeliveryNoteItem.delivery_note_id)
        .where(
            DeliveryNote.invoice_id == invoice_id,
            DeliveryNote.status == DeliveryNoteStatus.CONFIRMED,
            DeliveryNote.deleted_at.is_(None),
            DeliveryNoteItem.invoice_item_id.is_not(None),
        )
        .group_by(DeliveryNoteItem.invoice_item_id)
    )
    return {item_id: qty_dec(qty) for item_id, qty in result.all() if item_id}


def remaining_of(ordered: Decimal, delivered: Decimal) -> Decimal:
    leftover = qty_dec(ordered) - qty_dec(delivered)
    return leftover if leftover > ZERO else ZERO


async def assert_catalog_product(
    session: AsyncSession,
    product_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    on_confirm: bool = False,
) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.workspace_id != workspace_id:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Product not found")
    if product.deleted_at is not None or not product.is_active:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            (
                "Product is inactive"
                if not on_confirm
                else "Product is inactive and cannot be issued"
            ),
            "product_id",
        )
    if not product_still_catalog(product, workspace_id):
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Product not found")
    return product


def snapshot_from_parent(parent_line) -> dict:
    return {
        "product_id": parent_line.product_id,
        "uom_id": parent_line.uom_id,
        "sku_snapshot": parent_line.sku_snapshot,
        "description": parent_line.description,
    }


async def build_item(
    session: AsyncSession,
    dn: DeliveryNote,
    workspace_id: uuid.UUID,
    parent_line,
    quantity: Decimal,
    bin_id: uuid.UUID,
    *,
    from_lpo: bool,
) -> DeliveryNoteItem:
    qty = qty_dec(quantity)
    if qty <= ZERO:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "quantity must be greater than zero",
            "quantity",
        )
    if parent_line.product_id is not None:
        await assert_catalog_product(session, parent_line.product_id, workspace_id)
    snap = snapshot_from_parent(parent_line)
    if not snap["description"]:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "description is required",
            "description",
        )
    item = DeliveryNoteItem(
        delivery_note_id=dn.id,
        customer_purchase_order_item_id=parent_line.id if from_lpo else None,
        invoice_item_id=None if from_lpo else parent_line.id,
        quantity=qty,
        bin_id=bin_id,
        created_at=now(),
        updated_at=now(),
        **snap,
    )
    session.add(item)
    return item


async def replace_items(session: AsyncSession, dn: DeliveryNote) -> None:
    await session.execute(
        delete(DeliveryNoteItem).where(DeliveryNoteItem.delivery_note_id == dn.id)
    )
    await session.flush()


async def load_client(
    session: AsyncSession, client_id: uuid.UUID, workspace_id: uuid.UUID
) -> Client:
    result = await session.execute(
        select(Client).where(
            Client.id == client_id,
            Client.workspace_id == workspace_id,
            Client.deleted_at.is_(None),
        )
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found")
    return client


async def resolve_bin_id(
    session: AsyncSession,
    warehouse_id: uuid.UUID,
    workspace_id: uuid.UUID,
    bin_id: Optional[uuid.UUID],
) -> uuid.UUID:
    resolved = await resolve_header_bin(session, warehouse_id, workspace_id, bin_id)
    return resolved.id


async def recalc_delivered(session: AsyncSession, lpo_id: uuid.UUID) -> None:
    result = await session.execute(
        select(CustomerPurchaseOrderItem).where(
            CustomerPurchaseOrderItem.customer_purchase_order_id == lpo_id
        )
    )
    items = list(result.scalars().all())
    qty_map = await confirmed_cpo_qty_map(session, lpo_id)
    for item in items:
        item.quantity_delivered = qty_map.get(item.id, ZERO)
        item.updated_at = now()


def serialize(dn: DeliveryNote):
    from app.schemas.delivery_notes import (
        DeliveryNoteItemResponse,
        DeliveryNoteResponse,
    )

    items = [DeliveryNoteItemResponse.model_validate(item) for item in (dn.items or [])]
    payload = DeliveryNoteResponse.model_validate(dn)
    return payload.model_copy(update={"items": items})


def serialize_list_item(dn: DeliveryNote):
    from app.schemas.delivery_notes import DeliveryNoteListItem

    return DeliveryNoteListItem.model_validate(dn)


def lines_for_remaining(
    parent_items: Sequence,
    qty_map: Dict[uuid.UUID, Decimal],
) -> List[tuple]:
    rows = []
    for item in parent_items:
        leftover = remaining_of(item.quantity, qty_map.get(item.id, ZERO))
        if leftover > ZERO:
            rows.append((item, leftover))
    return rows


def resolve_slices(
    parent,
    from_lpo: bool,
    requested: Optional[List[dict]],
    qty_map: Dict[uuid.UUID, Decimal],
) -> List[tuple]:
    items = list(parent.items or [])
    by_id = {item.id: item for item in items}
    if not requested:
        return [
            (item, leftover, None)
            for item, leftover in lines_for_remaining(items, qty_map)
        ]
    leftover = {
        item.id: remaining_of(item.quantity, qty_map.get(item.id, ZERO))
        for item in items
    }
    key = "customer_purchase_order_item_id" if from_lpo else "invoice_item_id"
    slices: List[tuple] = []
    for row in requested:
        item_id = row.get(key)
        if item_id is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Item parent must match the delivery-note header",
            )
        item = by_id.get(item_id)
        if item is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Parent line not found",
            )
        qty = qty_dec(row["quantity"])
        remaining = leftover[item_id]
        if qty > remaining:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot over-deliver a parent line",
                "quantity",
            )
        leftover[item_id] = remaining - qty
        slices.append((item, qty, row.get("bin_id")))
    return slices
