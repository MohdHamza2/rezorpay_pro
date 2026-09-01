"""Tax credit note request/response schemas. Extra keys → 422."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.credit_note import CreditNoteReason, CreditNoteStatus


class CreditNoteItemCreate(BaseModel):
    """Qty against a parent invoice line. Money fields optional; mismatch → 422."""

    model_config = ConfigDict(extra="forbid")

    invoice_item_id: UUID
    quantity: Decimal = Field(..., gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    discount_percent: Optional[Decimal] = Field(None, ge=0)
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=500)
    product_id: Optional[UUID] = None


class CreditNoteItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    credit_note_id: UUID
    invoice_item_id: UUID
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


class CreditNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    reason: CreditNoteReason
    reason_notes: Optional[str] = Field(None, max_length=5000)
    issue_date: Optional[date] = None
    items: List[CreditNoteItemCreate] = Field(..., min_length=1)


class CreditNoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[CreditNoteReason] = None
    reason_notes: Optional[str] = Field(None, max_length=5000)
    issue_date: Optional[date] = None
    items: Optional[List[CreditNoteItemCreate]] = Field(None, min_length=1)


class CreditNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    invoice_id: UUID
    credit_note_number: str
    status: CreditNoteStatus
    currency: str
    issue_date: date
    reason: CreditNoteReason
    reason_notes: Optional[str] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    original_invoice_number: Optional[str] = None
    original_issue_date: Optional[date] = None
    invoice_kind: Optional[str] = None
    seller_trn_snapshot: Optional[str] = None
    seller_name_snapshot: Optional[str] = None
    seller_address_snapshot: Optional[str] = None
    buyer_trn_snapshot: Optional[str] = None
    buyer_name_snapshot: Optional[str] = None
    buyer_address_snapshot: Optional[str] = None
    items: List[CreditNoteItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CreditNoteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    invoice_id: UUID
    credit_note_number: str
    status: CreditNoteStatus
    total_amount: Decimal
    issue_date: date
    created_at: datetime


class CreditNoteIssueRequest(BaseModel):
    """Empty issue body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")
