"""
Standardized API response schemas.

All API responses follow a consistent format for easy frontend parsing.
"""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

# Generic type for typed responses
T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Standardized error detail."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(
        None, description="Field that caused the error, if applicable"
    )


# -----------------------------
# SUCCESS RESPONSE (GENERIC)
# -----------------------------
class SuccessResponse(BaseModel, Generic[T]):
    """Standardized success response wrapper."""

    success: bool = True
    data: T


# -----------------------------
# ERROR RESPONSE
# -----------------------------
class ErrorResponse(BaseModel):
    """Standardized error response wrapper."""

    success: bool = False
    error: ErrorDetail


# -----------------------------
# PAGINATION
# -----------------------------
class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number (1-based)")
    per_page: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_prev: bool = Field(..., description="Whether there are previous pages")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized paginated response."""

    success: bool = True
    data: List[T]
    pagination: PaginationMeta


# -----------------------------
# GENERIC API RESPONSE
# -----------------------------
class APIResponse(BaseModel, Generic[T]):
    """
    Generic API response wrapper.

    Usage:
        APIResponse[ClientResponse]
        APIResponse[List[ClientResponse]]
    """

    success: bool = True
    data: T


# -----------------------------
# ERROR CODES
# -----------------------------
class ErrorCode:
    """Standardized error codes."""

    INVALID_STATE = "INVALID_STATE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PAYMENT_EXCEEDS_BALANCE = "PAYMENT_EXCEEDS_BALANCE"
    RETURN_QTY_EXCEEDS_RECEIVED = "RETURN_QTY_EXCEEDS_RECEIVED"
    DEBIT_NOTE_EXCEEDS_BALANCE = "DEBIT_NOTE_EXCEEDS_BALANCE"
    DUPLICATE_INVOICE_NUMBER = "DUPLICATE_INVOICE_NUMBER"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    FTA_SEND_BLOCKED = "FTA_SEND_BLOCKED"
    CREDIT_HOLD = "CREDIT_HOLD"
    CREDIT_EXCEEDS_REMAINING = "CREDIT_EXCEEDS_REMAINING"
    DATE_RANGE_TOO_LONG = "DATE_RANGE_TOO_LONG"
    STATEMENT_TOO_LARGE = "STATEMENT_TOO_LARGE"
    NO_LIST_PRICE = "NO_LIST_PRICE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNSUPPORTED_DOCUMENT = "UNSUPPORTED_DOCUMENT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
