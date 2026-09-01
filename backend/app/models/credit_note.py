import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.credit_note_event import CreditNoteEvent
    from app.models.credit_note_item import CreditNoteItem


class CreditNoteStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"


class CreditNoteReason(str, Enum):
    SALES_RETURN = "SALES_RETURN"
    INVOICE_ERROR = "INVOICE_ERROR"
    DISCOUNT = "DISCOUNT"
    GOODWILL = "GOODWILL"
    OTHER = "OTHER"


class CreditNote(SQLModel, table=True):
    __tablename__ = "credit_notes"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "credit_note_number", name="uq_workspace_credit_note_number"
        ),
        CheckConstraint("subtotal >= 0", name="check_cn_subtotal_positive"),
        CheckConstraint("tax_amount >= 0", name="check_cn_tax_amount_positive"),
        CheckConstraint("total_amount >= 0", name="check_cn_total_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)
    invoice_id: uuid.UUID = Field(foreign_key="invoices.id", nullable=False, index=True)

    credit_note_number: str = Field(max_length=50, index=True)
    status: CreditNoteStatus = Field(
        sa_column=Column(
            SQLEnum(CreditNoteStatus, name="creditnotestatus"),
            default=CreditNoteStatus.DRAFT,
            nullable=False,
        )
    )
    currency: str = Field(default="AED", max_length=3)
    issue_date: date = Field(sa_column=Column(Date, nullable=False))
    reason: CreditNoteReason = Field(
        sa_column=Column(
            SQLEnum(CreditNoteReason, name="creditnotereason"), nullable=False
        )
    )
    reason_notes: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    subtotal: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    original_invoice_number: Optional[str] = Field(default=None, max_length=50)
    original_issue_date: Optional[date] = Field(
        default=None, sa_column=Column(Date, nullable=True)
    )
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

    items: list["CreditNoteItem"] = Relationship(back_populates="credit_note")
    events: list["CreditNoteEvent"] = Relationship(back_populates="credit_note")
