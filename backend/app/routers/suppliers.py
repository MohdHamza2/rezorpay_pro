import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id
from app.models.supplier import Supplier
from app.schemas.suppliers import (
    SupplierCreate,
    SupplierProductCreate,
    SupplierProductResponse,
    SupplierResponse,
)
from app.schemas.common import SuccessResponse
from app.services.supplier_product_service import SupplierProductService

router = APIRouter(prefix="/suppliers", tags=["Supplier Master"])


@router.get("", response_model=SuccessResponse[List[SupplierResponse]])
async def list_suppliers(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(Supplier).where(
            Supplier.workspace_id == workspace_id, Supplier.deleted_at.is_(None)
        )
    )
    return SuccessResponse(data=result.scalars().all())


@router.post("", response_model=SuccessResponse[SupplierResponse])
async def create_supplier(
    data: SupplierCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    supplier = Supplier(workspace_id=workspace_id, **data.model_dump())
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    return SuccessResponse(data=supplier)


@router.get(
    "/{supplier_id}/products",
    response_model=SuccessResponse[List[SupplierProductResponse]],
)
async def list_supplier_products(
    supplier_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    rows = await SupplierProductService.list_links(session, workspace_id, supplier_id)
    return SuccessResponse(data=rows)


@router.post(
    "/{supplier_id}/products",
    response_model=SuccessResponse[SupplierProductResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_supplier_product(
    supplier_id: uuid.UUID,
    data: SupplierProductCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    row = await SupplierProductService.create_link(
        session, workspace_id, supplier_id, data
    )
    await session.commit()
    await session.refresh(row)
    return SuccessResponse(data=row)


@router.delete(
    "/{supplier_id}/products/{product_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_supplier_product(
    supplier_id: uuid.UUID,
    product_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    await SupplierProductService.delete_link(
        session, workspace_id, supplier_id, product_id
    )
    await session.commit()
    return SuccessResponse[None](success=True, data=None)
