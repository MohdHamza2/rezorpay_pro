"""Wave 28 — UAE VAT Compliance Pack export (read-only).

`GET /api/v1/reports/vat-compliance?from&to&format=csv|json`

- OWNER/ADMIN only; rate limited 10/minute.
- `format=csv` → raw `StreamingResponse` zip (not wrapped; parent §5.4).
- `format=json` → the same aggregates wrapped in `SuccessResponse`.
- Period guards reuse `ar_statement_service` (from≤to, ≤366 days).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace

from app.database import get_session
from app.limiter import limiter
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode, SuccessResponse
from app.schemas.vat_compliance import VatComplianceJsonResponse
from app.services.customer_po_support import raise_error
from app.services.vat_compliance_service import build_report, build_zip

router = APIRouter(tags=["Reports"])


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may export the VAT compliance pack",
        )


@router.get("/reports/vat-compliance")
@limiter.limit("10/minute")
async def get_vat_compliance(
    request: Request,
    period_from: date = Query(..., alias="from"),
    period_to: date = Query(..., alias="to"),
    format: Literal["csv", "json"] = Query("csv"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
):
    """Export the workspace UAE VAT compliance pack for [from, to]."""
    _require_owner_admin(user)
    payload = await build_report(session, workspace, period_from, period_to)
    if format == "csv":
        zip_bytes = build_zip(payload)
        return StreamingResponse(
            iter([zip_bytes]),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="vat-compliance-'
                    f'{period_from}_to_{period_to}.zip"'
                )
            },
        )
    return SuccessResponse(data=VatComplianceJsonResponse.model_validate(payload))
