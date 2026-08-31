"""
Client CRUD Schemas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models.credit_status_event import CreditStatus

ALLOWED_PAYMENT_TERMS = frozenset({0, 30, 45, 60})


def _validate_terms(value: int) -> int:
    if value not in ALLOWED_PAYMENT_TERMS:
        raise ValueError("payment_terms_days must be 0, 30, 45, or 60")
    return value


class ClientBase(BaseModel):
    """Base client schema with common fields."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    tax_id: Optional[str] = Field(
        None,
        max_length=50,
        validation_alias=AliasChoices("tax_id", "trn"),
    )


class ClientCreate(ClientBase):
    """Schema for creating a new client."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: int = Field(default=0)

    @field_validator("payment_terms_days")
    @classmethod
    def payment_terms_allowlist(cls, value: int) -> int:
        return _validate_terms(value)


class ClientUpdate(BaseModel):
    """Schema for updating a client."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    tax_id: Optional[str] = Field(
        None,
        max_length=50,
        validation_alias=AliasChoices("tax_id", "trn"),
    )
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int] = None

    @field_validator("payment_terms_days")
    @classmethod
    def payment_terms_allowlist(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        return _validate_terms(value)


class ClientResponse(ClientBase):
    """Schema for client response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    credit_limit: Optional[Decimal] = None
    payment_terms_days: int = 0
    credit_status: CreditStatus = CreditStatus.ACTIVE
    effective_credit_limit: Decimal = Decimal("0.00")
    exposure: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CreditBuckets(BaseModel):
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_90_plus: Decimal


class ClientCreditResponse(BaseModel):
    credit_status: CreditStatus
    credit_limit: Optional[Decimal]
    effective_credit_limit: Decimal
    payment_terms_days: int
    exposure: Decimal
    oldest_overdue_days: Optional[int] = None
    buckets: CreditBuckets


class ClientListResponse(BaseModel):
    """Schema for list of clients with pagination."""

    success: bool = True
    data: list[ClientResponse]
    pagination: dict
