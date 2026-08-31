"""Delivery Note lifecycle: XOR parent, remaining, confirm ISSUE, HOLD gate."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.credit_status_event import CreditEventReason
from app.models.customer_purchase_order import CustomerPurchaseOrder
from app.models.delivery_note import DeliveryNote, DeliveryNoteStatus
from app.models.delivery_note_event import DeliveryNoteEventType
from app.models.invoice import Invoice
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.services.credit_control_service import CreditControlService
from app.services.customer_po_support import raise_error
from app.services.delivery_note_support import (
    ZERO,
    assert_catalog_product,
    assert_draft,
    build_item,
    confirmed_cpo_qty_map,
    confirmed_invoice_qty_map,
    load_client,
    load_invoice,
    load_lpo,
    log_event,
    now,
    recalc_delivered,
    remaining_of,
    replace_items,
    resolve_bin_id,
    resolve_slices,
    serialize,
    serialize_list_item,
    utc_today,
)
from app.services.dn_number import DnNumberService
from app.services.inventory_ledger import post_issue, qty_dec


class DeliveryNoteService:
    """XOR parent, remaining vs CONFIRMED, confirm ISSUE, cancel reverse."""

    serialize = staticmethod(serialize)
    serialize_list_item = staticmethod(serialize_list_item)

    @staticmethod
    async def get_visible(
        session: AsyncSession,
        dn_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[DeliveryNote]:
        query = (
            select(DeliveryNote)
            .options(selectinload(DeliveryNote.items))
            .where(DeliveryNote.id == dn_id)
            .where(DeliveryNote.workspace_id == workspace_id)
            .where(DeliveryNote.deleted_at.is_(None))
        )
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def wrapped(cls, session: AsyncSession, dn: DeliveryNote):
        loaded = await cls.get_visible(session, dn.id, dn.workspace_id)
        return serialize(loaded or dn)

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        customer_purchase_order_id: Optional[uuid.UUID] = None,
        invoice_id: Optional[uuid.UUID] = None,
        bin_id: Optional[uuid.UUID] = None,
        delivery_date: Optional[date] = None,
        shipping_address: Optional[str] = None,
        vehicle_number: Optional[str] = None,
        driver_name: Optional[str] = None,
        notes: Optional[str] = None,
        items: Optional[List[dict]] = None,
    ) -> DeliveryNote:
        number = await DnNumberService.generate_dn_number(session, workspace_id)
        parent, from_lpo = await cls._load_parent(
            session, workspace_id, customer_purchase_order_id, invoice_id
        )
        header_bin = await resolve_bin_id(session, warehouse_id, workspace_id, bin_id)
        client = await load_client(session, parent.client_id, workspace_id)
        parent_id = parent.id
        client_id = parent.client_id
        dn = DeliveryNote(
            workspace_id=workspace_id,
            client_id=client_id,
            customer_purchase_order_id=parent_id if from_lpo else None,
            invoice_id=None if from_lpo else parent_id,
            warehouse_id=warehouse_id,
            bin_id=header_bin,
            dn_number=number,
            status=DeliveryNoteStatus.DRAFT,
            delivery_date=delivery_date or utc_today(),
            shipping_address=shipping_address or client.address,
            vehicle_number=vehicle_number,
            driver_name=driver_name,
            notes=notes,
            created_at=now(),
            updated_at=now(),
        )
        session.add(dn)
        await session.flush()
        await cls._add_lines(
            session, dn, workspace_id, parent, from_lpo, items, header_bin
        )
        await log_event(
            session,
            dn,
            user_id,
            DeliveryNoteEventType.DN_CREATED,
            None,
            DeliveryNoteStatus.DRAFT.value,
            {"items_count": len(dn.items or [])},
        )
        return dn

    @classmethod
    async def update_draft(
        cls,
        session: AsyncSession,
        dn: DeliveryNote,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> DeliveryNote:
        assert_draft(dn)
        warehouse_id = patch.get("warehouse_id", dn.warehouse_id)
        bin_id = patch.get("bin_id", dn.bin_id) if "bin_id" in patch else dn.bin_id
        if "warehouse_id" in patch or "bin_id" in patch:
            header_bin = await resolve_bin_id(
                session, warehouse_id, dn.workspace_id, bin_id
            )
            patch["warehouse_id"] = warehouse_id
            patch["bin_id"] = header_bin
        for field, value in patch.items():
            setattr(dn, field, value)
        if items is not None:
            await replace_items(session, dn)
            parent, from_lpo = await cls._load_parent(
                session,
                dn.workspace_id,
                dn.customer_purchase_order_id,
                dn.invoice_id,
            )
            await cls._add_lines(
                session, dn, dn.workspace_id, parent, from_lpo, items, dn.bin_id
            )
        elif "bin_id" in patch:
            for line in dn.items or []:
                line.bin_id = dn.bin_id
                line.updated_at = now()
        dn.updated_at = now()
        await log_event(
            session,
            dn,
            user_id,
            DeliveryNoteEventType.DN_UPDATED,
            DeliveryNoteStatus.DRAFT.value,
            DeliveryNoteStatus.DRAFT.value,
            {"changed": list(patch.keys()) + (["items"] if items is not None else [])},
        )
        return dn

    @staticmethod
    async def soft_delete(dn: DeliveryNote) -> None:
        assert_draft(dn)
        dn.deleted_at = now()
        dn.updated_at = now()

    @classmethod
    async def confirm(
        cls,
        session: AsyncSession,
        dn: DeliveryNote,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> DeliveryNote:
        if dn.status == DeliveryNoteStatus.CONFIRMED:
            return dn
        if dn.status != DeliveryNoteStatus.DRAFT:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot confirm delivery note with status '{dn.status.value}'.",
            )
        if not dn.items:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "At least one line is required",
            )
        parent, from_lpo = await cls._load_parent(
            session,
            workspace_id,
            dn.customer_purchase_order_id,
            dn.invoice_id,
            for_update=True,
        )
        await cls._assert_hold(session, dn, user_id)
        qty_map = await cls._qty_map(session, parent, from_lpo)
        await cls._assert_remaining(dn, parent, from_lpo, qty_map)
        await cls._assert_products_on_confirm(session, dn, workspace_id)
        await cls._issue_stock(session, dn, user_id, workspace_id, reverse=False)
        previous = dn.status.value
        dn.status = DeliveryNoteStatus.CONFIRMED
        dn.confirmed_by = user_id
        dn.confirmed_at = now()
        dn.updated_at = now()
        if from_lpo:
            await recalc_delivered(session, parent.id)
        await log_event(
            session,
            dn,
            user_id,
            DeliveryNoteEventType.DN_CONFIRMED,
            previous,
            DeliveryNoteStatus.CONFIRMED.value,
            None,
        )
        return dn

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        dn: DeliveryNote,
        user_id: uuid.UUID,
        reason: Optional[str],
    ) -> DeliveryNote:
        if dn.status != DeliveryNoteStatus.CONFIRMED:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Only CONFIRMED delivery notes can be cancelled. "
                "Use DELETE for DRAFT.",
            )
        await cls._load_parent(
            session,
            dn.workspace_id,
            dn.customer_purchase_order_id,
            dn.invoice_id,
            for_update=True,
        )
        await cls._issue_stock(session, dn, user_id, dn.workspace_id, reverse=True)
        previous = dn.status.value
        dn.status = DeliveryNoteStatus.CANCELLED
        dn.cancellation_reason = reason
        dn.updated_at = now()
        if dn.customer_purchase_order_id is not None:
            await recalc_delivered(session, dn.customer_purchase_order_id)
        await log_event(
            session,
            dn,
            user_id,
            DeliveryNoteEventType.DN_CANCELLED,
            previous,
            DeliveryNoteStatus.CANCELLED.value,
            {"reason": (reason or "")[:200]},
        )
        return dn

    @staticmethod
    def list_filters(
        workspace_id: uuid.UUID,
        status_filter: Optional[DeliveryNoteStatus],
        client_id: Optional[uuid.UUID],
        customer_purchase_order_id: Optional[uuid.UUID],
        invoice_id: Optional[uuid.UUID],
        search: Optional[str],
    ):
        query = select(DeliveryNote).where(
            DeliveryNote.workspace_id == workspace_id,
            DeliveryNote.deleted_at.is_(None),
        )
        if status_filter:
            query = query.where(DeliveryNote.status == status_filter)
        if client_id:
            query = query.where(DeliveryNote.client_id == client_id)
        if customer_purchase_order_id:
            query = query.where(
                DeliveryNote.customer_purchase_order_id == customer_purchase_order_id
            )
        if invoice_id:
            query = query.where(DeliveryNote.invoice_id == invoice_id)
        if search:
            query = query.where(DeliveryNote.dn_number.ilike(f"%{search}%"))
        return query

    @staticmethod
    async def _load_parent(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        customer_purchase_order_id: Optional[uuid.UUID],
        invoice_id: Optional[uuid.UUID],
        *,
        for_update: bool = False,
    ) -> Tuple[CustomerPurchaseOrder | Invoice, bool]:
        has_lpo = customer_purchase_order_id is not None
        has_inv = invoice_id is not None
        if has_lpo == has_inv:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Exactly one of customer_purchase_order_id or invoice_id is required",
            )
        if has_lpo:
            return (
                await load_lpo(
                    session,
                    customer_purchase_order_id,
                    workspace_id,
                    for_update=for_update,
                ),
                True,
            )
        return (
            await load_invoice(
                session, invoice_id, workspace_id, for_update=for_update
            ),
            False,
        )

    @classmethod
    async def _add_lines(
        cls,
        session: AsyncSession,
        dn: DeliveryNote,
        workspace_id: uuid.UUID,
        parent,
        from_lpo: bool,
        requested: Optional[List[dict]],
        header_bin: uuid.UUID,
    ) -> None:
        qty_map = await cls._qty_map(session, parent, from_lpo)
        slices = resolve_slices(parent, from_lpo, requested, qty_map)
        if not slices:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "At least one line is required",
            )
        for parent_line, qty, line_bin in slices:
            bin_id = line_bin or header_bin
            if line_bin is not None:
                await resolve_bin_id(session, dn.warehouse_id, workspace_id, line_bin)
            await build_item(
                session, dn, workspace_id, parent_line, qty, bin_id, from_lpo=from_lpo
            )
        await session.flush()
        await session.refresh(dn, ["items"])

    @staticmethod
    async def _qty_map(session: AsyncSession, parent, from_lpo: bool):
        if from_lpo:
            return await confirmed_cpo_qty_map(session, parent.id)
        return await confirmed_invoice_qty_map(session, parent.id)

    @classmethod
    async def _assert_remaining(
        cls, dn: DeliveryNote, parent, from_lpo: bool, qty_map: Dict[uuid.UUID, Decimal]
    ) -> None:
        leftover = {
            item.id: remaining_of(item.quantity, qty_map.get(item.id, ZERO))
            for item in parent.items or []
        }
        key_attr = "customer_purchase_order_item_id" if from_lpo else "invoice_item_id"
        for line in dn.items:
            parent_id = getattr(line, key_attr)
            if parent_id is None or parent_id not in leftover:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Parent line not found",
                )
            if qty_dec(line.quantity) > leftover[parent_id]:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.VALIDATION_ERROR,
                    "Cannot over-deliver a parent line",
                    "quantity",
                )
            leftover[parent_id] -= qty_dec(line.quantity)

    @staticmethod
    async def _assert_products_on_confirm(
        session: AsyncSession, dn: DeliveryNote, workspace_id: uuid.UUID
    ) -> None:
        for line in dn.items:
            if line.product_id is None:
                continue
            await assert_catalog_product(
                session, line.product_id, workspace_id, on_confirm=True
            )

    @staticmethod
    async def _issue_stock(
        session: AsyncSession,
        dn: DeliveryNote,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        reverse: bool,
    ) -> None:
        catalog = [line for line in dn.items if line.product_id is not None]
        catalog.sort(key=lambda line: (str(line.product_id), str(line.bin_id)))
        for line in catalog:
            await post_issue(
                session,
                workspace_id,
                line.product_id,
                dn.warehouse_id,
                line.bin_id or dn.bin_id,
                qty_dec(line.quantity),
                user_id,
                line.id,
                reverse=reverse,
            )

    @staticmethod
    async def _assert_hold(
        session: AsyncSession, dn: DeliveryNote, user_id: uuid.UUID
    ) -> None:
        workspace = await session.get(Workspace, dn.workspace_id)
        client = await session.get(Client, dn.client_id)
        if workspace is None or client is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found"
            )
        if not workspace.block_do_on_hold:
            return
        await CreditControlService.assert_not_hold(
            session, client, workspace, user_id, CreditEventReason.DN_CONFIRM
        )
