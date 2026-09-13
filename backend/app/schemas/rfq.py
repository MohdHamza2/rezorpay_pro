from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime

from app.models.rfq import (
    RFQType,
    RFQAwardMode,
    RFQEvalCriteria,
    RFQStatus,
    QuoteStatus,
    QuoteCompleteness,
    AwardStatus,
)


class RFQItemCreate(BaseModel):
    product_id: Optional[uuid.UUID] = None
    uom_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)
    is_mandatory: bool = True


class RFQCreate(BaseModel):
    rfq_type: RFQType = RFQType.STANDARD
    award_mode: RFQAwardMode = RFQAwardMode.SPLIT
    evaluation_criteria: RFQEvalCriteria = RFQEvalCriteria.LOWEST_LANDED_COST
    deadline: datetime
    sealed_until: Optional[datetime] = None
    currency: str = "AED"
    items: List[RFQItemCreate]


class RFQItemResponse(RFQItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    awarded_quantity: Decimal


class QuoteItemCreate(BaseModel):
    rfq_item_id: uuid.UUID
    quantity_available: Decimal = Field(..., ge=0)
    quoted_unit_price: Decimal = Field(..., ge=0)
    # UOM the supplier quoted in. Defaults to the RFQ line UOM at intake.
    uom_id: Optional[uuid.UUID] = None
    is_alternate: bool = False
    alternate_product_id: Optional[uuid.UUID] = None


class QuoteResponseCreate(BaseModel):
    supplier_id: uuid.UUID
    # Exchange rate converting quote_currency into the RFQ reference currency
    # (normalized = quoted_unit_price * exchange_rate / uom_factor).
    quote_currency: str = Field(default="AED", max_length=3)
    exchange_rate: Decimal = Field(default=Decimal("1.0"), gt=0)
    items: List[QuoteItemCreate] = Field(..., min_length=1)


class QuoteItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    response_id: uuid.UUID
    rfq_item_id: uuid.UUID
    is_alternate: bool
    alternate_product_id: Optional[uuid.UUID]
    quantity_available: Decimal
    quoted_unit_price: Decimal
    # Per-base-UOM normalized price, or None when no UOM conversion exists.
    normalized_unit_price: Optional[Decimal]
    uom_id: Optional[uuid.UUID]


class QuoteResponseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    revision_number: int
    status: QuoteStatus
    completeness: QuoteCompleteness
    quote_currency: str
    exchange_rate: Decimal
    normalized_total: Optional[Decimal]
    quote_items: List[QuoteItemResponse] = []


class ComparisonRow(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str = ""
    quote_item_id: uuid.UUID
    quoted_unit_price: Decimal
    # Per-base-UOM normalized price (discount factor is 1.0: quotes carry no
    # discount field in this wave; VAT excluded throughout).
    normalized_unit_price: Optional[Decimal]
    comparable: bool
    non_comparable_reason: Optional[str] = None
    is_lowest: bool = False


class ComparisonLineGroup(BaseModel):
    rfq_item_id: uuid.UUID
    requested_quantity: Decimal
    rows: List[ComparisonRow] = []


class ComparisonResponse(BaseModel):
    rfq_id: uuid.UUID
    currency: str
    lines: List[ComparisonLineGroup] = []


class AwardLineCreate(BaseModel):
    quote_item_id: uuid.UUID
    awarded_quantity: Decimal = Field(..., gt=0)
    deviation_reason: Optional[str] = None


class AwardCreate(BaseModel):
    supplier_id: uuid.UUID
    justification: Optional[str] = None
    lines: List[AwardLineCreate] = Field(..., min_length=1)


class AwardLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    award_id: uuid.UUID
    quote_item_id: uuid.UUID
    awarded_quantity: Decimal
    is_lowest_price: bool
    deviation_reason: Optional[str]


class AwardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    award_number: str
    total_awarded_value: Decimal
    status: AwardStatus
    justification: Optional[str]
    awarded_by: Optional[uuid.UUID]
    approved_by: Optional[uuid.UUID]
    award_lines: List[AwardLineResponse] = []


class GenerateSPOsRequest(BaseModel):
    # Target warehouse for every generated SPO (RFQs carry no warehouse).
    warehouse_id: uuid.UUID


class GenerateSPOsResponse(BaseModel):
    award_id: uuid.UUID
    spo_ids: List[uuid.UUID] = []


class RFQResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    rfq_number: str
    rfq_type: RFQType
    award_mode: RFQAwardMode
    evaluation_criteria: RFQEvalCriteria
    deadline: datetime
    sealed_until: Optional[datetime]
    currency: str
    status: RFQStatus
    created_at: datetime
    updated_at: datetime
    items: List[RFQItemResponse] = []
    responses: List[QuoteResponseResponse] = []
    awards: List[AwardResponse] = []
