import uuid
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.grn import GoodsReceiptNote, GRNItem, GRNStatus
from app.models.inventory import (
    InventoryLevel,
    InventoryTransaction,
    TransactionType,
    WarehouseBin,
)
from app.models.landed_cost import (
    AllocationBasis,
    LandedCostAllocation,
    LandedCostStatus,
    LandedCostType,
)
from app.models.spo import SupplierPurchaseOrder, SupplierPurchaseOrderItem
from app.services.grn_number import GRNNumberService
from sqlalchemy import func

from app.schemas.grn import (
    GRNCreate,
    GRNUpdate,
    GRNItemCreate,
    GRNDispositionRequest,
    GRNCancelRequest,
)


class GRNService:
    @staticmethod
    async def create_draft_grn(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GRNCreate,
    ) -> GoodsReceiptNote:
        grn_number = await GRNNumberService.generate_grn_number(session, workspace_id)

        if data.spo_id is not None:
            # SPO-014: no receiving against an SPO with an unresolved amendment.
            blocked = await session.execute(
                select(SupplierPurchaseOrder.has_open_amendment).where(
                    SupplierPurchaseOrder.id == data.spo_id,
                    SupplierPurchaseOrder.workspace_id == workspace_id,
                )
            )
            if blocked.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail="SPO has an open amendment; resolve it before receiving",
                )

        grn = GoodsReceiptNote(
            workspace_id=workspace_id,
            grn_number=grn_number,
            received_by=user_id,
            status=GRNStatus.DRAFT,
            **data.model_dump(exclude={"items"}),
        )
        session.add(grn)
        await session.flush()

        # D-22 §7.1: inline items (with optional landed_cost_items) create
        # GRNItem rows plus DRAFT landed cost allocations.
        for item_in in data.items or []:
            spo_item = await session.get(SupplierPurchaseOrderItem, item_in.spo_item_id)
            if not spo_item:
                raise HTTPException(status_code=404, detail="SPO item not found")

            item_dump = item_in.model_dump()
            lc_items = item_dump.pop("landed_cost_items", None)
            item = GRNItem(
                grn_id=grn.id,
                quantity_ordered_snapshot=spo_item.quantity_ordered,
                quantity_confirmed_snapshot=spo_item.quantity_confirmed,
                quantity_accepted=item_dump.get(
                    "quantity_received", 0
                ),  # Satisfy DB constraint initially
                **item_dump,
            )
            session.add(item)
            await session.flush()
            await GRNService._create_landed_cost_allocations(
                session, workspace_id, user_id, grn, item, lc_items
            )

        return grn

    @staticmethod
    async def _create_landed_cost_allocations(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        grn: GoodsReceiptNote,
        item: GRNItem,
        landed_cost_items,
    ) -> None:
        """Create DRAFT landed cost allocations for a GRN item (D-22 §7.1).

        One row per entry, linked to the GRN item. Amounts are stored at
        2 decimals. MANUAL basis requires an explicit allocation_factor.
        Source fields are populated so the
        uq_landed_cost_source idempotency constraint is enforceable.
        Reprocessing the same item never duplicates rows (guard below).
        """
        if not landed_cost_items:
            return

        # Idempotency guard (D-22-06): an item that already has allocations
        # must not gain duplicates when reprocessed.
        existing = await session.execute(
            select(func.count(LandedCostAllocation.id)).where(
                LandedCostAllocation.grn_item_id == item.id
            )
        )
        if existing.scalar_one() > 0:
            return

        # Normalize: callers pass model_dump() output (nested dicts) or
        # LandedCostItemCreate objects — accept both.
        from app.schemas.grn import LandedCostItemCreate

        normalized = [
            lc if isinstance(lc, LandedCostItemCreate) else LandedCostItemCreate(**lc)
            for lc in landed_cost_items
        ]

        for lc in normalized:
            basis = (
                lc.allocation_basis.value
                if isinstance(lc.allocation_basis, AllocationBasis)
                else str(lc.allocation_basis)
            )
            if basis == AllocationBasis.MANUAL.value and lc.allocation_factor is None:
                raise HTTPException(
                    status_code=422,
                    detail="allocation_factor is required for MANUAL allocation basis",
                )
            component = (
                lc.component_type.value
                if isinstance(lc.component_type, LandedCostType)
                else str(lc.component_type)
            )
            session.add(
                LandedCostAllocation(
                    workspace_id=workspace_id,
                    grn_id=grn.id,
                    grn_item_id=item.id,
                    spo_item_id=item.spo_item_id,
                    component_type=component,
                    amount=lc.amount.quantize(Decimal("0.01")),
                    currency=lc.currency,
                    allocation_basis=basis,
                    allocation_factor=(
                        lc.allocation_factor
                        if lc.allocation_factor is not None
                        else Decimal("1.0")
                    ),
                    source_document_type="GRN",
                    source_document_id=grn.id,
                    source_line_id=uuid.uuid4(),
                    status=LandedCostStatus.DRAFT,
                    created_by=user_id,
                )
            )
        await session.flush()

    @staticmethod
    async def update_grn(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        grn_id: uuid.UUID,
        data: GRNUpdate,
    ) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.status not in (GRNStatus.DRAFT, GRNStatus.RECEIVING):
            raise HTTPException(
                status_code=400, detail="Cannot edit GRN in current status"
            )

        update_data = data.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(grn, k, v)

        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn

    @staticmethod
    async def start_receiving(
        session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID
    ) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.status != GRNStatus.DRAFT:
            raise HTTPException(
                status_code=400, detail="GRN must be DRAFT to start receiving"
            )

        grn.status = GRNStatus.RECEIVING
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn

    @staticmethod
    async def add_grn_item(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        grn_id: uuid.UUID,
        data: GRNItemCreate,
        user_id: uuid.UUID,
    ) -> GRNItem:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.status != GRNStatus.RECEIVING:
            raise HTTPException(
                status_code=400, detail="Items can only be added in RECEIVING state"
            )

        spo_item = await session.get(SupplierPurchaseOrderItem, data.spo_item_id)
        if not spo_item:
            raise HTTPException(status_code=404, detail="SPO item not found")

        dump_data = data.model_dump()
        # D-22 §7.1: landed_cost_items are allocation entries, not GRNItem columns.
        lc_items = dump_data.pop("landed_cost_items", None)
        item = GRNItem(
            grn_id=grn.id,
            quantity_ordered_snapshot=spo_item.quantity_ordered,
            quantity_confirmed_snapshot=spo_item.quantity_confirmed,
            quantity_accepted=dump_data.get(
                "quantity_received", 0
            ),  # Satisfy DB constraint initially
            **dump_data,
        )
        session.add(item)
        await session.flush()
        await GRNService._create_landed_cost_allocations(
            session, workspace_id, user_id, grn, item, lc_items
        )
        return item

    @staticmethod
    async def stage_for_inspection(
        session: AsyncSession, workspace_id: uuid.UUID, grn_id: uuid.UUID
    ) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.status != GRNStatus.RECEIVING:
            raise HTTPException(
                status_code=400, detail="Only RECEIVING GRNs can be staged"
            )

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
        data: GRNDispositionRequest,
    ) -> GoodsReceiptNote:
        grn_query = await session.execute(
            select(GoodsReceiptNote)
            .options(selectinload(GoodsReceiptNote.items))
            .where(
                GoodsReceiptNote.id == grn_id,
                GoodsReceiptNote.workspace_id == workspace_id,
            )
        )
        grn = grn_query.scalar_one_or_none()

        if not grn:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.status != GRNStatus.PENDING_INSPECTION:
            raise HTTPException(
                status_code=400, detail="GRN must be PENDING_INSPECTION"
            )

        item = next((i for i in grn.items if i.id == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="GRN item not found")

        # INV-5.1: received = accepted + damaged + rejected
        if item.quantity_received != (
            data.quantity_accepted + data.quantity_damaged + data.quantity_rejected
        ):
            raise HTTPException(
                status_code=400,
                detail="Disposition quantities must sum to received quantity",
            )

        # Rule GRN-002: Rejection and Damage reasons
        if data.quantity_damaged > 0 and (
            not data.damage_reason or len(data.damage_reason) < 10
        ):
            raise HTTPException(
                status_code=400, detail="Damage reason required (min 10 chars)"
            )
        if data.quantity_rejected > 0 and (
            not data.rejection_reason or len(data.rejection_reason) < 10
        ):
            raise HTTPException(
                status_code=400, detail="Rejection reason required (min 10 chars)"
            )

        from app.models.workspace import Workspace

        workspace = await session.get(Workspace, workspace_id)
        tolerance = getattr(workspace, "over_receipt_tolerance_percent", Decimal("0"))

        spo_item = await session.get(SupplierPurchaseOrderItem, item.spo_item_id)
        max_allowed = spo_item.quantity_confirmed * (1 + tolerance / 100)

        if (spo_item.quantity_received + item.quantity_received) > max_allowed:
            raise HTTPException(
                status_code=400, detail="Over-receipt tolerance exceeded"
            )

        # Landed cost capitalization (D-22) - for accepted quantities
        if data.quantity_accepted > 0:
            # Sum up DRAFT and ALLOCATED landed cost allocations for this GRN item
            pdc_result = await session.execute(
                select(
                    func.coalesce(
                        func.sum(LandedCostAllocation.amount), Decimal("0.00")
                    )
                ).where(
                    LandedCostAllocation.grn_item_id == item.id,
                    LandedCostAllocation.status.in_(
                        [LandedCostStatus.DRAFT, LandedCostStatus.ALLOCATED]
                    ),
                )
            )
            landed_cost_allocated = pdc_result.scalar_one()

            if landed_cost_allocated > 0:
                item.landed_cost_allocated = landed_cost_allocated
                item.landed_cost_per_unit = (
                    landed_cost_allocated / Decimal(str(data.quantity_accepted))
                ).quantize(Decimal("0.0001"))

                # Update landed cost allocation statuses to CAPITALIZED
                await session.execute(
                    LandedCostAllocation.__table__.update()
                    .where(
                        LandedCostAllocation.grn_item_id == item.id,
                        LandedCostAllocation.status.in_(
                            [LandedCostStatus.DRAFT, LandedCostStatus.ALLOCATED]
                        ),
                    )
                    .values(
                        status=LandedCostStatus.CAPITALIZED,
                        capitalized_at=datetime.now(timezone.utc),
                    )
                )

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
            .where(
                InventoryLevel.warehouse_id == grn.warehouse_id,
                InventoryLevel.product_id == item.product_id,
            )
            .with_for_update()
        )
        stock = stock_query.scalar_one_or_none()

        if not stock:
            # Need a bin for InventoryLevel, grab first bin or fail
            bin_query = await session.execute(
                select(WarehouseBin).where(
                    WarehouseBin.warehouse_id == grn.warehouse_id
                )
            )
            wh_bin = bin_query.scalar_one_or_none()
            if not wh_bin:
                raise HTTPException(
                    status_code=400,
                    detail="Warehouse must have at least one bin for stock posting",
                )

            stock = InventoryLevel(
                workspace_id=workspace_id,
                warehouse_id=grn.warehouse_id,
                product_id=item.product_id,
                bin_id=wh_bin.id,
                on_hand=0,
                reserved=0,
                damaged=0,
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
                user_id=user_id,
            )
            session.add(tx)

            stock.on_hand += item.quantity_accepted

        if item.quantity_damaged > 0:
            stock.damaged += item.quantity_damaged

        # Update SPO rollups
        spo_item.quantity_received += item.quantity_received
        spo_item.quantity_accepted += item.quantity_accepted
        spo_item.quantity_damaged_rejected += (
            item.quantity_damaged + item.quantity_rejected
        )

        # Auto-PurchaseReturn draft (GRN-004)
        if item.quantity_rejected > 0 or item.quantity_damaged > 0:
            from app.services.purchase_return_service import purchase_return_service

            await purchase_return_service.record_disposition_auto_items(
                session, workspace_id, user_id, grn, item
            )

        # Update GRN status
        grn.stock_posted = True

        # Check overall GRN status based on lines (partial logic simplified for this scope)
        if all(i.inspected_at is not None for i in grn.items):
            if all(i.quantity_accepted == i.quantity_received for i in grn.items):
                grn.status = GRNStatus.ACCEPTED
            elif all(i.quantity_rejected == i.quantity_received for i in grn.items):
                grn.status = GRNStatus.REJECTED
            elif (
                any(i.quantity_rejected > 0 for i in grn.items)
                and sum(i.quantity_accepted for i in grn.items) == 0
            ):
                grn.status = GRNStatus.PARTIALLY_REJECTED
            else:
                grn.status = GRNStatus.PARTIALLY_ACCEPTED

        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()

        # Optional: Audit event (Rule GRN-019) -> audit service integration

        return grn

    @staticmethod
    async def cancel_grn(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        grn_id: uuid.UUID,
        data: GRNCancelRequest,
    ) -> GoodsReceiptNote:
        grn = await session.get(GoodsReceiptNote, grn_id)
        if not grn or grn.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if grn.stock_posted:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel GRN once stock is posted (GRN-018)",
            )

        if grn.status not in (
            GRNStatus.DRAFT,
            GRNStatus.RECEIVING,
            GRNStatus.PENDING_INSPECTION,
        ):
            raise HTTPException(
                status_code=400,
                detail="Can only cancel GRN in Draft, Receiving, or Pending Inspection states",
            )

        grn.status = GRNStatus.CANCELLED
        grn.notes = f"{grn.notes or ''}\nCancelled Reason: {data.reason}".strip()
        grn.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return grn
