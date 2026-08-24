import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from fastapi import HTTPException

from app.models.spo import (
    SupplierPurchaseOrder,
    SupplierPurchaseOrderItem,
    SPOStatus,
    SPOStatusHistory,
)
from sqlalchemy.orm import selectinload
from app.schemas.spo import SPOCreate, SPOAcknowledgeReq
from app.services.spo_number import SPONumberService


class SPOService:
    @staticmethod
    async def _add_history(
        session: AsyncSession,
        spo_id: uuid.UUID,
        from_status: str,
        to_status: str,
        user_id: uuid.UUID,
        reason: Optional[str] = None,
    ):
        history = SPOStatusHistory(
            spo_id=spo_id,
            from_status=from_status,
            to_status=to_status,
            triggered_by=user_id,
            trigger_reason=reason,
        )
        session.add(history)

    @staticmethod
    async def _get_scoped_spo(
        session: AsyncSession, spo_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> SupplierPurchaseOrder:
        """Load an SPO by id, scoped to the workspace (multi-tenancy guard).

        Returns 404 for both missing and cross-tenant SPOs so callers cannot probe
        the existence of another workspace's orders.
        """
        result = await session.execute(
            select(SupplierPurchaseOrder)
            .where(SupplierPurchaseOrder.id == spo_id)
            .where(SupplierPurchaseOrder.workspace_id == workspace_id)
            .options(selectinload(SupplierPurchaseOrder.items))
        )
        spo = result.scalar_one_or_none()
        if not spo:
            raise HTTPException(status_code=404, detail="SPO not found")
        return spo

    @staticmethod
    async def create_draft(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_in: SPOCreate,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        # Gapless, workspace-scoped SPO number (SELECT FOR UPDATE on the counter)
        spo_number = await SPONumberService.generate_spo_number(session, workspace_id)

        spo = SupplierPurchaseOrder(
            workspace_id=workspace_id,
            spo_number=spo_number,
            **spo_in.model_dump(exclude={"items"}),
        )
        session.add(spo)
        await session.flush()

        subtotal = Decimal(0)
        vat_amount = Decimal(0)
        qty_total = Decimal(0)

        for item_in in spo_in.items:
            item_total = item_in.quantity_ordered * item_in.unit_price
            item_vat = item_total * (item_in.vat_rate / Decimal(100))

            item = SupplierPurchaseOrderItem(
                spo_id=spo.id,
                **item_in.model_dump(),
                total_price=item_total,
                vat_amount=item_vat,
                quantity_confirmed=item_in.quantity_ordered,
                open_quantity=item_in.quantity_ordered,
            )
            subtotal += item_total
            vat_amount += item_vat
            qty_total += item_in.quantity_ordered
            session.add(item)

        spo.subtotal = subtotal
        spo.vat_amount = vat_amount
        spo.total_amount = subtotal + vat_amount
        spo.quantity_ordered_total = qty_total
        spo.quantity_confirmed_total = qty_total

        await SPOService._add_history(
            session, spo.id, "NEW", SPOStatus.DRAFT.value, current_user_id
        )
        await session.commit()
        return (
            await session.scalars(
                select(SupplierPurchaseOrder)
                .where(SupplierPurchaseOrder.id == spo.id)
                .options(selectinload(SupplierPurchaseOrder.items))
            )
        ).first()

    @staticmethod
    async def submit_for_approval(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.PENDING_APPROVAL
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.DRAFT.value,
            SPOStatus.PENDING_APPROVAL.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def approve(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.PENDING_APPROVAL:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.APPROVED
        spo.approved_by = current_user_id
        spo.approved_at = datetime.now(timezone.utc)
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.PENDING_APPROVAL.value,
            SPOStatus.APPROVED.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def send(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.SENT
        spo.sent_at = datetime.now(timezone.utc)
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.APPROVED.value,
            SPOStatus.SENT.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def acknowledge(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        ack_req: SPOAcknowledgeReq,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status not in (SPOStatus.SENT, SPOStatus.PARTIALLY_ACKNOWLEDGED):
            raise HTTPException(status_code=400, detail="Invalid state transition")

        all_rejected = True

        for item in spo.items:
            if item.id in ack_req.lines:
                ack_line = ack_req.lines[item.id]
                item.quantity_confirmed = ack_line.quantity_confirmed
                item.quantity_backordered = (
                    item.quantity_ordered - ack_line.quantity_confirmed
                )
                item.open_quantity = item.quantity_confirmed
                if ack_line.unit_price != item.unit_price:
                    item.price_amendment_pending = True
                    # In a real impl, we create SPOAmendment here

            if item.quantity_confirmed > 0:
                all_rejected = False
            if (
                item.quantity_confirmed != item.quantity_ordered
                and not item.price_amendment_pending
            ):
                pass  # We should be robust here

        if all_rejected:
            new_status = SPOStatus.REJECTED
        elif not any(i.price_amendment_pending for i in spo.items):
            new_status = SPOStatus.ACKNOWLEDGED
            spo.acknowledged_at = datetime.now(timezone.utc)
        else:
            new_status = SPOStatus.PARTIALLY_ACKNOWLEDGED

        await SPOService._add_history(
            session,
            spo.id,
            spo.status.value,
            new_status.value,
            current_user_id,
            "Supplier acknowledged",
        )
        spo.status = new_status
        await session.commit()
        return spo

    @staticmethod
    async def cancel(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        reason: str,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status in (
            SPOStatus.CANCELLED,
            SPOStatus.CLOSED,
            SPOStatus.SHORT_CLOSED,
        ):
            raise HTTPException(status_code=400, detail="Invalid state transition")

        has_receipt = any(item.quantity_received > 0 for item in spo.items)
        if has_receipt:
            new_status = SPOStatus.PARTIALLY_CANCELLED
            for item in spo.items:
                if item.open_quantity > 0:
                    item.quantity_cancelled = item.open_quantity
                    item.open_quantity = Decimal(0)
        else:
            new_status = SPOStatus.CANCELLED
            for item in spo.items:
                item.quantity_cancelled = item.quantity_confirmed
                item.open_quantity = Decimal(0)

        await SPOService._add_history(
            session, spo.id, spo.status.value, new_status.value, current_user_id, reason
        )
        spo.status = new_status
        await session.commit()
        return await SPOService._get_scoped_spo(session, spo_id, workspace_id)
