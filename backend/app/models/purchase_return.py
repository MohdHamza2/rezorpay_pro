"""
Purchase Return Models — Wave 23 (Phase 4).

A purchase return ships accepted/rejected/damaged GRN quantities back to a
supplier and, once dispatched, automatically generates a supplier debit note
(SDN) that offsets the payable on approved supplier invoices.

Snapshots required by the addendum: product / sku / description / uom plus an
agreed return `unit_price` (from the payload, or the SPO unit price for
GRN-004 auto-items). `stock_out_qty` is the portion drawn from on-hand stock
at dispatch; rejected/damaged quantities never entered inventory, so their
stock_out is zero.
"""

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, Relationship, SQLModel


class PurchaseReturnStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_SUPPLIER = "PENDING_SUPPLIER"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    RECEIVED_BACK = "RECEIVED_BACK"


class ReturnType(str, enum.Enum):
    QUALITY_ISSUE = "QUALITY_ISSUE"
    DAMAGE = "DAMAGE"
    WRONG_ITEM = "WRONG_ITEM"
    EXCESS = "EXCESS"


class PurchaseReturnReceiptStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RECEIVING = "RECEIVING"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class ReturnCondition(str, enum.Enum):
    GOOD = "GOOD"
    DAMAGED = "DAMAGED"
    QUARANTINE = "QUARANTINE"


class PurchaseReturn(SQLModel, table=True):
    __tablename__ = "purchase_returns"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "prn_number", name="uq_purchase_return_workspace_number"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", index=True)
    grn_id: uuid.UUID = Field(foreign_key="goods_receipt_notes.id", index=True)

    prn_number: str = Field(sa_column=Column(Text, nullable=False, index=True))
    return_date: date
    status: PurchaseReturnStatus = Field(
        sa_column=Column(
            SAEnum(PurchaseReturnStatus, name="purchasereturnstatus"),
            default=PurchaseReturnStatus.DRAFT,
            nullable=False,
        )
    )

    reason: str = Field(sa_column=Column(Text, nullable=False))
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    items: List["PurchaseReturnItem"] = Relationship(back_populates="purchase_return")


class PurchaseReturnItem(SQLModel, table=True):
    __tablename__ = "purchase_return_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_preturn_item_quantity_positive"),
        CheckConstraint("stock_out_qty >= 0", name="chk_preturn_item_stock_out_nonneg"),
        CheckConstraint("unit_price > 0", name="chk_preturn_item_unit_price_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    purchase_return_id: uuid.UUID = Field(foreign_key="purchase_returns.id", index=True)
    grn_item_id: uuid.UUID = Field(foreign_key="grn_items.id", index=True)

    product_id: uuid.UUID = Field(foreign_key="products.id")
    internal_sku: str
    description: str
    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id")

    quantity: Decimal = Field(max_digits=12, decimal_places=4)
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    vat_rate: Decimal = Field(default=Decimal("0.00"), max_digits=5, decimal_places=2)
    vat_amount: Decimal = Field(
        default=Decimal("0.00"), max_digits=12, decimal_places=2
    )
    stock_out_qty: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    received_qty: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)

    return_type: ReturnType = Field(
        sa_column=Column(SAEnum(ReturnType, name="purchasereturntype"), nullable=False)
    )

    notes: Optional[str] = Field(sa_column=Column(Text), default=None)

    purchase_return: PurchaseReturn = Relationship(back_populates="items")
    receipt_items: List["PurchaseReturnReceiptItem"] = Relationship(
        back_populates="purchase_return_item"
    )


class PurchaseReturnCounter(SQLModel, table=True):
    """Workspace-scoped gapless counter for purchase returns (PRN-YYYY-XXXX)."""

    __tablename__ = "purchase_return_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id",
        primary_key=True,
        nullable=False,
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
        """Generate formatted purchase return number: PRN-2026-0001"""
        return f"PRN-{self.year}-{self.last_number:04d}"


class PurchaseReturnReceipt(SQLModel, table=True):
    """Return Receipt — Wave 31 Item 2.8.

    Represents the warehouse receiving of goods returned to a supplier
    that are sent back to us (replacement, repair, etc.).
    """

    __tablename__ = "purchase_return_receipts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "receipt_number",
            name="uq_purchase_return_receipt_workspace_number",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    purchase_return_id: uuid.UUID = Field(foreign_key="purchase_returns.id", index=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", index=True)
    bin_id: uuid.UUID = Field(
        foreign_key="warehouse_bins.id", index=True, nullable=True
    )

    receipt_number: str = Field(sa_column=Column(Text, nullable=False, index=True))
    receipt_date: date
    status: PurchaseReturnReceiptStatus = Field(
        sa_column=Column(
            SAEnum(PurchaseReturnReceiptStatus, name="purchasereturnreceiptstatus"),
            default=PurchaseReturnReceiptStatus.DRAFT,
            nullable=False,
        )
    )

    received_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    notes: Optional[str] = Field(sa_column=Column(Text), default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    items: List["PurchaseReturnReceiptItem"] = Relationship(
        back_populates="purchase_return_receipt"
    )


class PurchaseReturnReceiptItem(SQLModel, table=True):
    """Return Receipt Line — Wave 31 Item 2.8."""

    __tablename__ = "purchase_return_receipt_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="chk_preturn_receipt_item_quantity_positive"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    purchase_return_receipt_id: uuid.UUID = Field(
        foreign_key="purchase_return_receipts.id", index=True
    )
    purchase_return_item_id: uuid.UUID = Field(
        foreign_key="purchase_return_items.id", index=True
    )

    product_id: uuid.UUID = Field(foreign_key="products.id")
    quantity: Decimal = Field(max_digits=12, decimal_places=4)
    condition: ReturnCondition = Field(
        sa_column=Column(
            SAEnum(ReturnCondition, name="purchasereturncondition"), nullable=False
        )
    )
    bin_id: uuid.UUID = Field(foreign_key="warehouse_bins.id", nullable=True)

    notes: Optional[str] = Field(sa_column=Column(Text), default=None)

    purchase_return_receipt: "PurchaseReturnReceipt" = Relationship(
        back_populates="items"
    )
    purchase_return_item: "PurchaseReturnItem" = Relationship(
        back_populates="receipt_items"
    )


class PurchaseReturnReceiptCounter(SQLModel, table=True):
    """Workspace-scoped gapless counter for return receipts (RRN-YYYY-XXXX)."""

    __tablename__ = "purchase_return_receipt_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id",
        primary_key=True,
        nullable=False,
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
        """Generate formatted return receipt number: RRN-2026-0001"""
        return f"RRN-{self.year}-{self.last_number:04d}"
