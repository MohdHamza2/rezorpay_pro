"""Workspace-scoped inventory ISSUE / ADJUSTMENT posting.

Mirrors GRN FOR UPDATE + first-bin create, but always filters workspace_id.
Never uses float. Delivery notes must not call adjust().
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.inventory import (
    InventoryLevel,
    InventoryTransaction,
    TransactionType,
    Warehouse,
    WarehouseBin,
)
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error

ZERO = Decimal("0.00")
FILS = Decimal("0.01")


def qty_dec(value: Decimal) -> Decimal:
    """Coerce to Decimal without float."""
    return Decimal(str(value))


def available(level: InventoryLevel) -> Decimal:
    return qty_dec(level.on_hand) - qty_dec(level.reserved) - qty_dec(level.damaged)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def load_warehouse(
    session: AsyncSession, warehouse_id: uuid.UUID, workspace_id: uuid.UUID
) -> Warehouse:
    result = await session.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.workspace_id == workspace_id,
        )
    )
    warehouse = result.scalar_one_or_none()
    if warehouse is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Warehouse not found"
        )
    if not warehouse.is_active:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "Warehouse is inactive",
            "warehouse_id",
        )
    return warehouse


async def load_bin(
    session: AsyncSession,
    bin_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> WarehouseBin:
    result = await session.execute(
        select(WarehouseBin)
        .join(Warehouse, Warehouse.id == WarehouseBin.warehouse_id)
        .where(
            WarehouseBin.id == bin_id,
            WarehouseBin.warehouse_id == warehouse_id,
            Warehouse.workspace_id == workspace_id,
        )
    )
    wh_bin = result.scalar_one_or_none()
    if wh_bin is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Bin not found")
    if not wh_bin.is_active:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "Bin is inactive",
            "bin_id",
        )
    return wh_bin


async def first_active_bin(
    session: AsyncSession, warehouse_id: uuid.UUID, workspace_id: uuid.UUID
) -> WarehouseBin:
    result = await session.execute(
        select(WarehouseBin)
        .join(Warehouse, Warehouse.id == WarehouseBin.warehouse_id)
        .where(
            WarehouseBin.warehouse_id == warehouse_id,
            Warehouse.workspace_id == workspace_id,
            WarehouseBin.is_active.is_(True),
        )
        .order_by(WarehouseBin.code.asc())
        .limit(1)
    )
    wh_bin = result.scalar_one_or_none()
    if wh_bin is None:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "Warehouse must have at least one active bin",
            "bin_id",
        )
    return wh_bin


async def resolve_header_bin(
    session: AsyncSession,
    warehouse_id: uuid.UUID,
    workspace_id: uuid.UUID,
    bin_id: Optional[uuid.UUID],
) -> WarehouseBin:
    await load_warehouse(session, warehouse_id, workspace_id)
    if bin_id is not None:
        return await load_bin(session, bin_id, warehouse_id, workspace_id)
    return await first_active_bin(session, warehouse_id, workspace_id)


async def lock_or_create_level(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    bin_id: uuid.UUID,
) -> InventoryLevel:
    result = await session.execute(
        select(InventoryLevel)
        .where(
            InventoryLevel.workspace_id == workspace_id,
            InventoryLevel.product_id == product_id,
            InventoryLevel.warehouse_id == warehouse_id,
            InventoryLevel.bin_id == bin_id,
        )
        .with_for_update()
    )
    level = result.scalar_one_or_none()
    if level is not None:
        return level
    await load_bin(session, bin_id, warehouse_id, workspace_id)
    level = InventoryLevel(
        workspace_id=workspace_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        bin_id=bin_id,
        on_hand=ZERO,
        reserved=ZERO,
        damaged=ZERO,
        updated_at=_now(),
    )
    session.add(level)
    await session.flush()
    locked = await session.execute(
        select(InventoryLevel).where(InventoryLevel.id == level.id).with_for_update()
    )
    return locked.scalar_one()


async def post_issue(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    bin_id: uuid.UUID,
    quantity: Decimal,
    user_id: uuid.UUID,
    reference_id: uuid.UUID,
    *,
    reverse: bool = False,
    reference_type: Optional[str] = None,
    reason: Optional[str] = None,
) -> InventoryLevel:
    """ISSUE −qty on confirm, ISSUE +qty on cancel. Never ADJUSTMENT.

    `reference_type`/`reason` default to delivery-note lineage (DN / DN_CANCEL);
    purchase returns pass reference_type="PRN", reason="PURCHASE_RETURN".
    """
    qty = qty_dec(quantity)
    if qty <= ZERO:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "quantity must be greater than zero",
            "quantity",
        )
    level = await lock_or_create_level(
        session, workspace_id, product_id, warehouse_id, bin_id
    )
    if reverse:
        level.on_hand = qty_dec(level.on_hand) + qty
        txn_qty = qty
        source_bin_id = None
        destination_bin_id = bin_id
        ref_type = reference_type or "DN_CANCEL"
    else:
        if available(level) < qty:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Insufficient available stock",
                "quantity",
            )
        level.on_hand = qty_dec(level.on_hand) - qty
        txn_qty = -qty
        source_bin_id = bin_id
        destination_bin_id = None
        ref_type = reference_type or "DN"
    level.updated_at = _now()
    session.add(
        InventoryTransaction(
            workspace_id=workspace_id,
            product_id=product_id,
            transaction_type=TransactionType.ISSUE,
            quantity=txn_qty,
            source_bin_id=source_bin_id,
            destination_bin_id=destination_bin_id,
            reference_type=ref_type,
            reference_id=reference_id,
            user_id=user_id,
            reason=reason,
        )
    )
    return level


async def load_product(
    session: AsyncSession, product_id: uuid.UUID, workspace_id: uuid.UUID
) -> Product:
    result = await session.execute(
        select(Product).where(
            Product.id == product_id,
            Product.workspace_id == workspace_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Product not found")
    return product


async def adjust(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    bin_id: uuid.UUID,
    quantity: Decimal,
    reason: str,
    notes: str,
) -> InventoryLevel:
    """OWNER/ADMIN back door. Always writes an ADJUSTMENT ledger row."""
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may adjust inventory",
        )
    await load_product(session, product_id, workspace_id)
    await load_warehouse(session, warehouse_id, workspace_id)
    await load_bin(session, bin_id, warehouse_id, workspace_id)
    qty = qty_dec(quantity)
    if qty == ZERO:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "quantity must not be zero",
            "quantity",
        )
    level = await lock_or_create_level(
        session, workspace_id, product_id, warehouse_id, bin_id
    )
    next_on_hand = qty_dec(level.on_hand) + qty
    if next_on_hand < ZERO:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "Cannot have negative on-hand stock",
            "quantity",
        )
    level.on_hand = next_on_hand
    level.updated_at = _now()
    session.add(
        InventoryTransaction(
            workspace_id=workspace_id,
            product_id=product_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity=qty,
            destination_bin_id=bin_id if qty > ZERO else None,
            source_bin_id=bin_id if qty < ZERO else None,
            reference_type="ADJUSTMENT",
            reference_id=None,
            reason=reason,
            notes=notes,
            user_id=user.id,
        )
    )
    return level
