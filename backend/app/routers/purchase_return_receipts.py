"""
Purchase Return Receipt Router — Wave 31 Item 2.8.

Endpoints:
- POST /purchase-returns/{id}/receive                    create DRAFT receipt
- GET /purchase-returns/{id}/receive                     list receipts for a return
- GET /purchase-returns/{id}/receive/{receipt_id}        one receipt
- POST /purchase-returns/{id}/receive/{receipt_id}/confirm  confirm receiving
- POST /purchase-returns/{id}/receive/{receipt_id}/cancel   cancel receipt
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.purchase_return import PurchaseReturnReceiptStatus
from app.models.user import User, UserRole
from app.schemas.common import (
    ErrorCode,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.purchase_return_receipts import (
    PurchaseReturnReceiptCreate,
    PurchaseReturnReceiptResponse,
)
from app.services.customer_po_support import raise_error
from app.services.purchase_return_receipt_service import purchase_return_receipt_service

router = APIRouter(tags=["Purchase Return Receipts"])


def _require_admin(user: User) -> User:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may modify purchase return receipts",
        )
    return user


@router.post(
    "/purchase-returns/{return_id}/receive",
    response_model=SuccessResponse[PurchaseReturnReceiptResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_return_receipt(
    request: Request,
    return_id: UUID,
    data: PurchaseReturnReceiptCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT purchase return receipt (OWNER/ADMIN)."""
    _require_admin(user)
    if data.purchase_return_id != return_id:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            "purchase_return_id in body must match return_id in path",
        )
    receipt = await purchase_return_receipt_service.create(
        session, workspace_id, user.id, data
    )
    await session.commit()
    refreshed = await purchase_return_receipt_service.get(
        session, workspace_id, receipt.id
    )
    return SuccessResponse(data=PurchaseReturnReceiptResponse.model_validate(refreshed))


@router.get(
    "/purchase-returns/{return_id}/receive",
    response_model=PaginatedResponse,
)
async def list_purchase_return_receipts(
    request: Request,
    return_id: UUID,
    status_value: Optional[PurchaseReturnReceiptStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List purchase return receipts for a purchase return (paginated, filterable)."""
    receipts, total = await purchase_return_receipt_service.list(
        session=session,
        workspace_id=workspace_id,
        purchase_return_id=return_id,
        status_value=status_value,
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
        data=[PurchaseReturnReceiptResponse.model_validate(r) for r in receipts],
        pagination=pagination,
    )


@router.get(
    "/purchase-returns/{return_id}/receive/{receipt_id}",
    response_model=SuccessResponse[PurchaseReturnReceiptResponse],
)
async def get_purchase_return_receipt(
    request: Request,
    return_id: UUID,
    receipt_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return one purchase return receipt with its items."""
    receipt = await purchase_return_receipt_service.get(
        session, workspace_id, receipt_id
    )
    if receipt is None or receipt.purchase_return_id != return_id:
        raise_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "Purchase return receipt not found",
        )
    return SuccessResponse(data=PurchaseReturnReceiptResponse.model_validate(receipt))


@router.post(
    "/purchase-returns/{return_id}/receive/{receipt_id}/confirm",
    response_model=SuccessResponse[PurchaseReturnReceiptResponse],
)
async def confirm_purchase_return_receipt(
    request: Request,
    return_id: UUID,
    receipt_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Confirm a DRAFT receipt: post RECEIPT ledger and update status (OWNER/ADMIN)."""
    _require_admin(user)
    receipt = await purchase_return_receipt_service.confirm_receipt(
        session, workspace_id, receipt_id
    )
    if receipt.purchase_return_id != return_id:
        raise_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "Purchase return receipt not found",
        )
    await session.commit()
    refreshed = await purchase_return_receipt_service.get(
        session, workspace_id, receipt_id
    )
    return SuccessResponse(data=PurchaseReturnReceiptResponse.model_validate(refreshed))


@router.post(
    "/purchase-returns/{return_id}/receive/{receipt_id}/cancel",
    response_model=SuccessResponse[PurchaseReturnReceiptResponse],
)
async def cancel_purchase_return_receipt(
    request: Request,
    return_id: UUID,
    receipt_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Cancel a RECEIVED receipt: reverse the RECEIPT ledger (OWNER/ADMIN)."""
    _require_admin(user)
    receipt = await purchase_return_receipt_service.cancel_receipt(
        session, workspace_id, receipt_id
    )
    if receipt.purchase_return_id != return_id:
        raise_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "Purchase return receipt not found",
        )
    await session.commit()
    refreshed = await purchase_return_receipt_service.get(
        session, workspace_id, receipt_id
    )
    return SuccessResponse(data=PurchaseReturnReceiptResponse.model_validate(refreshed))
