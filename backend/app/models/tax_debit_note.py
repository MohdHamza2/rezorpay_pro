import datetime
from enum import Enum
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.client import Client
    from app.models.invoice import Invoice
    from app.models.invoice_item import InvoiceItem

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship, SQLModel


class TaxDebitNoteCounter(SQLModel, table=True):
    __tablename__ = "tax_debit_note_counters"

    workspace_id: UUID = Field(primary_key=True, foreign_key="workspaces.id")
    year: int = Field(primary_key=True)
    last_sequence: int = Field(default=0)


class TaxDebitNoteStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"


class TaxDebitNoteReason(str, Enum):
    INVOICE_ERROR = "INVOICE_ERROR"
    PRICE_INCREASE = "PRICE_INCREASE"
    QTY_UNDERSTATED = "QTY_UNDERSTATED"
    ADDITIONAL_CHARGE = "ADDITIONAL_CHARGE"
    OTHER = "OTHER"


class TaxDebitNoteBase(SQLModel):
    debit_note_number: str = Field(
        sa_column=Column("debit_note_number", String(50), nullable=False)
    )
    status: str = Field(default=TaxDebitNoteStatus.DRAFT)
    currency: str = Field(default="AED", max_length=3)
    issue_date: datetime.date = Field(default_factory=datetime.date.today)
    reason: str
    reason_notes: Optional[str] = None
    subtotal: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    total_amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)

    original_invoice_number: Optional[str] = Field(default=None, max_length=50)
    original_issue_date: Optional[datetime.date] = None
    invoice_kind: Optional[str] = Field(default=None, max_length=20)

    # Seller Snapshot
    seller_name_snapshot: Optional[str] = None
    seller_trn_snapshot: Optional[str] = None
    seller_address_snapshot: Optional[str] = None

    # Buyer Snapshot
    buyer_name_snapshot: Optional[str] = None
    buyer_trn_snapshot: Optional[str] = None
    buyer_address_snapshot: Optional[str] = None


class TaxDebitNote(TaxDebitNoteBase, table=True):
    __tablename__ = "tax_debit_notes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspaces.id", index=True)
    client_id: UUID = Field(foreign_key="clients.id", index=True)
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)

    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    deleted_at: Optional[datetime.datetime] = Field(default=None, index=True)

    # Relationships
    workspace: "Workspace" = Relationship()  # type: ignore
    client: "Client" = Relationship()  # type: ignore
    invoice: "Invoice" = Relationship()  # type: ignore
    items: List["TaxDebitNoteItem"] = Relationship(
        back_populates="debit_note",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class TaxDebitNoteItemBase(SQLModel):
    product_id: Optional[UUID] = Field(default=None, foreign_key="products.id")
    uom_id: Optional[UUID] = Field(default=None, foreign_key="units_of_measure.id")
    sku_snapshot: Optional[str] = Field(default=None, max_length=100)
    description: str
    quantity: Decimal = Field(max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    tax_rate: Decimal = Field(max_digits=5, decimal_places=2)
    discount_percent: Decimal = Field(default=0, max_digits=5, decimal_places=2)
    discount_amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    line_net: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal = Field(max_digits=12, decimal_places=2)
    total_price: Decimal = Field(max_digits=12, decimal_places=2)


class TaxDebitNoteItem(TaxDebitNoteItemBase, table=True):
    __tablename__ = "tax_debit_note_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tax_debit_note_id: UUID = Field(foreign_key="tax_debit_notes.id", index=True)
    invoice_item_id: UUID = Field(foreign_key="invoice_items.id")

    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime.datetime = Field(
        default_factory=datetime.datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )

    debit_note: TaxDebitNote = Relationship(back_populates="items")
    invoice_item: "InvoiceItem" = Relationship()  # type: ignore
