import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Numeric
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.delivery_note import DeliveryNote


class DeliveryNoteItem(SQLModel, table=True):
    __tablename__ = "delivery_note_items"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_dn_item_qty_positive"),
        CheckConstraint(
            "(customer_purchase_order_item_id IS NULL) <> (invoice_item_id IS NULL)",
            name="check_dn_item_parent_xor",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    delivery_note_id: uuid.UUID = Field(
        foreign_key="delivery_notes.id", nullable=False, index=True
    )
    customer_purchase_order_item_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="customer_purchase_order_items.id",
        index=True,
    )
    invoice_item_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="invoice_items.id", index=True
    )
    product_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="products.id", index=True
    )
    uom_id: Optional[uuid.UUID] = Field(default=None, foreign_key="units_of_measure.id")
    sku_snapshot: Optional[str] = Field(default=None, max_length=100)
    description: str = Field(max_length=500)
    quantity: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    bin_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="warehouse_bins.id", index=True
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    delivery_note: "DeliveryNote" = Relationship(back_populates="items")
