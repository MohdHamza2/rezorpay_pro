from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.stock_transfer import TransferStatus


class TransferItemCreate(BaseModel):
    """Bin optional — falls back to the first active bin of each warehouse."""

    product_id: uuid.UUID
    quantity: Decimal
    source_bin_id: Optional[uuid.UUID] = None
    destination_bin_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def quantity_positive(self) -> "TransferItemCreate":
        if self.quantity <= Decimal("0.00"):
            raise ValueError("quantity must be greater than zero")
        return self


class StockTransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    notes: Optional[str] = None
    items: List[TransferItemCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def distinct_warehouses(self) -> "StockTransferCreate":
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise ValueError("source and destination warehouses must differ")
        return self


class TransferReceiveItem(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal


class TransferReceiveRequest(BaseModel):
    """Optional per-line received quantities; default is the full quantity."""

    model_config = ConfigDict(extra="forbid")

    received: Optional[List[TransferReceiveItem]] = None


class TransferCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(default=None, max_length=500)


class StockTransferItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    received_quantity: Decimal
    source_bin_id: uuid.UUID
    destination_bin_id: uuid.UUID
    remaining: Decimal = Decimal("0.00")


class StockTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transfer_number: str
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    status: TransferStatus
    notes: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_by: uuid.UUID
    created_at: datetime
    items: List[StockTransferItemResponse] = []


class StockTransferListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transfer_number: str
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    status: TransferStatus
    notes: Optional[str] = None
    created_at: datetime
    item_count: int = 0
    total_quantity: Decimal = Decimal("0.00")
