"""
Supplier AP Payment Router — Wave 22 (Phase 4).

Endpoints:
- POST /supplier-payments            record AP payment (idempotent, rate limited)
- GET /supplier-payments             paginated list w/ filters
- GET /supplier-payments/{id}        one payment
- PUT /supplier-payments/{id}        405 immutable
- GET /supplier-invoices/{id}/ap-balance  AP balance snapshot
- GET /supplier-invoices/{id}/payments    paginated payments for an invoice
- GET /ap-aging                      AP aging report (summary/detail/by_supplier)
- GET /suppliers/{id}/statement      supplier statement = AP ledger
"""

from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Request,
    status,
)
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.limiter import limiter
from app.models.payment import PaymentStatus
from app.models.supplier_invoice import SupplierInvoice
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.ap_aging import (
    ApAgingBySupplierResponse,
    ApAgingDetailResponse,
    ApAgingSummaryResponse,
)
from app.schemas.common import (
    ErrorCode,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.supplier_payments import (
    SupplierApBalanceResponse,
    SupplierPaymentCreate,
    SupplierPaymentResponse,
)
from app.schemas.supplier_statements import SupplierStatementResponse
from app.services.customer_po_support import raise_error
from app.services.supplier_payment_service import supplier_payment_service
from app.services.supplier_statement_service import supplier_statement_service

router = APIRouter(tags=["Supplier AP Payments"])


def _require_idempotency_key(idempotency_key: Optional[str]) -> str:
    if not idempotency_key:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key header is required",
        )
    if len(idempotency_key) > 255:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            "IDEMPOTENCY_KEY_TOO_LONG",
            "Idempotency-Key must be 255 characters or less",
        )
    return idempotency_key


@router.post(
    "/supplier-payments", response_model=SuccessResponse[SupplierPaymentResponse]
)
@limiter.limit("10/minute")
async def create_supplier_payment(
    request: Request,
    payment_data: SupplierPaymentCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Record a payment against an approved supplier invoice.

    **Rate Limited:** 10 requests per minute per IP.
    **Idempotent:** the same `Idempotency-Key` (48h) returns the same payment.
    **Eligibility:** only APPROVED / PARTIALLY_PAID invoices are payable.
    **No overpayment:** amount cannot exceed balance due.
    """
    key = _require_idempotency_key(idempotency_key)
    invoice_id = payment_data.supplier_invoice_id
    payment = await supplier_payment_service.record_payment(
        session=session,
        workspace_id=workspace_id,
        supplier_invoice_id=invoice_id,
        user_id=user.id,
        amount=payment_data.amount,
        idempotency_key=key,
        payment_method=payment_data.payment_method,
        payment_date=payment_data.payment_date,
        reference_number=payment_data.reference_number,
        bank_name=payment_data.bank_name,
    )
    await session.commit()
    return SuccessResponse(data=SupplierPaymentResponse.model_validate(payment))


@router.get("/supplier-payments", response_model=PaginatedResponse)
async def list_supplier_payments(
    request: Request,
    supplier_id: Optional[UUID] = Query(None),
    supplier_invoice_id: Optional[UUID] = Query(None),
    payment_status: Optional[PaymentStatus] = Query(None, alias="status"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List supplier payments for a workspace (paginated, filterable)."""
    payments, total = await supplier_payment_service.list_payments(
        session=session,
        workspace_id=workspace_id,
        supplier_id=supplier_id,
        supplier_invoice_id=supplier_invoice_id,
        status_value=payment_status,
        from_date=from_date,
        to_date=to_date,
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
        data=[SupplierPaymentResponse.model_validate(p) for p in payments],
        pagination=pagination,
    )


@router.get(
    "/supplier-payments/{payment_id}",
    response_model=SuccessResponse[SupplierPaymentResponse],
)
async def get_supplier_payment(
    request: Request,
    payment_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return one supplier payment (workspace-scoped)."""
    payment = await supplier_payment_service.get_payment(
        session, payment_id, workspace_id
    )
    if payment is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Payment not found")
    return SuccessResponse(data=SupplierPaymentResponse.model_validate(payment))


@router.put(
    "/supplier-payments/{payment_id}",
    response_model=SuccessResponse[SupplierPaymentResponse],
)
async def update_supplier_payment(
    request: Request,
    payment_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Supplier payments are immutable."""
    del payment_id
    raise_error(
        status.HTTP_405_METHOD_NOT_ALLOWED,
        ErrorCode.METHOD_NOT_ALLOWED,
        "Supplier payment records cannot be updated or deleted",
    )


@router.get(
    "/supplier-invoices/{invoice_id}/ap-balance",
    response_model=SuccessResponse[SupplierApBalanceResponse],
)
async def get_ap_balance(
    request: Request,
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Return supplier-invoice AP: total, paid, and remaining due."""
    result = await session.execute(
        select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id,
            SupplierInvoice.workspace_id == workspace_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found")
    return SuccessResponse(
        data=SupplierApBalanceResponse(
            total_amount=invoice.total_amount,
            amount_paid=invoice.amount_paid,
            balance_due=invoice.balance_due,
            currency=invoice.currency,
        )
    )


@router.get(
    "/supplier-invoices/{invoice_id}/payments", response_model=PaginatedResponse
)
async def list_invoice_payments(
    request: Request,
    invoice_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List all payments for a supplier invoice (paginated)."""
    result = await session.execute(
        select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id,
            SupplierInvoice.workspace_id == workspace_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise_error(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice not found")
    payments, total = await supplier_payment_service.list_payments(
        session=session,
        workspace_id=workspace_id,
        supplier_invoice_id=invoice_id,
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
        data=[SupplierPaymentResponse.model_validate(p) for p in payments],
        pagination=pagination,
    )


@router.get("/ap-aging", response_model=SuccessResponse[ApAgingSummaryResponse])
async def ap_aging_summary(
    request: Request,
    as_of: Optional[date] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """AP aging report (default view=summary)."""
    payload = await supplier_payment_service.ap_aging(
        session, workspace_id, as_of=as_of, supplier_id=supplier_id, view="summary"
    )
    return SuccessResponse(data=payload)


@router.get("/ap-aging/detail", response_model=SuccessResponse[ApAgingDetailResponse])
async def ap_aging_detail(
    request: Request,
    as_of: Optional[date] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """AP aging, invoice-level detail."""
    payload = await supplier_payment_service.ap_aging(
        session, workspace_id, as_of=as_of, supplier_id=supplier_id, view="detail"
    )
    return SuccessResponse(data=payload)


@router.get(
    "/ap-aging/by-supplier", response_model=SuccessResponse[ApAgingBySupplierResponse]
)
async def ap_aging_by_supplier(
    request: Request,
    as_of: Optional[date] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """AP aging, per-supplier breakdown."""
    payload = await supplier_payment_service.ap_aging(
        session,
        workspace_id,
        as_of=as_of,
        supplier_id=supplier_id,
        view="by_supplier",
    )
    return SuccessResponse(data=payload)


@router.get(
    "/suppliers/{supplier_id}/statement",
    response_model=SuccessResponse[SupplierStatementResponse],
    response_model_by_alias=True,
)
async def get_supplier_statement(
    request: Request,
    supplier_id: UUID,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    as_of: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Generated supplier statement = the AP ledger. Read-only."""
    workspace = await session.get(Workspace, workspace_id)
    payload = await supplier_statement_service.get_statement(
        session,
        workspace,
        supplier_id,
        period_from,
        period_to,
        as_of,
        actor_id=user.id,
    )
    return SuccessResponse(data=SupplierStatementResponse.model_validate(payload))
