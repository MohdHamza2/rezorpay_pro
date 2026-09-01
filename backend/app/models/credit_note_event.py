import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.credit_note import CreditNote
    from app.models.user import User


class CreditNoteEventType(str, Enum):
    CN_CREATED = "CN_CREATED"
    CN_UPDATED = "CN_UPDATED"
    CN_ISSUED = "CN_ISSUED"


class CreditNoteEvent(SQLModel, table=True):
    __tablename__ = "credit_note_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    credit_note_id: uuid.UUID = Field(
        foreign_key="credit_notes.id", nullable=False, index=True
    )

    event_type: CreditNoteEventType = Field(
        sa_column=Column(
            SAEnum(CreditNoteEventType, name="creditnoteeventtype"),
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

    credit_note: "CreditNote" = Relationship(back_populates="events")
    changed_by_user: "User" = Relationship(back_populates="credit_note_events")
