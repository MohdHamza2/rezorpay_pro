from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
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


class SupplierProductCreate(BaseModel):
    """Link an existing product to this supplier (Item 2.4)."""

    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    supplier_sku: Optional[str] = Field(default=None, max_length=100)
    lead_time_days: Optional[int] = Field(default=None, ge=0)
    moq: Optional[Decimal] = Field(default=None, ge=0)

    @field_validator("supplier_sku", mode="before")
    @classmethod
    def strip_sku(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("supplier_sku must be non-empty")
            return stripped
        return value


class SupplierProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    supplier_id: uuid.UUID
    product_id: uuid.UUID
    supplier_sku: Optional[str]
    lead_time_days: Optional[int]
    moq: Optional[Decimal]
    created_at: datetime
