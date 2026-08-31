"""Customer LPO CRUD router with inbound-demand state machine."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.client import Client
from app.models.customer_purchase_order import (
    CustomerPurchaseOrder,
    CustomerPurchaseOrderStatus,
)
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.customer_purchase_orders import (
    CustomerPurchaseOrderCancelRequest,
    CustomerPurchaseOrderCreate,
    CustomerPurchaseOrderReceiveRequest,
    CustomerPurchaseOrderResponse,
    CustomerPurchaseOrderUpdate,
    LpoInvoiceCreateRequest,
)
from app.schemas.invoices import InvoiceResponse
from app.services.customer_po_service import CustomerPurchaseOrderService
from app.services.invoice_service import InvoiceService

router = APIRouter(
    prefix="/customer-purchase-orders", tags=["Customer Purchase Orders"]
)


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
    lpo_id: UUID,
    workspace_id: UUID,
    *,
    for_update: bool = False,
) -> CustomerPurchaseOrder:
    lpo = await CustomerPurchaseOrderService.get_visible(
        session, lpo_id, workspace_id, for_update=for_update
    )
    if lpo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="LPO not found"
        )
    return lpo


async def _wrapped(
    session: AsyncSession, lpo: CustomerPurchaseOrder, workspace_id: UUID
) -> SuccessResponse[CustomerPurchaseOrderResponse]:
    return SuccessResponse(
        data=await CustomerPurchaseOrderService.wrapped(session, lpo, workspace_id)
    )


@router.post(
    "",
    response_model=SuccessResponse[CustomerPurchaseOrderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_purchase_order(
    lpo_data: CustomerPurchaseOrderCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT LPO with LPO-YYYY-XXXX numbering."""
    await _require_client(session, lpo_data.client_id, workspace_id)
    lpo = await CustomerPurchaseOrderService.create(
        session=session,
        workspace_id=workspace_id,
        client_id=lpo_data.client_id,
        user_id=user.id,
        items=[item.model_dump() for item in lpo_data.items],
        customer_po_number=lpo_data.customer_po_number,
        lpo_date=lpo_data.lpo_date,
        expected_delivery_date=lpo_data.expected_delivery_date,
        currency=lpo_data.currency.value,
        notes=lpo_data.notes,
    )
    loaded = await CustomerPurchaseOrderService.get_visible(
        session, lpo.id, workspace_id
    )
    await session.commit()
    return await _wrapped(session, loaded, workspace_id)


@router.get("", response_model=PaginatedResponse)
async def list_customer_purchase_orders(
    status_filter: Optional[CustomerPurchaseOrderStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    client_id: Optional[UUID] = Query(None, description="Filter by client"),
    search: Optional[str] = Query(
        None, description="Search LPO number or customer PO number"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List LPOs. Search matches lpo_number or customer_po_number."""
    query = CustomerPurchaseOrderService.list_filters(
        workspace_id, status_filter, client_id, search
    )
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    query = query.order_by(CustomerPurchaseOrder.created_at.desc())
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
        data=[CustomerPurchaseOrderService.serialize_list_item(row) for row in rows],
        pagination=pagination,
    )


@router.get("/{lpo_id}", response_model=SuccessResponse[CustomerPurchaseOrderResponse])
async def get_customer_purchase_order(
    lpo_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get an LPO with remaining qty and countable invoices."""
    lpo = await _load_or_404(session, lpo_id, workspace_id)
    return await _wrapped(session, lpo, workspace_id)


@router.put("/{lpo_id}", response_model=SuccessResponse[CustomerPurchaseOrderResponse])
async def update_customer_purchase_order(
    lpo_id: UUID,
    lpo_data: CustomerPurchaseOrderUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Replace DRAFT LPO fields. Non-DRAFT → 403 INVALID_STATE."""
    lpo = await _load_or_404(session, lpo_id, workspace_id, for_update=True)
    patch = lpo_data.model_dump(exclude_unset=True)
    items = patch.pop("items", None)
    await CustomerPurchaseOrderService.update_draft(
        session=session,
        lpo=lpo,
        user_id=user.id,
        patch=patch,
        items=items,
    )
    await session.commit()
    loaded = await CustomerPurchaseOrderService.get_visible(
        session, lpo.id, workspace_id
    )
    return await _wrapped(session, loaded, workspace_id)


@router.delete("/{lpo_id}", status_code=status.HTTP_200_OK)
async def delete_customer_purchase_order(
    lpo_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Soft-delete a DRAFT LPO. Does not rewind the number counter."""
    lpo = await _load_or_404(session, lpo_id, workspace_id, for_update=True)
    await CustomerPurchaseOrderService.soft_delete(lpo)
    await session.commit()
    return SuccessResponse(
        data={"message": "LPO deleted successfully", "lpo_id": str(lpo_id)}
    )


@router.post(
    "/{lpo_id}/receive",
    response_model=SuccessResponse[CustomerPurchaseOrderResponse],
)
async def receive_customer_purchase_order(
    lpo_id: UUID,
    _body: CustomerPurchaseOrderReceiveRequest = Body(
        default_factory=CustomerPurchaseOrderReceiveRequest
    ),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """DRAFT → RECEIVED. Lines freeze; invoicing is allowed after this."""
    lpo = await _load_or_404(session, lpo_id, workspace_id, for_update=True)
    await CustomerPurchaseOrderService.receive(session, lpo, user.id)
    await session.commit()
    loaded = await CustomerPurchaseOrderService.get_visible(
        session, lpo.id, workspace_id
    )
    return await _wrapped(session, loaded, workspace_id)


@router.post(
    "/{lpo_id}/cancel",
    response_model=SuccessResponse[CustomerPurchaseOrderResponse],
)
async def cancel_customer_purchase_order(
    lpo_id: UUID,
    cancel_data: CustomerPurchaseOrderCancelRequest = Body(
        default_factory=CustomerPurchaseOrderCancelRequest
    ),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """RECEIVED → CANCELLED when there are no countable invoices."""
    lpo = await _load_or_404(session, lpo_id, workspace_id, for_update=True)
    await CustomerPurchaseOrderService.cancel(session, lpo, user.id, cancel_data.reason)
    await session.commit()
    loaded = await CustomerPurchaseOrderService.get_visible(
        session, lpo.id, workspace_id
    )
    return await _wrapped(session, loaded, workspace_id)


@router.post(
    "/{lpo_id}/invoices",
    response_model=SuccessResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def invoice_customer_purchase_order(
    lpo_id: UUID,
    body: LpoInvoiceCreateRequest = Body(default_factory=LpoInvoiceCreateRequest),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a DRAFT tax invoice from remaining LPO qty. Always 201."""
    lpo = await _load_or_404(session, lpo_id, workspace_id, for_update=True)
    requested = None
    if body.items is not None:
        requested = [item.model_dump() for item in body.items]
    invoice = await CustomerPurchaseOrderService.create_invoices(
        session=session,
        lpo=lpo,
        user_id=user.id,
        workspace_id=workspace_id,
        requested=requested,
        notes=body.notes,
        issue_date=body.issue_date,
        supply_date=body.supply_date,
        due_date=body.due_date,
    )
    await session.commit()
    loaded = await InvoiceService.get_for_response(session, invoice.id, workspace_id)
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    return SuccessResponse(data=InvoiceService.serialize_invoice_response(loaded))
