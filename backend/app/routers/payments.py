"""
Payment Router with Idempotency and Rate Limiting.

Endpoints:
- POST /invoices/{id}/payments - Record payment (rate limited, idempotent)
- GET /invoices/{id}/payments - List payments
- GET /invoices/{id}/balance - Cash paid, credits, and remaining due
"""

from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.user import User
from app.schemas.common import (
    ErrorCode,
    ErrorDetail,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.payments import (
    BalanceDueResponse,
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    PdcActionRequest,
)
from app.services.customer_po_support import raise_error
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService
from app.services.pdc_service import PdcService
from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.limiter import limiter

router = APIRouter(tags=["Payments"])


def _balance_payload(invoice: Invoice) -> BalanceDueResponse:
    """Cash and credits are separate; due is max(0, total − paid − credited)."""
    amount_paid = invoice.amount_paid
    return BalanceDueResponse(
        total_amount=invoice.total_amount,
        amount_paid=amount_paid,
        amount_credited=invoice.amount_credited,
        total_paid=amount_paid,
        balance_due=InvoiceService.calculate_balance_due(invoice),
        currency=invoice.currency,
    )


@router.post(
    "/invoices/{invoice_id}/payments", response_model=SuccessResponse[PaymentResponse]
)
@limiter.limit("10/minute")
async def create_payment(
    request: Request,
    invoice_id: UUID,
    payment_data: PaymentCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
    settings: Settings = Depends(get_settings),
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
                message="Idempotency-Key header is required",
            ).model_dump(),
        )

    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(
                code="IDEMPOTENCY_KEY_TOO_LONG",
                message="Idempotency-Key must be 255 characters or less",
            ).model_dump(),
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
            payment_method=payment_data.payment_method,
            payment_date=payment_data.payment_date,
            reference_number=payment_data.reference_number,
            bank_name=payment_data.bank_name,
            pdc_date=payment_data.pdc_date,
            pdc_status=payment_data.pdc_status,
            gateway_transaction_id=payment_data.gateway_transaction_id,
        )

        await session.commit()

        return SuccessResponse(data=PaymentResponse.model_validate(payment))

    except ValueError as e:
        error_msg = str(e)

        if "exceeds balance due" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorDetail(
                    code="PAYMENT_EXCEEDS_BALANCE", message=error_msg
                ).model_dump(),
            )
        elif "Invoice not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorDetail(code="NOT_FOUND", message=error_msg).model_dump(),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorDetail(
                    code="VALIDATION_ERROR", message=error_msg
                ).model_dump(),
            )


@router.get("/invoices/{invoice_id}/payments", response_model=PaginatedResponse)
async def list_payments(
    request: Request,
    invoice_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
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
        has_prev=page > 1,
    )

    return PaginatedResponse(
        data=[PaymentResponse.model_validate(p) for p in payments],
        pagination=pagination,
    )


@router.get(
    "/invoices/{invoice_id}/balance", response_model=SuccessResponse[BalanceDueResponse]
)
async def get_balance_due(
    request: Request,
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return invoice AR: cash paid, credits, and remaining due."""
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    return SuccessResponse(data=_balance_payload(invoice))


async def _pdc_response(
    session: AsyncSession, payment: Payment
) -> SuccessResponse[PaymentResponse]:
    await session.commit()
    return SuccessResponse(data=PaymentResponse.model_validate(payment))


@router.put(
    "/invoices/{invoice_id}/payments/{payment_id}",
    response_model=SuccessResponse[PaymentResponse],
)
async def update_payment(
    invoice_id: UUID,
    payment_id: UUID,
    payment_data: PaymentUpdate = Body(default_factory=PaymentUpdate),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Payments are immutable. PDC lifecycle uses dedicated POST actions."""
    del payment_id, payment_data
    invoice_result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
    )
    if invoice_result.scalar_one_or_none() is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found")
    raise_error(
        status.HTTP_405_METHOD_NOT_ALLOWED,
        ErrorCode.METHOD_NOT_ALLOWED,
        "Payment records cannot be updated; use PDC deposit, clear, bounce, or return",
    )


@router.post(
    "/invoices/{invoice_id}/payments/{payment_id}/pdc/deposit",
    response_model=SuccessResponse[PaymentResponse],
)
@limiter.limit("10/minute")
async def deposit_pdc(
    request: Request,
    invoice_id: UUID,
    payment_id: UUID,
    _body: PdcActionRequest = Body(default_factory=PdcActionRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """RECEIVED → DEPOSITED on or after pdc_date. Stays PENDING."""
    payment = await PdcService.deposit(
        session, workspace_id, invoice_id, payment_id, user
    )
    return await _pdc_response(session, payment)


@router.post(
    "/invoices/{invoice_id}/payments/{payment_id}/pdc/clear",
    response_model=SuccessResponse[PaymentResponse],
)
@limiter.limit("10/minute")
async def clear_pdc(
    request: Request,
    invoice_id: UUID,
    payment_id: UUID,
    _body: PdcActionRequest = Body(default_factory=PdcActionRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DEPOSITED → CLEARED (SUCCESS). Historical SUCCESS PDC is a 200 no-op."""
    payment = await PdcService.clear(
        session, workspace_id, invoice_id, payment_id, user
    )
    return await _pdc_response(session, payment)


@router.post(
    "/invoices/{invoice_id}/payments/{payment_id}/pdc/bounce",
    response_model=SuccessResponse[PaymentResponse],
)
@limiter.limit("10/minute")
async def bounce_pdc(
    request: Request,
    invoice_id: UUID,
    payment_id: UUID,
    _body: PdcActionRequest = Body(default_factory=PdcActionRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DEPOSITED → BOUNCED (FAILED). Re-evaluates credit HOLD."""
    payment = await PdcService.bounce(
        session, workspace_id, invoice_id, payment_id, user
    )
    return await _pdc_response(session, payment)


@router.post(
    "/invoices/{invoice_id}/payments/{payment_id}/pdc/return",
    response_model=SuccessResponse[PaymentResponse],
)
@limiter.limit("10/minute")
async def return_pdc(
    request: Request,
    invoice_id: UUID,
    payment_id: UUID,
    _body: PdcActionRequest = Body(default_factory=PdcActionRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """RECEIVED → RETURNED (CANCELLED). Illegal from DEPOSITED."""
    payment = await PdcService.return_cheque(
        session, workspace_id, invoice_id, payment_id, user
    )
    return await _pdc_response(session, payment)
