"""Purchase return schemas — Wave 23 (Phase 4)."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.purchase_return import PurchaseReturnStatus, ReturnType
from app.services.line_money import money


class PurchaseReturnItemCreate(BaseModel):
    grn_item_id: UUID
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    return_type: ReturnType
    notes: Optional[str] = None
    vat_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)


class PurchaseReturnCreate(BaseModel):
    supplier_id: UUID
    grn_id: UUID
    return_date: date
    reason: str = Field(min_length=5)
    items: List[PurchaseReturnItemCreate] = Field(min_length=1)


class PurchaseReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_return_id: UUID
    grn_item_id: UUID
    product_id: UUID
    internal_sku: str
    description: str
    uom_id: UUID
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    stock_out_qty: Decimal
    return_type: ReturnType
    notes: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def line_net(self) -> Decimal:
        return money(self.quantity * self.unit_price)

    @computed_field  # type: ignore[misc]
    @property
    def total_price(self) -> Decimal:
        return money(self.line_net + self.vat_amount)


class PurchaseReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID
    grn_id: UUID
    prn_number: str
    return_date: date
    status: PurchaseReturnStatus
    reason: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseReturnItemResponse] = []

    @computed_field  # type: ignore[misc]
    @property
    def total_value(self) -> Decimal:
        """Gross total including VAT (for backward compatibility with existing consumers)."""
        return money(
            sum(
                (i.quantity * i.unit_price + i.vat_amount for i in self.items),
                Decimal("0"),
            )
        )

    @computed_field  # type: ignore[misc]
    @property
    def total_net(self) -> Decimal:
        """Net total excluding VAT."""
        return money(sum((i.quantity * i.unit_price for i in self.items), Decimal("0")))

    @computed_field  # type: ignore[misc]
    @property
    def total_vat(self) -> Decimal:
        return money(sum((i.vat_amount for i in self.items), Decimal("0")))
