from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime, date

from app.models.procurement import PRSourceType, PRDestinationType, PRPriority, PRMethod, PRStatus


class ProcurementRequestItemBase(BaseModel):
    product_id: uuid.UUID
    uom_id: uuid.UUID
    requested_quantity: Decimal = Field(..., gt=0)


class ProcurementRequestItemCreate(ProcurementRequestItemBase):
    pass


class ProcurementRequestItemResponse(ProcurementRequestItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    approved_quantity: Decimal
    ordered_quantity: Decimal
    cancelled_quantity: Decimal
    received_quantity: Decimal


class ProcurementRequestBase(BaseModel):
    source_type: PRSourceType
    destination_type: PRDestinationType
    customer_id: Optional[uuid.UUID] = None
    warehouse_id: Optional[uuid.UUID] = None
    priority: PRPriority = PRPriority.NORMAL
    procurement_method: PRMethod = PRMethod.DIRECT
    required_by_date: date
    notes: Optional[str] = None


class ProcurementRequestCreate(ProcurementRequestBase):
    items: List[ProcurementRequestItemCreate]


class ProcurementRequestResponse(ProcurementRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    request_number: str
    status: PRStatus
    requested_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: List[ProcurementRequestItemResponse] = []
