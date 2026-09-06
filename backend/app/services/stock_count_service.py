"""Workspace-scoped stock counting / reconciliation.

Expected quantities are snapshotted at schedule time from each bin's
``InventoryLevel.on_hand`` (physical count includes reserved and damaged).
Variance = counted − expected. Lines beyond ``COUNT_TOLERANCE_PERCENT`` are
flagged ``requires_approval`` and only applied after a manager approves the
count. Reconciliation moves each bin's ``on_hand`` by the variance delta and
writes an ADJUSTMENT ledger row per line. Reserved / damaged / in_transit are
never touched by a count.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.inventory import (
    InventoryLevel,
    InventoryTransaction,
    TransactionType,
)
from app.models.stock_count import (
    StockCount,
    StockCountItem,
    StockCountStatus,
)
from app.models.user import User, UserRole
from app.schemas.common import ErrorCode
from app.schemas.stock_count import (
    StockCountItemResponse,
    StockCountListItem,
    StockCountResponse,
)
from app.services.customer_po_support import raise_error
from app.services.inventory_ledger import (
    ZERO,
    load_warehouse,
    lock_or_create_level,
    qty_dec,
)
from app.services.stock_count_number import StockCountNumberService

COUNT_TOLERANCE_PERCENT = Decimal("2.00")
COUNT_REASON = "COUNT_CORRECTION"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _variance(item: StockCountItem) -> Decimal:
    if item.counted_quantity is None:
        return ZERO
    return qty_dec(item.counted_quantity) - qty_dec(item.expected_quantity)


def needs_approval(expected: Decimal, counted: Optional[Decimal]) -> bool:
    """Flag lines whose variance exceeds tolerance. No floats, no division."""
    if counted is None:
        return False
    expected = qty_dec(expected)
    counted = qty_dec(counted)
    variance = counted - expected
    if variance == ZERO:
        return False
    if expected == ZERO:
        return True
    return abs(variance) * Decimal("100") > expected * COUNT_TOLERANCE_PERCENT


def _require_manager(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may manage stock counts",
        )


async def _load_count(
    session: AsyncSession, count_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[StockCount]:
    result = await session.execute(
        select(StockCount)
        .options(selectinload(StockCount.items))
        .where(StockCount.id == count_id)
        .where(StockCount.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def get_visible(
    session: AsyncSession, count_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[StockCount]:
    return await _load_count(session, count_id, workspace_id)


async def _require(
    session: AsyncSession, count_id: uuid.UUID, workspace_id: uuid.UUID
) -> StockCount:
    header = await _load_count(session, count_id, workspace_id)
    if header is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Stock count not found"
        )
    return header


async def create_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    warehouse_id: uuid.UUID,
    notes: Optional[str],
) -> StockCount:
    _require_manager(user)
    await load_warehouse(session, warehouse_id, workspace_id)

    count_number = await StockCountNumberService.generate_count_number(
        session, workspace_id
    )
    header = StockCount(
        workspace_id=workspace_id,
        count_number=count_number,
        warehouse_id=warehouse_id,
        status=StockCountStatus.SCHEDULED,
        notes=notes,
        created_by=user.id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(header)
    await session.flush()

    result = await session.execute(
        select(InventoryLevel).where(
            InventoryLevel.workspace_id == workspace_id,
            InventoryLevel.warehouse_id == warehouse_id,
        )
    )
    levels = result.scalars().all()
    for level in levels:
        session.add(
            StockCountItem(
                count_id=header.id,
                product_id=level.product_id,
                bin_id=level.bin_id,
                expected_quantity=qty_dec(level.on_hand),
                counted_quantity=None,
                requires_approval=False,
                approved=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )

    await session.flush()
    return header


async def record_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    count_id: uuid.UUID,
    item_id: uuid.UUID,
    counted_quantity: Decimal,
    notes: Optional[str],
) -> StockCount:
    _require_manager(user)
    header = await _require(session, count_id, workspace_id)
    if header.status in (
        StockCountStatus.COMPLETED,
        StockCountStatus.RECONCILED,
        StockCountStatus.CANCELLED,
    ):
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Counts that are COMPLETED, RECONCILED or CANCELLED cannot be recorded against",
        )
    item = next((line for line in header.items if line.id == item_id), None)
    if item is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Stock count item not found"
        )
    item.counted_quantity = qty_dec(counted_quantity)
    if notes is not None:
        item.notes = notes
    item.updated_at = _now()
    if header.status is StockCountStatus.SCHEDULED:
        header.status = StockCountStatus.IN_PROGRESS
        header.started_at = _now()
        header.updated_at = _now()
    await session.flush()
    return header


async def complete_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    count_id: uuid.UUID,
) -> StockCount:
    _require_manager(user)
    header = await _require(session, count_id, workspace_id)
    if header.status in (
        StockCountStatus.COMPLETED,
        StockCountStatus.RECONCILED,
        StockCountStatus.CANCELLED,
    ):
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Counts that are COMPLETED, RECONCILED or CANCELLED cannot be completed again",
        )
    uncounted = [line for line in header.items if line.counted_quantity is None]
    if uncounted:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            f"All lines must be counted before completing ({len(uncounted)} uncounted)",
            "counted_quantity",
        )
    for line in header.items:
        line.requires_approval = needs_approval(
            line.expected_quantity, line.counted_quantity
        )
        line.updated_at = _now()
    header.status = StockCountStatus.COMPLETED
    header.completed_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


async def approve_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    count_id: uuid.UUID,
) -> StockCount:
    _require_manager(user)
    header = await _require(session, count_id, workspace_id)
    if header.status is not StockCountStatus.COMPLETED:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only COMPLETED counts can be approved",
        )
    for line in header.items:
        if line.requires_approval:
            line.approved = True
            line.updated_at = _now()
    header.approved_by = user.id
    header.approved_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


async def reconcile_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    count_id: uuid.UUID,
) -> StockCount:
    _require_manager(user)
    header = await _require(session, count_id, workspace_id)
    if header.status is not StockCountStatus.COMPLETED:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only COMPLETED counts can be reconciled",
        )
    pending = [
        line for line in header.items if line.requires_approval and not line.approved
    ]
    if pending:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            f"Reconciliation requires approving {len(pending)} variance line(s) first",
            "approved",
        )
    for item in sorted(header.items, key=lambda line: line.created_at):
        variance = _variance(item)
        if variance == ZERO:
            continue
        level = await lock_or_create_level(
            session,
            workspace_id,
            item.product_id,
            header.warehouse_id,
            item.bin_id,
        )
        level.on_hand = qty_dec(level.on_hand) + variance
        level.updated_at = _now()
        session.add(
            InventoryTransaction(
                workspace_id=workspace_id,
                product_id=item.product_id,
                transaction_type=TransactionType.ADJUSTMENT,
                quantity=variance,
                source_bin_id=item.bin_id if variance < ZERO else None,
                destination_bin_id=item.bin_id if variance > ZERO else None,
                reference_type="COUNT",
                reference_id=header.id,
                reason=COUNT_REASON,
                notes=f"{header.count_number} variance",
                user_id=user.id,
            )
        )
    header.status = StockCountStatus.RECONCILED
    header.reconciled_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


async def cancel_count(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    count_id: uuid.UUID,
) -> StockCount:
    _require_manager(user)
    header = await _require(session, count_id, workspace_id)
    if header.status in (
        StockCountStatus.COMPLETED,
        StockCountStatus.RECONCILED,
        StockCountStatus.CANCELLED,
    ):
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "COMPLETED, RECONCILED or CANCELLED counts cannot be cancelled",
        )
    header.status = StockCountStatus.CANCELLED
    header.cancelled_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


def serialize(header: StockCount) -> StockCountResponse:
    if header.items is None:
        header.items = []
    items = [
        StockCountItemResponse(
            id=item.id,
            product_id=item.product_id,
            bin_id=item.bin_id,
            expected_quantity=item.expected_quantity,
            counted_quantity=item.counted_quantity,
            requires_approval=item.requires_approval,
            approved=item.approved,
            variance=_variance(item),
        )
        for item in header.items
    ]
    return StockCountResponse(
        id=header.id,
        count_number=header.count_number,
        warehouse_id=header.warehouse_id,
        status=header.status,
        notes=header.notes,
        started_at=header.started_at,
        completed_at=header.completed_at,
        reconciled_at=header.reconciled_at,
        cancelled_at=header.cancelled_at,
        approved_by=header.approved_by,
        approved_at=header.approved_at,
        created_by=header.created_by,
        created_at=header.created_at,
        items=items,
    )


def serialize_list_item(header: StockCount) -> StockCountListItem:
    if header.items is None:
        header.items = []
    return StockCountListItem(
        id=header.id,
        count_number=header.count_number,
        warehouse_id=header.warehouse_id,
        status=header.status,
        notes=header.notes,
        created_at=header.created_at,
        item_count=len(header.items),
        count_in_progress=sum(
            1 for line in header.items if line.counted_quantity is not None
        ),
        flagged_lines=sum(1 for line in header.items if line.requires_approval),
    )
