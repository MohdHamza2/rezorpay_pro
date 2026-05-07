"""
Payment Schemas.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.payment import PaymentGateway, PaymentStatus


class PaymentBase(BaseModel):
    """Base payment schema."""
    amount: Decimal = Field(..., gt=0)  # Must be > 0
    gateway: PaymentGateway = PaymentGateway.MANUAL
    gateway_transaction_id: Optional[str] = Field(None, max_length=255)
    payment_date: Optional[date] = None
    
    @field_validator('payment_date')
    @classmethod
    def payment_date_not_future(cls, v: Optional[date]) -> Optional[date]:
        """Validate payment_date <= today."""
        if v and v > date.today():
            raise ValueError('Payment date cannot be in the future')
        return v


class PaymentCreate(PaymentBase):
    """
    Schema for creating a payment.
    
    Requires Idempotency-Key header in request.
    """
    pass


class PaymentResponse(PaymentBase):
    """Schema for payment response."""
    id: UUID
    invoice_id: UUID
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Schema for list of payments."""
    success: bool = True
    data: list[PaymentResponse]
    pagination: dict


class BalanceDueResponse(BaseModel):
    """Schema for balance due response."""
    success: bool = True
    total_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    currency: str
