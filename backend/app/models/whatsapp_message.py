"""
WhatsApp Business API models — Wave 27 (Phase 5).

Tracks every message sent through (outbound) or received from (inbound) the
Meta WhatsApp Cloud API. `direction`/`status`/`type` live in dedicated PG
enums. `simulated=True` marks dry-run records that never reached a provider.

Field rules (see wave-whatsapp-pdf-addendum §2.6, locked):
- `document_*` fields identify the generated outbound document artifact;
  `linked_entity_*` fields identify the business entity associated with the
  communication; they are not interchangeable.
- ON DOCUMENT sends the service auto-populates `linked_entity_*` from the
  resolved artifact, so `document_*` == `linked_entity_*` by construction.
- Timestamps: `received_at` is INBOUND only; `sent_at`/`delivered_at`/`read_at`
  are OUTBOUND only. Inbound rows stay `RECEIVED` and never pass through
  SENT/DELIVERED/READ.
- `provider_error_code`/`provider_error_category`/`error_message` carry
  NORMALIZED provider info only — never raw provider response bodies.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Text
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WhatsAppDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class WhatsAppMessageStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    RECEIVED = "RECEIVED"
    FAILED = "FAILED"


class WhatsAppMessageType(str, Enum):
    TEXT = "TEXT"
    DOCUMENT = "DOCUMENT"
    MEDIA = "MEDIA"


class WhatsAppMessage(SQLModel, table=True):
    __tablename__ = "whatsapp_messages"

    __table_args__ = (
        Index(
            "ix_whatsapp_messages_workspace_id_created_at", "workspace_id", "created_at"
        ),
        Index(
            "ix_whatsapp_messages_workspace_linked",
            "workspace_id",
            "linked_entity_type",
            "linked_entity_id",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    direction: WhatsAppDirection = Field(default=WhatsAppDirection.OUTBOUND)
    message_type: WhatsAppMessageType = Field(default=WhatsAppMessageType.TEXT)

    to_number: Optional[str] = Field(
        default=None, sa_column=Column(String(20), nullable=True)
    )
    from_number: Optional[str] = Field(
        default=None, sa_column=Column(String(20), nullable=True)
    )
    message_body: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    caption: Optional[str] = Field(
        default=None, sa_column=Column(String(1024), nullable=True)
    )

    document_type: Optional[str] = Field(
        default=None, sa_column=Column(String(50), nullable=True)
    )
    document_id: Optional[uuid.UUID] = Field(default=None)
    document_filename: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    media_id: Optional[str] = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )
    statement_from: Optional[date] = Field(
        default=None, sa_column=Column(Date, nullable=True)
    )
    statement_to: Optional[date] = Field(
        default=None, sa_column=Column(Date, nullable=True)
    )

    linked_entity_type: Optional[str] = Field(
        default=None, sa_column=Column(String(50), nullable=True)
    )
    linked_entity_id: Optional[uuid.UUID] = Field(default=None)

    status: WhatsAppMessageStatus = Field(default=WhatsAppMessageStatus.QUEUED)
    whatsapp_message_id: Optional[str] = Field(
        default=None, sa_column=Column(String(128), unique=True, nullable=True)
    )
    simulated: bool = Field(default=False)

    provider_error_code: Optional[str] = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    provider_error_category: Optional[str] = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    error_message: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )

    sent_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    delivered_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    read_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    received_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    def __repr__(self) -> str:
        return (
            f"<WhatsAppMessage(id={self.id}, dir={self.direction.value}, "
            f"status={self.status.value}, simulated={self.simulated})>"
        )


class WhatsAppIdempotencyKey(SQLModel, table=True):
    """Workspace-scoped send idempotency (48h TTL) with a request fingerprint.

    PK `(workspace_id, idempotency_key)` is the final authority for concurrent
    same-key requests; `request_fingerprint` disambiguates same-key/different-
    payload retries (409 IDEMPOTENCY_CONFLICT).
    """

    __tablename__ = "whatsapp_idempotency_keys"

    workspace_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("workspaces.id"), primary_key=True, nullable=False)
    )
    key: str = Field(sa_column=Column(String(255), primary_key=True, nullable=False))
    request_fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    message_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("whatsapp_messages.id"), nullable=False, index=True)
    )

    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime = Field(
        default_factory=lambda: _now() + timedelta(hours=48),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def is_expired(self) -> bool:
        return _now() > self.expires_at

    def __repr__(self) -> str:
        return (
            f"<WhatsAppIdempotencyKey(workspace={self.workspace_id}, "
            f"key={self.key[:20]}...)>"
        )
