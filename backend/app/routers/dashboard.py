import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from decimal import Decimal

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id
from app.models.invoice import Invoice, InvoiceStatus
from app.models.procurement import ProcurementRequest, PRStatus
from app.models.rfq import RFQ, RFQStatus
from app.models.grn import GoodsReceiptNote, GRNStatus
from app.schemas.dashboard import DashboardStatsResponse
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats", response_model=SuccessResponse[DashboardStatsResponse])
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session), 
    workspace_id: uuid.UUID = Depends(get_current_workspace_id)
):
    # Total Invoices (Non-Void)
    inv_count = await session.execute(select(func.count(Invoice.id)).where(Invoice.workspace_id == workspace_id, Invoice.status != InvoiceStatus.CANCELLED))
    total_invoices = inv_count.scalar_one()
    
    # Outstanding Balance
    invoices_result = await session.execute(
        select(Invoice).options(selectinload(Invoice.payments)).where(Invoice.workspace_id == workspace_id, Invoice.status != InvoiceStatus.CANCELLED)
    )
    invoices = invoices_result.scalars().all()
    outstanding_balance = sum((inv.balance_due for inv in invoices), Decimal('0'))
    
    # Pending PRs
    pr_count = await session.execute(
        select(func.count(ProcurementRequest.id))
        .where(ProcurementRequest.workspace_id == workspace_id, ProcurementRequest.status.in_([PRStatus.DRAFT, PRStatus.SUBMITTED, PRStatus.UNDER_REVIEW]))
    )
    pending_prs = pr_count.scalar_one()
    
    # Active RFQs
    rfq_count = await session.execute(
        select(func.count(RFQ.id))
        .where(RFQ.workspace_id == workspace_id, RFQ.status.in_([RFQStatus.SENT, RFQStatus.PARTIALLY_RESPONDED, RFQStatus.FULLY_RESPONDED]))
    )
    active_rfqs = rfq_count.scalar_one()
    
    # Unposted GRNs (Pending Inspection/Posting)
    grn_count = await session.execute(
        select(func.count(GoodsReceiptNote.id))
        .where(GoodsReceiptNote.workspace_id == workspace_id, ~GoodsReceiptNote.status.in_([GRNStatus.ACCEPTED, GRNStatus.REJECTED, GRNStatus.CANCELLED]))
    )
    unposted_grns = grn_count.scalar_one()
    
    stats = DashboardStatsResponse(
        total_invoices=total_invoices,
        outstanding_balance=outstanding_balance,
        pending_prs=pending_prs,
        active_rfqs=active_rfqs,
        unposted_grns=unposted_grns
    )
    
    return SuccessResponse(data=stats)
