import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column,
    Text,
    DateTime,
    Date,
    Numeric,
    CheckConstraint,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.client import Client
    from app.models.invoice_item import InvoiceItem
    from app.models.payment import Payment
    from app.models.invoice_event import InvoiceEvent


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "invoice_number", name="uq_workspace_invoice_number"
        ),
        CheckConstraint("subtotal >= 0", name="check_subtotal_positive"),
        CheckConstraint("tax_amount >= 0", name="check_tax_amount_positive"),
        CheckConstraint("total_amount >= 0", name="check_total_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)

    invoice_number: str = Field(max_length=50, index=True)
    currency: str = Field(default="AED", max_length=3)  # ISO 4217

    # Financial fields (all DECIMAL 12,2)
    subtotal: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    status: InvoiceStatus = Field(
        sa_column=Column(
            SQLEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False
        )
    )
    issue_date: date = Field(sa_column=Column(Date, nullable=False))
    supply_date: date = Field(sa_column=Column(Date, nullable=False))
    due_date: date = Field(sa_column=Column(Date, nullable=False))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    quotation_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="quotations.id", unique=True, index=True
    )
    customer_purchase_order_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="customer_purchase_orders.id",
        index=True,
    )

    # FTA snapshots — null on DRAFT; frozen at send
    invoice_kind: Optional[str] = Field(default=None, max_length=20)
    seller_trn_snapshot: Optional[str] = Field(default=None, max_length=15)
    seller_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    seller_address_snapshot: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    buyer_trn_snapshot: Optional[str] = Field(default=None, max_length=15)
    buyer_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    buyer_address_snapshot: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Relationships
    workspace: Optional["Workspace"] = Relationship(back_populates="invoices")
    client: Optional["Client"] = Relationship(back_populates="invoices")
    items: list["InvoiceItem"] = Relationship(back_populates="invoice")
    payments: list["Payment"] = Relationship(back_populates="invoice")
    events: list["InvoiceEvent"] = Relationship(back_populates="invoice")

    @property
    def amount_paid(self) -> Decimal:
        from app.models.payment import PaymentStatus

        if not getattr(self, "payments", None):
            return Decimal("0")
        return sum(
            (p.amount for p in self.payments if p.status == PaymentStatus.SUCCESS),
            Decimal("0"),
        )

    @property
    def balance_due(self) -> Decimal:
        return self.total_amount - self.amount_paid
