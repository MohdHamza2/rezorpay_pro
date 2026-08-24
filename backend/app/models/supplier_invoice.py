import enum
import uuid
from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint
from sqlalchemy import Column, DateTime, Numeric, func


class SupplierInvoiceStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PENDING_MATCHING = "PENDING_MATCHING"
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    APPROVED = "APPROVED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class MatchResult(str, enum.Enum):
    NOT_CHECKED = "NOT_CHECKED"
    PASSED = "PASSED"
    FAILED_QTY = "FAILED_QTY"
    FAILED_PRICE = "FAILED_PRICE"
    FAILED_TAX = "FAILED_TAX"
    FAILED_SUPPLIER = "FAILED_SUPPLIER"
    FAILED_CURRENCY = "FAILED_CURRENCY"
    FAILED_PRODUCT = "FAILED_PRODUCT"
    FAILED_UOM = "FAILED_UOM"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    UNRECEIVED_ITEMS = "UNRECEIVED_ITEMS"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class SupplierInvoice(SQLModel, table=True):
    __tablename__ = "supplier_invoices"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "supplier_id",
            "supplier_invoice_number",
            name="uq_workspace_supplier_invoice_num",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", index=True)

    supplier_invoice_number: str = Field(index=True)
    our_reference: Optional[str] = Field(default=None)

    invoice_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    due_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    currency: str = Field(max_length=3)

    # All monetary fields use Decimal(12,2) per CLAUDE.md Rule 4
    subtotal: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2)))
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    vat_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    total_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    amount_paid: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    balance_due: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )

    status: SupplierInvoiceStatus = Field(default=SupplierInvoiceStatus.RECEIVED)

    three_way_match_status: MatchResult = Field(default=MatchResult.NOT_CHECKED)
    three_way_match_notes: Optional[str] = Field(default=None)

    document_url: Optional[str] = Field(default=None)
    ocr_job_id: Optional[str] = Field(default=None)
    ocr_extracted: bool = Field(default=False)

    primary_spo_id: Optional[uuid.UUID] = Field(
        foreign_key="supplier_purchase_orders.id", nullable=True
    )

    received_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    matched_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    approved_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    paid_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        )
    )

    items: List["SupplierInvoiceItem"] = Relationship(back_populates="supplier_invoice")


class SupplierInvoiceItem(SQLModel, table=True):
    __tablename__ = "supplier_invoice_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_invoice_id: uuid.UUID = Field(
        foreign_key="supplier_invoices.id", index=True
    )

    spo_item_id: Optional[uuid.UUID] = Field(
        foreign_key="supplier_purchase_order_items.id", nullable=True
    )
    grn_item_id: Optional[uuid.UUID] = Field(foreign_key="grn_items.id", nullable=True)

    product_id: uuid.UUID = Field(foreign_key="products.id")
    description: str

    # Quantity uses Decimal(12,4) for precision (matches GRN convention)
    quantity: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(12, 4)))
    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id")

    # Monetary fields use Decimal(12,2) per CLAUDE.md Rule 4
    unit_price: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    discount_percent: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2))
    )
    vat_rate: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(5, 2)))
    vat_amount: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    total_price: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )

    currency: str = Field(max_length=3)

    match_status: MatchResult = Field(default=MatchResult.NOT_CHECKED)
    # Variance fields also Decimal for precise comparison
    variance_quantity: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(12, 4))
    )
    variance_price: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )
    variance_tax: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(12, 2))
    )

    variance_notes: Optional[str] = Field(default=None)

    supplier_invoice: SupplierInvoice = Relationship(back_populates="items")
