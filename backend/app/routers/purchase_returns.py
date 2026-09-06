"""
Purchase Return Router — Wave 23 (Phase 4).

Endpoints:
- POST /purchase-returns                              create DRAFT return
- GET /purchase-returns                               paginated list w/ filters
- GET /purchase-returns/{id}                          one return
- POST /purchase-returns/{id}/submit-for-supplier-approval
- POST /purchase-returns/{id}/approve
- POST /purchase-returns/{id}/dispatch                stock-out + auto SDN
- POST /purchase-returns/{id}/complete
- POST /purchase-returns/{id}/reject
- POST /purchase-returns/{id}/cancel

All mutations are OWNER/ADMIN gated; reads are member-accessible.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.purchase_return import PurchaseReturnStatus
from app.models.user import User, UserRole
from app.schemas.common import (
    ErrorCode,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.purchase_returns import PurchaseReturnCreate, PurchaseReturnResponse
from app.services.customer_po_support import raise_error
from app.services.purchase_return_service import purchase_return_service

router = APIRouter(tags=["Purchase Returns"])


def _require_admin(user: User) -> User:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may modify purchase returns",
        )
    return user


@router.post(
    "/purchase-returns",
    response_model=SuccessResponse[PurchaseReturnResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_return(
    request: Request,
    data: PurchaseReturnCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT purchase return (OWNER/ADMIN)."""
    _require_admin(user)
    record = await purchase_return_service.create(session, workspace_id, user.id, data)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, record.id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.get("/purchase-returns", response_model=PaginatedResponse)
async def list_purchase_returns(
    request: Request,
    supplier_id: Optional[UUID] = Query(None),
    grn_id: Optional[UUID] = Query(None),
    return_status: Optional[PurchaseReturnStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List purchase returns for a workspace (paginated, filterable)."""
    records, total = await purchase_return_service.list(
        session=session,
        workspace_id=workspace_id,
        supplier_id=supplier_id,
        grn_id=grn_id,
        status_value=return_status,
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
        data=[PurchaseReturnResponse.model_validate(p) for p in records],
        pagination=pagination,
    )


@router.get(
    "/purchase-returns/{return_id}",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def get_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return one purchase return with its items."""
    record = await purchase_return_service.get(session, workspace_id, return_id)
    if record is None:
        raise_error(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Purchase return not found"
        )
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(record))


@router.post(
    "/purchase-returns/{return_id}/submit-for-supplier-approval",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def submit_for_supplier_approval(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Move a DRAFT return to PENDING_SUPPLIER (OWNER/ADMIN)."""
    _require_admin(user)
    await purchase_return_service.submit_for_supplier_approval(
        session, workspace_id, return_id
    )
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/approve",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def approve_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Approve a PENDING_SUPPLIER return (OWNER/ADMIN)."""
    _require_admin(user)
    await purchase_return_service.approve(session, workspace_id, return_id)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/dispatch",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def dispatch_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Dispatch an APPROVED return: stock-out ledger + auto supplier debit note.
    (OWNER/ADMIN)"""
    _require_admin(user)
    await purchase_return_service.dispatch(session, workspace_id, return_id)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/complete",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def complete_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Mark a DISPATCHED return COMPLETED (OWNER/ADMIN)."""
    _require_admin(user)
    await purchase_return_service.complete(session, workspace_id, return_id)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/reject",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def reject_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Reject a PENDING_SUPPLIER return (OWNER/ADMIN)."""
    _require_admin(user)
    await purchase_return_service.reject(session, workspace_id, return_id)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/cancel",
    response_model=SuccessResponse[PurchaseReturnResponse],
)
async def cancel_purchase_return(
    request: Request,
    return_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Cancel a DRAFT / PENDING_SUPPLIER return (OWNER/ADMIN)."""
    _require_admin(user)
    await purchase_return_service.cancel(session, workspace_id, return_id)
    await session.commit()
    refreshed = await purchase_return_service.get(session, workspace_id, return_id)
    return SuccessResponse(data=PurchaseReturnResponse.model_validate(refreshed))
