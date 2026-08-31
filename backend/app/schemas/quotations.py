"""Quotation CRUD schemas (WP-A). Mirror invoice create lines."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.quotation import QuotationStatus
from app.schemas.invoices import Currency, InvoiceItemCreate


class QuotationItemCreate(InvoiceItemCreate):
    """Same shape as InvoiceItemCreate (qty, price, XOR discount, optional product)."""


class QuotationItemResponse(BaseModel):
    """Line with resolved tax, net, VAT, and gross."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quotation_id: UUID
    product_id: Optional[UUID] = None
    uom_id: Optional[UUID] = None
    sku_snapshot: Optional[str] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    line_net: Decimal
    tax_amount: Decimal
    total_price: Decimal
    created_at: datetime
    updated_at: datetime


class QuotationCreate(BaseModel):
    """Create a commercial quotation (not a tax invoice)."""

    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    quotation_date: Optional[date] = None
    valid_until: Optional[date] = None
    currency: Currency = Currency.AED
    notes: Optional[str] = Field(None, max_length=5000)
    items: List[QuotationItemCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def valid_until_not_before_date(self) -> "QuotationCreate":
        if (
            self.quotation_date is not None
            and self.valid_until is not None
            and self.valid_until < self.quotation_date
        ):
            raise ValueError("valid_until must be on or after quotation_date")
        return self


class QuotationUpdate(BaseModel):
    """Replace draft header fields and optionally all lines."""

    model_config = ConfigDict(extra="forbid")

    quotation_date: Optional[date] = None
    valid_until: Optional[date] = None
    currency: Optional[Currency] = None
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[QuotationItemCreate]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def valid_until_not_before_date(self) -> "QuotationUpdate":
        if (
            self.quotation_date is not None
            and self.valid_until is not None
            and self.valid_until < self.quotation_date
        ):
            raise ValueError("valid_until must be on or after quotation_date")
        return self


class QuotationResponse(BaseModel):
    """Quotation with lines. converted_invoice_id hydrated from invoices."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    quotation_number: str
    status: QuotationStatus
    currency: Currency
    quotation_date: date
    valid_until: date
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    items: List[QuotationItemResponse]
    converted_invoice_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class QuotationListItem(BaseModel):
    """List row without full line payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    quotation_number: str
    status: QuotationStatus
    total_amount: Decimal
    quotation_date: date
    valid_until: date
    converted_invoice_id: Optional[UUID] = None
    created_at: datetime


class QuotationSendRequest(BaseModel):
    """Empty send body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")


class QuotationRejectRequest(BaseModel):
    """Optional reject reason."""

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500)
