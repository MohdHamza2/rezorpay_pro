import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Numeric
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.quotation import Quotation


class QuotationItem(SQLModel, table=True):
    __tablename__ = "quotation_items"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_quotation_item_qty_positive"),
        CheckConstraint("unit_price >= 0", name="check_quotation_item_price_positive"),
        CheckConstraint("tax_rate >= 0", name="check_quotation_item_tax_rate_positive"),
        CheckConstraint("total_price >= 0", name="check_quotation_item_total_positive"),
        CheckConstraint(
            "discount_percent >= 0", name="check_quotation_disc_pct_nonneg"
        ),
        CheckConstraint("discount_amount >= 0", name="check_quotation_disc_amt_nonneg"),
        CheckConstraint("line_net >= 0", name="check_quotation_line_net_nonneg"),
        CheckConstraint("tax_amount >= 0", name="check_quotation_item_tax_nonneg"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    quotation_id: uuid.UUID = Field(
        foreign_key="quotations.id", nullable=False, index=True
    )

    product_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="products.id", index=True
    )
    uom_id: Optional[uuid.UUID] = Field(default=None, foreign_key="units_of_measure.id")
    sku_snapshot: Optional[str] = Field(default=None, max_length=100)

    description: str = Field(max_length=500)
    quantity: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_rate: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )
    discount_percent: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False)
    )
    line_net: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False)
    )
    tax_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False)
    )
    total_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    quotation: "Quotation" = Relationship(back_populates="items")
