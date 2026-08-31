import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum as SAEnum, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CreditStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    HOLD = "HOLD"


class CreditEventReason(str, Enum):
    EVALUATE = "EVALUATE"
    PAYMENT = "PAYMENT"
    SEND_CHECK = "SEND_CHECK"
    RECEIVE_CHECK = "RECEIVE_CHECK"
    DN_CONFIRM = "DN_CONFIRM"


class CreditStatusEvent(SQLModel, table=True):
    __tablename__ = "credit_status_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    previous_status: str = Field(max_length=20)
    new_status: str = Field(max_length=20)
    exposure: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    effective_limit: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    oldest_overdue_days: Optional[int] = Field(default=None)
    reason: CreditEventReason = Field(
        sa_column=Column(
            SAEnum(CreditEventReason, name="crediteventreason"), nullable=False
        )
    )
    changed_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    metadata_log: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, default=dict, nullable=False)
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
