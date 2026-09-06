"""Workspace-scoped multi-warehouse stock transfers.

Dispatch: source ``on_hand -= qty`` / ``in_transit += qty`` (swing account).
Receipt: clears ``in_transit`` at source, ``on_hand += received`` at dest.
Cancel of an IN_TRANSIT transfer returns the shipped qty to the source.
Every movement writes an immutable TRANSFER ledger row.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.inventory import (
    InventoryTransaction,
    TransactionType,
)
from app.models.stock_transfer import (
    StockTransfer,
    StockTransferItem,
    TransferStatus,
)
from app.schemas.common import ErrorCode
from app.schemas.stock_transfer import (
    StockTransferItemResponse,
    StockTransferListItem,
    StockTransferResponse,
)
from app.services.customer_po_support import raise_error
from app.services.inventory_ledger import (
    ZERO,
    available,
    first_active_bin,
    load_bin,
    load_product,
    load_warehouse,
    lock_or_create_level,
    qty_dec,
)
from app.services.transfer_number import TransferNumberService

_FAILING_STATES = (
    TransferStatus.RECEIVED,
    TransferStatus.CANCELLED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_bin(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    bin_id: Optional[uuid.UUID],
) -> uuid.UUID:
    if bin_id is not None:
        return (await load_bin(session, bin_id, warehouse_id, workspace_id)).id
    return (await first_active_bin(session, warehouse_id, workspace_id)).id


async def _load_transfer(
    session: AsyncSession, transfer_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[StockTransfer]:
    result = await session.execute(
        select(StockTransfer)
        .options(selectinload(StockTransfer.items))
        .where(StockTransfer.id == transfer_id)
        .where(StockTransfer.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def get_visible(
    session: AsyncSession, transfer_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[StockTransfer]:
    return await _load_transfer(session, transfer_id, workspace_id)


async def create_transfer(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_warehouse_id: uuid.UUID,
    destination_warehouse_id: uuid.UUID,
    notes: Optional[str],
    items: List[dict],
) -> StockTransfer:
    source_wh = await load_warehouse(session, source_warehouse_id, workspace_id)
    dest_wh = await load_warehouse(session, destination_warehouse_id, workspace_id)
    if source_wh.id == dest_wh.id:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "source and destination warehouses must differ",
            "destination_warehouse_id",
        )

    transfer_number = await TransferNumberService.generate_transfer_number(
        session, workspace_id
    )
    header = StockTransfer(
        workspace_id=workspace_id,
        transfer_number=transfer_number,
        source_warehouse_id=source_warehouse_id,
        destination_warehouse_id=destination_warehouse_id,
        status=TransferStatus.DRAFT,
        notes=notes,
        created_by=user_id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(header)
    await session.flush()

    for row in items:
        product = await load_product(session, row["product_id"], workspace_id)
        quantity = qty_dec(row["quantity"])
        source_bin_id = await _resolve_bin(
            session, workspace_id, source_warehouse_id, row.get("source_bin_id")
        )
        destination_bin_id = await _resolve_bin(
            session,
            workspace_id,
            destination_warehouse_id,
            row.get("destination_bin_id"),
        )
        session.add(
            StockTransferItem(
                transfer_id=header.id,
                product_id=product.id,
                quantity=quantity,
                received_quantity=ZERO,
                source_bin_id=source_bin_id,
                destination_bin_id=destination_bin_id,
                created_at=_now(),
                updated_at=_now(),
            )
        )

    await session.flush()
    return header


async def approve_transfer(
    session: AsyncSession, transfer_id: uuid.UUID, workspace_id: uuid.UUID
) -> StockTransfer:
    header = await _require(transfer_id, workspace_id, session)
    if header.status not in (TransferStatus.DRAFT,):
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only DRAFT transfers can be approved",
        )
    header.status = TransferStatus.APPROVED
    header.updated_at = _now()
    await session.flush()
    return header


async def dispatch_transfer(
    session: AsyncSession,
    transfer_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> StockTransfer:
    header = await _require(transfer_id, workspace_id, session)
    if header.status is not TransferStatus.APPROVED:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only APPROVED transfers can be dispatched",
        )
    for item in sorted(header.items, key=lambda line: line.created_at):
        level = await lock_or_create_level(
            session,
            workspace_id,
            item.product_id,
            header.source_warehouse_id,
            item.source_bin_id,
        )
        if available(level) < qty_dec(item.quantity):
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Insufficient available stock at source warehouse",
                "quantity",
            )
        level.on_hand = qty_dec(level.on_hand) - qty_dec(item.quantity)
        level.in_transit = qty_dec(level.in_transit) + qty_dec(item.quantity)
        level.updated_at = _now()
        session.add(
            InventoryTransaction(
                workspace_id=workspace_id,
                product_id=item.product_id,
                transaction_type=TransactionType.TRANSFER,
                quantity=-qty_dec(item.quantity),
                source_bin_id=item.source_bin_id,
                destination_bin_id=None,
                reference_type="TRANSFER",
                reference_id=header.id,
                user_id=user_id,
            )
        )
    header.status = TransferStatus.IN_TRANSIT
    header.dispatched_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


async def receive_transfer(
    session: AsyncSession,
    transfer_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    received_map: Dict[uuid.UUID, Decimal],
) -> StockTransfer:
    header = await _require(transfer_id, workspace_id, session)
    if header.status is not TransferStatus.IN_TRANSIT:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only IN_TRANSIT transfers can be received",
        )
    for item in sorted(header.items, key=lambda line: line.created_at):
        received = received_map.get(item.product_id, qty_dec(item.quantity))
        received = qty_dec(received)
        dispatched = qty_dec(item.quantity)
        if received < ZERO or received > dispatched:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "received quantity must be between 0 and the dispatched quantity",
                "quantity",
            )
        dest_level = await lock_or_create_level(
            session,
            workspace_id,
            item.product_id,
            header.destination_warehouse_id,
            item.destination_bin_id,
        )
        dest_level.on_hand = qty_dec(dest_level.on_hand) + received
        dest_level.updated_at = _now()
        source_level = await lock_or_create_level(
            session,
            workspace_id,
            item.product_id,
            header.source_warehouse_id,
            item.source_bin_id,
        )
        source_level.in_transit = qty_dec(source_level.in_transit) - dispatched
        source_level.updated_at = _now()
        item.received_quantity = received
        item.updated_at = _now()
        session.add(
            InventoryTransaction(
                workspace_id=workspace_id,
                product_id=item.product_id,
                transaction_type=TransactionType.TRANSFER,
                quantity=received,
                source_bin_id=None,
                destination_bin_id=item.destination_bin_id,
                reference_type="TRANSFER",
                reference_id=header.id,
                user_id=user_id,
            )
        )
    header.status = TransferStatus.RECEIVED
    header.received_at = _now()
    header.updated_at = _now()
    await session.flush()
    return header


async def cancel_transfer(
    session: AsyncSession,
    transfer_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: Optional[str],
) -> StockTransfer:
    header = await _require(transfer_id, workspace_id, session)
    if header.status in _FAILING_STATES:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "RECEIVED or CANCELLED transfers cannot be cancelled",
        )
    if header.status is TransferStatus.IN_TRANSIT:
        for item in sorted(header.items, key=lambda line: line.created_at):
            source_level = await lock_or_create_level(
                session,
                workspace_id,
                item.product_id,
                header.source_warehouse_id,
                item.source_bin_id,
            )
            source_level.on_hand = qty_dec(source_level.on_hand) + qty_dec(
                item.quantity
            )
            source_level.in_transit = qty_dec(source_level.in_transit) - qty_dec(
                item.quantity
            )
            source_level.updated_at = _now()
            session.add(
                InventoryTransaction(
                    workspace_id=workspace_id,
                    product_id=item.product_id,
                    transaction_type=TransactionType.TRANSFER,
                    quantity=qty_dec(item.quantity),
                    source_bin_id=item.source_bin_id,
                    destination_bin_id=None,
                    reference_type="TRANSFER_RETURN",
                    reference_id=header.id,
                    user_id=user_id,
                )
            )
    header.status = TransferStatus.CANCELLED
    header.cancelled_at = _now()
    header.cancellation_reason = reason
    header.updated_at = _now()
    await session.flush()
    return header


async def _require(
    transfer_id: uuid.UUID, workspace_id: uuid.UUID, session: AsyncSession
) -> StockTransfer:
    header = await _load_transfer(session, transfer_id, workspace_id)
    if header is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Transfer not found"
        )
    return header


def serialize(header: StockTransfer) -> StockTransferResponse:
    if header.items is None:
        header.items = []
    items = [
        StockTransferItemResponse(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            received_quantity=item.received_quantity,
            source_bin_id=item.source_bin_id,
            destination_bin_id=item.destination_bin_id,
            remaining=qty_dec(item.quantity) - qty_dec(item.received_quantity),
        )
        for item in header.items
    ]
    return StockTransferResponse(
        id=header.id,
        transfer_number=header.transfer_number,
        source_warehouse_id=header.source_warehouse_id,
        destination_warehouse_id=header.destination_warehouse_id,
        status=header.status,
        notes=header.notes,
        dispatched_at=header.dispatched_at,
        received_at=header.received_at,
        cancelled_at=header.cancelled_at,
        cancellation_reason=header.cancellation_reason,
        created_by=header.created_by,
        created_at=header.created_at,
        items=items,
    )


def serialize_list_item(header: StockTransfer) -> StockTransferListItem:
    if header.items is None:
        header.items = []
    return StockTransferListItem(
        id=header.id,
        transfer_number=header.transfer_number,
        source_warehouse_id=header.source_warehouse_id,
        destination_warehouse_id=header.destination_warehouse_id,
        status=header.status,
        notes=header.notes,
        created_at=header.created_at,
        item_count=len(header.items),
        total_quantity=sum(qty_dec(item.quantity) for item in header.items),
    )
