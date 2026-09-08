"""Wave 30 — BI analytics router.

`GET /api/v1/reports/analytics/{revenue|sales-by-customer|sales-by-product|cashflow}`

- OWNER/ADMIN only (mirrors the VAT compliance export); rate limited 10/minute.
- Period guards reuse `analytics_service.resolve_period` (from<=to, <=366 days).
- JSON `SuccessResponse` always (no streaming/CSV in this wave).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace
from app.database import get_session
from app.limiter import limiter
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.schemas.analytics import (
    CashflowReport,
    RevenueReport,
    SalesByCustomerReport,
    SalesByProductReport,
)
from app.schemas.common import ErrorCode, SuccessResponse
from app.services import analytics_service
from app.services.customer_po_support import raise_error

router = APIRouter(tags=["Analytics"])


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            403,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may view analytics reports",
        )


@router.get("/reports/analytics/revenue", response_model=SuccessResponse[RevenueReport])
@limiter.limit("10/minute")
async def get_revenue(
    request: Request,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    interval: Literal["day", "week", "month"] = Query("day"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    """Invoiced revenue by period bucket."""
    _require_owner_admin(user)
    payload = await analytics_service.revenue(
        session, workspace.id, period_from, period_to, interval
    )
    return SuccessResponse(data=RevenueReport.model_validate(payload))


@router.get(
    "/reports/analytics/sales-by-customer",
    response_model=SuccessResponse[SalesByCustomerReport],
)
@limiter.limit("10/minute")
async def get_sales_by_customer(
    request: Request,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    """Invoiced sales grouped by customer."""
    _require_owner_admin(user)
    payload = await analytics_service.sales_by_customer(
        session, workspace.id, period_from, period_to
    )
    return SuccessResponse(data=SalesByCustomerReport.model_validate(payload))


@router.get(
    "/reports/analytics/sales-by-product",
    response_model=SuccessResponse[SalesByProductReport],
)
@limiter.limit("10/minute")
async def get_sales_by_product(
    request: Request,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    """Invoiced line items grouped by product."""
    _require_owner_admin(user)
    payload = await analytics_service.sales_by_product(
        session, workspace.id, period_from, period_to
    )
    return SuccessResponse(data=SalesByProductReport.model_validate(payload))


@router.get(
    "/reports/analytics/cashflow", response_model=SuccessResponse[CashflowReport]
)
@limiter.limit("10/minute")
async def get_cashflow(
    request: Request,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    interval: Literal["day", "week", "month"] = Query("day"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    """Cash inflow (AR receipts) vs outflow (AP payments) by period."""
    _require_owner_admin(user)
    payload = await analytics_service.cashflow(
        session, workspace.id, period_from, period_to, interval
    )
    return SuccessResponse(data=CashflowReport.model_validate(payload))
