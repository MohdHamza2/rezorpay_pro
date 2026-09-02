from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.tax_debit_note import TaxDebitNoteStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.schemas.tax_debit_notes import (
    TaxDebitNoteCreate,
    TaxDebitNoteDetailResponse,
    TaxDebitNoteResponse,
    TaxDebitNoteUpdate,
)
from app.services.tax_debit_note_service import TaxDebitNoteService

router = APIRouter(prefix="/debit-notes", tags=["Debit Notes"])


def _deleted() -> SuccessResponse[None]:
    return SuccessResponse[None](success=True, data=None)


@router.get("", response_model=PaginatedResponse)
async def list_debit_notes(
    invoice_id: Optional[UUID] = Query(None),
    client_id: Optional[UUID] = Query(None),
    status_filter: Optional[TaxDebitNoteStatus] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    query = TaxDebitNoteService.list_filters(
        workspace_id, status_filter, client_id, invoice_id, search
    )
    # Simple pagination
    offset = (page - 1) * per_page
    paginated_query = query.offset(offset).limit(per_page)

    result = await session.execute(paginated_query)
    items = result.scalars().all()

    count_query = query.with_only_columns(
        __import__("sqlalchemy").func.count()
    ).order_by(None)
    total_count = (await session.execute(count_query)).scalar() or 0

    return PaginatedResponse(
        data=[TaxDebitNoteService.serialize(item) for item in items],
        pagination={
            "page": page,
            "per_page": per_page,
            "total_items": total_count,
            "total_pages": (total_count + per_page - 1) // per_page,
        },
    )


@router.post(
    "",
    response_model=SuccessResponse[TaxDebitNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_debit_note(
    data: TaxDebitNoteCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    tdn = await TaxDebitNoteService.create(
        session,
        workspace_id,
        user.id,
        data.invoice_id,
        data.reason,
        data.reason_notes,
        data.issue_date,
        [item.model_dump() for item in data.items],
    )
    await session.commit()
    await session.refresh(tdn)
    return SuccessResponse(data=TaxDebitNoteService.serialize(tdn))


@router.get("/{id}", response_model=SuccessResponse[TaxDebitNoteDetailResponse])
async def get_debit_note(
    id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    tdn = await TaxDebitNoteService.get_visible(session, id, workspace_id)
    if not tdn:
        from app.services.customer_po_support import raise_error
        from app.schemas.common import ErrorCode

        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Debit note not found"
        )
    return SuccessResponse(data=TaxDebitNoteService.serialize_detail(tdn))


@router.put("/{id}", response_model=SuccessResponse[TaxDebitNoteResponse])
async def update_debit_note(
    id: UUID,
    data: TaxDebitNoteUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    tdn = await TaxDebitNoteService.get_visible(
        session, id, workspace_id, for_update=True
    )
    if not tdn:
        from app.services.customer_po_support import raise_error
        from app.schemas.common import ErrorCode

        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Debit note not found"
        )

    patch = data.model_dump(exclude_unset=True, exclude={"items"})
    items_raw = None
    if data.items is not None:
        items_raw = [item.model_dump() for item in data.items]

    updated = await TaxDebitNoteService.update_draft(
        session, tdn, user.id, patch, items_raw
    )
    await session.commit()
    await session.refresh(updated)
    return SuccessResponse(data=TaxDebitNoteService.serialize(updated))


@router.delete(
    ("/{id}"),
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_debit_note(
    id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    tdn = await TaxDebitNoteService.get_visible(
        session, id, workspace_id, for_update=True
    )
    if not tdn:
        from app.services.customer_po_support import raise_error
        from app.schemas.common import ErrorCode

        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Debit note not found"
        )

    await TaxDebitNoteService.soft_delete(tdn)
    await session.commit()
    return _deleted()


@router.post(
    "/{id}/issue",
    response_model=SuccessResponse[TaxDebitNoteResponse],
    status_code=status.HTTP_200_OK,
)
async def issue_debit_note(
    id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
):
    tdn = await TaxDebitNoteService.get_visible(
        session, id, workspace_id, for_update=True
    )
    if not tdn:
        from app.services.customer_po_support import raise_error
        from app.schemas.common import ErrorCode

        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Debit note not found"
        )

    issued = await TaxDebitNoteService.issue(session, tdn, user.id, workspace_id)
    await session.commit()
    await session.refresh(issued)
    return SuccessResponse(data=TaxDebitNoteService.serialize(issued))
