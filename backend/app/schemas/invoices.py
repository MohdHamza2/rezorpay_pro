"""
Invoice CRUD Schemas.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.invoice import InvoiceStatus


class Currency(str, Enum):
    """Supported currencies for MVP."""

    AED = "AED"  # UAE Dirham
    USD = "USD"  # US Dollar


class InvoiceItemBase(BaseModel):
    """Base invoice item schema."""

    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(..., gt=0)  # Must be > 0
    unit_price: Decimal = Field(..., ge=0)  # Must be >= 0
    tax_rate: Decimal = Field(default=0, ge=0)  # Must be >= 0


class InvoiceItemCreate(InvoiceItemBase):
    """Schema for creating an invoice item."""

    pass


class InvoiceItemUpdate(BaseModel):
    """Schema for updating an invoice item."""

    description: Optional[str] = Field(None, min_length=1, max_length=500)
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0)


class InvoiceItemResponse(InvoiceItemBase):
    """Schema for invoice item response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    total_price: Decimal
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

    client_id: UUID
    items: List[InvoiceItemCreate] = Field(
        ..., min_length=1
    )  # At least 1 item required


class InvoiceUpdate(BaseModel):
    """Schema for updating a draft invoice."""

    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[Currency] = None
    notes: Optional[str] = Field(None, max_length=5000)
    items: Optional[List[InvoiceItemCreate]] = None

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


class InvoiceResponse(InvoiceBase):
    """Schema for invoice response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    client_id: UUID
    invoice_number: str
    status: InvoiceStatus
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
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

    recipient: Optional[str] = None  # Email or phone for notification


class InvoiceVoidRequest(BaseModel):
    """Schema for voiding an invoice."""

    reason: str = Field(..., min_length=5, max_length=500)
