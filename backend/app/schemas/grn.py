import uuid
from decimal import Decimal
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.grn import GRNStatus
from app.models.landed_cost import LandedCostType, AllocationBasis


class LandedCostItemCreate(BaseModel):
    component_type: LandedCostType
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="AED", max_length=3)
    allocation_basis: AllocationBasis = Field(default=AllocationBasis.QUANTITY)
    allocation_factor: Optional[Decimal] = None


class GRNItemBase(BaseModel):
    spo_item_id: uuid.UUID
    spo_delivery_schedule_id: Optional[uuid.UUID] = None
    product_id: uuid.UUID
    internal_sku: str
    description: str
    uom_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    quantity_received: Decimal = Field(
        default=Decimal(0), max_digits=12, decimal_places=4
    )
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class GRNItemCreate(GRNItemBase):
    landed_cost_items: Optional[List[LandedCostItemCreate]] = None


class GRNItemResponse(GRNItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    grn_id: uuid.UUID
    quantity_ordered_snapshot: Decimal
    quantity_confirmed_snapshot: Decimal
    quantity_accepted: Decimal
    quantity_damaged: Decimal
    quantity_rejected: Decimal
    damage_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    inspected_by: Optional[uuid.UUID] = None
    inspected_at: Optional[datetime] = None
    # Landed cost fields (D-22)
    landed_cost_allocated: Decimal = Field(default=Decimal("0.00"))
    landed_cost_per_unit: Decimal = Field(default=Decimal("0.0000"))


class GRNBase(BaseModel):
    supplier_id: uuid.UUID
    spo_id: Optional[uuid.UUID] = None
    warehouse_id: uuid.UUID
    received_date: date
    delivery_reference: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None


class GRNCreate(GRNBase):
    items: List[GRNItemCreate] = []


class GRNUpdate(BaseModel):
    delivery_reference: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None


class GRNResponse(GRNBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    grn_number: str
    received_by: uuid.UUID
    status: GRNStatus
    stock_posted: bool
    created_at: datetime
    updated_at: datetime
    items: List[GRNItemResponse] = []


class GRNDispositionRequest(BaseModel):
    quantity_accepted: Decimal = Field(
        default=Decimal(0), max_digits=12, decimal_places=4
    )
    quantity_damaged: Decimal = Field(
        default=Decimal(0), max_digits=12, decimal_places=4
    )
    quantity_rejected: Decimal = Field(
        default=Decimal(0), max_digits=12, decimal_places=4
    )
    damage_reason: Optional[str] = None
    rejection_reason: Optional[str] = None


class GRNCancelRequest(BaseModel):
    reason: str = Field(..., min_length=10)
