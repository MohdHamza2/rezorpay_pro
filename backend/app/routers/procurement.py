import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id, get_current_user
from app.models.user import User
from app.models.procurement import ProcurementRequest, ProcurementRequestItem
from app.schemas.procurement import ProcurementRequestCreate, ProcurementRequestResponse
from app.schemas.common import SuccessResponse
from app.services.pr_number import PRNumberService

router = APIRouter(prefix="/procurement", tags=["Procurement Management"])


@router.get(
    "/requests", response_model=SuccessResponse[List[ProcurementRequestResponse]]
)
async def list_pr(
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(ProcurementRequest)
        .options(selectinload(ProcurementRequest.items))
        .where(ProcurementRequest.workspace_id == workspace_id)
        .order_by(ProcurementRequest.created_at.desc())
    )
    return SuccessResponse(data=result.scalars().all())


@router.post("/requests", response_model=SuccessResponse[ProcurementRequestResponse])
async def create_pr(
    data: ProcurementRequestCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    user_id = user.id
    req_num = await PRNumberService.generate_pr_number(session, workspace_id)

    pr = ProcurementRequest(
        workspace_id=workspace_id,
        request_number=req_num,
        requested_by_id=user_id,
        **data.model_dump(exclude={"items"}),
    )
    session.add(pr)
    await session.flush()

    for item_data in data.items:
        item = ProcurementRequestItem(request_id=pr.id, **item_data.model_dump())
        session.add(item)

    await session.commit()
    await session.refresh(pr)

    # Reload with items
    result = await session.execute(
        select(ProcurementRequest)
        .options(selectinload(ProcurementRequest.items))
        .where(ProcurementRequest.id == pr.id)
    )
    return SuccessResponse(data=result.scalar_one())
