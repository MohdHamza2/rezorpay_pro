import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User
from app.models.inventory import (
    Warehouse,
    WarehouseBin,
    InventoryLevel,
)
from app.schemas.inventory import (
    WarehouseCreate,
    WarehouseResponse,
    WarehouseBinCreate,
    WarehouseBinResponse,
    InventoryLevelResponse,
    StockAdjustmentRequest,
)
from app.schemas.common import SuccessResponse
from app.services.inventory_ledger import adjust, available

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
