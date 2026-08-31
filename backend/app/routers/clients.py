"""
Client CRUD Router.

Endpoints:
- POST /clients - Create client
- GET /clients - List clients (with search/pagination)
- GET /clients/{id} - Get client
- GET /clients/{id}/credit - Aging JSON
- PUT /clients/{id} - Update client
- DELETE /clients/{id} - Soft delete client
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.database import get_session
from app.models.client import Client
from app.models.credit_status_event import CreditEventReason, CreditStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.clients import (
    ClientCreate,
    ClientCreditResponse,
    ClientResponse,
    ClientUpdate,
)
from app.schemas.common import (
    ErrorDetail,
    PaginationMeta,
    PaginatedResponse,
    SuccessResponse,
)
from app.services.credit_control_service import CreditControlService

router = APIRouter(prefix="/clients", tags=["Clients"])


async def _workspace(session: AsyncSession, workspace_id: UUID) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return workspace


async def _visible_client(
    session: AsyncSession, client_id: UUID, workspace_id: UUID
) -> Client:
    client = await CreditControlService.load_client(session, client_id, workspace_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


async def _to_response(
    session: AsyncSession,
    client: Client,
    workspace: Workspace,
    user_id: UUID,
) -> ClientResponse:
    snap = await CreditControlService.evaluate(
        session, client, workspace, user_id, CreditEventReason.EVALUATE
    )
    payload = ClientResponse.model_validate(client)
    return payload.model_copy(
        update={
            "credit_status": snap.status,
            "effective_credit_limit": snap.effective_limit,
            "exposure": snap.exposure,
        }
    )


@router.post(
    "",
    response_model=SuccessResponse[ClientResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_client(
    request: Request,
    client_data: ClientCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Create a new client in the workspace."""
    workspace = await _workspace(session, workspace_id)
    client = Client(
        workspace_id=workspace_id,
        name=client_data.name,
        email=client_data.email,
        phone=client_data.phone,
        address=client_data.address,
        tax_id=client_data.tax_id,
        credit_limit=client_data.credit_limit,
        payment_terms_days=client_data.payment_terms_days,
    )
    session.add(client)
    await session.flush()
    data = await _to_response(session, client, workspace, user.id)
    await session.commit()
    return SuccessResponse(data=data)


@router.get("", response_model=PaginatedResponse)
async def list_clients(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    credit_status: Optional[CreditStatus] = Query(
        None, description="Filter by evaluated credit status"
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    include_deleted: bool = Query(False, description="Include soft-deleted clients"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """List clients with search and pagination. Evaluates credit on-read."""
    workspace = await _workspace(session, workspace_id)
    query = select(Client).where(Client.workspace_id == workspace_id)
    if not include_deleted:
        query = query.where(Client.deleted_at.is_(None))
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Client.name.ilike(search_term))
            | (Client.email.ilike(search_term))
            | (Client.phone.ilike(search_term))
        )
    query = query.order_by(Client.name)
    result = await session.execute(query)
    rows = list(result.scalars().all())
    payloads = []
    for client in rows:
        payload = await _to_response(session, client, workspace, user.id)
        if credit_status is None or payload.credit_status == credit_status:
            payloads.append(payload)
    await session.commit()
    total = len(payloads)
    pages = (total + per_page - 1) // per_page if total else 0
    start = (page - 1) * per_page
    pagination = PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return PaginatedResponse(
        data=payloads[start : start + per_page], pagination=pagination
    )


@router.get("/{client_id}", response_model=SuccessResponse[ClientResponse])
async def get_client(
    request: Request,
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a specific client by ID."""
    workspace = await _workspace(session, workspace_id)
    client = await _visible_client(session, client_id, workspace_id)
    data = await _to_response(session, client, workspace, user.id)
    await session.commit()
    return SuccessResponse(data=data)


@router.get("/{client_id}/credit", response_model=SuccessResponse[ClientCreditResponse])
async def get_client_credit(
    request: Request,
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Aging buckets and live exposure for a client. Isolation 404."""
    workspace = await _workspace(session, workspace_id)
    client = await _visible_client(session, client_id, workspace_id)
    await CreditControlService.evaluate(
        session, client, workspace, user.id, CreditEventReason.EVALUATE
    )
    payload = await CreditControlService.aging(session, client, workspace)
    await session.commit()
    return SuccessResponse(data=ClientCreditResponse.model_validate(payload))


@router.put("/{client_id}", response_model=SuccessResponse[ClientResponse])
async def update_client(
    request: Request,
    client_id: UUID,
    client_data: ClientUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Update a client."""
    workspace = await _workspace(session, workspace_id)
    client = await _visible_client(session, client_id, workspace_id)
    update_data = client_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)
    data = await _to_response(session, client, workspace, user.id)
    await session.commit()
    return SuccessResponse(data=data)


@router.delete("/{client_id}", status_code=status.HTTP_200_OK)
async def delete_client(
    request: Request,
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    Soft delete a client.

    Blocked if client has any non-draft invoices.
    """
    client = await _visible_client(session, client_id, workspace_id)
    invoice_result = await session.execute(
        select(Invoice)
        .where(Invoice.client_id == client_id)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
        .where(Invoice.status != InvoiceStatus.DRAFT)
    )
    non_draft_invoices = invoice_result.scalars().all()
    if non_draft_invoices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorDetail(
                code="CLIENT_HAS_INVOICES",
                message="Cannot delete client with non-draft invoices. "
                f"Found {len(non_draft_invoices)} invoice(s). "
                "Delete or void all invoices first.",
            ).model_dump(),
        )
    client.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return SuccessResponse(
        data={"message": "Client deleted successfully", "client_id": str(client_id)}
    )
