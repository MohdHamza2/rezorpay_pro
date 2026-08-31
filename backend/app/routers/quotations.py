"""Quotation CRUD router with commercial-offer state machine."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.client import Client
from app.models.quotation import Quotation, QuotationStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.customer_purchase_orders import (
    CustomerPurchaseOrderResponse,
    QuotationConvertToLpoRequest,
)
from app.schemas.invoices import InvoiceResponse
from app.schemas.quotations import (
    QuotationCreate,
    QuotationRejectRequest,
    QuotationResponse,
    QuotationSendRequest,
    QuotationUpdate,
)
from app.services.customer_po_service import CustomerPurchaseOrderService
from app.services.invoice_service import InvoiceService
from app.services.quotation_service import QuotationService

router = APIRouter(prefix="/quotations", tags=["Quotations"])


async def _require_client(
    session: AsyncSession, client_id: UUID, workspace_id: UUID
) -> None:
    result = await session.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )


async def _load_or_404(
    session: AsyncSession,
    quotation_id: UUID,
    workspace_id: UUID,
    *,
    for_update: bool = False,
) -> Quotation:
    quote = await QuotationService.get_visible(
        session, quotation_id, workspace_id, for_update=for_update
    )
    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found"
        )
    return quote


async def _wrapped(
    session: AsyncSession, quote: Quotation, workspace_id: UUID
) -> SuccessResponse[QuotationResponse]:
    converted = await QuotationService.map_converted_ids(
        session, [quote.id], workspace_id
    )
    lpos = await QuotationService.map_converted_lpo_ids(
        session, [quote.id], workspace_id
    )
    return SuccessResponse(
        data=QuotationService.serialize(
            quote, converted.get(quote.id), lpos.get(quote.id)
        )
    )


async def _load_and_expire(
    session: AsyncSession,
    quotation_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
) -> Quotation:
    quote = await _load_or_404(session, quotation_id, workspace_id, for_update=True)
    if await QuotationService.expire_if_due(session, quote, user_id):
        await session.commit()
    return quote


@router.post(
    "",
    response_model=SuccessResponse[QuotationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation(
    quotation_data: QuotationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT quotation with QUO-YYYY-XXXX numbering."""
    await _require_client(session, quotation_data.client_id, workspace_id)
    quote = await QuotationService.create(
        session=session,
        workspace_id=workspace_id,
        client_id=quotation_data.client_id,
        user_id=user.id,
        quotation_date=quotation_data.quotation_date,
        valid_until=quotation_data.valid_until,
        currency=quotation_data.currency.value,
        notes=quotation_data.notes,
        items=[item.model_dump() for item in quotation_data.items],
    )
    loaded = await QuotationService.get_visible(session, quote.id, workspace_id)
    await session.commit()
    return await _wrapped(session, loaded, workspace_id)


