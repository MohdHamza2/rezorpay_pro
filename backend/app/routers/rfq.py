import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User
from app.models.rfq import RFQ, RFQItem, RFQAward, SupplierRFQResponse
from app.schemas.rfq import (
    AwardCreate,
    AwardResponse,
    ComparisonResponse,
    GenerateSPOsRequest,
    GenerateSPOsResponse,
    QuoteResponseCreate,
    QuoteResponseResponse,
    RFQCreate,
    RFQResponse,
)
from app.schemas.common import SuccessResponse
from app.services.award_service import AwardService
from app.services.rfq_number import RFQNumberService

router = APIRouter(prefix="/rfq", tags=["RFQ & Sourcing"])


def _rfq_options():
    return (
        selectinload(RFQ.items),
        selectinload(RFQ.responses).selectinload(SupplierRFQResponse.quote_items),
        selectinload(RFQ.awards).selectinload(RFQAward.award_lines),
    )


@router.get("/requests", response_model=SuccessResponse[List[RFQResponse]])
async def list_rfq(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(RFQ)
        .options(*_rfq_options())
        .where(RFQ.workspace_id == workspace_id)
        .order_by(RFQ.created_at.desc())
    )
    return SuccessResponse(data=result.scalars().all())


@router.post("/requests", response_model=SuccessResponse[RFQResponse])
async def create_rfq(
    data: RFQCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    user_id = user.id
    rfq_number = await RFQNumberService.generate_rfq_number(session, workspace_id)

    rfq = RFQ(
        workspace_id=workspace_id,
        rfq_number=rfq_number,
        created_by_id=user_id,
        **data.model_dump(exclude={"items"}),
    )
    session.add(rfq)
    await session.flush()

    for item_data in data.items:
        item = RFQItem(rfq_id=rfq.id, **item_data.model_dump())
        session.add(item)

    await session.commit()
    await session.refresh(rfq)

    result = await session.execute(
        select(RFQ).options(*_rfq_options()).where(RFQ.id == rfq.id)
    )
    return SuccessResponse(data=result.scalar_one())


@router.get("/requests/{rfq_id}", response_model=SuccessResponse[RFQResponse])
async def get_rfq(
    rfq_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    rfq = await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)
    return SuccessResponse(data=rfq)


@router.post("/requests/{rfq_id}/send", response_model=SuccessResponse[RFQResponse])
async def send_rfq(
    rfq_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    rfq = await AwardService.send_rfq(session, workspace_id, rfq_id)
    return SuccessResponse(data=rfq)


@router.post(
    "/requests/{rfq_id}/responses",
    response_model=SuccessResponse[QuoteResponseResponse],
)
async def submit_quote(
    rfq_id: uuid.UUID,
    data: QuoteResponseCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    response = await AwardService.submit_quote(session, workspace_id, rfq_id, data)
    return SuccessResponse(data=response)


@router.get(
    "/requests/{rfq_id}/comparison", response_model=SuccessResponse[ComparisonResponse]
)
async def compare_quotes(
    rfq_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    payload = await AwardService.comparison(session, workspace_id, rfq_id)
    return SuccessResponse(data=payload)


@router.post("/requests/{rfq_id}/awards", response_model=SuccessResponse[AwardResponse])
async def draft_award(
    rfq_id: uuid.UUID,
    data: AwardCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    award = await AwardService.draft_award(session, workspace_id, rfq_id, data, user.id)
    await session.commit()
    return SuccessResponse(data=award)


@router.post(
    "/awards/{award_id}/approve", response_model=SuccessResponse[AwardResponse]
)
async def approve_award(
    award_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    award = await AwardService.approve_award(session, workspace_id, award_id, user.id)
    return SuccessResponse(data=award)


@router.post(
    "/awards/{award_id}/generate-spos",
    response_model=SuccessResponse[GenerateSPOsResponse],
)
async def generate_spos(
    award_id: uuid.UUID,
    data: GenerateSPOsRequest,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    payload = await AwardService.generate_spos(
        session, workspace_id, award_id, data, user.id
    )
    return SuccessResponse(data=payload)
