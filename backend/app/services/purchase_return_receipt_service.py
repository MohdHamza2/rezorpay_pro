"""Purchase Return Receipt Service — Wave 31 Item 2.8.

Handles the warehouse receiving of goods returned to a supplier
that are sent back to us (replacement, repair, etc.).
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

from app.models.grn import GoodsReceiptNote
from app.models.inventory import WarehouseBin
from app.models.purchase_return import (
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnStatus,
    PurchaseReturnReceipt,
    PurchaseReturnReceiptItem,
    PurchaseReturnReceiptStatus,
)
from app.services.customer_po_support import raise_error
from app.services.inventory_ledger import (
    available,
    lock_or_create_level,
    post_issue,
)
from app.services.purchase_return_receipt_number import (
    PurchaseReturnReceiptNumberService,
)
from app.schemas.common import ErrorCode
from app.schemas.purchase_return_receipts import PurchaseReturnReceiptCreate

ZERO = Decimal("0.00")

NON_CANCELLED_RETURN_STATUSES = (
    PurchaseReturnStatus.DRAFT,
    PurchaseReturnStatus.PENDING_SUPPLIER,
    PurchaseReturnStatus.APPROVED,
    PurchaseReturnStatus.DISPATCHED,
    PurchaseReturnStatus.COMPLETED,
    PurchaseReturnStatus.REJECTED,
)

NON_CANCELLED_RECEIPT_STATUSES = (
    PurchaseReturnReceiptStatus.DRAFT,
    PurchaseReturnReceiptStatus.RECEIVING,
    PurchaseReturnReceiptStatus.RECEIVED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_in(record, allowed: Sequence, action: str) -> None:
    if record.status not in allowed:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            f"Cannot {action} a purchase return receipt in status {record.status.value}",
        )


class PurchaseReturnReceiptService:
    # ------------------------------------------------------------------ reads
    @staticmethod
    async def get(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> Optional[PurchaseReturnReceipt]:
        result = await session.execute(
            select(PurchaseReturnReceipt)
            .options(selectinload(PurchaseReturnReceipt.items))
            .where(
                PurchaseReturnReceipt.id == receipt_id,
                PurchaseReturnReceipt.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        purchase_return_id: Optional[uuid.UUID] = None,
        status_value: Optional[PurchaseReturnReceiptStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[PurchaseReturnReceipt], int]:
        stmt = (
            select(PurchaseReturnReceipt)
            .options(selectinload(PurchaseReturnReceipt.items))
            .where(PurchaseReturnReceipt.workspace_id == workspace_id)
        )
        if purchase_return_id is not None:
            stmt = stmt.where(
                PurchaseReturnReceipt.purchase_return_id == purchase_return_id
            )
        if status_value is not None:
            stmt = stmt.where(PurchaseReturnReceipt.status == status_value)

        count_result = await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        total = count_result.scalar()

        rows = (
            (
                await session.execute(
                    stmt.order_by(PurchaseReturnReceipt.created_at.desc())
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
    async def _cumulative_received(
        session: AsyncSession,
        purchase_return_item_id: uuid.UUID,
        exclude_receipt_id: Optional[uuid.UUID] = None,
    ) -> Decimal:
        """Received qty for a purchase_return_item across non-CANCELLED receipts."""
        stmt = (
            select(func.coalesce(func.sum(PurchaseReturnReceiptItem.quantity), ZERO))
            .select_from(PurchaseReturnReceiptItem)
            .join(
                PurchaseReturnReceipt,
                PurchaseReturnReceipt.id
                == PurchaseReturnReceiptItem.purchase_return_receipt_id,
            )
            .where(
                PurchaseReturnReceiptItem.purchase_return_item_id
                == purchase_return_item_id,
                PurchaseReturnReceipt.status.in_(NON_CANCELLED_RECEIPT_STATUSES),
            )
        )
        if exclude_receipt_id is not None:
            stmt = stmt.where(PurchaseReturnReceipt.id != exclude_receipt_id)
        result = await session.execute(stmt)
        return Decimal(result.scalar() or 0)

    @classmethod
    async def _assert_quantity_receivable(
        cls,
        session: AsyncSession,
        purchase_return_item_id: uuid.UUID,
        proposed: Decimal,
        exclude_receipt_id: Optional[uuid.UUID] = None,
    ) -> PurchaseReturnItem:
        """FOR UPDATE lock the purchase_return_item and enforce the dispatched cap."""
        purchase_return_item = await cls._get_purchase_return_item(
            session, purchase_return_item_id
        )
        already_received = await cls._cumulative_received(
            session, purchase_return_item_id, exclude_receipt_id=exclude_receipt_id
        )
        # Can only receive up to what was dispatched (stock_out_qty)
        max_receivable = purchase_return_item.stock_out_qty
        if already_received + proposed > max_receivable:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                (
                    f"Cannot receive {proposed} units: only "
                    f"{max_receivable - already_received} units remain "
                    "receivable for this return line (limited by dispatched qty)"
                ),
            )
        return purchase_return_item

    @staticmethod
    async def _get_purchase_return_item(
        session: AsyncSession, purchase_return_item_id: uuid.UUID
    ) -> PurchaseReturnItem:
        result = await session.execute(
            select(PurchaseReturnItem)
            .where(PurchaseReturnItem.id == purchase_return_item_id)
            .with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Purchase return item not found",
            )
        return item

    @staticmethod
    def _group_quantities(items) -> list[tuple[uuid.UUID, Decimal]]:
        """Aggregate item.quantity by purchase_return_item_id for a grouped cap check."""
        totals: dict[uuid.UUID, Decimal] = {}
        for item in items:
            totals[item.purchase_return_item_id] = totals.get(
                item.purchase_return_item_id, ZERO
            ) + Decimal(item.quantity)
        return list(totals.items())

    # ------------------------------------------------------------- create
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: PurchaseReturnReceiptCreate,
    ) -> PurchaseReturnReceipt:
        # Verify the purchase return exists and is in a valid state for receiving
        result = await session.execute(
            select(PurchaseReturn)
            .options(selectinload(PurchaseReturn.items))
            .where(
                PurchaseReturn.id == data.purchase_return_id,
                PurchaseReturn.workspace_id == workspace_id,
            )
        )
        purchase_return = result.scalar_one_or_none()
        if not purchase_return:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Purchase return not found",
            )

        if purchase_return.status not in (
            PurchaseReturnStatus.DISPATCHED,
            PurchaseReturnStatus.COMPLETED,
        ):
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                f"Cannot create receipt for purchase return in status {purchase_return.status.value}. "
                "Must be DISPATCHED or COMPLETED.",
            )

        # Verify warehouse belongs to workspace
        warehouse_result = await session.execute(
            select(GoodsReceiptNote.warehouse_id).where(
                GoodsReceiptNote.id == purchase_return.grn_id,
                GoodsReceiptNote.workspace_id == workspace_id,
            )
        )
        grn_warehouse_id = warehouse_result.scalar_one_or_none()
        if grn_warehouse_id is None:
            raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "GRN not found")

        # If no bin specified, use the original GRN warehouse; otherwise validate the bin
        warehouse_id = data.warehouse_id if data.warehouse_id else grn_warehouse_id

        if data.bin_id:
            bin_result = await session.execute(
                select(WarehouseBin).where(
                    WarehouseBin.id == data.bin_id,
                    WarehouseBin.warehouse_id == warehouse_id,
                    WarehouseBin.workspace_id == workspace_id,
                    WarehouseBin.is_active.is_(True),
                )
            )
            bin_row = bin_result.scalar_one_or_none()
            if not bin_row:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Warehouse bin not found or not active",
                )
        else:
            # Default to first active bin in the warehouse
            bin_result = await session.execute(
                select(WarehouseBin)
                .where(
                    WarehouseBin.warehouse_id == warehouse_id,
                    WarehouseBin.workspace_id == workspace_id,
                    WarehouseBin.is_active.is_(True),
                )
                .limit(1)
            )
            bin_row = bin_result.scalar_one_or_none()
            if not bin_row:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.VALIDATION_ERROR,
                    "Warehouse must have at least one active bin for receipt",
                )

        # Validate items against the purchase return
        pending: dict[uuid.UUID, Decimal] = {}
        for item in data.items:
            # Verify the purchase_return_item belongs to this purchase_return
            pri_result = await session.execute(
                select(PurchaseReturnItem).where(
                    PurchaseReturnItem.id == item.purchase_return_item_id,
                    PurchaseReturnItem.purchase_return_id == purchase_return.id,
                )
            )
            pri = pri_result.scalar_one_or_none()
            if not pri:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.INVALID_STATE,
                    "Purchase return item does not belong to this purchase return",
                )

            pending[item.purchase_return_item_id] = (
                pending.get(item.purchase_return_item_id, ZERO) + item.quantity
            )

            # Check that we're not receiving more than what was dispatched
            await cls._assert_quantity_receivable(
                session,
                item.purchase_return_item_id,
                pending[item.purchase_return_item_id],
            )

        rrn_number = await PurchaseReturnReceiptNumberService.generate_receipt_number(
            session, workspace_id
        )
        receipt = PurchaseReturnReceipt(
            workspace_id=workspace_id,
            purchase_return_id=data.purchase_return_id,
            warehouse_id=warehouse_id,
            bin_id=data.bin_id if data.bin_id else bin_row.id,
            receipt_number=rrn_number,
            receipt_date=data.receipt_date,
            status=PurchaseReturnReceiptStatus.DRAFT,
            received_by=user_id,
            notes=data.notes,
        )
        session.add(receipt)
        await session.flush()

        for item in data.items:
            session.add(
                PurchaseReturnReceiptItem(
                    purchase_return_receipt_id=receipt.id,
                    purchase_return_item_id=item.purchase_return_item_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    condition=item.condition,
                    bin_id=item.bin_id if item.bin_id else bin_row.id,
                    notes=item.notes,
                )
            )
        await session.flush()
        return receipt

    # ------------------------------------------------------------- transitions
    @classmethod
    async def confirm_receipt(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> PurchaseReturnReceipt:
        """Confirm receipt: post RECEIPT ledger, update status, update received_qty on return items."""
        record = await cls._require_receipt(
            session, workspace_id, receipt_id, load_items=True
        )
        _require_in(record, (PurchaseReturnReceiptStatus.DRAFT,), "confirm")

        # Re-verify caps at confirm time
        for pri_id, total in cls._group_quantities(record.items):
            await cls._assert_quantity_receivable(
                session,
                pri_id,
                total,
                exclude_receipt_id=record.id,
            )

        # Post RECEIPT ledger entries
        for item in record.items:
            # Use the receipt's bin or default to the receipt's bin
            bin_id = item.bin_id if item.bin_id else record.bin_id
            if not bin_id:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.VALIDATION_ERROR,
                    "No bin available for receipt",
                )

            level = await lock_or_create_level(
                session,
                workspace_id,
                item.product_id,
                record.warehouse_id,
                bin_id,
            )
            # Post RECEIPT transaction
            await post_issue(
                session,
                workspace_id,
                item.product_id,
                record.warehouse_id,
                bin_id,
                item.quantity,  # positive for receipt
                record.received_by,
                item.id,
                reference_type="PRN_RECEIPT",
                reason="PURCHASE_RETURN_RECEIPT",
            )

            level.on_hand = available(level) + item.quantity
            level.updated_at = _now()

        # Update received_qty on purchase_return_items
        for item in record.items:
            pri_result = await session.execute(
                select(PurchaseReturnItem).where(
                    PurchaseReturnItem.id == item.purchase_return_item_id
                )
            )
            pri = pri_result.scalar_one_or_none()
            if pri:
                pri.received_qty = Decimal(pri.received_qty) + item.quantity
                session.add(pri)

        record.status = PurchaseReturnReceiptStatus.RECEIVED
        record.updated_at = _now()
        await session.flush()

        # Check if all dispatched quantities have been received
        purchase_return = await session.get(PurchaseReturn, record.purchase_return_id)
        if purchase_return:
            await cls._update_purchase_return_status(session, purchase_return)

        return record

    @classmethod
    async def _update_purchase_return_status(
        cls,
        session: AsyncSession,
        purchase_return: PurchaseReturn,
    ) -> None:
        """Update purchase return status to RECEIVED_BACK if all dispatched quantities received."""
        # Check if all items have received_qty >= stock_out_qty
        all_received = True
        for item in purchase_return.items:
            if item.stock_out_qty > item.received_qty:
                all_received = False
                break

        if all_received and purchase_return.status in (
            PurchaseReturnStatus.DISPATCHED,
            PurchaseReturnStatus.COMPLETED,
        ):
            purchase_return.status = PurchaseReturnStatus.RECEIVED_BACK
            purchase_return.updated_at = _now()

    @classmethod
    async def cancel_receipt(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> PurchaseReturnReceipt:
        """Cancel a confirmed receipt: reverse the RECEIPT ledger entries."""
        record = await cls._require_receipt(
            session, workspace_id, receipt_id, load_items=True
        )
        _require_in(record, (PurchaseReturnReceiptStatus.RECEIVED,), "cancel")

        # Reverse RECEIPT ledger entries (post ISSUE with +qty)
        for item in record.items:
            bin_id = item.bin_id if item.bin_id else record.bin_id
            if not bin_id:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.VALIDATION_ERROR,
                    "No bin available for receipt cancellation",
                )

            level = await lock_or_create_level(
                session,
                workspace_id,
                item.product_id,
                record.warehouse_id,
                bin_id,
            )
            if available(level) < item.quantity:
                raise_error(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.VALIDATION_ERROR,
                    "Insufficient on-hand stock to cancel receipt",
                )

            await post_issue(
                session,
                workspace_id,
                item.product_id,
                record.warehouse_id,
                bin_id,
                item.quantity,  # positive quantity for reverse (ISSUE +qty)
                record.received_by,
                item.id,
                reference_type="PRN_RECEIPT_CANCEL",
                reason="PURCHASE_RETURN_RECEIPT_CANCEL",
                reverse=True,
            )

            level.on_hand = available(level) - item.quantity
            level.updated_at = _now()

        # Update received_qty on purchase_return_items
        for item in record.items:
            pri_result = await session.execute(
                select(PurchaseReturnItem).where(
                    PurchaseReturnItem.id == item.purchase_return_item_id
                )
            )
            pri = pri_result.scalar_one_or_none()
            if pri:
                pri.received_qty = Decimal(pri.received_qty) - item.quantity
                session.add(pri)

        record.status = PurchaseReturnReceiptStatus.CANCELLED
        record.updated_at = _now()
        await session.flush()

        # Update purchase return status if needed
        purchase_return = await session.get(PurchaseReturn, record.purchase_return_id)
        if purchase_return:
            await cls._update_purchase_return_status(session, purchase_return)

        return record

    @staticmethod
    async def _require_receipt(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        receipt_id: uuid.UUID,
        load_items: bool = False,
    ) -> PurchaseReturnReceipt:
        stmt = select(PurchaseReturnReceipt).where(
            PurchaseReturnReceipt.id == receipt_id,
            PurchaseReturnReceipt.workspace_id == workspace_id,
        )
        if load_items:
            stmt = stmt.options(selectinload(PurchaseReturnReceipt.items))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Purchase return receipt not found",
            )
        return record


purchase_return_receipt_service = PurchaseReturnReceiptService()
