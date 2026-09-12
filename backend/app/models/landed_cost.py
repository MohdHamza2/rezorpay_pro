import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    Numeric,
    UniqueConstraint,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.grn import GRNItem
    from app.models.spo import SupplierPurchaseOrderItem


class LandedCostType(str, Enum):
    FREIGHT = "FREIGHT"
    CUSTOMS = "CUSTOMS"
    INSURANCE = "INSURANCE"
    HANDLING = "HANDLING"
    BROKERAGE = "BROKERAGE"
    OTHER = "OTHER"


class AllocationBasis(str, Enum):
    QUANTITY = "QUANTITY"
    VALUE = "VALUE"
    MANUAL = "MANUAL"


class LandedCostStatus(str, Enum):
    DRAFT = "DRAFT"
    ALLOCATED = "ALLOCATED"
    CAPITALIZED = "CAPITALIZED"
    REVERSED = "REVERSED"


class LandedCostAllocation(SQLModel, table=True):
    __tablename__ = "landed_cost_allocations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_document_type",
            "source_document_id",
            "source_line_id",
            name="uq_landed_cost_source",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    grn_id: uuid.UUID = Field(
        foreign_key="goods_receipt_notes.id", nullable=False, index=True
    )
    grn_item_id: uuid.UUID = Field(
        foreign_key="grn_items.id", nullable=False, index=True
    )
    spo_item_id: uuid.UUID = Field(
        foreign_key="supplier_purchase_order_items.id", nullable=False, index=True
    )

    component_type: str = Field(max_length=20)
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(max_length=3, default="AED")

    allocation_basis: str = Field(max_length=20)  # QUANTITY, VALUE, MANUAL
    allocation_factor: Decimal = Field(
        sa_column=Column(Numeric(14, 6)), default=Decimal("1.0")
    )

    source_document_type: Optional[str] = Field(
        default=None, max_length=30
    )  # GRN, SUPPLIER_INVOICE, FREIGHT_BILL, CUSTOMS_ENTRY, MANUAL
    source_document_id: Optional[uuid.UUID] = Field(default=None)
    source_line_id: Optional[uuid.UUID] = Field(default=None)

    status: str = Field(
        max_length=20, default="DRAFT"
    )  # DRAFT, ALLOCATED, CAPITALIZED, REVERSED

    allocated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    capitalized_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    # Relationships
    grn_item: Optional["GRNItem"] = Relationship(
        back_populates="landed_cost_allocations"
    )
    spo_item: Optional["SupplierPurchaseOrderItem"] = Relationship(
        back_populates="landed_cost_allocations"
    )
