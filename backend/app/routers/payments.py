"""
Payment Router with Idempotency and Rate Limiting.

Endpoints:
- POST /invoices/{id}/payments - Record payment (rate limited, idempotent)
- GET /invoices/{id}/payments - List payments
- GET /invoices/{id}/balance - Get balance due
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.common import ErrorDetail, PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.payments import BalanceDueResponse, PaymentCreate, PaymentListResponse, PaymentResponse
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService

router = APIRouter(tags=["Payments"])


async def get_current_user(request: Request) -> User:
    """Get current authenticated user from request state."""
    user = request.state.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


async def get_current_workspace_id(request: Request) -> UUID:
    """Get current workspace ID from request state."""
    workspace_id = request.state.workspace_id
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No workspace access"
        )
    return workspace_id


from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


@router.post("/invoices/{invoice_id}/payments", response_model=SuccessResponse[PaymentResponse])
@limiter.limit("10/minute")
async def create_payment(
    request: Request,
    invoice_id: UUID,
    payment_data: PaymentCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
    settings: Settings = Depends(get_settings)
):
    """
    Record a payment for an invoice.
    
    **Rate Limited:** 10 requests per minute per IP
    
    **Idempotent:** Include `Idempotency-Key` header to prevent duplicates.
    Same key within 48 hours returns the same payment without creating a new one.
    
    **No Overpayments:** Payment amount cannot exceed balance due.
    """
    # Validate idempotency key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(
                code="IDEMPOTENCY_KEY_REQUIRED",
                message="Idempotency-Key header is required"
            ).model_dump()
        )
    
    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(
                code="IDEMPOTENCY_KEY_TOO_LONG",
                message="Idempotency-Key must be 255 characters or less"
            ).model_dump()
        )
    
    # Check rate limit (simplified - use slowapi in production)
    # In real implementation, this would be a decorator: @limiter.limit("10/minute")
    
    try:
        payment = await PaymentService.record_payment(
            session=session,
            workspace_id=workspace_id,
            invoice_id=invoice_id,
            user_id=user.id,
            amount=payment_data.amount,
            idempotency_key=idempotency_key,
            gateway=payment_data.gateway,
            gateway_transaction_id=payment_data.gateway_transaction_id,
            payment_date=payment_data.payment_date
        )
        
        await session.commit()
        
        return SuccessResponse(data=PaymentResponse.model_validate(payment))
    
    except ValueError as e:
        error_msg = str(e)
        
        if "exceeds balance due" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorDetail(
                    code="PAYMENT_EXCEEDS_BALANCE",
                    message=error_msg
                ).model_dump()
            )
        elif "Invoice not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorDetail(
                    code="NOT_FOUND",
                    message=error_msg
                ).model_dump()
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message=error_msg
                ).model_dump()
            )


@router.get("/invoices/{invoice_id}/payments", response_model=PaginatedResponse)
async def list_payments(
    request: Request,
    invoice_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id)
):
    """List all payments for an invoice."""
    from sqlalchemy import func
    
    # Verify invoice exists and belongs to workspace
    invoice_result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Get payments
    query = select(Payment).where(Payment.invoice_id == invoice_id)
    
    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    
    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.order_by(Payment.payment_date.desc())
    
    result = await session.execute(query)
    payments = result.scalars().all()
    
    # Build pagination metadata
    pages = (total + per_page - 1) // per_page
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1
    )
    
    return PaginatedResponse(
        data=[PaymentResponse.model_validate(p) for p in payments],
        pagination=pagination
    )


@router.get("/invoices/{invoice_id}/balance", response_model=SuccessResponse[BalanceDueResponse])
async def get_balance_due(
    request: Request,
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id)
):
    """
    Get current balance due for an invoice.
    
    Only counts successful payments toward balance.
    """
    # Get invoice with payments
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Calculate balance due (only successful payments)
    balance_due = InvoiceService.calculate_balance_due(invoice)
    
    # Calculate total paid (only successful payments)
    total_paid = invoice.total_amount - balance_due
    
    return SuccessResponse(
        data=BalanceDueResponse(
            total_amount=invoice.total_amount,
            total_paid=total_paid,
            balance_due=balance_due,
            currency=invoice.currency
        )
    )
