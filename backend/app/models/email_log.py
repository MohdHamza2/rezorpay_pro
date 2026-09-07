"""
Email Engine models — Wave 26 (Phase 5).

Tracks every transactional email sent through Resend. `status` lives in the
`emailstatus` PG enum; `simulated=True` marks dry-run records that never
reached a provider, so a simulated send can never be confused with real
delivery. `linked_entity_*` is a generic audit pair (workspace-validated at
send time); AR/supplier statements are generated reports and deliberately
have NO physical FK.
"""

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmailStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    FAILED = "FAILED"


class EmailLog(SQLModel, table=True):
    __tablename__ = "email_log"

    __table_args__ = (
        Index("ix_email_log_workspace_id_created_at", "workspace_id", "created_at"),
        Index(
            "ix_email_log_workspace_linked",
            "workspace_id",
            "linked_entity_type",
            "linked_entity_id",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    from_email: str = Field(sa_column=Column(String(255), nullable=False))
    to_email: str = Field(sa_column=Column(String(255), nullable=False))
    bcc: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, default=list, nullable=False)
    )

    subject: str = Field(sa_column=Column(String(255), nullable=False))
    body_html: str = Field(sa_column=Column(Text, nullable=False))

    linked_entity_type: Optional[str] = Field(
        default=None, sa_column=Column(String(50), nullable=True)
    )
    linked_entity_id: Optional[uuid.UUID] = Field(default=None)

    status: EmailStatus = Field(default=EmailStatus.QUEUED)
    resend_message_id: Optional[str] = Field(
        default=None, sa_column=Column(String(128), unique=True, nullable=True)
    )
    simulated: bool = Field(default=False)
    error_message: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )

    sent_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    delivered_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    def __repr__(self) -> str:
        return f"<EmailLog(id={self.id}, status={self.status.value}, simulated={self.simulated})>"


class EmailIdempotencyKey(SQLModel, table=True):
    """Workspace-scoped send idempotency (48h TTL, mirrors the payment key pair)."""

    __tablename__ = "email_idempotency_keys"

    workspace_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("workspaces.id"), primary_key=True, nullable=False)
    )
    key: str = Field(sa_column=Column(String(255), primary_key=True, nullable=False))
    email_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("email_log.id"), nullable=False, index=True)
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
            f"<EmailIdempotencyKey(workspace={self.workspace_id}, "
            f"key={self.key[:20]}...)>"
        )
