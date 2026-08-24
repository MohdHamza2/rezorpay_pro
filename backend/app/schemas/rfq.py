from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime

from app.models.rfq import RFQType, RFQAwardMode, RFQEvalCriteria, RFQStatus


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
