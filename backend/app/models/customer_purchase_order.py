import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.customer_purchase_order_event import CustomerPurchaseOrderEvent
    from app.models.customer_purchase_order_item import CustomerPurchaseOrderItem


class CustomerPurchaseOrderStatus(str, Enum):
    DRAFT = "DRAFT"
    RECEIVED = "RECEIVED"
    PARTIAL = "PARTIAL"
    INVOICED = "INVOICED"
    CANCELLED = "CANCELLED"


class CustomerPurchaseOrder(SQLModel, table=True):
    __tablename__ = "customer_purchase_orders"

    __table_args__ = (
        UniqueConstraint("workspace_id", "lpo_number", name="uq_workspace_lpo_number"),
        Index(
            "uq_cpo_workspace_client_po_number",
            "workspace_id",
            "client_id",
            "customer_po_number",
            unique=True,
            postgresql_where=text("customer_po_number IS NOT NULL"),
        ),
        CheckConstraint("subtotal >= 0", name="check_cpo_subtotal_positive"),
        CheckConstraint("tax_amount >= 0", name="check_cpo_tax_amount_positive"),
        CheckConstraint("total_amount >= 0", name="check_cpo_total_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)
    quotation_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="quotations.id", unique=True, index=True
    )

    lpo_number: str = Field(max_length=50, index=True)
    customer_po_number: Optional[str] = Field(default=None, max_length=100)
    currency: str = Field(default="AED", max_length=3)

    subtotal: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    status: CustomerPurchaseOrderStatus = Field(
        sa_column=Column(
            SQLEnum(CustomerPurchaseOrderStatus),
            default=CustomerPurchaseOrderStatus.DRAFT,
            nullable=False,
        )
    )
    lpo_date: date = Field(sa_column=Column(Date, nullable=False))
    expected_delivery_date: Optional[date] = Field(
        default=None, sa_column=Column(Date, nullable=True)
    )
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    cancellation_reason: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
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

    items: list["CustomerPurchaseOrderItem"] = Relationship(
        back_populates="customer_purchase_order"
    )
    events: list["CustomerPurchaseOrderEvent"] = Relationship(
        back_populates="customer_purchase_order"
    )
