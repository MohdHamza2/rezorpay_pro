import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.customer_purchase_order import CustomerPurchaseOrder
    from app.models.user import User


class CustomerPurchaseOrderEventType(str, Enum):
    CPO_CREATED = "CPO_CREATED"
    CPO_UPDATED = "CPO_UPDATED"
    CPO_RECEIVED = "CPO_RECEIVED"
    CPO_INVOICE_CREATED = "CPO_INVOICE_CREATED"
    CPO_CANCELLED = "CPO_CANCELLED"
    CPO_RECALC = "CPO_RECALC"


class CustomerPurchaseOrderEvent(SQLModel, table=True):
    __tablename__ = "customer_purchase_order_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    customer_purchase_order_id: uuid.UUID = Field(
        foreign_key="customer_purchase_orders.id", nullable=False, index=True
    )

    event_type: CustomerPurchaseOrderEventType = Field(
        sa_column=Column(SAEnum(CustomerPurchaseOrderEventType), nullable=False)
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

    customer_purchase_order: "CustomerPurchaseOrder" = Relationship(
        back_populates="events"
    )
    changed_by_user: "User" = Relationship(
        back_populates="customer_purchase_order_events"
    )
