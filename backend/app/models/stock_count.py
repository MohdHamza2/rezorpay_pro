import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Numeric,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlmodel import Field, Relationship, SQLModel


class StockCountStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RECONCILED = "RECONCILED"
    CANCELLED = "CANCELLED"


class StockCount(SQLModel, table=True):
    """Physical stock count vs system expected quantity.

    Expected quantities are snapshotted at schedule time from each bin's
    ``InventoryLevel.on_hand`` (a physical count includes reserved and damaged
    stock). Variance = counted − expected; lines beyond tolerance are flagged
    ``requires_approval`` and only applied to stock after manager approval.
    Reconciliation writes ADJUSTMENT ledger rows against the count.
    """

    __tablename__ = "stock_counts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    count_number: str = Field(max_length=50, index=True)
    warehouse_id: uuid.UUID = Field(
        foreign_key="warehouses.id", nullable=False, index=True
    )
    status: StockCountStatus = Field(
        default=StockCountStatus.SCHEDULED,
        sa_column=Column(
            SQLEnum(StockCountStatus, name="stockcountstatus"), nullable=False
        ),
    )

    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    completed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    reconciled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    approved_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    approved_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    items: list["StockCountItem"] = Relationship(
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "StockCountItem.created_at",
        }
    )


class StockCountItem(SQLModel, table=True):
    __tablename__ = "stock_count_items"
    __table_args__ = (
        UniqueConstraint(
            "count_id", "product_id", "bin_id", name="uq_count_item_product_bin"
        ),
        CheckConstraint(
            "expected_quantity >= 0", name="chk_count_item_expected_positive"
        ),
        CheckConstraint(
            "counted_quantity >= 0", name="chk_count_item_counted_positive"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    count_id: uuid.UUID = Field(
        foreign_key="stock_counts.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    bin_id: uuid.UUID = Field(
        foreign_key="warehouse_bins.id", nullable=False, index=True
    )
    expected_quantity: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    counted_quantity: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    requires_approval: bool = Field(default=False, nullable=False)
    approved: bool = Field(default=False, nullable=False)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class StockCountCounter(SQLModel, table=True):
    """Workspace-scoped stock count number counter (SC-YYYY-0001)."""

    __tablename__ = "stock_count_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", primary_key=True, nullable=False
    )
    year: int = Field(primary_key=True, nullable=False)
    last_number: int = Field(default=0, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    def generate_number(self) -> str:
        return f"SC-{self.year}-{self.last_number:04d}"
