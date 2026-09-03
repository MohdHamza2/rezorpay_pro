import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_session
from app.models.enquiry import Enquiry
from app.models.user import User
from app.schemas.enquiry import (
    EnquiryCreate,
    EnquiryListResponse,
    EnquiryRead,
    EnquiryStatusUpdate,
    EnquiryUpdate,
)
from app.schemas.quotations import QuotationResponse
from app.services.enquiry_service import EnquiryService
from app.services.quotation_service import QuotationService

router = APIRouter()


@router.get("", response_model=EnquiryListResponse)
async def get_enquiries(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    client_id: Optional[uuid.UUID] = None,
):
    query = select(Enquiry).where(
        Enquiry.workspace_id == user.workspace_id, Enquiry.deleted_at.is_(None)
    )
    if status:
        query = query.where(Enquiry.status == status)
    if client_id:
        query = query.where(Enquiry.client_id == client_id)

    total_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(total_query)).scalar_one()

    query = (
        query.options(selectinload(Enquiry.items))
        .order_by(Enquiry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(query)
    items = result.scalars().all()

    return EnquiryListResponse(
        items=items,
        total=total,
        page=(skip // limit) + 1,
        size=limit,
    )


@router.post("", response_model=EnquiryRead, status_code=status.HTTP_201_CREATED)
async def create_enquiry(
    data: EnquiryCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    enquiry = await EnquiryService.create(
        session=session,
        workspace_id=user.workspace_id,
        user_id=user.id,
        data=data,
    )
    await session.commit()
    await session.refresh(enquiry)
    return await EnquiryService.get_visible(session, enquiry.id, user.workspace_id)


@router.get("/{id}", response_model=EnquiryRead)
async def get_enquiry(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    enquiry = await EnquiryService.get_visible(session, id, user.workspace_id)
    if not enquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found"
        )
    return enquiry


@router.put("/{id}", response_model=EnquiryRead)
async def update_enquiry(
    id: uuid.UUID,
    data: EnquiryUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    enquiry = await EnquiryService.get_visible(
        session, id, user.workspace_id, for_update=True
    )
    if not enquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found"
        )

    enquiry = await EnquiryService.update(session, enquiry, user.id, data)
    await session.commit()
    return await EnquiryService.get_visible(session, enquiry.id, user.workspace_id)


@router.post("/{id}/status", response_model=EnquiryRead)
async def update_enquiry_status(
    id: uuid.UUID,
    data: EnquiryStatusUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    enquiry = await EnquiryService.get_visible(
        session, id, user.workspace_id, for_update=True
    )
    if not enquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found"
        )

    enquiry.status = data.status
    await session.commit()
    return await EnquiryService.get_visible(session, enquiry.id, user.workspace_id)


@router.post("/{id}/convert", response_model=QuotationResponse)
async def convert_enquiry_to_quotation(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    enquiry = await EnquiryService.get_visible(
        session, id, user.workspace_id, for_update=True
    )
    if not enquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found"
        )

    quotation, _ = await EnquiryService.convert_to_quotation(
        session=session,
        enquiry=enquiry,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    await session.commit()

    # We must format it using the quotation serialization logic
    q_read = await QuotationService.get_visible(
        session, quotation.id, user.workspace_id
    )
    return QuotationService.serialize(q_read)
