"""
Pydantic schemas for API request/response validation.

Organization:
- common.py: Standardized response wrappers and pagination
- clients.py: Client CRUD schemas
- invoices.py: Invoice CRUD schemas
- payments.py: Payment schemas
"""

from app.schemas.common import (
    SuccessResponse,
    ErrorResponse,
    PaginationMeta,
    PaginatedResponse,
    APIResponse,
)

__all__ = [
    "SuccessResponse",
    "ErrorResponse",
    "PaginationMeta",
    "PaginatedResponse",
    "APIResponse",
]
