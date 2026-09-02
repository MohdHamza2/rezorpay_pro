from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tax_debit_note import TaxDebitNoteStatus, TaxDebitNoteReason


class TaxDebitNoteItemCreate(BaseModel):
    invoice_item_id: UUID
    quantity: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    # The following are optional. If provided, they must match the invoice line
    unit_price: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2)
    tax_rate: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    discount_percent: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)


class TaxDebitNoteCreate(BaseModel):
    invoice_id: UUID
    reason: TaxDebitNoteReason
    reason_notes: Optional[str] = None
    issue_date: Optional[date] = None
    items: List[TaxDebitNoteItemCreate] = Field(..., min_length=1)


class TaxDebitNoteUpdate(BaseModel):
    # Only allowed in DRAFT
    reason: Optional[TaxDebitNoteReason] = None
    reason_notes: Optional[str] = None
    issue_date: Optional[date] = None
    items: Optional[List[TaxDebitNoteItemCreate]] = Field(None, min_length=1)


class TaxDebitNoteItemResponse(BaseModel):
    id: UUID
    tax_debit_note_id: UUID
    invoice_item_id: UUID
    product_id: Optional[UUID] = None
    internal_sku: Optional[str] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    discount_percent: Decimal
    tax_amount: Decimal
    total_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class TaxDebitNoteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    client_id: UUID
    invoice_id: UUID
    debit_note_number: str
    status: TaxDebitNoteStatus
    currency: str
    issue_date: date
    reason: TaxDebitNoteReason
    reason_notes: Optional[str]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    original_invoice_number: Optional[str]
    original_issue_date: Optional[date]
    invoice_kind: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaxDebitNoteDetailResponse(TaxDebitNoteResponse):
    items: List[TaxDebitNoteItemResponse]

    # Seller Snapshot
    seller_name: Optional[str]
    seller_trn: Optional[str]
    seller_address: Optional[str]

    # Buyer Snapshot
    buyer_name: Optional[str]
    buyer_trn: Optional[str]
    buyer_address: Optional[str]
