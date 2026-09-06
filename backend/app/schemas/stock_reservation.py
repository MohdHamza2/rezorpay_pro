"""Stock reservation request/response schemas. Extra keys → 422."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock_reservation import ReservationStatus


class ReservationItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_purchase_order_item_id: UUID
    bin_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)


class StockReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_purchase_order_id: UUID
    warehouse_id: UUID
    items: List[ReservationItemCreate] = Field(..., min_length=1)


class ReservationCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500)


class ReservationExpireRequest(BaseModel):
    """Empty expire body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")


class StockReservationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reservation_id: UUID
    customer_purchase_order_item_id: UUID
    product_id: UUID
    warehouse_id: UUID
    bin_id: UUID
    quantity: Decimal
    quantity_consumed: Decimal
    remaining: Decimal = Decimal("0.00")
    status: ReservationStatus
    dispatched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class StockReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_purchase_order_id: UUID
    status: ReservationStatus
    expires_at: datetime
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    items: List[StockReservationItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ReservationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_purchase_order_id: UUID
    status: ReservationStatus
    expires_at: datetime
    warehouse_id: Optional[UUID] = None
    created_at: datetime


class ReservationExpireResponse(BaseModel):
    expired: int
