"""
Email Engine router — Wave 26 (Phase 5).

Endpoints:
- POST /comms/emails             send a transactional email (OWNER/ADMIN, 30/min, idempotent)
- GET /comms/emails              paginated list w/ filters (any member)
- GET /comms/emails/{id}         one email (any member)
- POST /comms/emails/{id}/resend manual resend from FAILED/BOUNCED/QUEUED (OWNER/ADMIN)
- POST /webhooks/email           Resend webhook (Bearer secret, no IP limiter)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.config import get_settings
from app.database import get_session
from app.limiter import limiter
from app.models.email_log import EmailStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.email_comms import (
    EmailResponse,
    EmailSendRequest,
    EmailWebhookRequest,
)
from app.services.customer_po_support import raise_error
from app.services.email_service import email_service

router = APIRouter(tags=["Comms — Email"])

_bearer = HTTPBearer(auto_error=False)


def _require_idempotency_key(idempotency_key: Optional[str]) -> str:
    if not idempotency_key:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key header is required",
        )
    if len(idempotency_key) > 255:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            "IDEMPOTENCY_KEY_TOO_LONG",
            "Idempotency-Key must be 255 characters or less",
        )
    return idempotency_key


@router.post("/comms/emails", response_model=SuccessResponse[EmailResponse])
@limiter.limit("30/minute")
async def send_email(
    request: Request,
    payload: EmailSendRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Send a transactional email (Resend; simulated when COMMS_DRY_RUN=true)."""
    key = _require_idempotency_key(idempotency_key)
    email = await email_service.send_email(
        session=session,
        workspace_id=workspace_id,
        user=user,
        to_email=payload.to_email,
        subject=payload.subject,
        body_html=payload.body_html,
        idempotency_key=key,
        bcc=list(payload.bcc) if payload.bcc else None,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
    )
    await session.commit()
    return SuccessResponse(data=EmailResponse.model_validate(email))


@router.get("/comms/emails", response_model=PaginatedResponse[EmailResponse])
async def list_emails(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
    status: Optional[EmailStatus] = Query(None, alias="status"),
    linked_entity_type: Optional[str] = Query(None, max_length=50),
    linked_entity_id: Optional[UUID] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    emails, total = await email_service.list_emails(
        session=session,
        workspace_id=workspace_id,
        status_filter=status,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
        created_from=created_from,
        created_to=created_to,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page
    return PaginatedResponse[EmailResponse](
        data=[EmailResponse.model_validate(e) for e in emails],
        pagination=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        ),
    )


@router.get("/comms/emails/{email_id}", response_model=SuccessResponse[EmailResponse])
async def get_email(
    email_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    email = await email_service.get_email(session, workspace_id, email_id)
    return SuccessResponse(data=EmailResponse.model_validate(email))


@router.post(
    "/comms/emails/{email_id}/resend", response_model=SuccessResponse[EmailResponse]
)
@limiter.limit("30/minute")
async def resend_email(
    request: Request,
    email_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Manual resend. FAILED/BOUNCED/QUEUED re-send; SENT/DELIVERED is a 200 no-op."""
    email = await email_service.resend_email(session, workspace_id, email_id, user)
    await session.commit()
    return SuccessResponse(data=EmailResponse.model_validate(email))


@router.post("/webhooks/email", response_model=SuccessResponse[EmailResponse])
async def email_webhook(
    payload: EmailWebhookRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
):
    """Resend delivery webhook. Public callback, gated by a Bearer secret.

    `Authorization: Bearer {RESEND_WEBHOOK_SECRET}`. Not rate limited (provider
    bursts). Recognised: email.delivered / email.bounced / email.failed.
    """
    secret = get_settings().RESEND_WEBHOOK_SECRET
    if not secret or credentials is None or credentials.credentials != secret:
        raise_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid webhook secret",
        )
    email = await email_service.apply_webhook_event(
        session=session,
        resend_message_id=str(payload.data.get("id", "")),
        event=payload.type,
    )
    await session.commit()
    return SuccessResponse(data=EmailResponse.model_validate(email))
