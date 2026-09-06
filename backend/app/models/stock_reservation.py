import uuid
from datetime import datetime, timedelta, timezone
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

RESERVATION_TTL_DAYS = 7


class ReservationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class StockReservation(SQLModel, table=True):
    """Committed stock against a received Customer PO.

    Lines hold per-(product, warehouse, bin) quantities. The sum of remaining
    (quantity - quantity_consumed) over ACTIVE lines for a level is exactly the
    ``reserved`` column on ``InventoryLevel`` (available = on_hand - reserved -
    damaged).
    """

    __tablename__ = "stock_reservations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    customer_purchase_order_id: uuid.UUID = Field(
        foreign_key="customer_purchase_orders.id", nullable=False, index=True
    )

    status: ReservationStatus = Field(
        sa_column=Column(
            SQLEnum(ReservationStatus, name="reservationstatus"),
            default=ReservationStatus.ACTIVE,
            nullable=False,
        )
    )
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
        + timedelta(days=RESERVATION_TTL_DAYS),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancellation_reason: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    items: list["StockReservationItem"] = Relationship(back_populates="reservation")


class StockReservationItem(SQLModel, table=True):
    """One reserved (product, warehouse, bin) quantity under a reservation."""

    __tablename__ = "stock_reservation_items"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_reservation_item_qty_positive"),
        CheckConstraint(
            "quantity_consumed >= 0", name="chk_reservation_item_consumed_positive"
        ),
        CheckConstraint(
            "quantity_consumed <= quantity",
            name="chk_reservation_item_consumed_lte_qty",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    reservation_id: uuid.UUID = Field(
        foreign_key="stock_reservations.id", nullable=False, index=True
    )
    customer_purchase_order_item_id: uuid.UUID = Field(
        foreign_key="customer_purchase_order_items.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    warehouse_id: uuid.UUID = Field(
        foreign_key="warehouses.id", nullable=False, index=True
    )
    bin_id: uuid.UUID = Field(
        foreign_key="warehouse_bins.id", nullable=False, index=True
    )

    quantity: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    quantity_consumed: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False)
    )
    status: ReservationStatus = Field(
        sa_column=Column(
            SQLEnum(ReservationStatus, name="reservationstatus"),
            default=ReservationStatus.ACTIVE,
            nullable=False,
        )
    )
    dispatched_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    reservation: StockReservation = Relationship(back_populates="items")
