import uuid
import enum
from decimal import Decimal
from typing import List, Optional
from datetime import date, datetime, timezone
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column, String, Enum as SAEnum, Text, CheckConstraint, UniqueConstraint, Numeric, DateTime

class GRNStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RECEIVING = "RECEIVING"
    PENDING_INSPECTION = "PENDING_INSPECTION"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_REJECTED = "PARTIALLY_REJECTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class GoodsReceiptNote(SQLModel, table=True):
    __tablename__ = "goods_receipt_notes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "grn_number", name="uq_grn_workspace_number"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", index=True)
    grn_number: str = Field(sa_column=Column(String, index=True))
    spo_id: Optional[uuid.UUID] = Field(default=None, foreign_key="supplier_purchase_orders.id", index=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", index=True)
    
    received_date: date
    received_by: uuid.UUID = Field(foreign_key="users.id")
    delivery_reference: Optional[str] = Field(default=None)
    vehicle_number: Optional[str] = Field(default=None)
    driver_name: Optional[str] = Field(default=None)
    
    status: GRNStatus = Field(sa_column=Column(SAEnum(GRNStatus, name="grnstatus"), default=GRNStatus.DRAFT, nullable=False))
    stock_posted: bool = Field(default=False)
    notes: Optional[str] = Field(sa_column=Column(Text), default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True)))

    items: List["GRNItem"] = Relationship(back_populates="grn")


class GRNItem(SQLModel, table=True):
    __tablename__ = "grn_items"
    __table_args__ = (
        CheckConstraint(
            "quantity_received = quantity_accepted + quantity_damaged + quantity_rejected",
            name="chk_grnitem_quantity_received_match"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    grn_id: uuid.UUID = Field(foreign_key="goods_receipt_notes.id", index=True)
    spo_item_id: uuid.UUID = Field(foreign_key="supplier_purchase_order_items.id", index=True)
    spo_delivery_schedule_id: Optional[uuid.UUID] = Field(default=None, foreign_key="spo_delivery_schedules.id")
    product_id: uuid.UUID = Field(foreign_key="products.id")
    internal_sku: str
    description: str
    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id")
    location_id: Optional[uuid.UUID] = Field(default=None)
    
    quantity_ordered_snapshot: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    quantity_confirmed_snapshot: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    quantity_received: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    quantity_accepted: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    quantity_damaged: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    quantity_rejected: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=4)
    
    batch_number: Optional[str] = Field(default=None)
    expiry_date: Optional[date] = Field(default=None)
    
    damage_reason: Optional[str] = Field(sa_column=Column(Text), default=None)
    rejection_reason: Optional[str] = Field(sa_column=Column(Text), default=None)
    
    inspected_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    inspected_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    notes: Optional[str] = Field(sa_column=Column(Text), default=None)

    grn: GoodsReceiptNote = Relationship(back_populates="items")
