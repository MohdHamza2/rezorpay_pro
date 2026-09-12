import uuid
from typing import List

from sqlalchemy.orm import selectinload
from sqlmodel import select
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.spo import SPOAmendment, SupplierPurchaseOrder
from app.auth.dependencies import get_current_active_user, get_current_workspace_id
from app.schemas.common import SuccessResponse
from app.schemas.spo import (
    SPOAmendmentApplyRequest,
    SPOAmendmentCreate,
    SPOAmendmentResponse,
    SPOCreate,
    SPOResponse,
    SPOAcknowledgeReq,
)
from app.services.spo_service import SPOService

router = APIRouter(prefix="/spos", tags=["SPOs"])


@router.post("/", response_model=SuccessResponse[SPOResponse])
async def create_spo(
    spo_in: SPOCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.create_draft(
        session, current_user.workspace_id, spo_in, current_user.id
    )
    return SuccessResponse(data=spo)


@router.post("/{spo_id}/submit-approval", response_model=SuccessResponse[SPOResponse])
async def submit_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.submit_for_approval(
        session, current_user.workspace_id, spo_id, current_user.id
    )
    return SuccessResponse(data=spo)


@router.post("/{spo_id}/approve", response_model=SuccessResponse[SPOResponse])
async def approve_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.approve(
        session, current_user.workspace_id, spo_id, current_user.id
    )
    return SuccessResponse(data=spo)


@router.post("/{spo_id}/send", response_model=SuccessResponse[SPOResponse])
async def send_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.send(
        session, current_user.workspace_id, spo_id, current_user.id
    )
    return SuccessResponse(data=spo)


@router.post("/{spo_id}/items/acknowledge", response_model=SuccessResponse[SPOResponse])
async def acknowledge_spo(
    spo_id: uuid.UUID,
    ack_req: SPOAcknowledgeReq,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.acknowledge(
        session, current_user.workspace_id, spo_id, ack_req, current_user.id
    )
    return SuccessResponse(data=spo)


@router.post(
    "/{spo_id}/amendments", response_model=SuccessResponse[SPOAmendmentResponse]
)
async def propose_amendment(
    spo_id: uuid.UUID,
    data: SPOAmendmentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    amendment = await SPOService.propose_amendment(
        session, current_user.workspace_id, spo_id, data, current_user.id
    )
    await session.commit()
    return SuccessResponse(data=amendment)


@router.post(
    "/{spo_id}/amendments/{amendment_id}/approve",
    response_model=SuccessResponse[SPOAmendmentResponse],
)
async def approve_amendment(
    spo_id: uuid.UUID,
    amendment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    amendment = await SPOService.approve_amendment(
        session, current_user.workspace_id, spo_id, amendment_id, current_user.id
    )
    await session.commit()
    return SuccessResponse(data=amendment)


@router.post(
    "/{spo_id}/amendments/{amendment_id}/apply",
    response_model=SuccessResponse[SPOAmendmentResponse],
)
async def apply_amendment(
    spo_id: uuid.UUID,
    amendment_id: uuid.UUID,
    data: SPOAmendmentApplyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    amendment = await SPOService.apply_amendment(
        session, current_user.workspace_id, spo_id, amendment_id, data
    )
    await session.commit()
    return SuccessResponse(data=amendment)


@router.post("/{spo_id}/cancel", response_model=SuccessResponse[SPOResponse])
async def cancel_spo(
    spo_id: uuid.UUID,
    reason: str = Query(..., min_length=10),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    spo = await SPOService.cancel(
        session, current_user.workspace_id, spo_id, reason, current_user.id
    )
    return SuccessResponse(data=spo)


@router.get("/", response_model=SuccessResponse[List[SPOResponse]])
async def list_spos(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(SupplierPurchaseOrder)
        .options(
            selectinload(SupplierPurchaseOrder.items),
            selectinload(SupplierPurchaseOrder.amendments).selectinload(
                SPOAmendment.lines
            ),
        )
        .where(SupplierPurchaseOrder.workspace_id == workspace_id)
        .order_by(SupplierPurchaseOrder.created_at.desc())
    )
    return SuccessResponse(data=list(result.scalars().all()))


@router.get("/{spo_id}", response_model=SuccessResponse[SPOResponse])
async def get_spo(
    spo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(SupplierPurchaseOrder)
        .options(
            selectinload(SupplierPurchaseOrder.items),
            selectinload(SupplierPurchaseOrder.amendments).selectinload(
                SPOAmendment.lines
            ),
        )
        .where(SupplierPurchaseOrder.id == spo_id)
        .where(SupplierPurchaseOrder.workspace_id == workspace_id)
    )
    spo = result.scalar_one_or_none()
    if not spo:
        raise HTTPException(status_code=404, detail="SPO not found")
    return SuccessResponse(data=spo)
