from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    trn: Optional[str]
    logo_url: Optional[str]
    whatsapp_number: Optional[str]
    default_tax_rate: Decimal
    credit_limit_default: Decimal
    credit_warning_days: int
    credit_hold_days: int
    block_po_on_hold: bool
    block_do_on_hold: bool
    price_tolerance_percent: Decimal
    created_at: datetime
    updated_at: datetime


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    trn: Optional[str] = Field(None, max_length=50)
    logo_url: Optional[str] = Field(None, max_length=1000)
    whatsapp_number: Optional[str] = Field(None, max_length=50)
    default_tax_rate: Optional[Decimal] = Field(None, ge=0)
    credit_limit_default: Optional[Decimal] = Field(None, ge=0)
    credit_warning_days: Optional[int] = Field(None, ge=0)
    credit_hold_days: Optional[int] = Field(None, ge=0)
    block_po_on_hold: Optional[bool] = None
    block_do_on_hold: Optional[bool] = None
    price_tolerance_percent: Optional[Decimal] = Field(None, ge=0, le=100)
