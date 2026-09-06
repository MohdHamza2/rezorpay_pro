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
    Enum as SQLEnum,
)
from sqlmodel import Field, Relationship, SQLModel


class TransferStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class StockTransfer(SQLModel, table=True):
    """Warehouse → warehouse stock movement with an immutable ledger trail.

    Dispatch decrements the source ``InventoryLevel.on_hand`` and adds the
    quantity to ``in_transit`` (swing account, not part of available). Receipt
    clears ``in_transit`` at the source and adds to the destination's
    ``on_hand``. Partial receipt stores the discrepancy on the line.
    """

    __tablename__ = "stock_transfers"
    __table_args__ = (
        CheckConstraint(
            "source_warehouse_id != destination_warehouse_id",
            name="chk_st_transfer_distinct_warehouses",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    transfer_number: str = Field(max_length=50, index=True)
    source_warehouse_id: uuid.UUID = Field(
        foreign_key="warehouses.id", nullable=False, index=True
    )
    destination_warehouse_id: uuid.UUID = Field(
        foreign_key="warehouses.id", nullable=False, index=True
    )
    status: TransferStatus = Field(
        default=TransferStatus.DRAFT,
        sa_column=Column(
            SQLEnum(TransferStatus, name="transferstatus"), nullable=False
        ),
    )

    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    dispatched_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    received_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancellation_reason: Optional[str] = Field(default=None, max_length=500)
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    items: list["StockTransferItem"] = Relationship(
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "StockTransferItem.created_at",
        }
    )


class StockTransferItem(SQLModel, table=True):
    __tablename__ = "stock_transfer_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_st_item_quantity_positive"),
        CheckConstraint("received_quantity >= 0", name="chk_st_item_received_positive"),
        CheckConstraint(
            "received_quantity <= quantity", name="chk_st_item_received_leq_quantity"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    transfer_id: uuid.UUID = Field(
        foreign_key="stock_transfers.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    quantity: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    received_quantity: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False)
    )
    source_bin_id: uuid.UUID = Field(
        foreign_key="warehouse_bins.id", nullable=False, index=True
    )
    destination_bin_id: uuid.UUID = Field(
        foreign_key="warehouse_bins.id", nullable=False, index=True
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class StockTransferCounter(SQLModel, table=True):
    """Workspace-scoped stock transfer number counter (ST-YYYY-0001)."""

    __tablename__ = "stock_transfer_counters"

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
        return f"ST-{self.year}-{self.last_number:04d}"
