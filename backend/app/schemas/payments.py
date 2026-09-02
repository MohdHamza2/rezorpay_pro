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

    @field_validator("payment_date")
    @classmethod
    def payment_date_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v and v > date.today():
            raise ValueError("Payment date cannot be in the future")
        return v


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    """Unused. PUT payments returns 405 and does not apply this body."""

    status: Optional[PaymentStatus] = None
    pdc_status: Optional[PDCStatus] = None


class PdcActionRequest(BaseModel):
    """Empty PDC transition body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")


class PaymentResponse(PaymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime


class BalanceDueResponse(BaseModel):
    """Invoice AR snapshot. Credits are not cash.

    amount_paid / total_paid: Σ SUCCESS payments only.
    amount_credited: issued credit notes.
    amount_debited: issued tax debit notes.
    balance_due: max(0, total − paid − credited + debited).
    """

    total_amount: Decimal
    amount_paid: Decimal
    amount_credited: Decimal = Decimal("0.00")
    amount_debited: Decimal = Decimal("0.00")
    total_paid: Decimal
    balance_due: Decimal
    currency: str


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
