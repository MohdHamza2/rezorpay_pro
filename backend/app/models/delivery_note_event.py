import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.delivery_note import DeliveryNote
    from app.models.user import User


class DeliveryNoteEventType(str, Enum):
    DN_CREATED = "DN_CREATED"
    DN_UPDATED = "DN_UPDATED"
    DN_CONFIRMED = "DN_CONFIRMED"
    DN_CANCELLED = "DN_CANCELLED"


class DeliveryNoteEvent(SQLModel, table=True):
    __tablename__ = "delivery_note_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    delivery_note_id: uuid.UUID = Field(
        foreign_key="delivery_notes.id", nullable=False, index=True
    )

    event_type: DeliveryNoteEventType = Field(
        sa_column=Column(
            SAEnum(DeliveryNoteEventType, name="deliverynoteeventtype"),
            nullable=False,
        )
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

    delivery_note: "DeliveryNote" = Relationship(back_populates="events")
    changed_by_user: "User" = Relationship(back_populates="delivery_note_events")
