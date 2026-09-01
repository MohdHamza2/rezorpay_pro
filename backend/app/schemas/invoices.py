"""
Invoice CRUD Schemas (WP-A FTA tax invoice).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.invoice import InvoiceStatus


class Currency(str, Enum):
    """Write/send lock: AED only (USD tax invoices are out of this WP)."""

    AED = "AED"


class InvoiceKind(str, Enum):
    STANDARD = "STANDARD"
    SIMPLIFIED = "SIMPLIFIED"


class InvoiceItemCreate(BaseModel):
    """Create/replace line. Description and unit_price optional iff product_id."""

    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = Field(None, min_length=1, max_length=500)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    product_id: Optional[UUID] = None
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def xor_discounts_and_adhoc_fields(self) -> "InvoiceItemCreate":
        if self.discount_percent > 0 and self.discount_amount > 0:
            raise ValueError(
                "Provide either discount_percent or discount_amount, not both"
            )
        if self.product_id is None:
            if not self.description:
                raise ValueError("description is required when product_id is omitted")
            if self.unit_price is None:
                raise ValueError("unit_price is required when product_id is omitted")
        return self


class InvoiceItemUpdate(BaseModel):
    """Partial item patch (unused by current replace-all PUT)."""

    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = Field(None, min_length=1, max_length=500)
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    product_id: Optional[UUID] = None
    discount_percent: Optional[Decimal] = Field(None, ge=0)
    discount_amount: Optional[Decimal] = Field(None, ge=0)


class InvoiceItemResponse(BaseModel):
    """Line with resolved tax, net, VAT, and gross."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
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
    customer_purchase_order_item_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class InvoiceBase(BaseModel):
    """Base invoice schema."""

    issue_date: date
    due_date: date
    currency: Currency = Currency.AED
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("due_date")
    @classmethod
    def due_date_after_issue_date(cls, v: date, info) -> date:
        """Validate due_date >= issue_date."""
        issue_date = info.data.get("issue_date")
        if issue_date and v < issue_date:
            raise ValueError("Due date must be on or after issue date")
        return v


class InvoiceCreate(InvoiceBase):
    """Schema for creating a new invoice."""

    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    supply_date: Optional[date] = None
    items: List[InvoiceItemCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def supply_not_after_issue(self) -> "InvoiceCreate":
        if self.supply_date is not None and self.supply_date > self.issue_date:
            raise ValueError("supply_date may not be after issue_date")
        return self


class InvoiceUpdate(BaseModel):
    """Schema for updating a draft invoice."""

    model_config = ConfigDict(extra="forbid")

    issue_date: Optional[date] = None
    supply_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[Currency] = None
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[InvoiceItemCreate]] = Field(None, min_length=1)

    @field_validator("due_date")
    @classmethod
    def due_date_after_issue_date(cls, v: Optional[date], info) -> Optional[date]:
        """Validate due_date >= issue_date."""
        if v is None:
            return v
        issue_date = info.data.get("issue_date")
        if issue_date and v < issue_date:
            raise ValueError("Due date must be on or after issue date")
        return v

    @model_validator(mode="after")
    def supply_not_after_issue(self) -> "InvoiceUpdate":
        if (
            self.supply_date is not None
            and self.issue_date is not None
            and self.supply_date > self.issue_date
        ):
            raise ValueError("supply_date may not be after issue_date")
        return self


class InvoiceResponse(InvoiceBase):
    """Schema for invoice response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    invoice_number: str
    status: InvoiceStatus
    supply_date: date
    invoice_kind: Optional[InvoiceKind] = None
    seller_trn_snapshot: Optional[str] = None
    seller_name_snapshot: Optional[str] = None
    seller_address_snapshot: Optional[str] = None
    buyer_trn_snapshot: Optional[str] = None
    buyer_name_snapshot: Optional[str] = None
    buyer_address_snapshot: Optional[str] = None
    quotation_id: Optional[UUID] = None
    customer_purchase_order_id: Optional[UUID] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_credited: Decimal = Decimal("0.00")
    balance_due: Decimal
    items: List[InvoiceItemResponse]
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class InvoiceListItem(BaseModel):
    """Schema for invoice list item (without full items)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    invoice_number: str
    status: InvoiceStatus
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    issue_date: date
    due_date: date
    created_at: datetime


class InvoiceListResponse(BaseModel):
    """Schema for list of invoices with pagination."""

    success: bool = True
    data: List[InvoiceListItem]
    pagination: dict


class InvoiceSendRequest(BaseModel):
    """Schema for sending an invoice."""

    recipient: Optional[str] = None


class InvoiceVoidRequest(BaseModel):
    """Schema for voiding an invoice."""

    reason: str = Field(..., min_length=5, max_length=500)
