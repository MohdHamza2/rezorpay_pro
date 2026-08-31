from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdjustReason(str, Enum):
    DAMAGE = "DAMAGE"
    COUNT_CORRECTION = "COUNT_CORRECTION"
    LOSS = "LOSS"
    OPENING = "OPENING"
    OTHER = "OTHER"


class WarehouseBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    location: Optional[str] = None
    is_active: bool = True


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseResponse(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WarehouseBinBase(BaseModel):
    code: str = Field(..., max_length=50)
    barcode: Optional[str] = None
    is_active: bool = True


class WarehouseBinCreate(WarehouseBinBase):
    warehouse_id: Optional[uuid.UUID] = None


class WarehouseBinResponse(WarehouseBinBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    warehouse_id: uuid.UUID


class InventoryLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    on_hand: Decimal
    reserved: Decimal
    damaged: Decimal
    available: Decimal = Decimal("0.00")


class StockAdjustmentRequest(BaseModel):
    """ADMIN/OWNER stock back door. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    reason: AdjustReason
    notes: Optional[str] = Field(None, min_length=3)
    reference: Optional[str] = Field(None, min_length=3)

    @model_validator(mode="after")
    def notes_alias_and_nonzero(self) -> "StockAdjustmentRequest":
        notes = self.notes or self.reference
        if notes is None or len(notes.strip()) < 3:
            raise ValueError("notes is required (min 3 characters)")
        if self.quantity == 0:
            raise ValueError("quantity must not be zero")
        self.notes = notes
        return self
