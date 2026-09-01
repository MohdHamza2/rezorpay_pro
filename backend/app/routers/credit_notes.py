"""Tax credit note CRUD router. Issue posts AR. No /apply."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.credit_note import CreditNote, CreditNoteStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.credit_notes import (
    CreditNoteCreate,
    CreditNoteIssueRequest,
    CreditNoteResponse,
    CreditNoteUpdate,
)
from app.services.credit_note_service import CreditNoteService

router = APIRouter(prefix="/credit-notes", tags=["Credit Notes"])


async def _load_or_404(
    session: AsyncSession,
    cn_id: UUID,
    workspace_id: UUID,
    *,
    for_update: bool = False,
) -> CreditNote:
    cn = await CreditNoteService.get_visible(
        session, cn_id, workspace_id, for_update=for_update
    )
    if cn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credit note not found"
        )
    return cn


async def _wrapped(
    session: AsyncSession, cn: CreditNote
) -> SuccessResponse[CreditNoteResponse]:
    return SuccessResponse(data=await CreditNoteService.wrapped(session, cn))


@router.post(
    "",
    response_model=SuccessResponse[CreditNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_credit_note(
    body: CreditNoteCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT credit note with CN-YYYY-XXXX numbering."""
    cn = await CreditNoteService.create(
        session=session,
        workspace_id=workspace_id,
        user_id=user.id,
        invoice_id=body.invoice_id,
        reason=body.reason,
        reason_notes=body.reason_notes,
        issue_date=body.issue_date,
        items=[item.model_dump() for item in body.items],
    )
    await session.commit()
    return await _wrapped(session, cn)


@router.get("", response_model=PaginatedResponse)
async def list_credit_notes(
    status_filter: Optional[CreditNoteStatus] = Query(None, alias="status"),
    client_id: Optional[UUID] = Query(None),
    invoice_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, description="Search credit note number"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List credit notes. Search matches credit_note_number."""
    query = CreditNoteService.list_filters(
        workspace_id, status_filter, client_id, invoice_id, search
    )
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(CreditNote.created_at.desc())
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
        data=[CreditNoteService.serialize_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.get("/{cn_id}", response_model=SuccessResponse[CreditNoteResponse])
async def get_credit_note(
    cn_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a credit note with lines."""
    cn = await _load_or_404(session, cn_id, workspace_id)
    return await _wrapped(session, cn)


@router.put("/{cn_id}", response_model=SuccessResponse[CreditNoteResponse])
async def update_credit_note(
    cn_id: UUID,
    body: CreditNoteUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Replace DRAFT fields. Non-DRAFT → 403 INVALID_STATE."""
    cn = await _load_or_404(session, cn_id, workspace_id, for_update=True)
    patch = body.model_dump(exclude_unset=True)
    items = patch.pop("items", None)
    await CreditNoteService.update_draft(
        session=session, cn=cn, user_id=user.id, patch=patch, items=items
    )
    await session.commit()
    loaded = await CreditNoteService.get_visible(session, cn.id, workspace_id)
    return await _wrapped(session, loaded)


@router.delete("/{cn_id}", status_code=status.HTTP_200_OK)
async def delete_credit_note(
    cn_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Soft-delete a DRAFT credit note. Does not rewind the number counter."""
    cn = await _load_or_404(session, cn_id, workspace_id, for_update=True)
    await CreditNoteService.soft_delete(cn)
    await session.commit()
    return SuccessResponse(
        data={"message": "Credit note deleted successfully", "cn_id": str(cn_id)}
    )


@router.post(
    "/{cn_id}/issue",
    response_model=SuccessResponse[CreditNoteResponse],
)
async def issue_credit_note(
    cn_id: UUID,
    _body: CreditNoteIssueRequest = Body(default_factory=CreditNoteIssueRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DRAFT → ISSUED. Posts AR. Idempotent 200. Never CREDIT_HOLD."""
    cn = await _load_or_404(session, cn_id, workspace_id, for_update=True)
    await CreditNoteService.issue(session, cn, user.id, workspace_id)
    await session.commit()
    loaded = await CreditNoteService.get_visible(session, cn.id, workspace_id)
    return await _wrapped(session, loaded)
