"""Wave 28 — UAE VAT Compliance Pack export response schemas.

Read-only report. Row models mirror the CSV columns exactly so `format=json`
returns the same aggregates/datasets as the ZIP (addendum §3/§5).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VatSalesInvoiceRow(BaseModel):
    invoice_number: str
    issue_date: date
    supply_date: date
    due_date: date
    invoice_kind: Optional[str]
    status: str
    currency: str
    client_name: Optional[str]
    client_trn: Optional[str]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    seller_trn: Optional[str]


class VatInvoiceLineRow(BaseModel):
    invoice_number: str
    description: str
    sku_snapshot: Optional[str]
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    discount_amount: Decimal
    line_net: Decimal
    tax_amount: Decimal
    total_price: Decimal


class VatCreditNoteRow(BaseModel):
    credit_note_number: str
    issue_date: date
    original_invoice_number: Optional[str]
    reason: str
    status: str
    client_name: Optional[str]
    client_trn: Optional[str]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class VatTaxDebitNoteRow(BaseModel):
    debit_note_number: str
    issue_date: date
    original_invoice_number: Optional[str]
    reason: str
    status: str
    client_name: Optional[str]
    client_trn: Optional[str]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class VatPurchaseInvoiceRow(BaseModel):
    supplier_invoice_number: str
    invoice_date: date
    supplier_name: Optional[str]
    supplier_trn: Optional[str]
    currency: str
    subtotal: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    status: str


class VatSummaryRow(BaseModel):
    direction: str
    tax_rate: Decimal
    count: int
    taxable_amount: Decimal
    vat_amount: Decimal


class VatManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generator: str
    version: str
    generated_at: datetime
    period: dict[str, str] = Field(default_factory=dict)
    org: dict[str, str] = Field(default_factory=dict)
    currency: str
    warnings: dict[str, List[str]] = Field(default_factory=dict)
    summary: dict[str, str] = Field(default_factory=dict)
    files: List[str] = Field(default_factory=list)
    excluded: dict[str, str] = Field(default_factory=dict)


class VatComplianceJsonResponse(BaseModel):
    """`format=json` payload: manifest + the six tabular datasets."""

    manifest: VatManifest
    sales_invoices: List[VatSalesInvoiceRow]
    invoice_lines: List[VatInvoiceLineRow]
    credit_notes: List[VatCreditNoteRow]
    tax_debit_notes: List[VatTaxDebitNoteRow]
    purchase_invoices: List[VatPurchaseInvoiceRow]
    vat_summary: List[VatSummaryRow]
