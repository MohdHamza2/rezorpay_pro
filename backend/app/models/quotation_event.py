import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.quotation import Quotation
    from app.models.user import User


class QuotationEventType(str, Enum):
    QUOTATION_CREATED = "QUOTATION_CREATED"
    QUOTATION_UPDATED = "QUOTATION_UPDATED"
    QUOTATION_SENT = "QUOTATION_SENT"
    QUOTATION_ACCEPTED = "QUOTATION_ACCEPTED"
    QUOTATION_REJECTED = "QUOTATION_REJECTED"
    QUOTATION_EXPIRED = "QUOTATION_EXPIRED"
    QUOTATION_CONVERTED = "QUOTATION_CONVERTED"


class QuotationEvent(SQLModel, table=True):
    __tablename__ = "quotation_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    quotation_id: uuid.UUID = Field(
        foreign_key="quotations.id", nullable=False, index=True
    )

    event_type: QuotationEventType = Field(
        sa_column=Column(SAEnum(QuotationEventType), nullable=False)
    )

    previous_status: Optional[str] = Field(default=None, max_length=50)
    new_status: str = Field(max_length=50)
    changed_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    metadata_log: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, default=dict, nullable=False)
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    quotation: "Quotation" = Relationship(back_populates="events")
    changed_by_user: "User" = Relationship(back_populates="quotation_events")
