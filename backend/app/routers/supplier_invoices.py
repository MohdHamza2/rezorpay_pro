import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.supplier_invoice import SupplierInvoice
from app.schemas.common import SuccessResponse
from app.schemas.supplier_invoices import (
    SupplierInvoiceCreate,
    SupplierInvoiceResponse,
    SupplierInvoiceDiscrepancyResolution,
)
from app.services.supplier_invoice_service import supplier_invoice_service

router = APIRouter(prefix="/supplier-invoices", tags=["Supplier Invoices"])


@router.post("", response_model=SuccessResponse[SupplierInvoiceResponse])
async def create_supplier_invoice(
    invoice_in: SupplierInvoiceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    invoice = await supplier_invoice_service.create_supplier_invoice(
        session, current_user.workspace_id, invoice_in
    )
    return SuccessResponse(data=invoice)


@router.get("", response_model=SuccessResponse[List[SupplierInvoiceResponse]])
async def list_supplier_invoices(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(SupplierInvoice)
        .where(SupplierInvoice.workspace_id == current_user.workspace_id)
        .options(selectinload(SupplierInvoice.items))
    )
    invoices = (await session.execute(stmt)).scalars().all()
    return SuccessResponse(data=list(invoices))


@router.get("/{id}", response_model=SuccessResponse[SupplierInvoiceResponse])
async def get_supplier_invoice(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(SupplierInvoice).where(
        SupplierInvoice.id == id,
        SupplierInvoice.workspace_id == current_user.workspace_id,
    )
    invoice = (await session.execute(stmt)).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await session.refresh(invoice, ["items"])
    return SuccessResponse(data=invoice)


@router.post(
    "/{id}/submit-matching", response_model=SuccessResponse[SupplierInvoiceResponse]
)
async def submit_matching(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    invoice = await supplier_invoice_service.submit_matching(
        session, id, current_user.workspace_id
    )
    return SuccessResponse(data=invoice)


@router.post(
    "/{id}/resolve-discrepancy", response_model=SuccessResponse[SupplierInvoiceResponse]
)
async def resolve_discrepancy(
    id: uuid.UUID,
    resolution: SupplierInvoiceDiscrepancyResolution,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    invoice = await supplier_invoice_service.resolve_discrepancy(
        session, id, current_user.workspace_id, resolution
    )
    return SuccessResponse(data=invoice)


@router.post("/{id}/approve", response_model=SuccessResponse[SupplierInvoiceResponse])
async def approve_invoice(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    invoice = await supplier_invoice_service.approve_invoice(
        session, id, current_user.workspace_id
    )
    return SuccessResponse(data=invoice)
