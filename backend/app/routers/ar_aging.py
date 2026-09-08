"""
AR Aging Router — Wave 29 (Phase 6).

Mirrors the AP aging endpoints from `supplier_payments.py` 1:1 (same auth,
same params, same guards) on the receivables side.
"""

import uuid
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace_id
from app.database import get_session
from app.schemas.ar_aging import (
    ArAgingByCustomerResponse,
    ArAgingDetailResponse,
    ArAgingSummaryResponse,
)
from app.schemas.common import SuccessResponse
from app.services.ar_aging import ar_aging

router = APIRouter(tags=["AR Aging"])


@router.get("/ar-aging", response_model=SuccessResponse[ArAgingSummaryResponse])
async def ar_aging_summary(
    request: Request,
    as_of: Optional[date] = Query(None),
    client_id: Optional[UUID] = Query(None),
    historical: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """AR aging report (default view=summary).

    `historical=true` reconstructs balances from ledger history as of `as_of`
    (Wave 30 item 1.2) instead of using the live `balance_due`. This is a
    **balance reconstruction, not a point-in-time lifecycle snapshot**: it
    uses today's status eligibility, so historical status transitions (e.g.
    DRAFT on `as_of`, voided after) are not reconstructed.
    """
    payload = await ar_aging(
        session,
        workspace_id,
        as_of=as_of,
        client_id=client_id,
        view="summary",
        historical=historical,
    )
    return SuccessResponse(data=payload)


@router.get("/ar-aging/detail", response_model=SuccessResponse[ArAgingDetailResponse])
async def ar_aging_detail(
    request: Request,
    as_of: Optional[date] = Query(None),
    client_id: Optional[UUID] = Query(None),
    historical: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """AR aging, invoice-level detail.

    `historical=true` reconstructs balances from ledger history as of `as_of`
    (Wave 30 item 1.2) instead of using the live `balance_due`. This is a
    **balance reconstruction, not a point-in-time lifecycle snapshot**:
    historical status transitions are not reconstructed.
    """
    payload = await ar_aging(
        session,
        workspace_id,
        as_of=as_of,
        client_id=client_id,
        view="detail",
        historical=historical,
    )
    return SuccessResponse(data=payload)


@router.get(
    "/ar-aging/by-customer", response_model=SuccessResponse[ArAgingByCustomerResponse]
)
async def ar_aging_by_customer(
    request: Request,
    as_of: Optional[date] = Query(None),
    client_id: Optional[UUID] = Query(None),
    historical: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    """AR aging, per-client breakdown.

    `historical=true` reconstructs balances from ledger history as of `as_of`
    (Wave 30 item 1.2) instead of using the live `balance_due`. This is a
    **balance reconstruction, not a point-in-time lifecycle snapshot**:
    historical status transitions are not reconstructed.
    """
    payload = await ar_aging(
        session,
        workspace_id,
        as_of=as_of,
        client_id=client_id,
        view="by_customer",
        historical=historical,
    )
    return SuccessResponse(data=payload)
