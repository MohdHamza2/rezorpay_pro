from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.payment import PaymentMethod, PaymentStatus, PDCStatus


class PaymentBase(BaseModel):
    amount: Decimal = Field(..., gt=0)
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    payment_date: Optional[date] = None
    
    reference_number: Optional[str] = Field(None, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=255)
    
    pdc_date: Optional[date] = None
    pdc_status: Optional[PDCStatus] = None
    
    gateway_transaction_id: Optional[str] = Field(None, max_length=255)
    
    @field_validator('payment_date')
    @classmethod
    def payment_date_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v and v > date.today():
            raise ValueError('Payment date cannot be in the future')
        return v

class PaymentCreate(PaymentBase):
    pass

class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    pdc_status: Optional[PDCStatus] = None

class PaymentResponse(PaymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime


class BalanceDueResponse(BaseModel):
    total_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    currency: str

class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
