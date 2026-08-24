from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime


class SupplierBase(BaseModel):
    supplier_code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    trade_name: Optional[str] = None
    trn: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    payment_terms: str = "CASH"
    status: str = "ACTIVE"
    rating: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
