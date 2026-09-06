"""Supplier debit note schemas — Wave 23 (Phase 4)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.supplier_debit_note import SupplierDebitNoteStatus


class SupplierDebitNoteCreate(BaseModel):
    supplier_id: UUID
    issue_date: date
    amount: Decimal = Field(gt=0)
    reason: Optional[str] = None


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
