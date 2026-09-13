from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.supplier_invoice import SupplierInvoiceStatus, MatchResult
from app.models.supplier_invoice_event import SupplierInvoiceEventType


class SupplierInvoiceItemBase(BaseModel):
    spo_item_id: Optional[uuid.UUID] = None
    grn_item_id: Optional[uuid.UUID] = None
    product_id: uuid.UUID
    description: str
    quantity: Decimal = Field(..., ge=0)
    uom_id: uuid.UUID
    unit_price: Decimal = Field(..., ge=0)
    discount_percent: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_rate: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(max_length=3)


class SupplierInvoiceItemCreate(SupplierInvoiceItemBase):
    pass


class SupplierInvoiceItemResponse(SupplierInvoiceItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_invoice_id: uuid.UUID
    match_status: MatchResult
    variance_quantity: Decimal
    variance_price: Decimal
    variance_tax: Decimal
    variance_notes: Optional[str]


class SupplierInvoiceBase(BaseModel):
    supplier_id: uuid.UUID
    supplier_invoice_number: str
    our_reference: Optional[str] = None
    invoice_date: datetime
    due_date: datetime
    currency: str = Field(max_length=3)
    subtotal: Decimal = Field(default=Decimal("0.00"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    primary_spo_id: Optional[uuid.UUID] = None


class SupplierInvoiceCreate(SupplierInvoiceBase):
    items: List[SupplierInvoiceItemCreate]


class SupplierInvoiceResponse(SupplierInvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    amount_paid: Decimal
    balance_due: Decimal
    status: SupplierInvoiceStatus
    three_way_match_status: MatchResult
    three_way_match_notes: Optional[str]
    document_url: Optional[str]
    ocr_job_id: Optional[str]
    ocr_extracted: bool
    received_at: datetime
    matched_at: Optional[datetime]
    approved_at: Optional[datetime]
    paid_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[SupplierInvoiceItemResponse]


class SupplierInvoiceDiscrepancyResolution(BaseModel):
    notes: str


class SupplierInvoiceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_invoice_id: uuid.UUID
    workspace_id: uuid.UUID
    event_type: SupplierInvoiceEventType
    previous_status: Optional[str]
    new_status: str
    actor_id: uuid.UUID
    metadata_log: dict
    created_at: datetime
