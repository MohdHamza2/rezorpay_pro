"""Shared quotation helpers: money lines, expiry, convert payload, events."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, NoReturn, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice import Invoice
from app.models.product import Product
from app.models.quotation import Quotation, QuotationStatus
from app.models.quotation_event import QuotationEvent, QuotationEventType
from app.models.quotation_item import QuotationItem
from app.models.customer_purchase_order import CustomerPurchaseOrder
from app.schemas.common import ErrorCode, ErrorDetail
from app.services.invoice_service import _resolve_line
from app.services.line_money import apply_line_money, money

logger = logging.getLogger(__name__)

VALIDITY_DAYS = 14
INVOICE_DUE_DAYS = 30
EDITABLE = QuotationStatus.DRAFT
CONVERTIBLE = QuotationStatus.ACCEPTED


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
            "Quotation currency must be AED",
            "currency",
        )


def assert_validity(quotation_date: date, valid_until: date) -> None:
    if valid_until < quotation_date:
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "valid_until must be on or after quotation_date",
            "valid_until",
        )


def should_expire(quotation: Quotation) -> bool:
    return (
        quotation.status == QuotationStatus.SENT and quotation.valid_until < utc_today()
    )


async def expire_locked(
    session: AsyncSession, quotation: Quotation, user_id: uuid.UUID
) -> bool:
    """Mark SENT+past-due as EXPIRED. True if the caller must persist before 403."""
    if not should_expire(quotation):
        return False
    await mark_expired(session, quotation, user_id)
    return True


async def mark_expired(
    session: AsyncSession, quotation: Quotation, user_id: uuid.UUID
) -> None:
    if quotation.status != QuotationStatus.SENT:
        return
    previous = quotation.status.value
    quotation.status = QuotationStatus.EXPIRED
    quotation.updated_at = now()
    await log_event(
        session,
        quotation,
        user_id,
        QuotationEventType.QUOTATION_EXPIRED,
        previous,
        QuotationStatus.EXPIRED.value,
        None,
    )


def assert_draft(quotation: Quotation) -> None:
    if quotation.status != EDITABLE:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot modify quotation with status '{quotation.status.value}'. "
            "Only DRAFT quotations can be edited or deleted.",
        )


def assert_status(quotation: Quotation, expected: QuotationStatus, action: str) -> None:
    if quotation.status != expected:
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INVALID_STATE,
            f"Cannot {action} quotation with status '{quotation.status.value}'.",
        )


async def existing_converted_invoice(
    session: AsyncSession, quotation: Quotation, workspace_id: uuid.UUID
) -> Invoice:
    result = await session.execute(
        select(Invoice).where(
            Invoice.quotation_id == quotation.id,
            Invoice.workspace_id == workspace_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None or invoice.deleted_at is not None:
        raise_error(
            status.HTTP_409_CONFLICT,
            ErrorCode.CONFLICT,
            "This quotation was already converted; the invoice was deleted. "
            "Create a new invoice manually.",
            "quotation_id",
        )
    return invoice


async def existing_converted_lpo(
    session: AsyncSession, quotation: Quotation, workspace_id: uuid.UUID
) -> Optional[CustomerPurchaseOrder]:
    result = await session.execute(
        select(CustomerPurchaseOrder).where(
            CustomerPurchaseOrder.quotation_id == quotation.id,
            CustomerPurchaseOrder.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


def converted_notes(quotation: Quotation) -> str:
    prefix = f"Converted from {quotation.quotation_number}."
    extra = (quotation.notes or "").strip()
    return f"{prefix} {extra}" if extra else prefix


async def frozen_invoice_items(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    items: Sequence[QuotationItem],
) -> List[dict]:
    payload: List[dict] = []
    for item in items:
        product_id = item.product_id
        description = item.description
        if product_id is not None:
            product = await session.get(Product, product_id)
            if not product_still_catalog(product, workspace_id):
                product_id = None
                if item.sku_snapshot:
                    description = f"{item.sku_snapshot} {description}".strip()
        payload.append(
            {
                "description": description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "tax_rate": item.tax_rate,
                "discount_percent": item.discount_percent,
                "discount_amount": item.discount_amount,
                "product_id": product_id,
            }
        )
    return payload


def product_still_catalog(product: Optional[Product], workspace_id: uuid.UUID) -> bool:
    return (
        product is not None
        and product.workspace_id == workspace_id
        and product.deleted_at is None
        and product.is_active
    )


async def add_items(
    session: AsyncSession,
    quotation: Quotation,
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
            line_owner="quotation",
            client_id=quotation.client_id,
        )
        item = QuotationItem(
            quotation_id=quotation.id,
            **resolved,
            line_net=Decimal("0"),
            tax_amount=Decimal("0"),
            total_price=Decimal("0"),
            created_at=now(),
            updated_at=now(),
        )
        apply_line_money(item)
        session.add(item)
    await session.flush()


async def recalculate(session: AsyncSession, quotation: Quotation) -> None:
    result = await session.execute(
        select(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
    )
    items = result.scalars().all()
    for item in items:
        apply_line_money(item)
    subtotal = sum((item.line_net for item in items), Decimal("0"))
    tax_amount = sum((item.tax_amount for item in items), Decimal("0"))
    quotation.subtotal = subtotal
    quotation.tax_amount = tax_amount
    quotation.total_amount = money(subtotal + tax_amount)
    quotation.updated_at = now()


async def log_event(
    session: AsyncSession,
    quotation: Quotation,
    user_id: uuid.UUID,
    event_type: QuotationEventType,
    previous_status: Optional[str],
    new_status: str,
    metadata: Optional[dict],
) -> None:
    session.add(
        QuotationEvent(
            quotation_id=quotation.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user_id,
            metadata_log=metadata or {},
            timestamp=now(),
        )
    )
    logger.info(
        "quotation_event",
        extra={
            "quotation_id": str(quotation.id),
            "event_type": event_type.value,
            "status": new_status,
        },
    )