@router.get("", response_model=PaginatedResponse)
async def list_quotations(
    status_filter: Optional[QuotationStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    client_id: Optional[UUID] = Query(None, description="Filter by client"),
    search: Optional[str] = Query(None, description="Search quotation number"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List quotations. Expires overdue SENT rows on-read before filtering."""
    await QuotationService.expire_workspace_sent(session, workspace_id, user.id)
    query = select(Quotation).where(Quotation.workspace_id == workspace_id)
    query = query.where(Quotation.deleted_at.is_(None))
    if status_filter:
        query = query.where(Quotation.status == status_filter)
    if client_id:
        query = query.where(Quotation.client_id == client_id)
    if search:
        query = query.where(Quotation.quotation_number.ilike(f"%{search}%"))
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(Quotation.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(query)
    quotes = result.scalars().all()
    converted = await QuotationService.map_converted_ids(
        session, [q.id for q in quotes], workspace_id
    )
    lpos = await QuotationService.map_converted_lpo_ids(
        session, [q.id for q in quotes], workspace_id
    )
    await session.commit()
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
        data=[
            QuotationService.serialize_list_item(q, converted.get(q.id), lpos.get(q.id))
            for q in quotes
        ],
        pagination=pagination,
    )


@router.get("/{quotation_id}", response_model=SuccessResponse[QuotationResponse])
async def get_quotation(
    quotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a quotation. SENT past valid_until becomes EXPIRED on-read."""
    quote = await QuotationService.get_for_response(
        session, quotation_id, workspace_id, user.id
    )
    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found"
        )
    await session.commit()
    return await _wrapped(session, quote, workspace_id)


@router.put("/{quotation_id}", response_model=SuccessResponse[QuotationResponse])
async def update_quotation(
    quotation_id: UUID,
    quotation_data: QuotationUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Replace DRAFT quotation fields. Non-DRAFT → 403 INVALID_STATE."""
    quote = await _load_or_404(session, quotation_id, workspace_id, for_update=True)
    patch = quotation_data.model_dump(exclude_unset=True)
    items = patch.pop("items", None)
    await QuotationService.update_draft(
        session=session,
        quotation=quote,
        user_id=user.id,
        patch=patch,
        items=items,
    )
    await session.commit()
    loaded = await QuotationService.get_visible(session, quote.id, workspace_id)
    return await _wrapped(session, loaded, workspace_id)


@router.delete("/{quotation_id}", status_code=status.HTTP_200_OK)
async def delete_quotation(
    quotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Soft-delete a DRAFT quotation. Does not rewind the number counter."""
    quote = await _load_or_404(session, quotation_id, workspace_id, for_update=True)
    await QuotationService.soft_delete(quote)
    await session.commit()
    return SuccessResponse(
        data={
            "message": "Quotation deleted successfully",
            "quotation_id": str(quotation_id),
        }
    )


@router.post("/{quotation_id}/send", response_model=SuccessResponse[QuotationResponse])
async def send_quotation(
    quotation_id: UUID,
    _body: QuotationSendRequest = Body(default_factory=QuotationSendRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DRAFT → SENT. No FTA TRN/address gate (quotes are not tax invoices)."""
    quote = await _load_or_404(session, quotation_id, workspace_id, for_update=True)
    await QuotationService.send(session, quote, user.id)
    await session.commit()
    loaded = await QuotationService.get_visible(session, quote.id, workspace_id)
    return await _wrapped(session, loaded, workspace_id)


@router.post(
    "/{quotation_id}/accept", response_model=SuccessResponse[QuotationResponse]
)
async def accept_quotation(
    quotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """SENT → ACCEPTED. Expired on-read cannot accept."""
    quote = await _load_and_expire(session, quotation_id, workspace_id, user.id)
    await QuotationService.accept(session, quote, user.id)
    await session.commit()
    loaded = await QuotationService.get_visible(session, quote.id, workspace_id)
    return await _wrapped(session, loaded, workspace_id)


@router.post(
    "/{quotation_id}/reject", response_model=SuccessResponse[QuotationResponse]
)
async def reject_quotation(
    quotation_id: UUID,
    reject_data: QuotationRejectRequest = Body(default_factory=QuotationRejectRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """SENT → REJECTED. Optional `{reason}`."""
    quote = await _load_and_expire(session, quotation_id, workspace_id, user.id)
    reason = reject_data.reason
    await QuotationService.reject(session, quote, user.id, reason)
    await session.commit()
    loaded = await QuotationService.get_visible(session, quote.id, workspace_id)
    return await _wrapped(session, loaded, workspace_id)


@router.post(
    "/{quotation_id}/convert-to-invoice",
    response_model=SuccessResponse[InvoiceResponse],
)
async def convert_quotation_to_invoice(
    quotation_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """ACCEPTED → CONVERTED + DRAFT invoice. Idempotent 200; deleted invoice 409."""
    quote = await _load_and_expire(session, quotation_id, workspace_id, user.id)
    invoice, created = await QuotationService.convert_to_invoice(
        session, quote, user.id, workspace_id
    )
    await session.commit()
    loaded = await InvoiceService.get_for_response(session, invoice.id, workspace_id)
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return SuccessResponse(data=InvoiceService.serialize_invoice_response(loaded))


@router.post(
    "/{quotation_id}/convert-to-lpo",
    response_model=SuccessResponse[CustomerPurchaseOrderResponse],
)
async def convert_quotation_to_lpo(
    quotation_id: UUID,
    response: Response,
    body: QuotationConvertToLpoRequest = Body(
        default_factory=QuotationConvertToLpoRequest
    ),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """ACCEPTED → CONVERTED + DRAFT LPO. Idempotent 200; mutex with invoice convert."""
    quote = await _load_and_expire(session, quotation_id, workspace_id, user.id)
    lpo, created = await QuotationService.convert_to_lpo(
        session,
        quote,
        user.id,
        workspace_id,
        customer_po_number=body.customer_po_number,
        lpo_date=body.lpo_date,
        expected_delivery_date=body.expected_delivery_date,
        notes=body.notes,
    )
    await session.commit()
    loaded = await CustomerPurchaseOrderService.get_visible(
        session, lpo.id, workspace_id
    )
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="LPO not found"
        )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return SuccessResponse(
        data=await CustomerPurchaseOrderService.wrapped(session, loaded, workspace_id)
    )
