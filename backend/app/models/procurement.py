import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, List
from enum import Enum

from sqlalchemy import Column, DateTime, Date, Numeric, UniqueConstraint, Text
from sqlmodel import Field, Relationship, SQLModel


class PRSourceType(str, Enum):
    STOCK_REPLENISHMENT = "STOCK_REPLENISHMENT"
    CUSTOMER_ORDER = "CUSTOMER_ORDER"
    PROJECT = "PROJECT"
    MANUAL = "MANUAL"
    BACKORDER = "BACKORDER"
    INTERNAL_REQUIREMENT = "INTERNAL_REQUIREMENT"


class PRDestinationType(str, Enum):
    WAREHOUSE = "WAREHOUSE"
    CUSTOMER = "CUSTOMER"
    PROJECT = "PROJECT"
    INTERNAL = "INTERNAL"
    UNALLOCATED = "UNALLOCATED"


class PRPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class PRMethod(str, Enum):
    RFQ = "RFQ"
    DIRECT = "DIRECT"
    CONTRACT = "CONTRACT"
    EMERGENCY = "EMERGENCY"


class PRStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    PARTIALLY_ORDERED = "PARTIALLY_ORDERED"
    FULLY_ORDERED = "FULLY_ORDERED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class ProcurementRequest(SQLModel, table=True):
    __tablename__ = "procurement_requests"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "request_number", name="uq_workspace_pr_number"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    request_number: str = Field(max_length=50, index=True)  # PR-YYYY-000001

    source_type: PRSourceType = Field(nullable=False)
    destination_type: PRDestinationType = Field(nullable=False)

    # Traceability links
    customer_id: Optional[uuid.UUID] = Field(default=None, foreign_key="clients.id")
    warehouse_id: Optional[uuid.UUID] = Field(default=None, foreign_key="warehouses.id")
    # project_id: Optional[uuid.UUID] = Field(default=None) # To be linked later if Project module exists

    priority: PRPriority = Field(default=PRPriority.NORMAL)
    procurement_method: PRMethod = Field(default=PRMethod.DIRECT)

    required_by_date: date = Field(sa_column=Column(Date, nullable=False))
    status: PRStatus = Field(default=PRStatus.DRAFT)

    notes: Optional[str] = Field(default=None, sa_column=Column(Text))

    requested_by_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    items: List["ProcurementRequestItem"] = Relationship(back_populates="request")


class ProcurementRequestItem(SQLModel, table=True):
    __tablename__ = "procurement_request_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: uuid.UUID = Field(
        foreign_key="procurement_requests.id", nullable=False, index=True
    )

    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False)
    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id", nullable=False)

    # Traceability
    # customer_po_item_id: Optional[uuid.UUID] = Field(default=None, foreign_key="customer_po_items.id")

    # Quantity Tracking (Rule C-02)
    requested_quantity: Decimal = Field(
        sa_column=Column(Numeric(12, 2), nullable=False)
    )
    approved_quantity: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 2), nullable=False)
    )
    ordered_quantity: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 2), nullable=False)
    )
    cancelled_quantity: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 2), nullable=False)
    )
    received_quantity: Decimal = Field(
        default=0, sa_column=Column(Numeric(12, 2), nullable=False)
    )

    request: ProcurementRequest = Relationship(back_populates="items")
