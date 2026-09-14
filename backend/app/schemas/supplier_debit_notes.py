"""Supplier debit note schemas — Wave 23 (Phase 4)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.supplier_debit_note import SupplierDebitNoteStatus
from app.services.line_money import money


class SupplierDebitNoteCreate(BaseModel):
    supplier_id: UUID
    issue_date: date
    subtotal: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_amount: Decimal = Field(default=Decimal("0.00"), gt=0)
    amount: Optional[Decimal] = Field(default=None, ge=0)
    reason: Optional[str] = None

    def model_post_init(self, __context):
        if self.amount is not None:
            self.total_amount = money(self.amount)
        if self.subtotal == Decimal("0.00") and self.vat_amount == Decimal("0.00"):
            self.subtotal = (
                money(self.total_amount * Decimal("100") / Decimal("105"))
                if self.total_amount
                else Decimal("0.00")
            )
            self.vat_amount = money(self.total_amount - self.subtotal)


class SupplierDebitNoteApplyRequest(BaseModel):
    supplier_invoice_id: UUID


class SupplierDebitNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID
    purchase_return_id: Optional[UUID] = None
    dn_number: str
    amount: Decimal
    subtotal: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    status: SupplierDebitNoteStatus
    source_type: str
    issue_date: date
    applied_invoice_id: Optional[UUID] = None
    reason: Optional[str] = None
    created_by: UUID
    applied_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
