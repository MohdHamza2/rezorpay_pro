"""BI / analytics schemas — Wave 30 (Phase 6 continuation).

Shared row shapes for the three report families:
- revenue (invoiced totals by period bucket),
- cashflow (AR receipts vs AP payments by period bucket),
- sales by customer / by product.

All money values are `Decimal` (12,2). Period buckets are string keys:
`YYYY-MM-DD` (day), ISO `YYYY-W##` (week), `YYYY-MM` (month).
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Interval = Literal["day", "week", "month"]


class RevenueRow(BaseModel):
    period: str
    invoice_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class RevenueReport(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    interval: Interval
    currency: str
    rows: list[RevenueRow]

    model_config = {"populate_by_name": True}


class SalesByCustomerRow(BaseModel):
    client_id: UUID
    client_name: str
    invoice_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class SalesByCustomerReport(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    currency: str
    rows: list[SalesByCustomerRow]

    model_config = {"populate_by_name": True}


class SalesByProductRow(BaseModel):
    product_id: Optional[UUID]
    product_name: str
    sku: str
    quantity: Decimal
    line_net: Decimal
    tax_amount: Decimal
    total_price: Decimal


class SalesByProductReport(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    currency: str
    rows: list[SalesByProductRow]

    model_config = {"populate_by_name": True}


class CashflowRow(BaseModel):
    period: str
    inflows: Decimal
    outflows: Decimal
    net: Decimal


class CashflowReport(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    interval: Interval
    currency: str
    non_aed_payments_excluded: int = 0
    rows: list[CashflowRow]

    model_config = {"populate_by_name": True}
