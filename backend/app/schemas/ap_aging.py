"""AP aging report schemas — Wave 22 (Phase 4). Wave 30 item 1.5 adds PDC aggregates."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.clients import CreditBuckets


class ApAgingSummaryResponse(BaseModel):
    as_of: date
    supplier_count: int
    invoice_count: int
    total_outstanding: Decimal
    buckets: CreditBuckets
    # AP PDC Outstanding — operational PDC instrument metric, not a balance due component
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


class ApAgingDetailRow(BaseModel):
    supplier_id: UUID
    supplier_name: str
    supplier_invoice_id: UUID
    supplier_invoice_number: str
    invoice_date: date
    due_date: date
    days_overdue: int
    balance_due: Decimal
    bucket: str
    # Per-supplier-invoice PDC outstanding aggregate (RECEIVED + DEPOSITED only)
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


class ApAgingDetailResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    invoices: list[ApAgingDetailRow]


class ApAgingSupplierRow(BaseModel):
    supplier: dict
    total_outstanding: Decimal
    buckets: CreditBuckets
    # Per-supplier PDC outstanding aggregate (RECEIVED + DEPOSITED only)
    pdc_outstanding_count: int = 0
    pdc_outstanding_amount: Decimal = Decimal("0.00")


class ApAgingBySupplierResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    suppliers: list[ApAgingSupplierRow]
