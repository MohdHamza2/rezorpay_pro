"""Supplier AP payment schemas — Wave 22 (Phase 4)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.payment import PaymentMethod, PaymentStatus

# AP posts only cash / bank transfer / cheque (PDC-to-supplier deferred).
AP_PAYMENT_METHODS = frozenset(
    {PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER, PaymentMethod.CHEQUE}
)


class SupplierPaymentCreate(BaseModel):
    supplier_invoice_id: UUID
    amount: Decimal = Field(..., gt=0)
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    payment_date: Optional[date] = None

    reference_number: Optional[str] = Field(None, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=255)

    @field_validator("payment_method")
    @classmethod
    def ap_method_only(cls, v: PaymentMethod) -> PaymentMethod:
        if v not in AP_PAYMENT_METHODS:
            raise ValueError("AP payments support only CASH, BANK_TRANSFER, CHEQUE")
        return v

    @field_validator("payment_date")
    @classmethod
    def payment_date_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v and v > date.today():
            raise ValueError("Payment date cannot be in the future")
        return v


class SupplierPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID
    supplier_invoice_id: UUID
    amount: Decimal
    payment_date: datetime
    payment_method: PaymentMethod
    status: PaymentStatus
    reference_number: Optional[str] = None
    bank_name: Optional[str] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class SupplierApBalanceResponse(BaseModel):
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    currency: str
