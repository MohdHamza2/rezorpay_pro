import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.user import User


class InvoiceEventType(str, Enum):
    """
    Comprehensive audit event types for invoice lifecycle.

    Reserved for Future Use:
    - INVOICE_VIEWED: For Step 3+ Client Portal (track when client views invoice)
    """

    INVOICE_CREATED = "INVOICE_CREATED"
    INVOICE_UPDATED = "INVOICE_UPDATED"
    INVOICE_SENT = "INVOICE_SENT"
    INVOICE_VIEWED = "INVOICE_VIEWED"  # Reserved - Step 3+ Client Portal
    PAYMENT_ADDED = "PAYMENT_ADDED"
    STATUS_CHANGED = "STATUS_CHANGED"
    INVOICE_VOIDED = "INVOICE_VOIDED"
    CREDIT_NOTE_ISSUED = "CREDIT_NOTE_ISSUED"
    DEBIT_NOTE_ISSUED = "DEBIT_NOTE_ISSUED"


class InvoiceEvent(SQLModel, table=True):
    __tablename__ = "invoice_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    invoice_id: uuid.UUID = Field(foreign_key="invoices.id", nullable=False, index=True)

    # Event classification
    event_type: InvoiceEventType = Field(
        sa_column=Column(SAEnum(InvoiceEventType), nullable=False)
    )

    # Status tracking (for STATUS_CHANGED events)
    previous_status: Optional[str] = Field(default=None, max_length=50)
    new_status: str = Field(max_length=50)
    changed_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    # Use JSONB for queryable context
    metadata_log: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, default=dict, nullable=False)
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Relationships
    invoice: "Invoice" = Relationship(back_populates="events")
    changed_by_user: "User" = Relationship(back_populates="invoice_events")
