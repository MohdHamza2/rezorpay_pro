import uuid
from decimal import Decimal
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.grn import GoodsReceiptNote, GRNItem, GRNStatus
from app.models.inventory import InventoryLevel, InventoryTransaction, TransactionType, WarehouseBin
from app.models.spo import SupplierPurchaseOrderItem
from app.models.user import User

from app.schemas.grn import (
    GRNCreate, GRNUpdate, GRNItemCreate, GRNDispositionRequest, GRNCancelRequest
)

class GRNService:
    @staticmethod
    async def _generate_grn_number(session: AsyncSession, workspace_id: uuid.UUID) -> str:
        # A proper sequence generator should be used, but simplified here
        count_query = await session.execute(select(GoodsReceiptNote).where(GoodsReceiptNote.workspace_id == workspace_id))
        count = len(count_query.scalars().all())
        return f"GRN-{datetime.now().strftime('%Y')}-{str(count + 1).zfill(6)}"

    @staticmethod
    async def create_draft_grn(session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, data: GRNCreate) -> GoodsReceiptNote:
        grn_number = await GRNService._generate_grn_number(session, workspace_id)
        
        grn = GoodsReceiptNote(
            workspace_id=workspace_id,
            grn_number=grn_number,
            received_by=user_id,
            status=GRNStatus.DRAFT,
            **data.model_dump(exclude={"items"})
        )
        session.add(grn)
        await session.flush()
        
        return grn

    @staticmethod
    async def update_grn(session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID, data: GRNUpdate) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.status not in (GRNStatus.DRAFT, GRNStatus.RECEIVING):
            raise HTTPException(status_code=400, detail="Cannot edit GRN in current status")
            
        update_data = data.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(grn, k, v)
            
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn

    @staticmethod
    async def start_receiving(session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.status != GRNStatus.DRAFT:
            raise HTTPException(status_code=400, detail="GRN must be DRAFT to start receiving")
            
        grn.status = GRNStatus.RECEIVING
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn

    @staticmethod
    async def add_grn_item(session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID, data: GRNItemCreate) -> GRNItem:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.status != GRNStatus.RECEIVING:
            raise HTTPException(status_code=400, detail="Items can only be added in RECEIVING state")

        spo_item = await session.get(SupplierPurchaseOrderItem, data.spo_item_id)
        if not spo_item:
            raise HTTPException(status_code=404, detail="SPO item not found")

        dump_data = data.model_dump()
        item = GRNItem(
            grn_id=grn.id,
            quantity_ordered_snapshot=spo_item.quantity_ordered,
            quantity_confirmed_snapshot=spo_item.quantity_confirmed,
            quantity_accepted=dump_data.get("quantity_received", 0),  # Satisfy DB constraint initially
            **dump_data
        )
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def stage_for_inspection(session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.status != GRNStatus.RECEIVING:
            raise HTTPException(status_code=400, detail="Only RECEIVING GRNs can be staged")
            
        result = await session.execute(select(GRNItem).where(GRNItem.grn_id == grn_id))
        items = result.scalars().all()
        if not items:
            raise HTTPException(status_code=400, detail="Cannot stage an empty GRN")

        grn.status = GRNStatus.PENDING_INSPECTION
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn

    @staticmethod
    async def record_disposition(
        session: AsyncSession, 
        workspace_id: uuid.UUID, 
        grn_id: uuid.UUID, 
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GRNDispositionRequest
    ) -> GoodsReceiptNote:
        grn_query = await session.execute(
            select(GoodsReceiptNote)
            .options(selectinload(GoodsReceiptNote.items))
            .where(GoodsReceiptNote.id == grn_id, GoodsReceiptNote.workspace_id == workspace_id)
        )
        grn = grn_query.scalar_one_or_none()
        
        if not grn:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.status != GRNStatus.PENDING_INSPECTION:
            raise HTTPException(status_code=400, detail="GRN must be PENDING_INSPECTION")

        item = next((i for i in grn.items if i.id == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="GRN item not found")

        # INV-5.1: received = accepted + damaged + rejected
        if item.quantity_received != (data.quantity_accepted + data.quantity_damaged + data.quantity_rejected):
            raise HTTPException(status_code=400, detail="Disposition quantities must sum to received quantity")

        # Rule GRN-002: Rejection and Damage reasons
        if data.quantity_damaged > 0 and (not data.damage_reason or len(data.damage_reason) < 10):
            raise HTTPException(status_code=400, detail="Damage reason required (min 10 chars)")
        if data.quantity_rejected > 0 and (not data.rejection_reason or len(data.rejection_reason) < 10):
            raise HTTPException(status_code=400, detail="Rejection reason required (min 10 chars)")

        from app.models.workspace import Workspace
        workspace = await session.get(Workspace, workspace_id)
        tolerance = getattr(workspace, "over_receipt_tolerance_percent", Decimal("0"))
        
        spo_item = await session.get(SupplierPurchaseOrderItem, item.spo_item_id)
        max_allowed = spo_item.quantity_confirmed * (1 + tolerance / 100)
        
        if (spo_item.quantity_received + item.quantity_received) > max_allowed:
            raise HTTPException(status_code=400, detail=f"Over-receipt tolerance exceeded")

        # Update item disposition
        item.quantity_accepted = data.quantity_accepted
        item.quantity_damaged = data.quantity_damaged
        item.quantity_rejected = data.quantity_rejected
        item.damage_reason = data.damage_reason
        item.rejection_reason = data.rejection_reason
        item.inspected_by = user_id
        item.inspected_at = datetime.now(timezone.utc)

        # Atomic Stock Posting Transaction (GRN-006)
        stock_query = await session.execute(
            select(InventoryLevel)
            .where(InventoryLevel.warehouse_id == grn.warehouse_id, InventoryLevel.product_id == item.product_id)
            .with_for_update()
        )
        stock = stock_query.scalar_one_or_none()
        
        if not stock:
            # Need a bin for InventoryLevel, grab first bin or fail
            bin_query = await session.execute(select(WarehouseBin).where(WarehouseBin.warehouse_id == grn.warehouse_id))
            wh_bin = bin_query.scalar_one_or_none()
            if not wh_bin:
                raise HTTPException(status_code=400, detail="Warehouse must have at least one bin for stock posting")

            stock = InventoryLevel(
                workspace_id=workspace_id,
                warehouse_id=grn.warehouse_id,
                product_id=item.product_id,
                bin_id=wh_bin.id,
                on_hand=0,
                reserved=0,
                damaged=0
            )
            session.add(stock)
            await session.flush()

        if item.quantity_accepted > 0:
            tx = InventoryTransaction(
                workspace_id=workspace_id,
                product_id=item.product_id,
                transaction_type=TransactionType.RECEIPT,
                quantity=item.quantity_accepted,
                destination_bin_id=stock.bin_id,
                reference_type="grn",
                reference_id=item.id,
                user_id=user_id
            )
            session.add(tx)

            stock.on_hand += item.quantity_accepted

        if item.quantity_damaged > 0:
            stock.damaged += item.quantity_damaged

        # Update SPO rollups
        spo_item.quantity_received += item.quantity_received
        spo_item.quantity_accepted += item.quantity_accepted
        spo_item.quantity_damaged_rejected += (item.quantity_damaged + item.quantity_rejected)

        # Auto-PurchaseReturn draft (GRN-004)
        if item.quantity_rejected > 0:
            # Hook logic placeholder. PurchaseReturn model assumed to be handled separately or added later if exists.
            pass

        # Update GRN status
        grn.stock_posted = True
        
        # Check overall GRN status based on lines (partial logic simplified for this scope)
        if all(i.inspected_at is not None for i in grn.items):
            if all(i.quantity_accepted == i.quantity_received for i in grn.items):
                grn.status = GRNStatus.ACCEPTED
            elif all(i.quantity_rejected == i.quantity_received for i in grn.items):
                grn.status = GRNStatus.REJECTED
            elif any(i.quantity_rejected > 0 for i in grn.items) and sum(i.quantity_accepted for i in grn.items) == 0:
                grn.status = GRNStatus.PARTIALLY_REJECTED
            else:
                grn.status = GRNStatus.PARTIALLY_ACCEPTED

        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        
        # Optional: Audit event (Rule GRN-019) -> audit service integration
        
        return grn

    @staticmethod
    async def cancel_grn(session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID, data: GRNCancelRequest) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")
            
        if grn.stock_posted:
            raise HTTPException(status_code=400, detail="Cannot cancel GRN once stock is posted (GRN-018)")
            
        if grn.status not in (GRNStatus.DRAFT, GRNStatus.RECEIVING, GRNStatus.PENDING_INSPECTION):
            raise HTTPException(status_code=400, detail="Can only cancel GRN in Draft, Receiving, or Pending Inspection states")

        grn.status = GRNStatus.CANCELLED
        grn.notes = f"{grn.notes or ''}\nCancelled Reason: {data.reason}".strip()
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn
