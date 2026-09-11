"""AR aging report schemas — Wave 29 (Phase 6). Wave 30 item 1.5 adds PDC aggregates."""

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
    # AR PDC Outstanding — operational PDC instrument metric, not a balance due component
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


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
    # Per-invoice PDC outstanding aggregate (RECEIVED + DEPOSITED only)
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


class ArAgingDetailResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    invoices: list[ArAgingDetailRow]


class ArAgingCustomerRow(BaseModel):
    client: dict
    total_outstanding: Decimal
    buckets: CreditBuckets
    # Per-client PDC outstanding aggregate (RECEIVED + DEPOSITED only)
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


class ArAgingByCustomerResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    customers: list[ArAgingCustomerRow]
