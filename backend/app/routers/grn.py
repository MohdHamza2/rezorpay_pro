import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User
from app.models.grn import GoodsReceiptNote, GRNItem, GRNStatus
from app.schemas.grn import (
    GRNCreate, GRNUpdate, GRNResponse, GRNItemCreate, 
    GRNDispositionRequest, GRNCancelRequest
)
from app.schemas.common import SuccessResponse
from app.services.grn_service import GRNService

router = APIRouter(prefix="", tags=["Goods Receipt Notes"])

@router.post("/grns", response_model=SuccessResponse[GRNResponse], status_code=201)
async def create_grn(
    data: GRNCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user)
):
    grn = await GRNService.create_draft_grn(session, workspace_id, user.id, data)
    await session.commit()
    
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == grn.id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.patch("/grns/{id}", response_model=SuccessResponse[GRNResponse])
async def update_grn(
    id: uuid.UUID,
    data: GRNUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    grn = await GRNService.update_grn(session, workspace_id, id, data)
    await session.commit()
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == grn.id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.post("/grns/{id}/start-receiving", response_model=SuccessResponse[GRNResponse])
async def start_receiving(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    grn = await GRNService.start_receiving(session, workspace_id, id)
    await session.commit()
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == grn.id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.post("/grns/{id}/items", response_model=SuccessResponse[GRNResponse])
async def add_grn_item(
    id: uuid.UUID,
    data: GRNItemCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    await GRNService.add_grn_item(session, workspace_id, id, data)
    await session.commit()
    
    # Return updated GRN
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.post("/grns/{id}/stage-for-inspection", response_model=SuccessResponse[GRNResponse])
async def stage_for_inspection(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    grn = await GRNService.stage_for_inspection(session, workspace_id, id)
    await session.commit()
    
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.post("/grns/{id}/items/{item_id}/disposition", response_model=SuccessResponse[GRNResponse])
async def record_disposition(
    id: uuid.UUID,
    item_id: uuid.UUID,
    data: GRNDispositionRequest,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user)
):
    grn = await GRNService.record_disposition(session, workspace_id, id, item_id, user.id, data)
    await session.commit()
    
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.post("/grns/{id}/cancel", response_model=SuccessResponse[GRNResponse])
async def cancel_grn(
    id: uuid.UUID,
    data: GRNCancelRequest,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    grn = await GRNService.cancel_grn(session, workspace_id, id, data)
    await session.commit()
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.id == grn.id)
    )
    return SuccessResponse(data=grn_query.scalar_one())

@router.get("/grns/{id}/reconciliation")
async def get_grn_reconciliation(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    grn_query = await session.execute(
        select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(
            GoodsReceiptNote.id == id,
            GoodsReceiptNote.workspace_id == workspace_id
        )
    )
    grn = grn_query.scalar_one_or_none()
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
        
    # Return a specialized view
    return SuccessResponse(data=grn)

@router.get("/grns", response_model=SuccessResponse[List[GRNResponse]])
async def list_grns(
    status: Optional[GRNStatus] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    spo_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    query = select(GoodsReceiptNote).options(selectinload(GoodsReceiptNote.items)).where(GoodsReceiptNote.workspace_id == workspace_id)
    if status:
        query = query.where(GoodsReceiptNote.status == status)
    if supplier_id:
        query = query.where(GoodsReceiptNote.supplier_id == supplier_id)
    if spo_id:
        query = query.where(GoodsReceiptNote.spo_id == spo_id)
        
    query = query.order_by(GoodsReceiptNote.created_at.desc())
    result = await session.execute(query)
    return SuccessResponse(data=result.scalars().all())

@router.get("/spos/{id}/grns", response_model=SuccessResponse[List[GRNResponse]])
async def list_spo_grns(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    result = await session.execute(
        select(GoodsReceiptNote)
        .options(selectinload(GoodsReceiptNote.items))
        .where(
            GoodsReceiptNote.workspace_id == workspace_id,
            GoodsReceiptNote.spo_id == id
        )
        .order_by(GoodsReceiptNote.created_at.desc())
    )
    return SuccessResponse(data=result.scalars().all())
