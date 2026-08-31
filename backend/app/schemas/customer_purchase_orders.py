"""LPO request/response schemas. Extra keys → 422."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.customer_purchase_order import CustomerPurchaseOrderStatus
from app.models.invoice import InvoiceStatus
from app.schemas.invoices import Currency, InvoiceItemCreate


class CustomerPurchaseOrderItemCreate(InvoiceItemCreate):
    """Same shape as quotation/invoice line create."""


class CustomerPurchaseOrderItemResponse(BaseModel):
    """Line with ordered vs invoiced qty."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_purchase_order_id: UUID
    product_id: Optional[UUID] = None
    uom_id: Optional[UUID] = None
    sku_snapshot: Optional[str] = None
    description: str
    quantity: Decimal
    quantity_invoiced: Decimal
    quantity_remaining: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    line_net: Decimal
    tax_amount: Decimal
    total_price: Decimal
    created_at: datetime
    updated_at: datetime


class LinkedInvoiceSummary(BaseModel):
    """Countable invoice linked to an LPO."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_number: str
    status: InvoiceStatus
    total_amount: Decimal


class CustomerPurchaseOrderCreate(BaseModel):
    """Manual DRAFT LPO (no quotation_id)."""

    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    customer_po_number: Optional[str] = Field(None, max_length=100)
    lpo_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    currency: Currency = Currency.AED
    notes: Optional[str] = Field(None, max_length=5000)
    items: List[CustomerPurchaseOrderItemCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def delivery_not_before_lpo_date(self) -> "CustomerPurchaseOrderCreate":
        if (
            self.lpo_date is not None
            and self.expected_delivery_date is not None
            and self.expected_delivery_date < self.lpo_date
        ):
            raise ValueError("expected_delivery_date must be on or after lpo_date")
        return self


class CustomerPurchaseOrderUpdate(BaseModel):
    """Replace DRAFT header fields and optionally all lines."""

    model_config = ConfigDict(extra="forbid")

    customer_po_number: Optional[str] = Field(None, max_length=100)
    lpo_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    currency: Optional[Currency] = None
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[CustomerPurchaseOrderItemCreate]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def delivery_not_before_lpo_date(self) -> "CustomerPurchaseOrderUpdate":
        if (
            self.lpo_date is not None
            and self.expected_delivery_date is not None
            and self.expected_delivery_date < self.lpo_date
        ):
            raise ValueError("expected_delivery_date must be on or after lpo_date")
        return self


class CustomerPurchaseOrderResponse(BaseModel):
    """LPO with lines and countable invoices."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    quotation_id: Optional[UUID] = None
    lpo_number: str
    customer_po_number: Optional[str] = None
    status: CustomerPurchaseOrderStatus
    currency: Currency
    lpo_date: date
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    items: List[CustomerPurchaseOrderItemResponse]
    invoices: List[LinkedInvoiceSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CustomerPurchaseOrderListItem(BaseModel):
    """List row without full line payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    lpo_number: str
    customer_po_number: Optional[str] = None
    status: CustomerPurchaseOrderStatus
    total_amount: Decimal
    lpo_date: date
    expected_delivery_date: Optional[date] = None
    quotation_id: Optional[UUID] = None
    created_at: datetime


class CustomerPurchaseOrderReceiveRequest(BaseModel):
    """Empty receive body. Extra keys → 422."""

    model_config = ConfigDict(extra="forbid")


class CustomerPurchaseOrderCancelRequest(BaseModel):
    """Optional cancel reason. RECEIVED only."""

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500)


class LpoInvoiceLineRequest(BaseModel):
    """Slice of one LPO line onto a DRAFT invoice."""

    model_config = ConfigDict(extra="forbid")

    customer_purchase_order_item_id: UUID
    quantity: Decimal = Field(..., gt=0)


class LpoInvoiceCreateRequest(BaseModel):
    """Convert remaining LPO qty into a DRAFT tax invoice."""

    model_config = ConfigDict(extra="forbid")

    items: Optional[List[LpoInvoiceLineRequest]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    issue_date: Optional[date] = None
    supply_date: Optional[date] = None
    due_date: Optional[date] = None

    @model_validator(mode="after")
    def supply_not_after_issue(self) -> "LpoInvoiceCreateRequest":
        if (
            self.supply_date is not None
            and self.issue_date is not None
            and self.supply_date > self.issue_date
        ):
            raise ValueError("supply_date may not be after issue_date")
        return self


class QuotationConvertToLpoRequest(BaseModel):
    """Optional LPO header fields when converting an ACCEPTED quote."""

    model_config = ConfigDict(extra="forbid")

    customer_po_number: Optional[str] = Field(None, max_length=100)
    lpo_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=5000)

    @model_validator(mode="after")
    def delivery_not_before_lpo_date(self) -> "QuotationConvertToLpoRequest":
        if (
            self.lpo_date is not None
            and self.expected_delivery_date is not None
            and self.expected_delivery_date < self.lpo_date
        ):
            raise ValueError("expected_delivery_date must be on or after lpo_date")
        return self
