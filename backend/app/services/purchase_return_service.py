"""Purchase Return Service — Wave 23 (Phase 4).

State machine (procurement-rules + api-contracts reconciled):
    DRAFT → PENDING_SUPPLIER → APPROVED → DISPATCHED → COMPLETED
    DRAFT / PENDING_SUPPLIER → CANCELLED
    PENDING_SUPPLIER → REJECTED

Invariants (enforced at create and re-checked at submit):
    - cumulative returned qty per grn_item ≤ grn_item.quantity_received
      (FOR UPDATE on the grn_item, excludes CANCELLED returns only)
    - dispatch computes stock_out_qty = min(quantity, remaining accepted,
      available on-hand); ONLY lines with stock_out_qty > 0 post ISSUE ledger
      rows (reference_type="PRN", reason="PURCHASE_RETURN")

Dispatch is the money+stock boundary: one transaction — status flip, stock-out,
and auto-creation of the ISSUED supplier debit note (SDN) for the return value.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.grn import GoodsReceiptNote, GRNItem
from app.models.inventory import InventoryLevel, WarehouseBin
from app.models.purchase_return import (
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnStatus,
    ReturnType,
)
from app.models.spo import SupplierPurchaseOrderItem
from app.models.supplier import Supplier
from app.services.customer_po_support import raise_error
from app.services.inventory_ledger import (
    available,
    first_active_bin,
    lock_or_create_level,
    post_issue,
)
from app.services.line_money import money
from app.services.purchase_return_number import PurchaseReturnNumberService
from app.services.supplier_debit_note_number import SupplierDebitNoteNumberService
from app.schemas.common import ErrorCode
from app.schemas.purchase_returns import PurchaseReturnCreate

from app.models.supplier_debit_note import (
    SupplierDebitNote,
    SupplierDebitNoteStatus,
)

ZERO = Decimal("0.00")

NON_CANCELLED = (
    PurchaseReturnStatus.DRAFT,
    PurchaseReturnStatus.PENDING_SUPPLIER,
    PurchaseReturnStatus.APPROVED,
    PurchaseReturnStatus.DISPATCHED,
    PurchaseReturnStatus.COMPLETED,
    PurchaseReturnStatus.REJECTED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_in(
    pr: PurchaseReturn, allowed: Sequence[PurchaseReturnStatus], action: str
) -> None:
    if pr.status not in allowed:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            f"Cannot {action} a purchase return in status {pr.status.value}",
        )


class PurchaseReturnService:
    # ------------------------------------------------------------------ reads
    @staticmethod
    async def get(
        session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> Optional[PurchaseReturn]:
        result = await session.execute(
            select(PurchaseReturn)
            .options(selectinload(PurchaseReturn.items))
            .where(
                PurchaseReturn.id == return_id,
                PurchaseReturn.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_id: Optional[uuid.UUID] = None,
        grn_id: Optional[uuid.UUID] = None,
        status_value: Optional[PurchaseReturnStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[PurchaseReturn], int]:
        stmt = (
            select(PurchaseReturn)
            .options(selectinload(PurchaseReturn.items))
            .where(PurchaseReturn.workspace_id == workspace_id)
        )
        if supplier_id is not None:
            stmt = stmt.where(PurchaseReturn.supplier_id == supplier_id)
        if grn_id is not None:
            stmt = stmt.where(PurchaseReturn.grn_id == grn_id)
        if status_value is not None:
            stmt = stmt.where(PurchaseReturn.status == status_value)

        count_result = await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        total = count_result.scalar()

        rows = (
            (
                await session.execute(
                    stmt.order_by(PurchaseReturn.created_at.desc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------- invariants
    @staticmethod
    async def _cumulative_returned(
        session: AsyncSession,
        grn_item_id: uuid.UUID,
        exclude_return_id: Optional[uuid.UUID] = None,
    ) -> Decimal:
        """Returned qty for a grn_item across non-CANCELLED returns."""
        stmt = (
            select(func.coalesce(func.sum(PurchaseReturnItem.quantity), ZERO))
            .select_from(PurchaseReturnItem)
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnItem.purchase_return_id,
            )
            .where(
                PurchaseReturnItem.grn_item_id == grn_item_id,
                PurchaseReturn.status.in_(NON_CANCELLED),
            )
        )
        if exclude_return_id is not None:
            stmt = stmt.where(PurchaseReturn.id != exclude_return_id)
        result = await session.execute(stmt)
        return Decimal(result.scalar() or 0)

    @classmethod
    async def _assert_quantity_available(
        cls,
        session: AsyncSession,
        grn_item_id: uuid.UUID,
        proposed: Decimal,
        exclude_return_id: Optional[uuid.UUID] = None,
    ) -> GRNItem:
        """FOR UPDATE lock the grn_item and enforce the received cap.

        `proposed` is the TOTAL quantity for this grn_item on the return being
        validated; `exclude_return_id` lets submit/dispatch exclude their own
        persisted rows (otherwise an at-cap return would reject itself).
        """
        grn_item = await cls._get_grn_item(session, grn_item_id)
        returned = await cls._cumulative_returned(
            session, grn_item_id, exclude_return_id=exclude_return_id
        )
        if returned + proposed > grn_item.quantity_received:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.RETURN_QTY_EXCEEDS_RECEIVED,
                (
                    f"Cannot return {proposed} units: only "
                    f"{grn_item.quantity_received - returned} units remain "
                    "returnable for this GRN line"
                ),
            )
        return grn_item

    @staticmethod
    async def _get_grn_item(session: AsyncSession, grn_item_id: uuid.UUID) -> GRNItem:
        result = await session.execute(
            select(GRNItem).where(GRNItem.id == grn_item_id).with_for_update()
        )
        grn_item = result.scalar_one_or_none()
        if grn_item is None:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "GRN item not found"
            )
        return grn_item

    @staticmethod
    def _group_quantities(items) -> list[tuple[uuid.UUID, Decimal]]:
        """Aggregate item.quantity by grn_item_id for a grouped cap check."""
        totals: dict[uuid.UUID, Decimal] = {}
        for item in items:
            totals[item.grn_item_id] = totals.get(item.grn_item_id, ZERO) + Decimal(
                item.quantity
            )
        return list(totals.items())

    # ------------------------------------------------------------- create
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: PurchaseReturnCreate,
    ) -> PurchaseReturn:
        supplier = await session.get(Supplier, data.supplier_id)
        if not supplier or supplier.workspace_id != workspace_id:
            raise_error(
                status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Supplier not found"
            )

        result = await session.execute(
            select(GoodsReceiptNote).where(
                GoodsReceiptNote.id == data.grn_id,
                GoodsReceiptNote.workspace_id == workspace_id,
            )
        )
        grn = result.scalar_one_or_none()
        if grn is None:
            raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "GRN not found")
        if grn.supplier_id != data.supplier_id:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "GRN does not belong to this supplier",
            )

        prn_number = await PurchaseReturnNumberService.generate_purchase_return_number(
            session, workspace_id
        )
        purchase_return = PurchaseReturn(
            workspace_id=workspace_id,
            supplier_id=data.supplier_id,
            grn_id=data.grn_id,
            prn_number=prn_number,
            return_date=data.return_date,
            status=PurchaseReturnStatus.DRAFT,
            reason=data.reason,
            created_by=user_id,
        )
        session.add(purchase_return)
        await session.flush()

        pending: dict[uuid.UUID, Decimal] = {}
        for item in data.items:
            pending[item.grn_item_id] = (
                pending.get(item.grn_item_id, ZERO) + item.quantity
            )
            await cls._assert_quantity_available(
                session, item.grn_item_id, pending[item.grn_item_id]
            )
            await cls._add_item(session, workspace_id, purchase_return.id, item)
        await session.flush()
        return purchase_return

    @staticmethod
    async def _add_item(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        purchase_return_id: uuid.UUID,
        item,
    ) -> None:
        grn_item = await PurchaseReturnService._get_grn_item(session, item.grn_item_id)
        spo_item = await session.get(SupplierPurchaseOrderItem, grn_item.spo_item_id)
        vat_rate = spo_item.vat_rate if spo_item and spo_item.vat_rate else Decimal("0")
        vat_amount = money(item.quantity * item.unit_price * vat_rate / Decimal("100"))
        session.add(
            PurchaseReturnItem(
                purchase_return_id=purchase_return_id,
                grn_item_id=grn_item.id,
                product_id=grn_item.product_id,
                internal_sku=grn_item.internal_sku,
                description=grn_item.description,
                uom_id=grn_item.uom_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                return_type=item.return_type,
                notes=item.notes,
            )
        )

    # ------------------------------------------------------------- transitions
    @classmethod
    async def submit_for_supplier_approval(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        record = await cls._require_return(
            session, workspace_id, return_id, load_items=True
        )
        _require_in(record, (PurchaseReturnStatus.DRAFT,), "submit")
        for grn_item_id, total in cls._group_quantities(record.items):
            await cls._assert_quantity_available(
                session,
                grn_item_id,
                total,
                exclude_return_id=record.id,
            )
        record.status = PurchaseReturnStatus.PENDING_SUPPLIER
        record.updated_at = _now()
        await session.flush()
        return record

    @classmethod
    async def approve(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        record = await cls._require_return(
            session, workspace_id, return_id, load_items=True
        )
        _require_in(record, (PurchaseReturnStatus.PENDING_SUPPLIER,), "approve")
        record.status = PurchaseReturnStatus.APPROVED
        record.updated_at = _now()
        await session.flush()
        return record

    @classmethod
    async def dispatch(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        """Dispatch: stock-out + auto-create the ISSUED supplier debit note."""
        record = await cls._require_return(
            session, workspace_id, return_id, load_items=True
        )
        _require_in(record, (PurchaseReturnStatus.APPROVED,), "dispatch")

        grn = await session.get(GoodsReceiptNote, record.grn_id)
        if grn is None or grn.workspace_id != workspace_id:
            raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "GRN not found")

        for grn_item_id, total in cls._group_quantities(record.items):
            await cls._assert_quantity_available(
                session,
                grn_item_id,
                total,
                exclude_return_id=record.id,
            )

        for item in record.items:
            stock_out, bin_row = await cls._compute_stock_out(
                session,
                workspace_id,
                grn,
                item,
                exclude_return_id=record.id,
            )
            item.stock_out_qty = stock_out
            if stock_out > ZERO and bin_row is not None:
                await post_issue(
                    session,
                    workspace_id,
                    item.product_id,
                    grn.warehouse_id,
                    bin_row.id,
                    stock_out,
                    record.created_by,
                    item.id,
                    reference_type="PRN",
                    reason="PURCHASE_RETURN",
                )

        record.status = PurchaseReturnStatus.DISPATCHED
        record.updated_at = _now()
        await session.flush()

        await cls._auto_create_debit_note(session, workspace_id, record)
        return record

    @classmethod
    async def _compute_stock_out(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        grn: GoodsReceiptNote,
        item: PurchaseReturnItem,
        exclude_return_id: Optional[uuid.UUID] = None,
    ) -> tuple[Decimal, Optional["WarehouseBin"]]:
        """stock_out_qty = min(qty, remaining accepted, available on-hand).

        Drains from the warehouse bin holding the most stock (single-bin
        semantics, matching delivery notes); returns ZERO when nothing is
        physically available to ship back.
        """
        grn_item = await cls._get_grn_item(session, item.grn_item_id)
        already_stocked = await cls._already_stocked(
            session,
            item.grn_item_id,
            item.id,
            exclude_return_id=exclude_return_id,
        )
        remaining_accepted = grn_item.quantity_accepted - already_stocked
        if remaining_accepted < ZERO:
            remaining_accepted = ZERO

        bin_row = await cls._resolve_stock_bin(
            session, workspace_id, item.product_id, grn.warehouse_id
        )
        if bin_row is None:
            return ZERO, None

        level = await lock_or_create_level(
            session,
            workspace_id,
            item.product_id,
            grn.warehouse_id,
            bin_row.id,
        )
        on_hand = available(level)
        if on_hand <= ZERO:
            return ZERO, bin_row
        return min(item.quantity, remaining_accepted, on_hand), bin_row

    @staticmethod
    async def _resolve_stock_bin(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
    ) -> Optional["WarehouseBin"]:
        """Bin with the most available stock, FOR UPDATE, else an active bin."""
        result = await session.execute(
            select(InventoryLevel)
            .where(
                InventoryLevel.workspace_id == workspace_id,
                InventoryLevel.product_id == product_id,
                InventoryLevel.warehouse_id == warehouse_id,
            )
            .with_for_update()
        )
        levels = list(result.scalars().all())
        if not levels:
            return await first_active_bin(session, warehouse_id, workspace_id)
        best = max(levels, key=lambda level: available(level))
        if available(best) <= ZERO:
            return None
        return await session.get(WarehouseBin, best.bin_id)

    @staticmethod
    async def _already_stocked(
        session: AsyncSession,
        grn_item_id: uuid.UUID,
        exclude_item_id: uuid.UUID,
        exclude_return_id: Optional[uuid.UUID] = None,
    ) -> Decimal:
        """Total stock_out_qty for a grn_item across all other return lines.

        When called at dispatch, exclude the entire current return so the
        remaining_accepted formula doesn't count THIS return's own rows.
        For GRN-004 auto-creation (no own rows yet), omit the return filter.
        """
        stmt = (
            select(func.coalesce(func.sum(PurchaseReturnItem.stock_out_qty), ZERO))
            .select_from(PurchaseReturnItem)
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnItem.purchase_return_id,
            )
            .where(
                PurchaseReturnItem.grn_item_id == grn_item_id,
                PurchaseReturnItem.id != exclude_item_id,
                PurchaseReturn.status.in_(NON_CANCELLED),
            )
        )
        if exclude_return_id is not None:
            stmt = stmt.where(PurchaseReturn.id != exclude_return_id)
        result = await session.execute(stmt)
        return Decimal(result.scalar() or 0)

    @staticmethod
    async def _auto_create_debit_note(
        session: AsyncSession, workspace_id: uuid.UUID, record: PurchaseReturn
    ) -> SupplierDebitNote:
        subtotal = money(sum((i.quantity * i.unit_price for i in record.items), ZERO))
        vat_amount = money(sum((i.vat_amount for i in record.items), ZERO))
        total_amount = money(subtotal + vat_amount)
        dn_number = await SupplierDebitNoteNumberService.generate_debit_note_number(
            session, workspace_id
        )
        note = SupplierDebitNote(
            workspace_id=workspace_id,
            supplier_id=record.supplier_id,
            purchase_return_id=record.id,
            dn_number=dn_number,
            amount=total_amount,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total_amount=total_amount,
            status=SupplierDebitNoteStatus.ISSUED,
            source_type="PURCHASE_RETURN",
            issue_date=record.return_date,
            created_by=record.created_by,
        )
        session.add(note)
        await session.flush()
        return note

    @classmethod
    async def complete(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        record = await cls._require_return(session, workspace_id, return_id)
        _require_in(record, (PurchaseReturnStatus.DISPATCHED,), "complete")
        record.status = PurchaseReturnStatus.COMPLETED
        record.updated_at = _now()
        await session.flush()
        return record

    @classmethod
    async def reject(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        record = await cls._require_return(session, workspace_id, return_id)
        _require_in(record, (PurchaseReturnStatus.PENDING_SUPPLIER,), "reject")
        record.status = PurchaseReturnStatus.REJECTED
        record.updated_at = _now()
        await session.flush()
        return record

    @classmethod
    async def cancel(
        cls, session: AsyncSession, workspace_id: uuid.UUID, return_id: uuid.UUID
    ) -> PurchaseReturn:
        record = await cls._require_return(session, workspace_id, return_id)
        _require_in(
            record,
            (PurchaseReturnStatus.DRAFT, PurchaseReturnStatus.PENDING_SUPPLIER),
            "cancel",
        )
        record.status = PurchaseReturnStatus.CANCELLED
        record.updated_at = _now()
        await session.flush()
        return record

    @staticmethod
    async def _require_return(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        return_id: uuid.UUID,
        load_items: bool = False,
    ) -> PurchaseReturn:
        stmt = select(PurchaseReturn).where(
            PurchaseReturn.id == return_id,
            PurchaseReturn.workspace_id == workspace_id,
        )
        if load_items:
            stmt = stmt.options(selectinload(PurchaseReturn.items))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Purchase return not found",
            )
        return record

    # ------------------------------------------------------------- GRN-004 hook
    @classmethod
    async def record_disposition_auto_items(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        grn: GoodsReceiptNote,
        grn_item: GRNItem,
    ) -> None:
        """Automatically create/accumulate return lines for rejected+damaged qty.

        Runs inside the GRN disposition transaction. Rejected qty maps to
        QUALITY_ISSUE, damaged qty to DAMAGE; both take the SPO unit price as
        the return price snapshot. Caps stay enforced (return can never exceed
        received).
        """
        spo_item = await session.get(SupplierPurchaseOrderItem, grn_item.spo_item_id)
        if spo_item is None:
            return
        unit_price = spo_item.unit_price

        result = await session.execute(
            select(PurchaseReturn)
            .options(selectinload(PurchaseReturn.items))
            .where(
                PurchaseReturn.workspace_id == workspace_id,
                PurchaseReturn.supplier_id == grn.supplier_id,
                PurchaseReturn.grn_id == grn.id,
                PurchaseReturn.status == PurchaseReturnStatus.DRAFT,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            prn_number = (
                await PurchaseReturnNumberService.generate_purchase_return_number(
                    session, workspace_id
                )
            )
            record = PurchaseReturn(
                workspace_id=workspace_id,
                supplier_id=grn.supplier_id,
                grn_id=grn.id,
                prn_number=prn_number,
                return_date=grn.received_date,
                status=PurchaseReturnStatus.DRAFT,
                reason="Auto-created from GRN disposition",
                created_by=user_id,
            )
            session.add(record)
            await session.flush()

        for return_type, qty in (
            (ReturnType.QUALITY_ISSUE, grn_item.quantity_rejected),
            (ReturnType.DAMAGE, grn_item.quantity_damaged),
        ):
            if qty <= ZERO:
                continue
            existing = await cls._existing_auto_item(
                session, record.id, grn_item.id, return_type
            )
            vat_rate = (
                spo_item.vat_rate if spo_item and spo_item.vat_rate else Decimal("0")
            )
            vat_amount = money(qty * unit_price * vat_rate / Decimal("100"))
            if existing is None:
                await cls._assert_quantity_available(session, grn_item.id, qty)
                session.add(
                    PurchaseReturnItem(
                        purchase_return_id=record.id,
                        grn_item_id=grn_item.id,
                        product_id=grn_item.product_id,
                        internal_sku=grn_item.internal_sku,
                        description=grn_item.description,
                        uom_id=grn_item.uom_id,
                        quantity=qty,
                        unit_price=unit_price,
                        vat_rate=vat_rate,
                        vat_amount=vat_amount,
                        stock_out_qty=ZERO,
                        return_type=return_type,
                    )
                )
            else:
                await cls._assert_quantity_available(session, grn_item.id, qty)
                existing.quantity = Decimal(existing.quantity) + Decimal(qty)
                existing.vat_amount = Decimal(existing.vat_amount) + vat_amount
        await session.flush()

    @staticmethod
    async def _existing_auto_item(
        session: AsyncSession,
        return_id: uuid.UUID,
        grn_item_id: uuid.UUID,
        return_type: ReturnType,
    ) -> Optional[PurchaseReturnItem]:
        result = await session.execute(
            select(PurchaseReturnItem).where(
                PurchaseReturnItem.purchase_return_id == return_id,
                PurchaseReturnItem.grn_item_id == grn_item_id,
                PurchaseReturnItem.return_type == return_type,
            )
        )
        return result.scalar_one_or_none()


purchase_return_service = PurchaseReturnService()
