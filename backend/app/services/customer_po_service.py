"""Customer LPO lifecycle: state machine, remaining qty, invoice slices."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.customer_purchase_order import (
    CustomerPurchaseOrder,
    CustomerPurchaseOrderStatus,
)
from app.models.customer_purchase_order_event import CustomerPurchaseOrderEventType
from app.models.customer_purchase_order_item import CustomerPurchaseOrderItem
from app.models.invoice import Invoice
from app.models.quotation import Quotation
from app.schemas.common import ErrorCode
from app.services.customer_po_support import (
    ZERO,
    add_items,
    assert_aed,
    assert_delivery,
    assert_draft,
    countable_invoices,
    copy_quote_item,
    has_countable_invoice,
    invoiced_qty_map,
    item_response_payload,
    log_event,
    normalize_po_number,
    now,
    raise_error,
    recalculate,
    remaining_qty,
    slice_invoice_items,
    utc_today,
)
from app.services.invoice_service import AED, InvoiceService, _workspace_tax_rate
from app.services.lpo_number import LpoNumberService
from app.services.quotation_support import INVOICE_DUE_DAYS


class CustomerPurchaseOrderService:
    """State machine, remaining qty, isolation, LPO→invoice slices."""

    @staticmethod
    def serialize(lpo: CustomerPurchaseOrder, invoices: Optional[List[Invoice]] = None):
        from app.schemas.customer_purchase_orders import (
            CustomerPurchaseOrderItemResponse,
            CustomerPurchaseOrderResponse,
            LinkedInvoiceSummary,
        )

        items = [
            CustomerPurchaseOrderItemResponse.model_validate(item_response_payload(i))
            for i in (lpo.items or [])
        ]
        linked = [LinkedInvoiceSummary.model_validate(inv) for inv in (invoices or [])]
        payload = CustomerPurchaseOrderResponse.model_validate(lpo)
        return payload.model_copy(update={"items": items, "invoices": linked})

    @staticmethod
    def serialize_list_item(lpo: CustomerPurchaseOrder):
        from app.schemas.customer_purchase_orders import CustomerPurchaseOrderListItem

        return CustomerPurchaseOrderListItem.model_validate(lpo)

    @staticmethod
    async def get_visible(
        session: AsyncSession,
        lpo_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[CustomerPurchaseOrder]:
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
        return result.scalar_one_or_none()

    @classmethod
    async def wrapped(
        cls,
        session: AsyncSession,
        lpo: CustomerPurchaseOrder,
        workspace_id: uuid.UUID,
    ):
        invoices = await countable_invoices(session, lpo.id, workspace_id)
        return cls.serialize(lpo, invoices)

    @staticmethod
    async def assert_unique_customer_po(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
        customer_po_number: Optional[str],
        exclude_id: Optional[uuid.UUID] = None,
    ) -> None:
        if customer_po_number is None:
            return
        query = select(CustomerPurchaseOrder.id).where(
            CustomerPurchaseOrder.workspace_id == workspace_id,
            CustomerPurchaseOrder.client_id == client_id,
            CustomerPurchaseOrder.customer_po_number == customer_po_number,
        )
        if exclude_id is not None:
            query = query.where(CustomerPurchaseOrder.id != exclude_id)
        result = await session.execute(query)
        if result.scalar_one_or_none() is not None:
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.CONFLICT,
                "Customer PO number already exists for this client",
                "customer_po_number",
            )

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        items: List[dict],
        customer_po_number: Optional[str] = None,
        lpo_date: Optional[date] = None,
        expected_delivery_date: Optional[date] = None,
        currency: str = AED,
        notes: Optional[str] = None,
        quotation_id: Optional[uuid.UUID] = None,
    ) -> CustomerPurchaseOrder:
        assert_aed(currency)
        po_number = normalize_po_number(customer_po_number)
        header_date = lpo_date or utc_today()
        assert_delivery(header_date, expected_delivery_date)
        await cls.assert_unique_customer_po(session, workspace_id, client_id, po_number)
        default_tax = await _workspace_tax_rate(session, workspace_id)
        number = await LpoNumberService.generate_lpo_number(session, workspace_id)
        lpo = CustomerPurchaseOrder(
            workspace_id=workspace_id,
            client_id=client_id,
            quotation_id=quotation_id,
            lpo_number=number,
            customer_po_number=po_number,
            currency=currency,
            status=CustomerPurchaseOrderStatus.DRAFT,
            lpo_date=header_date,
            expected_delivery_date=expected_delivery_date,
            notes=notes,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            created_at=now(),
            updated_at=now(),
        )
        session.add(lpo)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.CONFLICT,
                "Customer PO number already exists for this client",
                "customer_po_number",
            )
        await add_items(session, lpo, workspace_id, default_tax, items)
        await recalculate(session, lpo)
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_CREATED,
            None,
            CustomerPurchaseOrderStatus.DRAFT.value,
            {"items_count": len(items), "total": str(lpo.total_amount)},
        )
        return lpo

    @classmethod
    async def create_from_quotation(
        cls,
        session: AsyncSession,
        quotation: Quotation,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        customer_po_number: Optional[str] = None,
        lpo_date: Optional[date] = None,
        expected_delivery_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> CustomerPurchaseOrder:
        assert_aed(quotation.currency)
        po_number = normalize_po_number(customer_po_number)
        header_date = lpo_date or utc_today()
        assert_delivery(header_date, expected_delivery_date)
        await cls.assert_unique_customer_po(
            session, workspace_id, quotation.client_id, po_number
        )
        number = await LpoNumberService.generate_lpo_number(session, workspace_id)
        prefix = f"Converted from {quotation.quotation_number}."
        extra = (notes if notes is not None else quotation.notes) or ""
        extra = extra.strip()
        lpo = CustomerPurchaseOrder(
            workspace_id=workspace_id,
            client_id=quotation.client_id,
            quotation_id=quotation.id,
            lpo_number=number,
            customer_po_number=po_number,
            currency=quotation.currency,
            status=CustomerPurchaseOrderStatus.DRAFT,
            lpo_date=header_date,
            expected_delivery_date=expected_delivery_date,
            notes=f"{prefix} {extra}" if extra else prefix,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            created_at=now(),
            updated_at=now(),
        )
        session.add(lpo)
        await session.flush()
        for quote_item in quotation.items:
            session.add(copy_quote_item(lpo.id, quote_item))
        await session.flush()
        await recalculate(session, lpo)
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_CREATED,
            None,
            CustomerPurchaseOrderStatus.DRAFT.value,
            {"quotation_id": str(quotation.id), "total": str(lpo.total_amount)},
        )
        return lpo

    @classmethod
    async def update_draft(
        cls,
        session: AsyncSession,
        lpo: CustomerPurchaseOrder,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> CustomerPurchaseOrder:
        assert_draft(lpo)
        if "currency" in patch:
            raw = patch["currency"]
            patch["currency"] = raw.value if hasattr(raw, "value") else raw
            assert_aed(patch["currency"])
        if "customer_po_number" in patch:
            patch["customer_po_number"] = normalize_po_number(
                patch["customer_po_number"]
            )
            await cls.assert_unique_customer_po(
                session,
                lpo.workspace_id,
                lpo.client_id,
                patch["customer_po_number"],
                exclude_id=lpo.id,
            )
        lpo_date = patch.get("lpo_date", lpo.lpo_date)
        expected = patch.get("expected_delivery_date", lpo.expected_delivery_date)
        assert_delivery(lpo_date, expected)
        for field, value in patch.items():
            setattr(lpo, field, value)
        if items is not None:
            await session.execute(
                delete(CustomerPurchaseOrderItem).where(
                    CustomerPurchaseOrderItem.customer_purchase_order_id == lpo.id
                )
            )
            await session.flush()
            default_tax = await _workspace_tax_rate(session, lpo.workspace_id)
            await add_items(session, lpo, lpo.workspace_id, default_tax, items)
        await recalculate(session, lpo)
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_UPDATED,
            CustomerPurchaseOrderStatus.DRAFT.value,
            CustomerPurchaseOrderStatus.DRAFT.value,
            {"changed": list(patch.keys()) + (["items"] if items is not None else [])},
        )
        return lpo

    @staticmethod
    async def soft_delete(lpo: CustomerPurchaseOrder) -> None:
        assert_draft(lpo)
        lpo.deleted_at = now()
        lpo.updated_at = now()

    @classmethod
    async def receive(
        cls, session: AsyncSession, lpo: CustomerPurchaseOrder, user_id: uuid.UUID
    ) -> CustomerPurchaseOrder:
        assert_draft(lpo)
        assert_aed(lpo.currency)
        if not lpo.items:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot receive an LPO with no lines",
            )
        previous = lpo.status.value
        lpo.status = CustomerPurchaseOrderStatus.RECEIVED
        lpo.updated_at = now()
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_RECEIVED,
            previous,
            CustomerPurchaseOrderStatus.RECEIVED.value,
            None,
        )
        return lpo

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        lpo: CustomerPurchaseOrder,
        user_id: uuid.UUID,
        reason: Optional[str],
    ) -> CustomerPurchaseOrder:
        if lpo.status != CustomerPurchaseOrderStatus.RECEIVED:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot cancel LPO with status '{lpo.status.value}'.",
            )
        if await has_countable_invoice(session, lpo.id):
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot cancel an LPO that has invoices",
            )
        previous = lpo.status.value
        lpo.status = CustomerPurchaseOrderStatus.CANCELLED
        lpo.cancellation_reason = reason
        lpo.updated_at = now()
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_CANCELLED,
            previous,
            CustomerPurchaseOrderStatus.CANCELLED.value,
            {"reason": (reason or "")[:200]},
        )
        return lpo

    @classmethod
    async def recalc_invoiced(
        cls,
        session: AsyncSession,
        lpo_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[CustomerPurchaseOrder]:
        result = await session.execute(
            select(CustomerPurchaseOrder)
            .options(selectinload(CustomerPurchaseOrder.items))
            .where(CustomerPurchaseOrder.id == lpo_id)
            .with_for_update()
        )
        lpo = result.scalar_one_or_none()
        if lpo is None or lpo.deleted_at is not None:
            return lpo
        if lpo.status == CustomerPurchaseOrderStatus.CANCELLED:
            return lpo
        qty_map = await invoiced_qty_map(session, lpo.id)
        previous = lpo.status.value
        any_invoiced = False
        all_remaining_zero = True
        for item in lpo.items:
            invoiced = qty_map.get(item.id, ZERO)
            if invoiced > item.quantity:
                invoiced = item.quantity
            item.quantity_invoiced = invoiced
            item.updated_at = now()
            if invoiced > 0:
                any_invoiced = True
            if remaining_qty(item) > 0:
                all_remaining_zero = False
        countable = await has_countable_invoice(session, lpo.id)
        if all_remaining_zero and countable:
            lpo.status = CustomerPurchaseOrderStatus.INVOICED
        elif any_invoiced:
            lpo.status = CustomerPurchaseOrderStatus.PARTIAL
        elif lpo.status == CustomerPurchaseOrderStatus.DRAFT:
            lpo.status = CustomerPurchaseOrderStatus.DRAFT
        else:
            lpo.status = CustomerPurchaseOrderStatus.RECEIVED
        lpo.updated_at = now()
        if user_id is not None and previous != lpo.status.value:
            await log_event(
                session,
                lpo,
                user_id,
                CustomerPurchaseOrderEventType.CPO_RECALC,
                previous,
                lpo.status.value,
                {"quantity_invoiced": {str(k): str(v) for k, v in qty_map.items()}},
            )
        return lpo

    @classmethod
    async def create_invoices(
        cls,
        session: AsyncSession,
        lpo: CustomerPurchaseOrder,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        requested: Optional[List[dict]],
        notes: Optional[str],
        issue_date: Optional[date],
        supply_date: Optional[date],
        due_date: Optional[date],
    ) -> Invoice:
        if lpo.status == CustomerPurchaseOrderStatus.CANCELLED:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot invoice a cancelled LPO",
            )
        if lpo.status == CustomerPurchaseOrderStatus.DRAFT:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot invoice a DRAFT LPO. Receive it first.",
            )
        qty_map = await invoiced_qty_map(session, lpo.id)
        for item in lpo.items:
            item.quantity_invoiced = qty_map.get(item.id, ZERO)
        slices = _resolve_slices(lpo, requested)
        if not slices:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Nothing remaining to invoice",
                "quantity",
            )
        today = utc_today()
        issue = issue_date or today
        invoice_items = await slice_invoice_items(session, workspace_id, lpo, slices)
        invoice = await InvoiceService.create_invoice(
            session=session,
            workspace_id=workspace_id,
            client_id=lpo.client_id,
            user_id=user_id,
            issue_date=issue,
            supply_date=supply_date or issue,
            due_date=due_date or (today + timedelta(days=INVOICE_DUE_DAYS)),
            currency=AED,
            notes=notes or f"Invoiced from {lpo.lpo_number}.",
            items=invoice_items,
            quotation_id=None,
            customer_purchase_order_id=lpo.id,
        )
        await log_event(
            session,
            lpo,
            user_id,
            CustomerPurchaseOrderEventType.CPO_INVOICE_CREATED,
            lpo.status.value,
            lpo.status.value,
            {"invoice_id": str(invoice.id)},
        )
        await cls.recalc_invoiced(session, lpo.id, user_id)
        return invoice

    @staticmethod
    def list_filters(
        workspace_id: uuid.UUID,
        status_filter: Optional[CustomerPurchaseOrderStatus],
        client_id: Optional[uuid.UUID],
        search: Optional[str],
    ):
        query = select(CustomerPurchaseOrder).where(
            CustomerPurchaseOrder.workspace_id == workspace_id,
            CustomerPurchaseOrder.deleted_at.is_(None),
        )
        if status_filter:
            query = query.where(CustomerPurchaseOrder.status == status_filter)
        if client_id:
            query = query.where(CustomerPurchaseOrder.client_id == client_id)
        if search:
            term = f"%{search}%"
            query = query.where(
                or_(
                    CustomerPurchaseOrder.lpo_number.ilike(term),
                    CustomerPurchaseOrder.customer_po_number.ilike(term),
                )
            )
        return query


def _items_by_id(
    lpo: CustomerPurchaseOrder,
) -> Dict[uuid.UUID, CustomerPurchaseOrderItem]:
    return {item.id: item for item in lpo.items}


def _resolve_slices(
    lpo: CustomerPurchaseOrder, requested: Optional[List[dict]]
) -> List[Tuple[CustomerPurchaseOrderItem, Decimal]]:
    by_id = _items_by_id(lpo)
    if not requested:
        return [
            (item, remaining_qty(item)) for item in lpo.items if remaining_qty(item) > 0
        ]
    leftover = {item.id: remaining_qty(item) for item in lpo.items}
    seen: set[uuid.UUID] = set()
    slices: List[Tuple[CustomerPurchaseOrderItem, Decimal]] = []
    for row in requested:
        item_id = row["customer_purchase_order_item_id"]
        qty = Decimal(str(row["quantity"]))
        item = by_id.get(item_id)
        if item is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "LPO line not found",
            )
        remaining = leftover[item_id]
        if qty > remaining:
            if remaining <= 0 and item_id not in seen:
                continue
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot over-invoice an LPO line",
                "quantity",
            )
        leftover[item_id] = remaining - qty
        seen.add(item_id)
        slices.append((item, qty))
    return slices
