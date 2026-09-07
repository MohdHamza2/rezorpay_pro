"""
WhatsApp Business API service — Wave 27 (Phase 5).

Owns the WhatsApp workflow (wave-whatsapp-pdf-addendum §2.6–§2.8): workspace-
scoped idempotent TEXT/DOCUMENT sends (48h key + request fingerprint), sendable
lifecycle gates derived from the LIVE enums, document resolution + render
orchestration over ``DocumentRenderer``, manual resend (FAILED/QUEUED only;
AR_STATEMENT regenerates with stored replay params), and webhook intake
(challenge is router-level; event application + inbound->Enquiry live here).

Transaction discipline (locked): Txn 1 reserves the Idempotency-Key and inserts
the QUEUED row, COMMITs; the provider call happens OUTSIDE any DB session;
Txn 2 marks SENT / FAILED and COMMITs. Provider errors persist NORMALIZED
fields only — never raw bodies (Meta errors may embed phone numbers/user data).

Security: never log tokens, keys, secrets, message bodies, full recipient PII,
or raw webhook/provider payloads; only ids, status transitions, and sanitized
reasons.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.models.client import Client
from app.models.enquiry import EnquirySource
from app.models.invoice import InvoiceStatus
from app.models.product import UnitOfMeasure
from app.models.quotation import Quotation, QuotationStatus
from app.models.user import User, UserRole
from app.models.whatsapp_message import (
    WhatsAppDirection,
    WhatsAppIdempotencyKey,
    WhatsAppMessage,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
)
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode
from app.schemas.enquiry import EnquiryCreate
from app.schemas.whatsapp_comms import WhatsAppSendRequest
from app.services.ar_statement_service import ArStatementService
from app.services.credit_control_service import CreditControlService
from app.services.customer_po_support import raise_error
from app.services.email_service import _ENTITY_MODELS, _REFERENCE_ONLY_ENTITY_TYPES
from app.services.enquiry_service import EnquiryService
from app.services.invoice_service import InvoiceService
from app.services.pdf_service import DocumentRenderer
from app.services.providers import whatsapp_provider
from app.services.quotation_service import QuotationService
from app.services.quotation_support import should_expire
from app.utils.phones import normalize_phone_to_e164

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner_admin(user: User) -> None:
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise_error(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
            "Only OWNER or ADMIN may send WhatsApp messages",
        )


# System actor for webhook ingestion (not a workspace user). Only used to satisfy
# EnquiryService's user_id signature — never surfaced as a real user.
_SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Sendable lifecycle gates — derived from LIVE enums (§2.4), never invented.
_INVOICE_SENDABLE = {
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
}
_QUOTATION_SENDABLE = {
    QuotationStatus.SENT,
    QuotationStatus.ACCEPTED,
    QuotationStatus.CONVERTED,
}

# Provider webhook statuses -> enum; rank promotion is monotonic.
_WEBHOOK_STATUS: dict[str, WhatsAppMessageStatus] = {
    "sent": WhatsAppMessageStatus.SENT,
    "delivered": WhatsAppMessageStatus.DELIVERED,
    "read": WhatsAppMessageStatus.READ,
    "failed": WhatsAppMessageStatus.FAILED,
}
_STATUS_RANK = {
    WhatsAppMessageStatus.QUEUED: 0,
    WhatsAppMessageStatus.SENT: 1,
    WhatsAppMessageStatus.DELIVERED: 2,
    WhatsAppMessageStatus.READ: 3,
}

_SENDABLE = {"INVOICE": _INVOICE_SENDABLE, "QUOTATION": _QUOTATION_SENDABLE}


class WhatsAppService:
    provider = whatsapp_provider

    # ---------- send ----------

    @classmethod
    async def send_message(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user: User,
        payload: WhatsAppSendRequest,
        idempotency_key: str,
    ) -> WhatsAppMessage:
        """Reserve key + insert QUEUED row (Txn 1), dispatch, mark Txn 2."""
        _require_owner_admin(user)
        fingerprint = cls._fingerprint(payload)

        existing = await cls._reserve(
            session, workspace_id, idempotency_key, fingerprint
        )
        if existing is not None:
            return existing

        if payload.kind == "text":
            if payload.linked_entity_type or payload.linked_entity_id:
                await cls._validate_text_linked_entity(
                    session,
                    workspace_id,
                    payload.linked_entity_type,
                    payload.linked_entity_id,
                )
            message = WhatsAppMessage(
                workspace_id=workspace_id,
                direction=WhatsAppDirection.OUTBOUND,
                message_type=WhatsAppMessageType.TEXT,
                to_number=payload.to_number,
                message_body=payload.message_body,
                linked_entity_type=payload.linked_entity_type,
                linked_entity_id=payload.linked_entity_id,
                status=WhatsAppMessageStatus.QUEUED,
            )
            session.add(message)
            await session.flush()
            replay = await cls._commit_reservation(
                session, workspace_id, idempotency_key, fingerprint, message.id
            )
            if replay is not None:
                return replay
            await cls._dispatch_text(session, message)
            return message

        fields, _data, pdf_bytes = await cls._resolve_document(
            session,
            workspace_id,
            document_type=payload.document_type,
            document_id=payload.document_id,
            client_id=payload.client_id,
            statement_from=payload.statement_from,
            statement_to=payload.statement_to,
        )
        message = WhatsAppMessage(
            workspace_id=workspace_id,
            direction=WhatsAppDirection.OUTBOUND,
            message_type=WhatsAppMessageType.DOCUMENT,
            caption=payload.caption,
            status=WhatsAppMessageStatus.QUEUED,
            **fields,
        )
        session.add(message)
        await session.flush()
        replay = await cls._commit_reservation(
            session, workspace_id, idempotency_key, fingerprint, message.id
        )
        if replay is not None:
            return replay
        await cls._dispatch_document(session, message, pdf_bytes)
        return message

    # ---------- idempotency ----------

    @staticmethod
    def _canonical_json(values: dict) -> str:
        cleaned = {k: v for k, v in values.items() if v not in (None, "")}
        return json.dumps(
            cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )

    @classmethod
    def _fingerprint(cls, payload: WhatsAppSendRequest) -> str:
        values = payload.model_dump(mode="json", exclude_none=True)
        return hashlib.sha256(cls._canonical_json(values).encode("utf-8")).hexdigest()

    @staticmethod
    async def _reserve(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        key: str,
        fingerprint: str,
    ) -> Optional[WhatsAppMessage]:
        """Lookup (workspace, key). Same-key/same-request -> existing row (200,
        provider NEVER called); same-key/different-request -> 409; expired ->
        delete and continue as fresh."""
        result = await session.execute(
            select(WhatsAppIdempotencyKey).where(
                WhatsAppIdempotencyKey.workspace_id == workspace_id,
                WhatsAppIdempotencyKey.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None and not row.is_expired():
            if row.request_fingerprint != fingerprint:
                raise_error(
                    status.HTTP_409_CONFLICT,
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "Idempotency-Key was already used with a different request",
                )
            message = await session.get(WhatsAppMessage, row.message_id)
            if message is not None:
                return message
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.IDEMPOTENCY_KEY_REUSED,
                "Idempotency-Key references a missing message",
            )
        if row is not None:
            await session.delete(row)
            await session.flush()
        return None

    @staticmethod
    async def _commit_reservation(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        key: str,
        fingerprint: str,
        message_id: uuid.UUID,
    ) -> Optional[WhatsAppMessage]:
        """Txn 1 commit; the (workspace, key) PK arbitrates concurrent same-key
        requests. Loser re-reads the winner's reservation and, on matching
        fingerprint, returns the existing row so the provider is called once."""
        session.add(
            WhatsAppIdempotencyKey(
                workspace_id=workspace_id,
                key=key,
                request_fingerprint=fingerprint,
                message_id=message_id,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(
                select(WhatsAppIdempotencyKey).where(
                    WhatsAppIdempotencyKey.workspace_id == workspace_id,
                    WhatsAppIdempotencyKey.key == key,
                )
            )
            winning = result.scalar_one_or_none()
            if winning is not None and winning.request_fingerprint == fingerprint:
                return await session.get(WhatsAppMessage, winning.message_id)
            raise_error(
                status.HTTP_409_CONFLICT,
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency-Key was already used with a different request",
            )
        return None

    # ---------- dispatch (provider call OUTSIDE any DB session) ----------

    @classmethod
    async def _dispatch_text(
        cls, session: AsyncSession, message: WhatsAppMessage
    ) -> None:
        to_number = message.to_number
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message.message_body},
        }
        result = await cls.provider.send_message(
            get_settings().WHATSAPP_PHONE_NUMBER_ID, to_number, payload
        )
        await cls._apply_outcome(session, message, result)

    @classmethod
    async def _dispatch_document(
        cls, session: AsyncSession, message: WhatsAppMessage, pdf_bytes: bytes
    ) -> None:
        phone_number_id = get_settings().WHATSAPP_PHONE_NUMBER_ID
        upload = await cls.provider.upload_media(
            phone_number_id, message.document_filename, pdf_bytes
        )
        if not upload.ok:
            await cls._apply_outcome(session, message, upload)
            return  # unreachable: outcome raises 502
        media_id = upload.message_id or None
        document = {"id": media_id, "filename": message.document_filename}
        if message.caption:
            document["caption"] = message.caption
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to_number,
            "type": "document",
            "document": document,
        }
        result = await cls.provider.send_message(
            phone_number_id, message.to_number, payload
        )
        await cls._apply_outcome(
            session, message, result, success_updates={"media_id": media_id}
        )

    @classmethod
    async def _apply_outcome(
        cls,
        session: AsyncSession,
        message: WhatsAppMessage,
        result,
        *,
        success_updates: Optional[dict] = None,
    ) -> WhatsAppMessage:
        """Txn 2: SENT (+ ids/fresh media) or FAILED (normalized fields). On
        failure the row COMMITs as FAILED (persists for manual resend) and the
        request raises 502 PROVIDER_ERROR."""
        if not result.ok:
            message.status = WhatsAppMessageStatus.FAILED
            message.provider_error_code = result.provider_code
            message.provider_error_category = result.provider_category
            message.error_message = result.error
            message.media_id = None
            message.updated_at = _now()
            logger.warning(
                "whatsapp_send_failed",
                extra={
                    "message_id": str(message.id),
                    "provider_code": result.provider_code,
                    "provider_category": result.provider_category,
                    "error": result.error,
                },
            )
            await session.commit()
            raise_error(
                status.HTTP_502_BAD_GATEWAY,
                ErrorCode.PROVIDER_ERROR,
                "WhatsApp provider rejected the send; the message was recorded as FAILED",
            )
        for key, value in (success_updates or {}).items():
            if value is not None:
                setattr(message, key, value)
        message.status = WhatsAppMessageStatus.SENT
        message.error_message = None
        message.provider_error_code = None
        message.provider_error_category = None
        if result.message_id:
            message.whatsapp_message_id = result.message_id
        else:
            # Simulated (dry-run never dials a provider) — explicitly labelled.
            message.simulated = True
            message.whatsapp_message_id = None
            logger.info(
                "whatsapp_sent_simulated",
                extra={"message_id": str(message.id), "simulated": True},
            )
        message.sent_at = _now()
        message.updated_at = _now()
        await session.commit()
        return message

    # ---------- resend ----------

    @classmethod
    async def resend_message(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
    ) -> WhatsAppMessage:
        """Manual resend. FAILED/QUEUED re-dispatch (FOR UPDATE serialized);
        SENT/DELIVERED/READ is a 200 no-op."""
        _require_owner_admin(user)
        result = await session.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.id == message_id,
                WhatsAppMessage.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        message = result.scalar_one_or_none()
        if message is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "WhatsApp message not found or not in workspace",
            )
        if message.direction != WhatsAppDirection.OUTBOUND:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Only outbound messages can be resent",
            )
        if message.status in (
            WhatsAppMessageStatus.SENT,
            WhatsAppMessageStatus.DELIVERED,
            WhatsAppMessageStatus.READ,
        ):
            return message
        if message.message_type == WhatsAppMessageType.DOCUMENT:
            fields, _data, pdf_bytes = await cls._rebuild_document_for_resend(
                session, message
            )
            for key, value in fields.items():
                setattr(message, key, value)
            await session.flush()
            await cls._dispatch_document(session, message, pdf_bytes)
            return message
        await cls._dispatch_text(session, message)
        return message

    # ---------- read ----------

    @staticmethod
    async def get_message(
        session: AsyncSession, workspace_id: uuid.UUID, message_id: uuid.UUID
    ) -> WhatsAppMessage:
        result = await session.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.id == message_id,
                WhatsAppMessage.workspace_id == workspace_id,
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "WhatsApp message not found or not in workspace",
            )
        return message

    @staticmethod
    async def list_messages(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        status_filter: Optional[WhatsAppMessageStatus] = None,
        direction: Optional[WhatsAppDirection] = None,
        message_type: Optional[WhatsAppMessageType] = None,
        linked_entity_type: Optional[str] = None,
        linked_entity_id: Optional[uuid.UUID] = None,
        to_number: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Sequence[WhatsAppMessage], int]:
        filters = [WhatsAppMessage.workspace_id == workspace_id]
        if status_filter is not None:
            filters.append(WhatsAppMessage.status == status_filter)
        if direction is not None:
            filters.append(WhatsAppMessage.direction == direction)
        if message_type is not None:
            filters.append(WhatsAppMessage.message_type == message_type)
        if linked_entity_type is not None:
            filters.append(WhatsAppMessage.linked_entity_type == linked_entity_type)
        if linked_entity_id is not None:
            filters.append(WhatsAppMessage.linked_entity_id == linked_entity_id)
        if to_number is not None:
            filters.append(WhatsAppMessage.to_number == to_number)
        if created_from is not None:
            filters.append(WhatsAppMessage.created_at >= created_from)
        if created_to is not None:
            filters.append(WhatsAppMessage.created_at <= created_to)

        total = await session.execute(
            select(func.count()).select_from(WhatsAppMessage).where(*filters)
        )
        count = total.scalar() or 0

        result = await session.execute(
            select(WhatsAppMessage)
            .where(*filters)
            .order_by(WhatsAppMessage.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), count

    # ---------- document resolution + render orchestration ----------

    @classmethod
    async def _resolve_document(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        document_type: str,
        document_id: Optional[uuid.UUID],
        client_id: Optional[uuid.UUID],
        statement_from,
        statement_to,
    ) -> Tuple[dict, dict, bytes]:
        """Resolve the artifact, enforce the §2.4 lifecycle gate, derive the
        recipient from the canonicalized Client phone, render ONCE, and return
        the message fields + canonical data dict + PDF bytes."""
        if document_type == "AR_STATEMENT":
            workspace = await session.get(Workspace, workspace_id)
            if workspace is None:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Workspace not found",
                )
            client = await CreditControlService.load_client(
                session, client_id, workspace_id
            )
            if client is None:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Client not found or not in workspace",
                )
            to_number = cls._require_recipient(client)
            data = await ArStatementService.get_statement(
                session, workspace, client_id, statement_from, statement_to, as_of=None
            )
            rendered = DocumentRenderer.render("AR_STATEMENT", data)
            fields = {
                "to_number": to_number,
                "document_type": "AR_STATEMENT",
                "document_id": None,
                "document_filename": rendered.filename,
                "statement_from": statement_from,
                "statement_to": statement_to,
                "linked_entity_type": "AR_STATEMENT",
                "linked_entity_id": client_id,
            }
            return fields, data, rendered.data

        if document_type == "INVOICE":
            invoice = await InvoiceService.get_for_response(
                session, document_id, workspace_id
            )
            if invoice is None:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Invoice not found or not in workspace",
                )
            await cls._assert_sendable("INVOICE", invoice.status)
            client = await CreditControlService.load_client(
                session, invoice.client_id, workspace_id
            )
            if client is None:
                raise_error(
                    status.HTTP_404_NOT_FOUND,
                    ErrorCode.NOT_FOUND,
                    "Invoice client not found",
                )
            to_number = cls._require_recipient(client)
            workspace = await session.get(Workspace, workspace_id)
            data = await cls._invoice_render_data(session, invoice, client, workspace)
            rendered = DocumentRenderer.render("INVOICE", data)
            fields = {
                "to_number": to_number,
                "document_type": "INVOICE",
                "document_id": invoice.id,
                "document_filename": rendered.filename,
                "statement_from": None,
                "statement_to": None,
                "linked_entity_type": "INVOICE",
                "linked_entity_id": invoice.id,
            }
            return fields, data, rendered.data

        # QUOTATION
        quotation = await QuotationService.get_visible(
            session, document_id, workspace_id
        )
        if quotation is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Quotation not found or not in workspace",
            )
        await cls._assert_quotation_sendable(quotation)
        client = await CreditControlService.load_client(
            session, quotation.client_id, workspace_id
        )
        if client is None:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Quotation client not found",
            )
        to_number = cls._require_recipient(client)
        workspace = await session.get(Workspace, workspace_id)
        data = await cls._quotation_render_data(session, quotation, client, workspace)
        rendered = DocumentRenderer.render("QUOTATION", data)
        fields = {
            "to_number": to_number,
            "document_type": "QUOTATION",
            "document_id": quotation.id,
            "document_filename": rendered.filename,
            "statement_from": None,
            "statement_to": None,
            "linked_entity_type": "QUOTATION",
            "linked_entity_id": quotation.id,
        }
        return fields, data, rendered.data

    @classmethod
    async def _rebuild_document_for_resend(
        cls, session: AsyncSession, message: WhatsAppMessage
    ) -> Tuple[dict, dict, bytes]:
        if message.document_type == "AR_STATEMENT":
            return await cls._resolve_document(
                session,
                message.workspace_id,
                document_type="AR_STATEMENT",
                document_id=None,
                client_id=message.linked_entity_id,
                statement_from=message.statement_from,
                statement_to=message.statement_to,
            )
        return await cls._resolve_document(
            session,
            message.workspace_id,
            document_type=message.document_type,
            document_id=message.document_id,
            client_id=None,
            statement_from=None,
            statement_to=None,
        )

    @staticmethod
    def _require_recipient(client: Client) -> str:
        to_number = normalize_phone_to_e164(client.phone)
        if not to_number:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "Client 'phone' cannot be canonicalized to E.164; "
                "no derivable WhatsApp recipient",
                "to_number",
            )
        return to_number

    @staticmethod
    async def _assert_sendable(document_type: str, status_value) -> None:
        allowed = _SENDABLE[document_type]
        if status_value not in allowed:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot send {document_type.lower()} with status '{status_value.value}'; "
                f"allowed: {sorted(s.value for s in allowed)}",
            )

    @classmethod
    async def _assert_quotation_sendable(cls, quotation: Quotation) -> None:
        if should_expire(quotation):
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot send quotation; it has expired",
            )
        await cls._assert_sendable("QUOTATION", quotation.status)

    # ---------- canonical service data dicts (snapshot-winning) ----------

    @staticmethod
    async def _line_rows(session: AsyncSession, workspace_id: uuid.UUID, items) -> list:
        uom_names = await WhatsAppService._uom_names(
            session, workspace_id, [item.uom_id for item in items]
        )
        return [
            {
                "description": item.description,
                "quantity": item.quantity,
                "uom": uom_names.get(item.uom_id) or "",
                "unit_price": item.unit_price,
                "tax_rate": item.tax_rate,
                "line_net": item.line_net,
                "tax_amount": item.tax_amount,
                "total_price": item.total_price,
            }
            for item in items
        ]

    @staticmethod
    async def _uom_names(
        session: AsyncSession, workspace_id: uuid.UUID, uom_ids: Sequence
    ) -> dict:
        ids = sorted({row_id for row_id in uom_ids if row_id is not None})
        if not ids:
            return {}
        result = await session.execute(
            select(UnitOfMeasure).where(
                UnitOfMeasure.workspace_id == workspace_id,
                UnitOfMeasure.id.in_(ids),
            )
        )
        return {row.id: row.code for row in result.scalars().all()}

    @staticmethod
    async def _invoice_render_data(
        session: AsyncSession, invoice, client: Client, workspace: Optional[Workspace]
    ) -> dict:
        workspace = workspace or Workspace()
        lines = await WhatsAppService._line_rows(
            session, invoice.workspace_id, invoice.items
        )
        return {
            "invoice_number": invoice.invoice_number,
            "currency": invoice.currency,
            "issue_date": invoice.issue_date,
            "supply_date": invoice.supply_date,
            "due_date": invoice.due_date,
            "seller": {
                "name": invoice.seller_name_snapshot or workspace.name,
                "trn": invoice.seller_trn_snapshot or workspace.trn,
                "address": invoice.seller_address_snapshot or workspace.address,
            },
            "buyer": {
                "name": invoice.buyer_name_snapshot or client.name,
                "trn": invoice.buyer_trn_snapshot or client.tax_id,
                "address": invoice.buyer_address_snapshot or client.address,
            },
            "lines": lines,
            "subtotal": invoice.subtotal,
            "tax_amount": invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "notes": invoice.notes,
        }

    @staticmethod
    async def _quotation_render_data(
        session: AsyncSession, quotation, client: Client, workspace: Optional[Workspace]
    ) -> dict:
        workspace = workspace or Workspace()
        lines = await WhatsAppService._line_rows(
            session, quotation.workspace_id, quotation.items
        )
        return {
            "quotation_number": quotation.quotation_number,
            "currency": quotation.currency,
            "quotation_date": quotation.quotation_date,
            "valid_until": quotation.valid_until,
            "seller": {
                "name": workspace.name,
                "trn": workspace.trn,
                "address": workspace.address,
            },
            "buyer": {
                "name": client.name,
                "trn": client.tax_id,
                "address": client.address,
            },
            "lines": lines,
            "subtotal": quotation.subtotal,
            "tax_amount": quotation.tax_amount,
            "total_amount": quotation.total_amount,
            "notes": quotation.notes,
        }

    # ---------- TEXT audit reference ----------

    @staticmethod
    async def _validate_text_linked_entity(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        linked_entity_type: Optional[str],
        linked_entity_id: Optional[uuid.UUID],
    ) -> None:
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

    # ---------- webhook events (§2.7/§2.8) ----------

    @classmethod
    async def apply_webhook_events(cls, session: AsyncSession, raw_body: bytes) -> None:
        """Apply status + inbound events in ONE transaction. Anything after a
        verified HMAC responds 200 (Meta retry-storm rule); failures roll back
        everything and log a sanitized reason."""
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logger.warning("wa_webhook_unparseable", extra={"reason": "invalid_json"})
            await session.commit()
            return
        try:
            for entry in payload.get("entry") or []:
                if not isinstance(entry, dict):
                    continue
                for change in entry.get("changes") or []:
                    if not isinstance(change, dict):
                        continue
                    value = change.get("value")
                    if not isinstance(value, dict):
                        continue
                    if not cls._phone_number_id_matches(value):
                        continue
                    statuses = value.get("statuses") or []
                    messages = value.get("messages") or []
                    await cls._apply_statuses(
                        session, statuses if isinstance(statuses, list) else []
                    )
                    await cls._apply_inbound(
                        session, messages if isinstance(messages, list) else []
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("wa_webhook_processing_failed", extra={"reason": "rollback"})

    @staticmethod
    def _phone_number_id_matches(value: dict) -> bool:
        configured = get_settings().WHATSAPP_PHONE_NUMBER_ID
        metadata = value.get("metadata") or {}
        phone_id = (
            metadata.get("phone_number_id") if isinstance(metadata, dict) else None
        )
        if not configured:
            return True  # no sender configured: nothing to verify against
        if not phone_id or str(phone_id) != str(configured):
            logger.warning(
                "wa_webhook_wrong_phone_number_id",
                extra={"has_phone_id": bool(phone_id)},
            )
            return False
        return True

    @classmethod
    async def _apply_statuses(cls, session: AsyncSession, statuses: list) -> None:
        for item in statuses:
            if not isinstance(item, dict):
                continue
            wa_message_id = item.get("id")
            target = _WEBHOOK_STATUS.get(item.get("status"))
            if not wa_message_id or target is None:
                continue
            result = await session.execute(
                select(WhatsAppMessage).where(
                    WhatsAppMessage.whatsapp_message_id == wa_message_id
                )
            )
            message = result.scalar_one_or_none()
            if message is None or message.direction != WhatsAppDirection.OUTBOUND:
                continue  # unknown id / inbound row → 200 no-op
            cls._apply_report_status(message, target)

    @staticmethod
    def _apply_report_status(
        message: WhatsAppMessage, target: WhatsAppMessageStatus
    ) -> None:
        current = message.status
        if target == WhatsAppMessageStatus.FAILED:
            if current == WhatsAppMessageStatus.FAILED:
                return
            message.status = target
            message.error_message = "provider_webhook_failed"
            message.updated_at = _now()
            return
        if current == WhatsAppMessageStatus.FAILED:
            return  # FAILED is terminal; later soft events are a no-op
        if _STATUS_RANK.get(target, 0) <= _STATUS_RANK.get(current, 0):
            return  # already at/past target → idempotent no-op
        message.status = target
        message.updated_at = _now()
        if target == WhatsAppMessageStatus.DELIVERED and message.delivered_at is None:
            message.delivered_at = _now()
        if target == WhatsAppMessageStatus.READ and message.read_at is None:
            message.read_at = _now()

    @classmethod
    async def _apply_inbound(cls, session: AsyncSession, messages: list) -> None:
        inbound_workspace_id = get_settings().WHATSAPP_INBOUND_WORKSPACE_ID
        for item in messages:
            if not isinstance(item, dict):
                continue
            wa_id = item.get("id")
            if not wa_id:
                continue
            from_raw = item.get("from")
            canonical_from = normalize_phone_to_e164(from_raw)
            message_type, text_body = cls._inbound_payload(item)
            if not inbound_workspace_id:
                # Deployment-level routing unset → acknowledged but dropped.
                logger.info(
                    "wa_inbound_dropped_no_routing",
                    extra={"has_sender": bool(canonical_from)},
                )
                continue
            # Fast path only; the global unique whatsapp_message_id is the
            # dedup authority (race → unique-constraint IntegrityError).
            existing = await session.execute(
                select(WhatsAppMessage.id).where(
                    WhatsAppMessage.whatsapp_message_id == wa_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            try:
                async with session.begin_nested():
                    row = WhatsAppMessage(
                        workspace_id=uuid.UUID(inbound_workspace_id),
                        direction=WhatsAppDirection.INBOUND,
                        message_type=message_type,
                        status=WhatsAppMessageStatus.RECEIVED,
                        received_at=_now(),
                        from_number=canonical_from,
                        message_body=text_body,
                        whatsapp_message_id=str(wa_id),
                    )
                    session.add(row)
                    await session.flush()
                    if message_type == WhatsAppMessageType.TEXT:
                        client_id, client_name = await cls._match_client(
                            session, uuid.UUID(inbound_workspace_id), canonical_from
                        )
                        await EnquiryService.create(
                            session,
                            workspace_id=uuid.UUID(inbound_workspace_id),
                            user_id=_SYSTEM_USER_ID,
                            data=EnquiryCreate(
                                source=EnquirySource.WHATSAPP,
                                client_id=client_id,
                                contact_name=client_name,
                                contact_whatsapp=from_raw,
                                items_description=text_body,
                                whatsapp_message_id=str(wa_id),
                                items=[],
                            ),
                        )
                    else:
                        logger.info(
                            "wa_inbound_media_recorded",
                            extra={"whatsapp_message_id": str(wa_id)},
                        )
            except IntegrityError:
                # Concurrent duplicate webhook raced past both pre-checks; the
                # winner's rows stand, this delivery is an idempotent 200.
                logger.info(
                    "wa_inbound_duplicate_race",
                    extra={"whatsapp_message_id": str(wa_id)},
                )

    @staticmethod
    def _inbound_payload(item: dict) -> Tuple[WhatsAppMessageType, Optional[str]]:
        """text -> TEXT; media WITH caption -> TEXT (caption is the body);
        media WITHOUT caption -> MEDIA (transport record only, no Enquiry)."""
        msg_type = item.get("type")
        body = None
        if msg_type == "text":
            inner = item.get("text") or {}
            body = inner.get("body") if isinstance(inner, dict) else None
        else:
            inner = item.get(msg_type)
            caption = inner.get("caption") if isinstance(inner, dict) else None
            if caption is not None and str(caption).strip():
                body = str(caption)
        if body is not None and str(body).strip():
            return WhatsAppMessageType.TEXT, str(body)
        return WhatsAppMessageType.MEDIA, None

    @staticmethod
    async def _match_client(
        session: AsyncSession, workspace_id: uuid.UUID, canonical_from: Optional[str]
    ) -> Tuple[Optional[uuid.UUID], Optional[str]]:
        """Single canonical-phone match only. Zero/multiple matches → NULL
        (never guess, never auto-create a Client)."""
        if not canonical_from:
            return (None, None)
        result = await session.execute(
            select(Client).where(
                Client.workspace_id == workspace_id,
                Client.deleted_at.is_(None),
                Client.phone.is_not(None),
            )
        )
        matches = [
            client
            for client in result.scalars().all()
            if normalize_phone_to_e164(client.phone) == canonical_from
        ]
        if len(matches) == 1:
            return (matches[0].id, matches[0].name)
        if len(matches) > 1:
            logger.warning(
                "wa_client_match_ambiguous",
                extra={"matches": len(matches), "workspace_id": str(workspace_id)},
            )
        return (None, None)


whatsapp_service = WhatsAppService()
