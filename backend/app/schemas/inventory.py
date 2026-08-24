from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime

from app.models.inventory import TransactionType


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
    available: Decimal  # Computed dynamically


class StockAdjustmentRequest(BaseModel):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    reference: str
