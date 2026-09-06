"""
Supplier Debit Note Router — Wave 23 (Phase 4).

Endpoints:
- POST /supplier-debit-notes                     create manual DRAFT note
- GET /supplier-debit-notes                      paginated list w/ filters
- GET /supplier-debit-notes/{id}                 one note
- POST /supplier-debit-notes/{id}/issue
- POST /supplier-debit-notes/{id}/apply          reduce invoice balance_due
- POST /supplier-debit-notes/{id}/cancel

All mutations are OWNER/ADMIN gated; reads are member-accessible.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.supplier_debit_note import SupplierDebitNoteStatus
from app.models.user import User, UserRole
from app.schemas.common import (
    ErrorCode,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.supplier_debit_notes import (
    SupplierDebitNoteApplyRequest,
    SupplierDebitNoteCreate,
    SupplierDebitNoteResponse,
)
from app.services.customer_po_support import raise_error
from app.services.supplier_debit_note_service import supplier_debit_note_service

router = APIRouter(tags=["Supplier Debit Notes"])


def _require_admin(user: User) -> User:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may modify supplier debit notes",
        )
    return user


@router.post(
    "/supplier-debit-notes",
    response_model=SuccessResponse[SupplierDebitNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_supplier_debit_note(
    request: Request,
    data: SupplierDebitNoteCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a manual DRAFT supplier debit note (OWNER/ADMIN)."""
    _require_admin(user)
    note = await supplier_debit_note_service.create(
        session, workspace_id, user.id, data
    )
    await session.commit()
    return SuccessResponse(data=SupplierDebitNoteResponse.model_validate(note))


@router.get("/supplier-debit-notes", response_model=PaginatedResponse)
async def list_supplier_debit_notes(
    request: Request,
    supplier_id: Optional[UUID] = Query(None),
    note_status: Optional[SupplierDebitNoteStatus] = Query(None, alias="status"),
    purchase_return_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List supplier debit notes for a workspace (paginated, filterable)."""
    notes, total = await supplier_debit_note_service.list(
        session=session,
        workspace_id=workspace_id,
        supplier_id=supplier_id,
        status_value=note_status,
        purchase_return_id=purchase_return_id,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=[SupplierDebitNoteResponse.model_validate(n) for n in notes],
        pagination=pagination,
    )


@router.get(
    "/supplier-debit-notes/{note_id}",
    response_model=SuccessResponse[SupplierDebitNoteResponse],
)
async def get_supplier_debit_note(
    request: Request,
    note_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return one supplier debit note."""
    note = await supplier_debit_note_service.get(session, workspace_id, note_id)
    if note is None:
        raise_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "Supplier debit note not found",
        )
    return SuccessResponse(data=SupplierDebitNoteResponse.model_validate(note))


@router.post(
    "/supplier-debit-notes/{note_id}/issue",
    response_model=SuccessResponse[SupplierDebitNoteResponse],
)
async def issue_supplier_debit_note(
    request: Request,
    note_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Issue a DRAFT supplier debit note (OWNER/ADMIN)."""
    _require_admin(user)
    note = await supplier_debit_note_service.issue(session, workspace_id, note_id)
    await session.commit()
    return SuccessResponse(data=SupplierDebitNoteResponse.model_validate(note))


@router.post(
    "/supplier-debit-notes/{note_id}/apply",
    response_model=SuccessResponse[SupplierDebitNoteResponse],
)
async def apply_supplier_debit_note(
    request: Request,
    note_id: UUID,
    data: SupplierDebitNoteApplyRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Apply an ISSUED note to an APPROVED/PARTIALLY_PAID invoice: reduces
    balance_due only (OWNER/ADMIN)."""
    _require_admin(user)
    note = await supplier_debit_note_service.apply(
        session, workspace_id, note_id, data.supplier_invoice_id
    )
    await session.commit()
    return SuccessResponse(data=SupplierDebitNoteResponse.model_validate(note))


@router.post(
    "/supplier-debit-notes/{note_id}/cancel",
    response_model=SuccessResponse[SupplierDebitNoteResponse],
)
async def cancel_supplier_debit_note(
    request: Request,
    note_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Cancel a DRAFT / ISSUED supplier debit note (OWNER/ADMIN)."""
    _require_admin(user)
    note = await supplier_debit_note_service.cancel(session, workspace_id, note_id)
    await session.commit()
    return SuccessResponse(data=SupplierDebitNoteResponse.model_validate(note))
