import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.delivery_note_event import DeliveryNoteEvent
    from app.models.delivery_note_item import DeliveryNoteItem


class DeliveryNoteStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class DeliveryNote(SQLModel, table=True):
    __tablename__ = "delivery_notes"

    __table_args__ = (
        UniqueConstraint("workspace_id", "dn_number", name="uq_workspace_dn_number"),
        CheckConstraint(
            "(customer_purchase_order_id IS NULL) <> (invoice_id IS NULL)",
            name="check_dn_parent_xor",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)
    customer_purchase_order_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="customer_purchase_orders.id",
        index=True,
    )
    invoice_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="invoices.id", index=True
    )
    warehouse_id: uuid.UUID = Field(
        foreign_key="warehouses.id", nullable=False, index=True
    )
    bin_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="warehouse_bins.id", index=True
    )

    dn_number: str = Field(max_length=50, index=True)
    status: DeliveryNoteStatus = Field(
        sa_column=Column(
            SQLEnum(DeliveryNoteStatus, name="deliverynotestatus"),
            default=DeliveryNoteStatus.DRAFT,
            nullable=False,
        )
    )
    delivery_date: date = Field(sa_column=Column(Date, nullable=False))
    shipping_address: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    vehicle_number: Optional[str] = Field(default=None, max_length=100)
    driver_name: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    cancellation_reason: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    confirmed_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    confirmed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    items: list["DeliveryNoteItem"] = Relationship(back_populates="delivery_note")
    events: list["DeliveryNoteEvent"] = Relationship(back_populates="delivery_note")
