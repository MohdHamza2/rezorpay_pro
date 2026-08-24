import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Numeric, CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class InvoiceItem(SQLModel, table=True):
    __tablename__ = "invoice_items"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="check_unit_price_positive"),
        CheckConstraint("tax_rate >= 0", name="check_tax_rate_positive"),
        CheckConstraint("total_price >= 0", name="check_total_price_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    invoice_id: uuid.UUID = Field(foreign_key="invoices.id", nullable=False, index=True)

    description: str = Field(max_length=500)
    quantity: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_rate: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )
    total_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Relationships
    invoice: "Invoice" = Relationship(back_populates="items")
