"""Shared customer LPO helpers: money lines, remaining, events, isolation."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, NoReturn, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.customer_purchase_order import (
    CustomerPurchaseOrder,
    CustomerPurchaseOrderStatus,
)
from app.models.customer_purchase_order_event import (
    CustomerPurchaseOrderEvent,
    CustomerPurchaseOrderEventType,
)
from app.models.customer_purchase_order_item import CustomerPurchaseOrderItem
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.models.quotation_item import QuotationItem
from app.schemas.common import ErrorCode, ErrorDetail
from app.services.invoice_service import _resolve_line
from app.services.line_money import apply_line_money, money
from app.services.quotation_support import product_still_catalog

logger = logging.getLogger(__name__)

EDITABLE = CustomerPurchaseOrderStatus.DRAFT
ZERO = Decimal("0.00")


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def raise_error(
    http_status: int,
    code: str,
    message: str,
    field: Optional[str] = None,
) -> NoReturn:
    raise HTTPException(
        status_code=http_status,
        detail=ErrorDetail(code=code, message=message, field=field).model_dump(),
    )


def assert_aed(currency: str) -> None:
    if currency != "AED":
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "LPO currency must be AED",
            "currency",
        )


def assert_delivery(lpo_date: date, expected: Optional[date]) -> None:
    if expected is not None and expected < lpo_date:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "expected_delivery_date must be on or after lpo_date",
            "expected_delivery_date",
        )


def assert_draft(lpo: CustomerPurchaseOrder) -> None:
    if lpo.status != EDITABLE:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot modify LPO with status '{lpo.status.value}'. "
            "Only DRAFT LPOs can be edited or deleted.",
        )


def normalize_po_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def remaining_qty(item: CustomerPurchaseOrderItem) -> Decimal:
    return item.quantity - item.quantity_invoiced


def item_response_payload(item: CustomerPurchaseOrderItem) -> dict:
    return {
        "id": item.id,
        "customer_purchase_order_id": item.customer_purchase_order_id,
        "product_id": item.product_id,
        "uom_id": item.uom_id,
        "sku_snapshot": item.sku_snapshot,
        "description": item.description,
        "quantity": item.quantity,
        "quantity_invoiced": item.quantity_invoiced,
        "quantity_remaining": remaining_qty(item),
        "unit_price": item.unit_price,
        "tax_rate": item.tax_rate,
        "discount_percent": item.discount_percent,
        "discount_amount": item.discount_amount,
        "line_net": item.line_net,
        "tax_amount": item.tax_amount,
        "total_price": item.total_price,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def log_event(
    session: AsyncSession,
    lpo: CustomerPurchaseOrder,
    user_id: uuid.UUID,
    event_type: CustomerPurchaseOrderEventType,
    previous_status: Optional[str],
    new_status: str,
    metadata: Optional[dict],
) -> None:
    session.add(
        CustomerPurchaseOrderEvent(
            customer_purchase_order_id=lpo.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user_id,
            metadata_log=metadata or {},
            timestamp=now(),
        )
    )
    logger.info(
        "cpo_event",
        extra={
            "lpo_id": str(lpo.id),
            "event_type": event_type.value,
            "status": new_status,
        },
    )


async def add_items(
    session: AsyncSession,
    lpo: CustomerPurchaseOrder,
    workspace_id: uuid.UUID,
    default_tax_rate: Decimal,
    items: Sequence[dict],
) -> None:
    for item_data in items:
        resolved = await _resolve_line(
            session,
            workspace_id,
            default_tax_rate,
            item_data,
            line_owner="lpo",
        )
        item = CustomerPurchaseOrderItem(
            customer_purchase_order_id=lpo.id,
            **resolved,
            quantity_invoiced=ZERO,
            line_net=ZERO,
            tax_amount=ZERO,
            total_price=ZERO,
            created_at=now(),
            updated_at=now(),
        )
        apply_line_money(item)
        session.add(item)
    await session.flush()


def copy_quote_item(
    lpo_id: uuid.UUID, quote_item: QuotationItem
) -> CustomerPurchaseOrderItem:
    return CustomerPurchaseOrderItem(
        customer_purchase_order_id=lpo_id,
        product_id=quote_item.product_id,
        uom_id=quote_item.uom_id,
        sku_snapshot=quote_item.sku_snapshot,
        description=quote_item.description,
        quantity=quote_item.quantity,
        quantity_invoiced=ZERO,
        unit_price=quote_item.unit_price,
        tax_rate=quote_item.tax_rate,
        discount_percent=quote_item.discount_percent,
        discount_amount=quote_item.discount_amount,
        line_net=quote_item.line_net,
        tax_amount=quote_item.tax_amount,
        total_price=quote_item.total_price,
        created_at=now(),
        updated_at=now(),
    )


async def recalculate(session: AsyncSession, lpo: CustomerPurchaseOrder) -> None:
    result = await session.execute(
        select(CustomerPurchaseOrderItem).where(
            CustomerPurchaseOrderItem.customer_purchase_order_id == lpo.id
        )
    )
    items = result.scalars().all()
    for item in items:
        apply_line_money(item)
    subtotal = sum((item.line_net for item in items), Decimal("0"))
    tax_amount = sum((item.tax_amount for item in items), Decimal("0"))
    lpo.subtotal = subtotal
    lpo.tax_amount = tax_amount
    lpo.total_amount = money(subtotal + tax_amount)
    lpo.updated_at = now()


def countable_invoice_filter(lpo_id: uuid.UUID):
    return (
        Invoice.customer_purchase_order_id == lpo_id,
        Invoice.deleted_at.is_(None),
        Invoice.status != InvoiceStatus.CANCELLED,
    )


async def invoiced_qty_map(
    session: AsyncSession, lpo_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(
            InvoiceItem.customer_purchase_order_item_id,
            func.coalesce(func.sum(InvoiceItem.quantity), ZERO),
        )
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(
            *countable_invoice_filter(lpo_id),
            InvoiceItem.customer_purchase_order_item_id.is_not(None),
        )
        .group_by(InvoiceItem.customer_purchase_order_item_id)
    )
    return {item_id: Decimal(str(qty)) for item_id, qty in result.all() if item_id}


async def allocated_discount_map(
    session: AsyncSession, lpo_id: uuid.UUID
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(
            InvoiceItem.customer_purchase_order_item_id,
            func.coalesce(func.sum(InvoiceItem.discount_amount), ZERO),
        )
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(
            *countable_invoice_filter(lpo_id),
            InvoiceItem.customer_purchase_order_item_id.is_not(None),
        )
        .group_by(InvoiceItem.customer_purchase_order_item_id)
    )
    return {item_id: Decimal(str(amt)) for item_id, amt in result.all() if item_id}


async def has_countable_invoice(session: AsyncSession, lpo_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(func.count())
        .select_from(Invoice)
        .where(*countable_invoice_filter(lpo_id))
    )
    return (result.scalar() or 0) > 0


async def countable_invoices(
    session: AsyncSession, lpo_id: uuid.UUID, workspace_id: uuid.UUID
) -> List[Invoice]:
    result = await session.execute(
        select(Invoice)
        .where(
            *countable_invoice_filter(lpo_id),
            Invoice.workspace_id == workspace_id,
        )
        .order_by(Invoice.created_at.asc())
    )
    return list(result.scalars().all())


async def slice_invoice_items(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    lpo: CustomerPurchaseOrder,
    slices: Sequence[tuple[CustomerPurchaseOrderItem, Decimal]],
) -> List[dict]:
    allocated = await allocated_discount_map(session, lpo.id)
    invoiced = await invoiced_qty_map(session, lpo.id)
    payload: List[dict] = []
    for item, qty in slices:
        product_id = item.product_id
        description = item.description
        if product_id is not None:
            product = await session.get(Product, product_id)
            if not product_still_catalog(product, workspace_id):
                product_id = None
                if item.sku_snapshot:
                    description = f"{item.sku_snapshot} {description}".strip()
        already_qty = invoiced.get(item.id, ZERO)
        remaining = item.quantity - already_qty
        disc_pct, disc_amt = _slice_discount(
            item, qty, remaining, allocated.get(item.id, ZERO)
        )
        payload.append(
            {
                "description": description,
                "quantity": qty,
                "unit_price": item.unit_price,
                "tax_rate": item.tax_rate,
                "discount_percent": disc_pct,
                "discount_amount": disc_amt,
                "product_id": product_id,
                "customer_purchase_order_item_id": item.id,
            }
        )
    return payload


def _slice_discount(
    item: CustomerPurchaseOrderItem,
    invoice_qty: Decimal,
    remaining: Decimal,
    already_disc: Decimal,
) -> tuple[Decimal, Decimal]:
    if item.discount_percent > 0:
        return item.discount_percent, ZERO
    if item.discount_amount <= 0:
        return ZERO, ZERO
    leftover = money(item.discount_amount - already_disc)
    if leftover <= 0:
        return ZERO, ZERO
    if invoice_qty >= remaining:
        return ZERO, leftover
    sliced = money(item.discount_amount * invoice_qty / item.quantity)
    return ZERO, min(sliced, leftover)
