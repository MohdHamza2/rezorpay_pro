import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from enum import Enum

from sqlalchemy import Column, DateTime, Date, Numeric, UniqueConstraint, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.landed_cost import LandedCostAllocation


class ProcurementMethod(str, Enum):
    RFQ = "RFQ"
    DIRECT = "DIRECT"
    CONTRACT = "CONTRACT"
    EMERGENCY = "EMERGENCY"


class SPOStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    PARTIALLY_ACKNOWLEDGED = "PARTIALLY_ACKNOWLEDGED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    FULLY_RECEIVED = "FULLY_RECEIVED"
    SHORT_CLOSED = "SHORT_CLOSED"
    PARTIALLY_CANCELLED = "PARTIALLY_CANCELLED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class SPODeliveryScheduleStatus(str, Enum):
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"


class SPOAmendmentStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SUPPLIER_REJECTED = "SUPPLIER_REJECTED"
    APPLIED = "APPLIED"
    WITHDRAWN = "WITHDRAWN"


class SPOAmendmentField(str, Enum):
    QUANTITY_ORDERED = "QUANTITY_ORDERED"
    UNIT_PRICE = "UNIT_PRICE"
    DELIVERY_DATE = "DELIVERY_DATE"
    DELIVERY_TERMS = "DELIVERY_TERMS"
    OTHER = "OTHER"


class SupplierPurchaseOrder(SQLModel, table=True):
    __tablename__ = "supplier_purchase_orders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "spo_number", name="uq_workspace_spo_number"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )

    spo_number: str = Field(max_length=50, index=True)

    rfq_id: Optional[uuid.UUID] = Field(default=None, foreign_key="rfqs.id")
    procurement_request_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="procurement_requests.id"
    )

    procurement_method: ProcurementMethod = Field(nullable=False)
    single_source_justification: Optional[str] = Field(
        default=None, sa_column=Column(Text)
    )

    supplier_reference: Optional[str] = Field(default=None, max_length=100)
    status: SPOStatus = Field(default=SPOStatus.DRAFT)

    po_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    expected_delivery_date: Optional[date] = Field(default=None, sa_column=Column(Date))

    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False)

    currency: str = Field(default="AED", max_length=3)
    payment_terms_days: int = Field(default=0)
    delivery_terms: Optional[str] = Field(default=None, max_length=255)

    subtotal: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))
    vat_amount: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))
    total_amount: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))

    quantity_ordered_total: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_confirmed_total: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 4))
    )
    quantity_backordered_total: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 4))
    )

    has_open_amendment: bool = Field(default=False)

    approved_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    approved_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    sent_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    acknowledged_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    closed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    items: List["SupplierPurchaseOrderItem"] = Relationship(back_populates="spo")
    amendments: List["SPOAmendment"] = Relationship(back_populates="spo")
    status_history: List["SPOStatusHistory"] = Relationship(back_populates="spo")


class SupplierPurchaseOrderItem(SQLModel, table=True):
    __tablename__ = "supplier_purchase_order_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spo_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_orders.id", nullable=False, index=True
    )

    line_number: int = Field(nullable=False)

    rfq_award_line_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="rfq_award_lines.id"
    )
    procurement_request_item_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="procurement_request_items.id"
    )

    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False)
    internal_sku: Optional[str] = Field(default=None, max_length=100)
    supplier_sku: Optional[str] = Field(default=None, max_length=100)
    description: str = Field(max_length=255)

    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id", nullable=False)

    quantity_ordered: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_confirmed: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_backordered: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_received: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_accepted: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_damaged_rejected: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 4))
    )
    quantity_invoiced: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    quantity_cancelled: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    open_quantity: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))

    unit_price: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))
    discount_percent: Decimal = Field(default=0, sa_column=Column(Numeric(5, 2)))
    vat_rate: Decimal = Field(default=0, sa_column=Column(Numeric(5, 2)))
    vat_amount: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))
    total_price: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))

    price_amendment_pending: bool = Field(default=False)
    expected_delivery_date: Optional[date] = Field(default=None, sa_column=Column(Date))

    spo: SupplierPurchaseOrder = Relationship(back_populates="items")
    landed_cost_allocations: List["LandedCostAllocation"] = Relationship(
        back_populates="spo_item"
    )


class SPODeliverySchedule(SQLModel, table=True):
    __tablename__ = "spo_delivery_schedules"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spo_item_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_order_items.id", nullable=False, index=True
    )

    tranche_number: int = Field(nullable=False)
    scheduled_quantity: Decimal = Field(default=0, sa_column=Column(Numeric(12, 4)))
    scheduled_date: date = Field(sa_column=Column(Date, nullable=False))

    status: SPODeliveryScheduleStatus = Field(default=SPODeliveryScheduleStatus.PENDING)
    delayed_flagged_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )


class SPOAmendment(SQLModel, table=True):
    __tablename__ = "spo_amendments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spo_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_orders.id", nullable=False, index=True
    )

    amendment_number: int = Field(nullable=False)
    status: SPOAmendmentStatus = Field(default=SPOAmendmentStatus.PROPOSED)
    reason: str = Field(sa_column=Column(Text, nullable=False))
    requires_supplier_reconfirmation: bool = Field(default=False)

    amended_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    approved_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    applied_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )

    spo: SupplierPurchaseOrder = Relationship(back_populates="amendments")
    lines: List["SPOAmendmentLine"] = Relationship(back_populates="amendment")


class SPOAmendmentLine(SQLModel, table=True):
    __tablename__ = "spo_amendment_lines"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    amendment_id: uuid.UUID = Field(
        foreign_key="spo_amendments.id", nullable=False, index=True
    )
    spo_item_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_order_items.id", nullable=False
    )

    field_name: SPOAmendmentField = Field(nullable=False)
    old_value: Optional[str] = Field(default=None, max_length=255)
    new_value: Optional[str] = Field(default=None, max_length=255)

    amendment: Optional["SPOAmendment"] = Relationship(back_populates="lines")


class SPOStatusHistory(SQLModel, table=True):
    __tablename__ = "spo_status_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spo_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_orders.id", nullable=False, index=True
    )

    from_status: str = Field(max_length=50)
    to_status: str = Field(max_length=50)

    triggered_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    trigger_reason: Optional[str] = Field(default=None, max_length=255)

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    spo: SupplierPurchaseOrder = Relationship(back_populates="status_history")
