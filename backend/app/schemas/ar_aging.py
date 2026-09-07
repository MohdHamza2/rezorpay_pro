"""AR aging report schemas — Wave 29 (Phase 6)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.clients import CreditBuckets


class ArAgingSummaryResponse(BaseModel):
    as_of: date
    client_count: int
    invoice_count: int
    total_outstanding: Decimal
    buckets: CreditBuckets


class ArAgingDetailRow(BaseModel):
    client_id: UUID
    client_name: str
    invoice_id: UUID
    invoice_number: str
    issue_date: date
    due_date: date
    days_overdue: int
    balance_due: Decimal
    bucket: str


class ArAgingDetailResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    invoices: list[ArAgingDetailRow]


class ArAgingCustomerRow(BaseModel):
    client: dict
    total_outstanding: Decimal
    buckets: CreditBuckets


class ArAgingByCustomerResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    customers: list[ArAgingCustomerRow]
