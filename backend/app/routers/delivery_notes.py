"""Delivery Note CRUD router with confirm ISSUE / cancel reverse."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.delivery_note import DeliveryNote, DeliveryNoteStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.delivery_notes import (
    DeliveryNoteCancelRequest,
    DeliveryNoteConfirmRequest,
    DeliveryNoteCreate,
    DeliveryNoteResponse,
    DeliveryNoteUpdate,
)
from app.services.delivery_note_service import DeliveryNoteService

router = APIRouter(prefix="/delivery-notes", tags=["Delivery Notes"])


async def _load_or_404(
    session: AsyncSession,
    dn_id: UUID,
    workspace_id: UUID,
    *,
    for_update: bool = False,
) -> DeliveryNote:
    dn = await DeliveryNoteService.get_visible(
        session, dn_id, workspace_id, for_update=for_update
    )
    if dn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Delivery note not found"
        )
    return dn


async def _wrapped(
    session: AsyncSession, dn: DeliveryNote
) -> SuccessResponse[DeliveryNoteResponse]:
    return SuccessResponse(data=await DeliveryNoteService.wrapped(session, dn))


@router.post(
    "",
    response_model=SuccessResponse[DeliveryNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_delivery_note(
    body: DeliveryNoteCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT delivery note with DN-YYYY-XXXX numbering."""
    dn = await DeliveryNoteService.create(
        session=session,
        workspace_id=workspace_id,
        user_id=user.id,
        warehouse_id=body.warehouse_id,
        customer_purchase_order_id=body.customer_purchase_order_id,
        invoice_id=body.invoice_id,
        bin_id=body.bin_id,
        delivery_date=body.delivery_date,
        shipping_address=body.shipping_address,
        vehicle_number=body.vehicle_number,
        driver_name=body.driver_name,
        notes=body.notes,
        items=[item.model_dump() for item in body.items] if body.items else None,
    )
    await session.commit()
    return await _wrapped(session, dn)


@router.get("", response_model=PaginatedResponse)
async def list_delivery_notes(
    status_filter: Optional[DeliveryNoteStatus] = Query(None, alias="status"),
    client_id: Optional[UUID] = Query(None),
    customer_purchase_order_id: Optional[UUID] = Query(None),
    invoice_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, description="Search DN number"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List delivery notes. Search matches dn_number."""
    query = DeliveryNoteService.list_filters(
        workspace_id,
        status_filter,
        client_id,
        customer_purchase_order_id,
        invoice_id,
        search,
    )
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(DeliveryNote.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(query)
    rows = result.scalars().all()
    pages = (total + per_page - 1) // per_page if total else 0
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=[DeliveryNoteService.serialize_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.get("/{dn_id}", response_model=SuccessResponse[DeliveryNoteResponse])
async def get_delivery_note(
    dn_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a delivery note with lines."""
    dn = await _load_or_404(session, dn_id, workspace_id)
    return await _wrapped(session, dn)


@router.put("/{dn_id}", response_model=SuccessResponse[DeliveryNoteResponse])
async def update_delivery_note(
    dn_id: UUID,
    body: DeliveryNoteUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Replace DRAFT fields. Non-DRAFT → 403 INVALID_STATE."""
    dn = await _load_or_404(session, dn_id, workspace_id, for_update=True)
    patch = body.model_dump(exclude_unset=True)
    items = patch.pop("items", None)
    await DeliveryNoteService.update_draft(
        session=session, dn=dn, user_id=user.id, patch=patch, items=items
    )
    await session.commit()
    loaded = await DeliveryNoteService.get_visible(session, dn.id, workspace_id)
    return await _wrapped(session, loaded)


@router.delete("/{dn_id}", status_code=status.HTTP_200_OK)
async def delete_delivery_note(
    dn_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Soft-delete a DRAFT delivery note. Does not rewind the number counter."""
    dn = await _load_or_404(session, dn_id, workspace_id, for_update=True)
    await DeliveryNoteService.soft_delete(dn)
    await session.commit()
    return SuccessResponse(
        data={"message": "Delivery note deleted successfully", "dn_id": str(dn_id)}
    )


@router.post(
    "/{dn_id}/confirm",
    response_model=SuccessResponse[DeliveryNoteResponse],
)
async def confirm_delivery_note(
    dn_id: UUID,
    _body: DeliveryNoteConfirmRequest = Body(
        default_factory=DeliveryNoteConfirmRequest
    ),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DRAFT → CONFIRMED. Posts ISSUE for catalog lines. Idempotent 200."""
    dn = await _load_or_404(session, dn_id, workspace_id, for_update=True)
    await DeliveryNoteService.confirm(session, dn, user.id, workspace_id)
    await session.commit()
    loaded = await DeliveryNoteService.get_visible(session, dn.id, workspace_id)
    return await _wrapped(session, loaded)


@router.post(
    "/{dn_id}/cancel",
    response_model=SuccessResponse[DeliveryNoteResponse],
)
async def cancel_delivery_note(
    dn_id: UUID,
    body: DeliveryNoteCancelRequest = Body(default_factory=DeliveryNoteCancelRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """CONFIRMED → CANCELLED. Reverses ISSUE stock."""
    dn = await _load_or_404(session, dn_id, workspace_id, for_update=True)
    await DeliveryNoteService.cancel(session, dn, user.id, body.reason)
    await session.commit()
    loaded = await DeliveryNoteService.get_visible(session, dn.id, workspace_id)
    return await _wrapped(session, loaded)
