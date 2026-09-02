"""Generated customer Account Statement JSON. WP-A — no PDF, no table."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, AliasChoices

from app.schemas.clients import CreditBuckets


class StatementDocType(str, Enum):
    OPENING = "OPENING"
    TAX_INVOICE = "TAX_INVOICE"
    PAYMENT = "PAYMENT"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    TAX_CREDIT_NOTE = "TAX_CREDIT_NOTE"
    TAX_DEBIT_NOTE = "TAX_DEBIT_NOTE"


DOC_TYPE_LABELS = {
    StatementDocType.OPENING: "Opening balance",
    StatementDocType.TAX_INVOICE: "Tax Invoice",
    StatementDocType.PAYMENT: "Payment",
    StatementDocType.PAYMENT_PENDING: "Payment (pending)",
    StatementDocType.TAX_CREDIT_NOTE: "Tax Credit Note",
    StatementDocType.TAX_DEBIT_NOTE: "Tax Debit Note",
}


class ArStatementClient(BaseModel):
    id: UUID
    name: str
    tax_id: Optional[str] = None
    address: Optional[str] = None


class ArStatementWorkspace(BaseModel):
    name: str
    trn: Optional[str] = None
    address: Optional[str] = None


class ArStatementLine(BaseModel):
    date: date
    doc_type: StatementDocType
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


class ArStatementTotals(BaseModel):
    billed: Decimal
    paid: Decimal
    credited: Decimal
    debited: Decimal
    pending: Decimal
    closing_running: Decimal


class ArStatementAging(BaseModel):
    as_of: date
    buckets: CreditBuckets


class ArStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    client: ArStatementClient
    workspace: ArStatementWorkspace
    currency: str
    from_: date = Field(
        validation_alias=AliasChoices("from", "from_"),
        serialization_alias="from",
    )
    to: date
    as_of: date
    opening_balance: Decimal
    lines: list[ArStatementLine]
    totals: ArStatementTotals
    amount_due_now: Decimal
    credit_balance: Decimal
    aging: ArStatementAging
