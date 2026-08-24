import uuid
from typing import List

from sqlalchemy.orm import selectinload
from sqlmodel import select
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.spo import SupplierPurchaseOrder
from app.auth.dependencies import get_current_active_user, get_current_workspace_id
from app.schemas.spo import SPOCreate, SPOResponse, SPOAcknowledgeReq
from app.services.spo_service import SPOService

router = APIRouter(prefix="/spos", tags=["SPOs"])


@router.post("/", response_model=SPOResponse)
async def create_spo(
    spo_in: SPOCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.create_draft(
        session, current_user.workspace_id, spo_in, current_user.id
    )


@router.post("/{spo_id}/submit-approval", response_model=SPOResponse)
async def submit_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.submit_for_approval(
        session, current_user.workspace_id, spo_id, current_user.id
    )


@router.post("/{spo_id}/approve", response_model=SPOResponse)
async def approve_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.approve(
        session, current_user.workspace_id, spo_id, current_user.id
    )


@router.post("/{spo_id}/send", response_model=SPOResponse)
async def send_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.send(
        session, current_user.workspace_id, spo_id, current_user.id
    )


@router.post("/{spo_id}/items/acknowledge", response_model=SPOResponse)
async def acknowledge_spo(
    spo_id: uuid.UUID,
    ack_req: SPOAcknowledgeReq,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.acknowledge(
        session, current_user.workspace_id, spo_id, ack_req, current_user.id
    )


@router.post("/{spo_id}/cancel", response_model=SPOResponse)
async def cancel_spo(
    spo_id: uuid.UUID,
    reason: str = Query(..., min_length=10),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    return await SPOService.cancel(
        session, current_user.workspace_id, spo_id, reason, current_user.id
    )


@router.get("/", response_model=List[SPOResponse])
async def list_spos(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(SupplierPurchaseOrder)
        .options(selectinload(SupplierPurchaseOrder.items))
        .where(SupplierPurchaseOrder.workspace_id == workspace_id)
        .order_by(SupplierPurchaseOrder.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{spo_id}", response_model=SPOResponse)
async def get_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(SupplierPurchaseOrder)
        .options(selectinload(SupplierPurchaseOrder.items))
        .where(SupplierPurchaseOrder.id == spo_id)
        .where(SupplierPurchaseOrder.workspace_id == workspace_id)
    )
    spo = result.scalar_one_or_none()
    if not spo:
        raise HTTPException(status_code=404, detail="SPO not found")
    return spo
