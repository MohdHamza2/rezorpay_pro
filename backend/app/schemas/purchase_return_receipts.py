"""Purchase Return Receipt schemas — Wave 31 Item 2.8."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.purchase_return import (
    PurchaseReturnReceiptStatus,
    ReturnCondition,
)


class PurchaseReturnReceiptItemCreate(BaseModel):
    purchase_return_item_id: UUID
    quantity: Decimal = Field(gt=0)
    condition: ReturnCondition
    bin_id: Optional[UUID] = None
    notes: Optional[str] = None


class PurchaseReturnReceiptCreate(BaseModel):
    purchase_return_id: UUID
    warehouse_id: Optional[UUID] = None
    bin_id: Optional[UUID] = None
    receipt_date: date
    notes: Optional[str] = None
    items: List[PurchaseReturnReceiptItemCreate] = Field(min_length=1)


class PurchaseReturnReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_return_receipt_id: UUID
    purchase_return_item_id: UUID
    product_id: UUID
    quantity: Decimal
    condition: ReturnCondition
    bin_id: Optional[UUID] = None
    notes: Optional[str] = None


class PurchaseReturnReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    purchase_return_id: UUID
    warehouse_id: UUID
    bin_id: Optional[UUID] = None
    receipt_number: str
    receipt_date: date
    status: PurchaseReturnReceiptStatus
    received_by: UUID
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseReturnReceiptItemResponse] = []


class PurchaseReturnReceiptCounterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: UUID
    year: int
    last_number: int
