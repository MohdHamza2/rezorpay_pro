"""
WhatsApp coms router — Wave 27 (Phase 5).

Endpoints:
- POST /comms/whatsapp/messages             send TEXT/DOCUMENT (OWNER/ADMIN, 30/min, idempotent)
- GET /comms/whatsapp/messages              paginated list w/ filters (any member)
- GET /comms/whatsapp/messages/{id}         one message (any member)
- POST /comms/whatsapp/messages/{id}/resend manual resend FAILED/QUEUED (OWNER/ADMIN)
- GET /webhooks/whatsapp                    Meta challenge (verify token, no IP limiter)
- POST /webhooks/whatsapp                   Meta events (HMAC-SHA256, no IP limiter)

Webhooks are public provider callbacks: no IP limiter, body-size guard before
HMAC, and post-auth everything answers 200 (never trigger a Meta retry storm).
"""

import hashlib
import hmac
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.config import get_settings
from app.database import get_session
from app.limiter import limiter
from app.models.user import User
from app.models.whatsapp_message import (
    WhatsAppDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
)
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.whatsapp_comms import WhatsAppMessageResponse, WhatsAppSendRequest
from app.services.customer_po_support import raise_error
from app.services.whatsapp_service import whatsapp_service

router = APIRouter(tags=["Comms — WhatsApp"])


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


@router.post(
    "/comms/whatsapp/messages", response_model=SuccessResponse[WhatsAppMessageResponse]
)
@limiter.limit("30/minute")
async def send_whatsapp_message(
    request: Request,
    payload: WhatsAppSendRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Send a WhatsApp TEXT or DOCUMENT message (simulated when COMMS_DRY_RUN)."""
    key = _require_idempotency_key(idempotency_key)
    message = await whatsapp_service.send_message(
        session=session,
        workspace_id=workspace_id,
        user=user,
        payload=payload,
        idempotency_key=key,
    )
    await session.commit()
    return SuccessResponse(data=WhatsAppMessageResponse.model_validate(message))


@router.get(
    "/comms/whatsapp/messages",
    response_model=PaginatedResponse[WhatsAppMessageResponse],
)
async def list_whatsapp_messages(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
    status: Optional[WhatsAppMessageStatus] = Query(None, alias="status"),
    direction: Optional[WhatsAppDirection] = Query(None),
    message_type: Optional[WhatsAppMessageType] = Query(None, alias="message_type"),
    linked_entity_type: Optional[str] = Query(None, max_length=50),
    linked_entity_id: Optional[UUID] = Query(None),
    to_number: Optional[str] = Query(None, min_length=8, max_length=16),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    messages, total = await whatsapp_service.list_messages(
        session=session,
        workspace_id=workspace_id,
        status_filter=status,
        direction=direction,
        message_type=message_type,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
        to_number=to_number,
        created_from=created_from,
        created_to=created_to,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page
    return PaginatedResponse[WhatsAppMessageResponse](
        data=[WhatsAppMessageResponse.model_validate(m) for m in messages],
        pagination=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        ),
    )


@router.get(
    "/comms/whatsapp/messages/{message_id}",
    response_model=SuccessResponse[WhatsAppMessageResponse],
)
async def get_whatsapp_message(
    message_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    message = await whatsapp_service.get_message(session, workspace_id, message_id)
    return SuccessResponse(data=WhatsAppMessageResponse.model_validate(message))


@router.post(
    "/comms/whatsapp/messages/{message_id}/resend",
    response_model=SuccessResponse[WhatsAppMessageResponse],
)
@limiter.limit("30/minute")
async def resend_whatsapp_message(
    request: Request,
    message_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    """Manual resend. FAILED/QUEUED re-dispatch; SENT/DELIVERED/READ is a 200 no-op."""
    message = await whatsapp_service.resend_message(
        session, workspace_id, message_id, user
    )
    await session.commit()
    return SuccessResponse(data=WhatsAppMessageResponse.model_validate(message))


# ---------- Meta webhooks (no IP limiter) ----------


@router.get("/webhooks/whatsapp")
async def whatsapp_webhook_challenge(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    settings = get_settings()
    if (
        hub_mode == "subscribe"
        and hub_verify_token is not None
        and settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        and hmac.compare_digest(
            hub_verify_token, settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        )
        and hub_challenge is not None
    ):
        return PlainTextResponse(hub_challenge)
    raise_error(
        status.HTTP_403_FORBIDDEN,
        "FORBIDDEN",
        "Invalid webhook verification token",
    )


def _verify_signature(
    secret: str, raw_body: bytes, header_value: Optional[str]
) -> bool:
    if not secret or not header_value or not header_value.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(header_value, expected)


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    raw_body = await request.body()
    if len(raw_body) > settings.WHATSAPP_WEBHOOK_MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "success": False,
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "Webhook body too large",
                },
            },
        )
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(settings.WHATSAPP_APP_SECRET, raw_body, signature):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": {"code": "UNAUTHORIZED", "message": "Invalid signature"},
            },
        )
    await whatsapp_service.apply_webhook_events(session, raw_body)
    await session.commit()
    return {"success": True, "status": "processed"}
