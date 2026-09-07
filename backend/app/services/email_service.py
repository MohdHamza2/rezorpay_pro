"""
Email Engine service — Wave 26 (Phase 5).

Owns the transactional email workflow: workspace-scoped idempotent sends
(48h), linked-entity validation (AR/supplier statements have no physical
FK), dry-run simulation (`simulated=True`, never mistaken for real
delivery), manual resend, and webhook event application.

Security: env-keyed credentials, never log tokens/keys/secrets/message
bodies/full recipient PII — only ids, status transitions, and redacted
error classes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from fastapi import status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.models.client import Client
from app.models.credit_note import CreditNote
from app.models.email_log import EmailIdempotencyKey, EmailLog, EmailStatus
from app.models.enquiry import Enquiry
from app.models.invoice import Invoice
from app.models.purchase_return import PurchaseReturn
from app.models.quotation import Quotation
from app.models.supplier import Supplier
from app.models.supplier_debit_note import SupplierDebitNote
from app.models.supplier_invoice import SupplierInvoice
from app.models.tax_debit_note import TaxDebitNote
from app.models.user import User, UserRole
from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error
from app.services.providers import resend_provider

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may send emails",
        )


# Known audit reference types. Generated reports (AR / supplier statements)
# are reference-only: no physical row exists to validate.
_REFERENCE_ONLY_ENTITY_TYPES = {"AR_STATEMENT", "SUPPLIER_STATEMENT"}

_ENTITY_MODELS = {
    "INVOICE": Invoice,
    "QUOTATION": Quotation,
    "CREDIT_NOTE": CreditNote,
    "TAX_DEBIT_NOTE": TaxDebitNote,
    "SUPPLIER_INVOICE": SupplierInvoice,
    "PURCHASE_RETURN": PurchaseReturn,
    "SUPPLIER_DEBIT_NOTE": SupplierDebitNote,
    "ENQUIRY": Enquiry,
    "CLIENT": Client,
    "SUPPLIER": Supplier,
}


def _event_to_status(event: str) -> Optional[EmailStatus]:
    return {
        "email.delivered": EmailStatus.DELIVERED,
        "email.bounced": EmailStatus.BOUNCED,
        "email.failed": EmailStatus.FAILED,
    }.get(event)


class EmailService:
    provider = resend_provider

    # ---------- send ----------

    @classmethod
    async def send_email(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user: User,
        *,
        to_email: str,
        subject: str,
        body_html: str,
        idempotency_key: str,
        bcc: Optional[list] = None,
        linked_entity_type: Optional[str] = None,
        linked_entity_id: Optional[uuid.UUID] = None,
    ) -> EmailLog:
        """Create + dispatch one transactional email (atomic, idempotent)."""
        _require_owner_admin(user)

        existing_key = await session.execute(
            select(EmailIdempotencyKey).where(
                EmailIdempotencyKey.workspace_id == workspace_id,
                EmailIdempotencyKey.key == idempotency_key,
            )
        )
        key_row = existing_key.scalar_one_or_none()
        if key_row is not None:
            email = await session.get(EmailLog, key_row.email_id)
            if email is not None:
                return email
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.IDEMPOTENCY_KEY_REUSED,
                "Idempotency key references a missing email",
            )

        await cls._validate_linked_entity(
            session, workspace_id, linked_entity_type, linked_entity_id
        )

        email = EmailLog(
            workspace_id=workspace_id,
            from_email=get_settings().RESEND_FROM_EMAIL,
            to_email=to_email,
            bcc=list(bcc or []),
            subject=subject,
            body_html=body_html,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
            status=EmailStatus.QUEUED,
        )
        session.add(email)
        await session.flush()

        session.add(
            EmailIdempotencyKey(
                workspace_id=workspace_id,
                key=idempotency_key,
                email_id=email.id,
            )
        )

        await cls._dispatch(session, email)
        return email

    # ---------- dispatch (provider call + simulation) ----------

    @classmethod
    async def _dispatch(cls, session: AsyncSession, email: EmailLog) -> EmailLog:
        """Send through the provider. On failure the row is COMMITTED as FAILED
        (persists for manual resend) and the request raises 502 PROVIDER_ERROR."""
        result = await cls.provider.send(
            email.from_email,
            email.to_email,
            email.subject,
            email.body_html,
            email.bcc,
        )
        if not result.ok:
            email.status = EmailStatus.FAILED
            email.error_message = result.error
            email.updated_at = _now()
            logger.warning(
                "email_send_failed",
                extra={"email_id": str(email.id), "error": result.error},
            )
            await session.commit()
            raise_error(
                status.HTTP_502_BAD_GATEWAY,
                ErrorCode.PROVIDER_ERROR,
                "Email provider rejected the send; the email was recorded as FAILED",
            )
        email.status = EmailStatus.SENT
        email.error_message = None
        if result.message_id:
            email.resend_message_id = result.message_id
        else:
            # Simulated (dry-run never dials a provider) — explicitly labelled.
            email.simulated = True
            logger.info(
                "email_sent_simulated",
                extra={"email_id": str(email.id), "simulated": True},
            )
        email.sent_at = _now()
        email.updated_at = _now()
        return email

    # ---------- resend ----------

    @classmethod
    async def resend_email(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        email_id: uuid.UUID,
        user: User,
    ) -> EmailLog:
        """Manual resend from FAILED / BOUNCED / QUEUED. Already SENT or
        DELIVERED is a 200 no-op (never duplicated)."""
        _require_owner_admin(user)
        email = await cls.get_email(session, workspace_id, email_id)
        if email.status in (EmailStatus.SENT, EmailStatus.DELIVERED):
            return email
        return await cls._dispatch(session, email)

    # ---------- read ----------

    @staticmethod
    async def get_email(
        session: AsyncSession, workspace_id: uuid.UUID, email_id: uuid.UUID
    ) -> EmailLog:
        result = await session.execute(
            select(EmailLog).where(
                EmailLog.id == email_id,
                EmailLog.workspace_id == workspace_id,
            )
        )
        email = result.scalar_one_or_none()
        if email is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Email not found or not in workspace",
            )
        return email

    @staticmethod
    async def list_emails(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        status_filter: Optional[EmailStatus] = None,
        linked_entity_type: Optional[str] = None,
        linked_entity_id: Optional[uuid.UUID] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Sequence[EmailLog], int]:
        filters = [EmailLog.workspace_id == workspace_id]
        if status_filter is not None:
            filters.append(EmailLog.status == status_filter)
        if linked_entity_type is not None:
            filters.append(EmailLog.linked_entity_type == linked_entity_type)
        if linked_entity_id is not None:
            filters.append(EmailLog.linked_entity_id == linked_entity_id)
        if created_from is not None:
            filters.append(EmailLog.created_at >= created_from)
        if created_to is not None:
            filters.append(EmailLog.created_at <= created_to)

        total = await session.execute(
            select(func.count()).select_from(EmailLog).where(*filters)
        )
        count = total.scalar() or 0

        result = await session.execute(
            select(EmailLog)
            .where(*filters)
            .order_by(EmailLog.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), count

    # ---------- linked-entity resolver ----------

    @staticmethod
    async def _validate_linked_entity(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        linked_entity_type: Optional[str],
        linked_entity_id: Optional[uuid.UUID],
    ) -> None:
        if linked_entity_type is None and linked_entity_id is None:
            return
        if linked_entity_type is None or linked_entity_id is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "linked_entity_type and linked_entity_id must be provided together",
                "linked_entity_type",
            )
        if linked_entity_type in _REFERENCE_ONLY_ENTITY_TYPES:
            return  # generated report reference — no physical row
        model = _ENTITY_MODELS.get(linked_entity_type)
        if model is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                f"Unsupported linked_entity_type '{linked_entity_type}'",
                "linked_entity_type",
            )
        result = await session.execute(
            select(model.id).where(
                model.id == linked_entity_id,
                model.workspace_id == workspace_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Linked entity not found or not in workspace",
            )

    # ---------- webhook ----------

    @staticmethod
    async def apply_webhook_event(
        session: AsyncSession, resend_message_id: str, event: str
    ) -> EmailLog:
        result = await session.execute(
            select(EmailLog).where(EmailLog.resend_message_id == resend_message_id)
        )
        email = result.scalar_one_or_none()
        if email is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Email referenced by webhook not found",
            )
        target = _event_to_status(event)
        if target is None:
            return email  # informational events are a 200 no-op
        email.status = target
        if target == EmailStatus.DELIVERED and email.delivered_at is None:
            email.delivered_at = _now()
        email.updated_at = _now()
        return email


email_service = EmailService()
