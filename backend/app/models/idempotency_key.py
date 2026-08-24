import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, String, ForeignKey
from sqlmodel import Field, SQLModel


class IdempotencyKey(SQLModel, table=True):
    __tablename__ = "idempotency_keys"

    # Workspace-scoped compound key
    workspace_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("workspaces.id"), primary_key=True, nullable=False)
    )

    key: str = Field(sa_column=Column(String(255), primary_key=True, nullable=False))

    payment_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("payments.id"), nullable=False, index=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=48),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return (
            f"<IdempotencyKey(workspace={self.workspace_id}, key={self.key[:20]}...)>"
        )
