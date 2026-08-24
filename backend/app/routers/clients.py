"""
Client CRUD Router.

Endpoints:
- POST /clients - Create client
- GET /clients - List clients (with search/pagination)
- GET /clients/{id} - Get client
- PUT /clients/{id} - Update client
- DELETE /clients/{id} - Soft delete client
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.user import User
from app.schemas.clients import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.common import (
    ErrorDetail,
    PaginationMeta,
    PaginatedResponse,
    SuccessResponse,
)
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/clients", tags=["Clients"])


async def get_current_workspace_id(user: User = Depends(get_current_user)) -> UUID:
    """Get current workspace ID from user."""
    if not user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No workspace access"
        )
    return user.workspace_id


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
    # Create client
    client = Client(
        workspace_id=workspace_id,
        name=client_data.name,
        email=client_data.email,
        phone=client_data.phone,
        address=client_data.address,
        tax_id=client_data.tax_id,
    )

    session.add(client)
    await session.commit()
    await session.refresh(client)

    return SuccessResponse(data=ClientResponse.model_validate(client))


@router.get("", response_model=PaginatedResponse)
async def list_clients(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    include_deleted: bool = Query(False, description="Include soft-deleted clients"),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """
    List clients with search and pagination.

    Query Parameters:
    - search: Filter by name, email, or phone (case-insensitive)
    - page: Page number (1-based)
    - per_page: Items per page (max 100)
    - include_deleted: Include soft-deleted clients
    """
    # Base query
    query = select(Client).where(Client.workspace_id == workspace_id)

    # Exclude deleted by default
    if not include_deleted:
        query = query.where(Client.deleted_at.is_(None))

    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Client.name.ilike(search_term))
            | (Client.email.ilike(search_term))
            | (Client.phone.ilike(search_term))
        )

    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.order_by(Client.name)

    # Execute query
    result = await session.execute(query)
    clients = result.scalars().all()

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
        data=[ClientResponse.model_validate(c) for c in clients], pagination=pagination
    )


@router.get("/{client_id}", response_model=SuccessResponse[ClientResponse])
async def get_client(
    request: Request,
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Get a specific client by ID."""
    result = await session.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )

    return SuccessResponse(data=ClientResponse.model_validate(client))


@router.put("/{client_id}", response_model=SuccessResponse[ClientResponse])
async def update_client(
    request: Request,
    client_id: UUID,
    client_data: ClientUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Update a client."""
    result = await session.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )

    # Update fields
    update_data = client_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await session.commit()
    await session.refresh(client)

    return SuccessResponse(data=ClientResponse.model_validate(client))


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
    from datetime import datetime, timezone

    # Get client
    result = await session.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.workspace_id == workspace_id)
        .where(Client.deleted_at.is_(None))
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )

    # Check for non-draft invoices
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

    # Soft delete
    client.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    return SuccessResponse(
        data={"message": "Client deleted successfully", "client_id": str(client_id)}
    )
