import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

from app.models.spo import (
    ProcurementMethod, SPOStatus, SPODeliveryScheduleStatus,
    SPOAmendmentStatus, SPOAmendmentField
)

class SPOItemBase(BaseModel):
    product_id: uuid.UUID
    internal_sku: Optional[str] = None
    supplier_sku: Optional[str] = None
    description: str = Field(..., max_length=255)
    uom_id: uuid.UUID
    quantity_ordered: Decimal = Field(..., ge=0)
    unit_price: Decimal = Field(..., ge=0)
    discount_percent: Decimal = Field(Decimal("0"), ge=0)
    vat_rate: Decimal = Field(Decimal("0"), ge=0)
    expected_delivery_date: Optional[date] = None

class SPOItemCreate(SPOItemBase):
    rfq_award_line_id: Optional[uuid.UUID] = None
    procurement_request_item_id: Optional[uuid.UUID] = None
    line_number: int

class SPOItemResponse(SPOItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    spo_id: uuid.UUID
    line_number: int
    quantity_confirmed: Decimal
    quantity_backordered: Decimal
    quantity_received: Decimal
    quantity_accepted: Decimal
    quantity_damaged_rejected: Decimal
    quantity_invoiced: Decimal
    quantity_cancelled: Decimal
    open_quantity: Decimal
    vat_amount: Decimal
    total_price: Decimal
    price_amendment_pending: bool

class SPOCreate(BaseModel):
    supplier_id: uuid.UUID
    rfq_id: Optional[uuid.UUID] = None
    procurement_request_id: Optional[uuid.UUID] = None
    procurement_method: ProcurementMethod
    single_source_justification: Optional[str] = None
    supplier_reference: Optional[str] = None
    po_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    warehouse_id: uuid.UUID
    currency: str = "AED"
    payment_terms_days: int = 0
    delivery_terms: Optional[str] = None
    items: List[SPOItemCreate]

class SPOResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    supplier_id: uuid.UUID
    spo_number: str
    rfq_id: Optional[uuid.UUID]
    procurement_request_id: Optional[uuid.UUID]
    procurement_method: ProcurementMethod
    single_source_justification: Optional[str]
    supplier_reference: Optional[str]
    status: SPOStatus
    po_date: Optional[date]
    expected_delivery_date: Optional[date]
    warehouse_id: uuid.UUID
    currency: str
    payment_terms_days: int
    delivery_terms: Optional[str]
    subtotal: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    quantity_ordered_total: Decimal
    quantity_confirmed_total: Decimal
    quantity_backordered_total: Decimal
    has_open_amendment: bool
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    sent_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    closed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[SPOItemResponse] = []


class SPOAmendmentCreate(BaseModel):
    reason: str = Field(..., min_length=10)
    lines: List[dict]  # Define a more specific model for amendment lines if needed

class SPOAcknowledgeLine(BaseModel):
    quantity_confirmed: Decimal = Field(..., ge=0)
    unit_price: Decimal = Field(..., ge=0)

class SPOAcknowledgeReq(BaseModel):
    lines: dict[uuid.UUID, SPOAcknowledgeLine]

class SPODeliveryScheduleCreate(BaseModel):
    tranche_number: int
    scheduled_quantity: Decimal = Field(..., gt=0)
    scheduled_date: date
