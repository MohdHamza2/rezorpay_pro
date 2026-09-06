from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.stock_count import StockCountStatus


class StockCountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: uuid.UUID
    notes: Optional[str] = None


class CountRecordRequest(BaseModel):
    """Record the physical count for one stock count item line."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    counted_quantity: Decimal
    notes: Optional[str] = None

    @model_validator(mode="after")
    def counted_nonnegative(self) -> "CountRecordRequest":
        if self.counted_quantity < Decimal("0.00"):
            raise ValueError("counted_quantity must not be negative")
        return self


class StockCountItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    bin_id: uuid.UUID
    expected_quantity: Decimal
    counted_quantity: Optional[Decimal] = None
    requires_approval: bool
    approved: bool
    variance: Decimal = Decimal("0.00")


class StockCountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    count_number: str
    warehouse_id: uuid.UUID
    status: StockCountStatus
    notes: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    reconciled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_by: uuid.UUID
    created_at: datetime
    items: List[StockCountItemResponse] = []


class StockCountListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    count_number: str
    warehouse_id: uuid.UUID
    status: StockCountStatus
    notes: Optional[str] = None
    created_at: datetime
    item_count: int = 0
    count_in_progress: int = 0
    flagged_lines: int = 0
