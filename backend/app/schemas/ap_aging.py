"""AP aging report schemas — Wave 22 (Phase 4)."""

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


class ApAgingDetailResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    invoices: list[ApAgingDetailRow]


class ApAgingSupplierRow(BaseModel):
    supplier: dict
    total_outstanding: Decimal
    buckets: CreditBuckets


class ApAgingBySupplierResponse(BaseModel):
    as_of: date
    total_outstanding: Decimal
    buckets: CreditBuckets
    suppliers: list[ApAgingSupplierRow]
