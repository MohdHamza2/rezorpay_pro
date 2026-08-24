"""
Invoice CRUD Router with State Machine.

Endpoints:
- POST /invoices - Create invoice (gapless numbering)
- GET /invoices - List invoices (with filters/pagination)
- GET /invoices/{id} - Get invoice
- PUT /invoices/{id} - Update invoice (draft only)
- DELETE /invoices/{id} - Soft delete invoice (draft only)
- POST /invoices/{id}/send - Mark as sent
- POST /invoices/{id}/void - Void invoice
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.user import User
from app.schemas.common import (
    ErrorDetail,
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)
from app.schemas.invoices import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceSendRequest,
    InvoiceUpdate,
    InvoiceVoidRequest,
)
from app.services.invoice_service import InvoiceService
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/invoices", tags=["Invoices"])


async def get_current_workspace_id(user: User = Depends(get_current_user)) -> UUID:
    """Get current workspace ID from user."""
    if not user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No workspace access"
        )
    return user.workspace_id


@router.post(
    "",
    response_model=SuccessResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    request: Request,
    invoice_data: InvoiceCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Create a new invoice with gapless numbering.

    Invoice number is generated atomically with row locking.
    """
    # Validate client exists and belongs to workspace
    client_result = await session.execute(
        select(Client)
        .where(Client.id == invoice_data.client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
    )
    client = client_result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )

    # Create invoice
    invoice = await InvoiceService.create_invoice(
        session=session,
        workspace_id=workspace_id,
        client_id=invoice_data.client_id,
        user_id=user.id,
        issue_date=invoice_data.issue_date,
        due_date=invoice_data.due_date,
        currency=invoice_data.currency.value,
        notes=invoice_data.notes,
        items=[item.model_dump() for item in invoice_data.items],
    )

    # Eager load items for response
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice.id)
    )
    invoice_with_items = result.scalar_one()

    await session.commit()

    return SuccessResponse(
        data=InvoiceService.serialize_invoice_response(invoice_with_items)
    )


@router.get("", response_model=PaginatedResponse)
async def list_invoices(
    request: Request,
    status: Optional[InvoiceStatus] = Query(None, description="Filter by status"),
    client_id: Optional[UUID] = Query(None, description="Filter by client"),
    search: Optional[str] = Query(None, description="Search invoice number"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    include_deleted: bool = Query(False, description="Include soft-deleted invoices"),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    List invoices with filters and pagination.
    """
    # Base query with eager loading for performance
    query = (
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(Invoice.workspace_id == workspace_id)
    )

    # Exclude deleted by default
    if not include_deleted:
        query = query.where(Invoice.deleted_at.is_(None))

    # Status filter
    if status:
        query = query.where(Invoice.status == status)

    # Client filter
    if client_id:
        query = query.where(Invoice.client_id == client_id)

    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(Invoice.invoice_number.ilike(search_term))

    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.order_by(Invoice.created_at.desc())

    # Execute query
    result = await session.execute(query)
    invoices = result.scalars().all()

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
        data=[InvoiceService.serialize_invoice_list_item(inv) for inv in invoices],
        pagination=pagination,
    )


@router.get("/{invoice_id}", response_model=SuccessResponse[InvoiceResponse])
async def get_invoice(
    request: Request,
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a specific invoice with items."""
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    return SuccessResponse(data=InvoiceService.serialize_invoice_response(invoice))


@router.put("/{invoice_id}", response_model=SuccessResponse[InvoiceResponse])
async def update_invoice(
    request: Request,
    invoice_id: UUID,
    invoice_data: InvoiceUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Update an invoice.

    Only allowed for DRAFT invoices.
    """
    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    # Check if invoice can be edited (draft only)
    if not await InvoiceService.can_edit(invoice):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ErrorDetail(
                code="INVALID_STATE",
                message=f"Cannot edit invoice with status '{invoice.status.value}'. "
                "Only DRAFT invoices can be edited.",
            ).model_dump(),
        )

    # Update fields
    update_data = invoice_data.model_dump(exclude_unset=True)

    # Handle items update if provided
    if "items" in update_data:
        items_data = update_data.pop("items")
        # Delete existing items
        await session.execute(
            InvoiceItem.__table__.delete().where(InvoiceItem.invoice_id == invoice_id)
        )
        # Add new items
        for item_data in items_data:
            item = InvoiceItem(invoice_id=invoice_id, **item_data)
            item.total_price = (
                item.quantity * item.unit_price * (1 + item.tax_rate / 100)
            )
            session.add(item)

    # Update other fields
    for field, value in update_data.items():
        if field == "currency":
            value = value.value
        setattr(invoice, field, value)

    # Recalculate totals
    await InvoiceService._recalculate_totals(session, invoice)

    # Log update event
    from app.services.audit_service import AuditService

    await AuditService.log_invoice_updated(
        session=session,
        invoice_id=invoice.id,
        user_id=user.id,
        changed_fields=list(update_data.keys()),
    )

    await session.commit()
    await session.refresh(invoice)

    # Reload with items
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice.id)
    )
    invoice_with_items = result.scalar_one()

    return SuccessResponse(
        data=InvoiceService.serialize_invoice_response(invoice_with_items)
    )


@router.delete("/{invoice_id}", status_code=status.HTTP_200_OK)
async def delete_invoice(
    request: Request,
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Soft delete an invoice.

    Only allowed for DRAFT invoices. Use /void for sent/paid invoices.
    """
    from datetime import datetime, timezone

    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    # Check if invoice can be deleted (draft only)
    if not await InvoiceService.can_delete(invoice):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ErrorDetail(
                code="INVALID_STATE",
                message=f"Cannot delete invoice with status '{invoice.status.value}'. "
                "Use POST /invoices/{id}/void instead.",
            ).model_dump(),
        )

    # Soft delete
    invoice.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    return SuccessResponse(
        data={"message": "Invoice deleted successfully", "invoice_id": str(invoice_id)}
    )


@router.post("/{invoice_id}/send", response_model=SuccessResponse[InvoiceResponse])
async def send_invoice(
    request: Request,
    invoice_id: UUID,
    send_data: InvoiceSendRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Mark invoice as sent.

    Only allowed for DRAFT invoices.
    """
    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    # Mark as sent
    await InvoiceService.mark_as_sent(
        session=session,
        invoice=invoice,
        user_id=user.id,
        sent_method="email",
        recipient=send_data.recipient,
    )

    await session.commit()
    await session.refresh(invoice)

    # Reload with items
    result = await session.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice.id)
    )
    invoice_with_items = result.scalar_one()

    return SuccessResponse(data=InvoiceResponse.model_validate(invoice_with_items))


@router.post("/{invoice_id}/void", response_model=SuccessResponse[InvoiceResponse])
async def void_invoice(
    request: Request,
    invoice_id: UUID,
    void_data: InvoiceVoidRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Void (cancel) an invoice.

    Creates audit trail for accounting. Not allowed for already voided invoices.
    """
    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )

    # Void the invoice
    await InvoiceService.void_invoice(
        session=session, invoice=invoice, user_id=user.id, reason=void_data.reason
    )

    await session.commit()
    await session.refresh(invoice)

    return SuccessResponse(data=InvoiceResponse.model_validate(invoice))
