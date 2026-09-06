import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User
from app.models.rfq import RFQ, RFQItem
from app.schemas.rfq import RFQCreate, RFQResponse
from app.schemas.common import SuccessResponse
from app.services.rfq_number import RFQNumberService

router = APIRouter(prefix="/rfq", tags=["RFQ & Sourcing"])


@router.get("/requests", response_model=SuccessResponse[List[RFQResponse]])
async def list_rfq(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(RFQ)
        .options(selectinload(RFQ.items))
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
        select(RFQ).options(selectinload(RFQ.items)).where(RFQ.id == rfq.id)
    )
    return SuccessResponse(data=result.scalar_one())
