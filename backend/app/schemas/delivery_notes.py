"""Delivery Note request/response schemas. Extra keys → 422."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.delivery_note import DeliveryNoteStatus


class DeliveryNoteItemCreate(BaseModel):
    """Qty against exactly one parent line matching the header."""

    model_config = ConfigDict(extra="forbid")

    customer_purchase_order_item_id: Optional[UUID] = None
    invoice_item_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)
    bin_id: Optional[UUID] = None

    @model_validator(mode="after")
    def xor_parent_line(self) -> "DeliveryNoteItemCreate":
        has_cpo = self.customer_purchase_order_item_id is not None
        has_inv = self.invoice_item_id is not None
        if has_cpo == has_inv:
            raise ValueError(
                "Exactly one of customer_purchase_order_item_id or "
                "invoice_item_id is required"
            )
        return self


class DeliveryNoteItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    delivery_note_id: UUID
    customer_purchase_order_item_id: Optional[UUID] = None
    invoice_item_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    uom_id: Optional[UUID] = None
    sku_snapshot: Optional[str] = None
    description: str
    quantity: Decimal
    bin_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class DeliveryNoteCreate(BaseModel):
    """XOR parent. Omit items to copy remaining parent lines."""

    model_config = ConfigDict(extra="forbid")

    customer_purchase_order_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    warehouse_id: UUID
    bin_id: Optional[UUID] = None
    delivery_date: Optional[date] = None
    shipping_address: Optional[str] = Field(None, max_length=5000)
    vehicle_number: Optional[str] = Field(None, max_length=100)
    driver_name: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[DeliveryNoteItemCreate]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def xor_parent(self) -> "DeliveryNoteCreate":
        has_lpo = self.customer_purchase_order_id is not None
        has_inv = self.invoice_id is not None
        if has_lpo == has_inv:
            raise ValueError(
                "Exactly one of customer_purchase_order_id or invoice_id is required"
            )
        if self.items:
            for item in self.items:
                line_lpo = item.customer_purchase_order_item_id is not None
                if line_lpo != has_lpo:
                    raise ValueError("Item parent must match the delivery-note header")
        return self


class DeliveryNoteUpdate(BaseModel):
    """Replace DRAFT header fields and optionally all lines."""

    model_config = ConfigDict(extra="forbid")

    warehouse_id: Optional[UUID] = None
    bin_id: Optional[UUID] = None
    delivery_date: Optional[date] = None
    shipping_address: Optional[str] = Field(None, max_length=5000)
    vehicle_number: Optional[str] = Field(None, max_length=100)
    driver_name: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[DeliveryNoteItemCreate]] = Field(None, min_length=1)


class DeliveryNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    customer_purchase_order_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    warehouse_id: UUID
    bin_id: Optional[UUID] = None
    dn_number: str
    status: DeliveryNoteStatus
    delivery_date: date
    shipping_address: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None
    confirmed_by: Optional[UUID] = None
    confirmed_at: Optional[datetime] = None
    items: List[DeliveryNoteItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class DeliveryNoteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    dn_number: str
    status: DeliveryNoteStatus
    delivery_date: date
    customer_purchase_order_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    warehouse_id: UUID
    created_at: datetime


class DeliveryNoteConfirmRequest(BaseModel):
    """Empty confirm body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")


class DeliveryNoteCancelRequest(BaseModel):
    """Optional cancel reason. CONFIRMED only."""

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500)
