import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id
from app.models.supplier import Supplier
from app.schemas.suppliers import SupplierCreate, SupplierResponse
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/suppliers", tags=["Supplier Master"])

@router.get("", response_model=SuccessResponse[List[SupplierResponse]])
async def list_suppliers(session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    result = await session.execute(select(Supplier).where(Supplier.workspace_id == workspace_id, Supplier.deleted_at.is_(None)))
    return SuccessResponse(data=result.scalars().all())

@router.post("", response_model=SuccessResponse[SupplierResponse])
async def create_supplier(data: SupplierCreate, session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    supplier = Supplier(workspace_id=workspace_id, **data.model_dump())
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    return SuccessResponse(data=supplier)
