"""Generated supplier AP statement JSON (the AP ledger). Wave 22 — query, no table."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, AliasChoices

from app.schemas.clients import CreditBuckets


class SupplierStatementDocType(str, Enum):
    OPENING = "OPENING"
    SUPPLIER_INVOICE = "SUPPLIER_INVOICE"
    SUPPLIER_DEBIT_NOTE = "SUPPLIER_DEBIT_NOTE"
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
    SUPPLIER_PAYMENT_PENDING = "SUPPLIER_PAYMENT_PENDING"


DOC_TYPE_LABELS = {
    SupplierStatementDocType.OPENING: "Opening balance",
    SupplierStatementDocType.SUPPLIER_INVOICE: "Supplier Invoice",
    SupplierStatementDocType.SUPPLIER_DEBIT_NOTE: "Supplier debit note",
    SupplierStatementDocType.SUPPLIER_PAYMENT: "Payment",
    SupplierStatementDocType.SUPPLIER_PAYMENT_PENDING: "Payment (pending)",
}


class SupplierStatementSupplier(BaseModel):
    id: UUID
    name: str
    supplier_code: str


class SupplierStatementWorkspace(BaseModel):
    name: str
    trn: Optional[str] = None
    address: Optional[str] = None


class SupplierStatementLine(BaseModel):
    date: date
    doc_type: SupplierStatementDocType
    doc_type_label: str
    number: Optional[str] = None
    reference: Optional[str] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    cleared_cash: Optional[bool] = None
    pending_amount: Decimal
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


class SupplierStatementTotals(BaseModel):
    billed: Decimal
    paid: Decimal
    credited: Decimal
    pending: Decimal
    closing_running: Decimal


class SupplierStatementAging(BaseModel):
    as_of: date
    buckets: CreditBuckets


class SupplierStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    supplier: SupplierStatementSupplier
    workspace: SupplierStatementWorkspace
    currency: str
    from_: date = Field(
        validation_alias=AliasChoices("from", "from_"),
        serialization_alias="from",
    )
    to: date
    as_of: date
    opening_balance: Decimal
    lines: list[SupplierStatementLine]
    totals: SupplierStatementTotals
    amount_due_now: Decimal
    aging: SupplierStatementAging
