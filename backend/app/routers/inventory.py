import uuid
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User, UserRole
from app.models.inventory import (
    Warehouse,
    WarehouseBin,
    InventoryLevel,
)
from app.models.stock_reservation import (
    ReservationStatus,
    StockReservation,
    StockReservationItem,
)
from app.models.stock_transfer import StockTransfer, TransferStatus
from app.models.stock_count import StockCount, StockCountStatus
from app.schemas.inventory import (
    WarehouseCreate,
    WarehouseResponse,
    WarehouseBinCreate,
    WarehouseBinResponse,
    InventoryLevelResponse,
    StockAdjustmentRequest,
)
from app.schemas.common import (
    ErrorCode,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.stock_reservation import (
    ReservationCancelRequest,
    ReservationExpireRequest,
    ReservationExpireResponse,
    StockReservationCreate,
    StockReservationResponse,
)
from app.schemas.stock_transfer import (
    StockTransferCreate,
    StockTransferResponse,
    TransferCancelRequest,
    TransferReceiveRequest,
)
from app.schemas.stock_count import (
    CountRecordRequest,
    StockCountCreate,
    StockCountResponse,
)
from app.services.inventory_ledger import adjust, available
from app.services.stock_reservation_service import (
    cancel_reservation,
    create_reservation,
    expire_due,
    get_visible,
    serialize,
    serialize_list_item,
)
from app.services.stock_transfer_service import (
    approve_transfer,
    cancel_transfer,
    create_transfer,
    dispatch_transfer,
    get_visible as get_visible_transfer,
    receive_transfer,
    serialize as serialize_transfer,
    serialize_list_item as serialize_transfer_list_item,
)
from app.services.stock_count_service import (
    approve_count,
    cancel_count,
    complete_count,
    create_count,
    get_visible as get_visible_count,
    record_count,
    reconcile_count,
    serialize as serialize_count,
    serialize_list_item as serialize_count_list_item,
)
from app.services.customer_po_support import raise_error

router = APIRouter(prefix="/inventory", tags=["Inventory Management"])


@router.get("/warehouses", response_model=SuccessResponse[List[WarehouseResponse]])
async def list_warehouses(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(Warehouse).where(Warehouse.workspace_id == workspace_id)
    )
    return SuccessResponse(data=result.scalars().all())


@router.post("/warehouses", response_model=SuccessResponse[WarehouseResponse])
async def create_warehouse(
    data: WarehouseCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    warehouse = Warehouse(workspace_id=workspace_id, **data.model_dump())
    session.add(warehouse)
    await session.commit()
    await session.refresh(warehouse)
    return SuccessResponse(data=warehouse)


@router.post(
    "/warehouses/{warehouse_id}/bins",
    response_model=SuccessResponse[WarehouseBinResponse],
    status_code=201,
)
async def create_warehouse_bin(
    warehouse_id: uuid.UUID,
    data: WarehouseBinCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    # Verify warehouse belongs to this workspace
    wh = await session.get(Warehouse, warehouse_id)
    if not wh or wh.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    bin_data = data.model_dump()
    bin_data["warehouse_id"] = warehouse_id
    wh_bin = WarehouseBin(**bin_data)
    session.add(wh_bin)
    await session.commit()
    await session.refresh(wh_bin)
    return SuccessResponse(data=wh_bin)


@router.get(
    "/warehouses/{warehouse_id}/bins",
    response_model=SuccessResponse[List[WarehouseBinResponse]],
)
async def list_warehouse_bins(
    warehouse_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(WarehouseBin).where(WarehouseBin.warehouse_id == warehouse_id)
    )
    return SuccessResponse(data=result.scalars().all())


@router.get("/levels", response_model=SuccessResponse[List[InventoryLevelResponse]])
async def get_inventory_levels(
    product_id: uuid.UUID = None,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    query = select(InventoryLevel).where(InventoryLevel.workspace_id == workspace_id)
    if product_id:
        query = query.where(InventoryLevel.product_id == product_id)
    result = await session.execute(query)
    levels = result.scalars().all()

    # Compute available dynamically
    response_data = []
    for level in levels:
        resp = InventoryLevelResponse.model_validate(level)
        resp.available = level.on_hand - level.reserved - level.damaged
        response_data.append(resp)

    return SuccessResponse(data=response_data)


@router.post("/adjust", response_model=SuccessResponse[InventoryLevelResponse])
async def adjust_stock(
    data: StockAdjustmentRequest,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    level = await adjust(
        session,
        workspace_id,
        user,
        data.product_id,
        data.warehouse_id,
        data.bin_id,
        data.quantity,
        data.reason.value,
        data.notes,
    )
    await session.commit()
    await session.refresh(level)
    resp = InventoryLevelResponse.model_validate(level)
    resp.available = available(level)
    return SuccessResponse(data=resp)


@router.post(
    "/reservations",
    response_model=SuccessResponse[StockReservationResponse],
    status_code=201,
)
async def create_stock_reservation(
    data: StockReservationCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """Reserve LPO lines against one warehouse. 201."""
    reservation = await create_reservation(
        session,
        workspace_id,
        data.customer_purchase_order_id,
        data.warehouse_id,
        [item.model_dump() for item in data.items],
    )
    await session.commit()
    loaded = await get_visible(session, reservation.id, workspace_id) or reservation
    return SuccessResponse(data=serialize(loaded))


@router.get("/reservations", response_model=PaginatedResponse)
async def list_stock_reservations(
    status_filter: Optional[ReservationStatus] = Query(None, alias="status"),
    cpo_id: Optional[uuid.UUID] = Query(None),
    warehouse_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """List reservations. warehouse_id matches any item line."""
    query = select(StockReservation).where(
        StockReservation.workspace_id == workspace_id
    )
    if status_filter:
        query = query.where(StockReservation.status == status_filter)
    if cpo_id:
        query = query.where(StockReservation.customer_purchase_order_id == cpo_id)
    if warehouse_id:
        query = query.where(
            exists()
            .where(StockReservationItem.reservation_id == StockReservation.id)
            .where(StockReservationItem.warehouse_id == warehouse_id)
        )
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(StockReservation.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.options(selectinload(StockReservation.items))
    result = await session.execute(query)
    rows = result.scalars().all()
    pages = (total + per_page - 1) // per_page if total else 0
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=[serialize_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.post(
    "/reservations/expire",
    response_model=SuccessResponse[ReservationExpireResponse],
)
async def expire_stock_reservations(
    _body: ReservationExpireRequest = Body(default_factory=ReservationExpireRequest),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Release ACTIVE reservations past their TTL. OWNER/ADMIN only."""
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may expire reservations",
        )
    expired = await expire_due(session, workspace_id)
    await session.commit()
    return SuccessResponse(data=ReservationExpireResponse(expired=expired))


@router.get(
    "/reservations/{reservation_id}",
    response_model=SuccessResponse[StockReservationResponse],
)
async def get_stock_reservation(
    reservation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    reservation = await get_visible(session, reservation_id, workspace_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return SuccessResponse(data=serialize(reservation))


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=SuccessResponse[StockReservationResponse],
)
async def cancel_stock_reservation(
    reservation_id: uuid.UUID,
    body: ReservationCancelRequest = Body(default_factory=ReservationCancelRequest),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """ACTIVE → CANCELLED. Releases reserved back to available."""
    reservation = await cancel_reservation(
        session, workspace_id, reservation_id, body.reason
    )
    await session.commit()
    loaded = await get_visible(session, reservation.id, workspace_id) or reservation
    return SuccessResponse(data=serialize(loaded))


@router.post(
    "/transfers",
    response_model=SuccessResponse[StockTransferResponse],
    status_code=201,
)
async def create_stock_transfer(
    data: StockTransferCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Create a DRAFT transfer between two warehouses. 201."""
    transfer = await create_transfer(
        session,
        workspace_id,
        user.id,
        data.source_warehouse_id,
        data.destination_warehouse_id,
        data.notes,
        [item.model_dump() for item in data.items],
    )
    await session.commit()
    loaded = await get_visible_transfer(session, transfer.id, workspace_id) or transfer
    return SuccessResponse(data=serialize_transfer(loaded))


@router.get("/transfers", response_model=PaginatedResponse)
async def list_stock_transfers(
    status_filter: Optional[TransferStatus] = Query(None, alias="status"),
    source_warehouse_id: Optional[uuid.UUID] = Query(None),
    destination_warehouse_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    query = select(StockTransfer).where(StockTransfer.workspace_id == workspace_id)
    if status_filter:
        query = query.where(StockTransfer.status == status_filter)
    if source_warehouse_id:
        query = query.where(StockTransfer.source_warehouse_id == source_warehouse_id)
    if destination_warehouse_id:
        query = query.where(
            StockTransfer.destination_warehouse_id == destination_warehouse_id
        )
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(StockTransfer.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.options(selectinload(StockTransfer.items))
    result = await session.execute(query)
    rows = result.scalars().all()
    pages = (total + per_page - 1) // per_page if total else 0
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=[serialize_transfer_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.get(
    "/transfers/{transfer_id}",
    response_model=SuccessResponse[StockTransferResponse],
)
async def get_stock_transfer(
    transfer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    transfer = await get_visible_transfer(session, transfer_id, workspace_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return SuccessResponse(data=serialize_transfer(transfer))


@router.post(
    "/transfers/{transfer_id}/approve",
    response_model=SuccessResponse[StockTransferResponse],
)
async def approve_stock_transfer(
    transfer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    transfer = await approve_transfer(session, transfer_id, workspace_id)
    await session.commit()
    loaded = await get_visible_transfer(session, transfer.id, workspace_id) or transfer
    return SuccessResponse(data=serialize_transfer(loaded))


@router.post(
    "/transfers/{transfer_id}/dispatch",
    response_model=SuccessResponse[StockTransferResponse],
)
async def dispatch_stock_transfer(
    transfer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    transfer = await dispatch_transfer(session, transfer_id, workspace_id, user.id)
    await session.commit()
    loaded = await get_visible_transfer(session, transfer.id, workspace_id) or transfer
    return SuccessResponse(data=serialize_transfer(loaded))


@router.post(
    "/transfers/{transfer_id}/receive",
    response_model=SuccessResponse[StockTransferResponse],
)
async def receive_stock_transfer(
    transfer_id: uuid.UUID,
    body: TransferReceiveRequest = Body(default_factory=TransferReceiveRequest),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    received_map = {}
    for row in body.received or []:
        received_map[row.product_id] = row.quantity
    transfer = await receive_transfer(
        session, transfer_id, workspace_id, user.id, received_map
    )
    await session.commit()
    loaded = await get_visible_transfer(session, transfer.id, workspace_id) or transfer
    return SuccessResponse(data=serialize_transfer(loaded))


@router.post(
    "/transfers/{transfer_id}/cancel",
    response_model=SuccessResponse[StockTransferResponse],
)
async def cancel_stock_transfer(
    transfer_id: uuid.UUID,
    body: TransferCancelRequest = Body(default_factory=TransferCancelRequest),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    transfer = await cancel_transfer(
        session, transfer_id, workspace_id, user.id, body.reason
    )
    await session.commit()
    loaded = await get_visible_transfer(session, transfer.id, workspace_id) or transfer
    return SuccessResponse(data=serialize_transfer(loaded))


@router.post(
    "/counts",
    response_model=SuccessResponse[StockCountResponse],
    status_code=201,
)
async def create_stock_count(
    data: StockCountCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Schedule a physical stock count (snapshots expected quantities)."""
    header = await create_count(
        session, workspace_id, user, data.warehouse_id, data.notes
    )
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))


@router.get("/counts", response_model=PaginatedResponse)
async def list_stock_counts(
    status_filter: Optional[StockCountStatus] = Query(None, alias="status"),
    warehouse_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    query = select(StockCount).where(StockCount.workspace_id == workspace_id)
    if status_filter:
        query = query.where(StockCount.status == status_filter)
    if warehouse_id:
        query = query.where(StockCount.warehouse_id == warehouse_id)
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(StockCount.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.options(selectinload(StockCount.items))
    result = await session.execute(query)
    rows = result.scalars().all()
    pages = (total + per_page - 1) // per_page if total else 0
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=[serialize_count_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.get("/counts/{count_id}", response_model=SuccessResponse[StockCountResponse])
async def get_stock_count(
    count_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    header = await get_visible_count(session, count_id, workspace_id)
    if header is None:
        raise HTTPException(status_code=404, detail="Stock count not found")
    return SuccessResponse(data=serialize_count(header))


@router.post(
    "/counts/{count_id}/record",
    response_model=SuccessResponse[StockCountResponse],
)
async def record_stock_count(
    count_id: uuid.UUID,
    body: CountRecordRequest = Body(default_factory=CountRecordRequest),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Record the physical count for one line."""
    header = await record_count(
        session,
        workspace_id,
        user,
        count_id,
        body.item_id,
        body.counted_quantity,
        body.notes,
    )
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))


@router.post(
    "/counts/{count_id}/complete",
    response_model=SuccessResponse[StockCountResponse],
)
async def complete_stock_count(
    count_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Close counting; compute variances and flag tolerance lines."""
    header = await complete_count(session, workspace_id, user, count_id)
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))


@router.post(
    "/counts/{count_id}/approve",
    response_model=SuccessResponse[StockCountResponse],
)
async def approve_stock_count(
    count_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Manager review: approve all flagged variance lines."""
    header = await approve_count(session, workspace_id, user, count_id)
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))


@router.post(
    "/counts/{count_id}/reconcile",
    response_model=SuccessResponse[StockCountResponse],
)
async def reconcile_stock_count(
    count_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Apply variance deltas to on_hand and write ADJUSTMENT ledger rows."""
    header = await reconcile_count(session, workspace_id, user, count_id)
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))


@router.post(
    "/counts/{count_id}/cancel",
    response_model=SuccessResponse[StockCountResponse],
)
async def cancel_stock_count(
    count_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    """Void a SCHEDULED/IN_PROGRESS count; no stock movement."""
    header = await cancel_count(session, workspace_id, user, count_id)
    await session.commit()
    loaded = await get_visible_count(session, header.id, workspace_id) or header
    return SuccessResponse(data=serialize_count(loaded))
