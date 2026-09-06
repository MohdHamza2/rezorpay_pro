"""Stock reservations from Customer POs (Wave 18).

A reservation is a header + per-(product, warehouse, bin) item lines. Creating
one increments the matching ``InventoryLevel.reserved``; dispatch (DN
confirm), cancel, and expiry decrement them, keeping the invariant

    InventoryLevel.reserved == SUM(quantity - quantity_consumed)
    over ACTIVE items of that (product, warehouse, bin)

so that ``available = on_hand - reserved - damaged`` is honoured everywhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Set

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.stock_reservation import (
    RESERVATION_TTL_DAYS,
    ReservationStatus,
    StockReservation,
    StockReservationItem,
)
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error
from app.services.delivery_note_support import load_lpo, resolve_bin_id
from app.services.inventory_ledger import (
    ZERO,
    available,
    load_warehouse,
    lock_or_create_level,
    qty_dec,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at() -> datetime:
    return now() + timedelta(days=RESERVATION_TTL_DAYS)


async def get_visible(
    session: AsyncSession,
    reservation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Optional[StockReservation]:
    query = (
        select(StockReservation)
        .options(selectinload(StockReservation.items))
        .where(
            StockReservation.id == reservation_id,
            StockReservation.workspace_id == workspace_id,
        )
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def active_remaining_by_cpo_item(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    cpo_id: uuid.UUID,
) -> Dict[uuid.UUID, Decimal]:
    result = await session.execute(
        select(
            StockReservationItem.customer_purchase_order_item_id,
            func.coalesce(
                func.sum(StockReservationItem.quantity)
                - func.coalesce(func.sum(StockReservationItem.quantity_consumed), ZERO),
                ZERO,
            ),
        )
        .join(
            StockReservation,
            StockReservation.id == StockReservationItem.reservation_id,
        )
        .where(
            StockReservation.workspace_id == workspace_id,
            StockReservation.customer_purchase_order_id == cpo_id,
            StockReservationItem.status == ReservationStatus.ACTIVE,
        )
        .group_by(StockReservationItem.customer_purchase_order_item_id)
    )
    return {
        item_id: qty_dec(qty) for item_id, qty in result.all() if item_id is not None
    }


async def create_reservation(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    cpo_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    items: List[dict],
) -> StockReservation:
    """Reserve LPO lines against one warehouse. Locks levels FOR UPDATE."""
    lpo = await load_lpo(session, cpo_id, workspace_id)
    await load_warehouse(session, warehouse_id, workspace_id)
    lpo_items = {item.id: item for item in lpo.items}
    reserved_map = await active_remaining_by_cpo_item(session, workspace_id, cpo_id)

    header = StockReservation(
        workspace_id=workspace_id,
        customer_purchase_order_id=cpo_id,
        status=ReservationStatus.ACTIVE,
        expires_at=_expires_at(),
        created_at=now(),
        updated_at=now(),
    )
    session.add(header)
    await session.flush()

    for row in items:
        item_id = row["customer_purchase_order_item_id"]
        item = lpo_items.get(item_id)
        if item is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "LPO line not found",
                "customer_purchase_order_item_id",
            )
        if item.product_id is None:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot reserve an ad-hoc line without a product",
                "customer_purchase_order_item_id",
            )
        qty = qty_dec(row["quantity"])
        undelivered = qty_dec(item.quantity) - qty_dec(item.quantity_delivered)
        already = reserved_map.get(item_id, ZERO)
        if qty + already > undelivered:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot reserve more than the undelivered quantity",
                "quantity",
            )
        bin_id = await resolve_bin_id(
            session, warehouse_id, workspace_id, row.get("bin_id")
        )
        level = await lock_or_create_level(
            session, workspace_id, item.product_id, warehouse_id, bin_id
        )
        if available(level) < qty:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Insufficient available stock",
                "quantity",
            )
        level.reserved = qty_dec(level.reserved) + qty
        level.updated_at = now()
        session.add(
            StockReservationItem(
                reservation_id=header.id,
                customer_purchase_order_item_id=item_id,
                product_id=item.product_id,
                warehouse_id=warehouse_id,
                bin_id=bin_id,
                quantity=qty,
                quantity_consumed=ZERO,
                status=ReservationStatus.ACTIVE,
                created_at=now(),
                updated_at=now(),
            )
        )
        reserved_map[item_id] = already + qty
    await session.flush()
    return await get_visible(session, header.id, workspace_id) or header


async def _release_items(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    reservation: StockReservation,
    release_status: ReservationStatus,
) -> None:
    for item in reservation.items or []:
        if item.status != ReservationStatus.ACTIVE:
            continue
        remaining = qty_dec(item.quantity) - qty_dec(item.quantity_consumed)
        if remaining > ZERO:
            level = await lock_or_create_level(
                session,
                workspace_id,
                item.product_id,
                item.warehouse_id,
                item.bin_id,
            )
            level.reserved = max(ZERO, qty_dec(level.reserved) - remaining)
            level.updated_at = now()
        item.status = release_status
        item.updated_at = now()


async def cancel_reservation(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    reservation_id: uuid.UUID,
    reason: Optional[str],
) -> StockReservation:
    reservation = await get_visible(
        session, reservation_id, workspace_id, for_update=True
    )
    if reservation is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Reservation not found"
        )
    if reservation.status != ReservationStatus.ACTIVE:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.INVALID_STATE,
            "Only ACTIVE reservations can be cancelled",
        )
    await _release_items(
        session, workspace_id, reservation, ReservationStatus.CANCELLED
    )
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = now()
    reservation.cancellation_reason = reason
    reservation.updated_at = now()
    return reservation


async def expire_due(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    at: Optional[datetime] = None,
) -> int:
    cutoff = at or now()
    result = await session.execute(
        select(StockReservation)
        .options(selectinload(StockReservation.items))
        .where(
            StockReservation.workspace_id == workspace_id,
            StockReservation.status == ReservationStatus.ACTIVE,
            StockReservation.expires_at <= cutoff,
        )
        .with_for_update()
    )
    reservations = list(result.scalars().all())
    if not reservations:
        return 0
    for reservation in reservations:
        await _release_items(
            session, workspace_id, reservation, ReservationStatus.EXPIRED
        )
        reservation.status = ReservationStatus.EXPIRED
        reservation.updated_at = now()
    return len(reservations)


async def release_for_dispatch(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    cpo_item_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: Decimal,
) -> Decimal:
    """Consume ACTIVE reservations (FIFO by created_at) for an LPO line.

    Decrements ``InventoryLevel.reserved``; fully-consumed items become
    DISPATCHED. Returns the reserved quantity consumed — the rest of the ship
    qty comes from unreserved stock as today.
    """
    qty = qty_dec(quantity)
    if qty <= ZERO:
        return ZERO
    result = await session.execute(
        select(StockReservationItem)
        .join(
            StockReservation,
            StockReservation.id == StockReservationItem.reservation_id,
        )
        .where(
            StockReservation.workspace_id == workspace_id,
            StockReservationItem.customer_purchase_order_item_id == cpo_item_id,
            StockReservationItem.product_id == product_id,
            StockReservationItem.status == ReservationStatus.ACTIVE,
            StockReservationItem.quantity > StockReservationItem.quantity_consumed,
        )
        .order_by(
            StockReservationItem.created_at.asc(),
            StockReservationItem.id.asc(),
        )
    )
    items = list(result.scalars().all())
    consumed = ZERO
    impacted: Set[uuid.UUID] = set()
    for item in items:
        remaining = qty_dec(item.quantity) - qty_dec(item.quantity_consumed)
        if remaining <= ZERO:
            continue
        take = min(remaining, qty)
        level = await lock_or_create_level(
            session, workspace_id, product_id, item.warehouse_id, item.bin_id
        )
        level.reserved = max(ZERO, qty_dec(level.reserved) - take)
        level.updated_at = now()
        item.quantity_consumed = qty_dec(item.quantity_consumed) + take
        item.updated_at = now()
        if qty_dec(item.quantity_consumed) >= qty_dec(item.quantity):
            item.status = ReservationStatus.DISPATCHED
            item.dispatched_at = now()
        impacted.add(item.reservation_id)
        consumed += take
        qty -= take
        if qty <= ZERO:
            break
    if impacted:
        await _refresh_header_statuses(session, impacted)
    return consumed


async def _refresh_header_statuses(
    session: AsyncSession, reservation_ids: Set[uuid.UUID]
) -> None:
    if not reservation_ids:
        return
    result = await session.execute(
        select(StockReservation)
        .options(selectinload(StockReservation.items))
        .where(StockReservation.id.in_(reservation_ids))
    )
    for reservation in result.scalars().all():
        items = reservation.items or []
        if not items:
            continue
        if all(item.status == ReservationStatus.DISPATCHED for item in items):
            reservation.status = ReservationStatus.DISPATCHED
            reservation.updated_at = now()


def serialize(reservation: StockReservation):
    from app.schemas.stock_reservation import (
        StockReservationItemResponse,
        StockReservationResponse,
    )

    items = []
    for item in reservation.items or []:
        payload = StockReservationItemResponse.model_validate(item)
        items.append(
            payload.model_copy(
                update={
                    "remaining": qty_dec(item.quantity)
                    - qty_dec(item.quantity_consumed)
                }
            )
        )
    payload = StockReservationResponse.model_validate(reservation)
    return payload.model_copy(update={"items": items})


def serialize_list_item(reservation: StockReservation):
    from app.schemas.stock_reservation import ReservationListItem

    items = reservation.items or []
    data = {
        "id": reservation.id,
        "customer_purchase_order_id": reservation.customer_purchase_order_id,
        "status": reservation.status,
        "expires_at": reservation.expires_at,
        "created_at": reservation.created_at,
        "warehouse_id": items[0].warehouse_id if items else None,
    }
    return ReservationListItem.model_validate(data)
