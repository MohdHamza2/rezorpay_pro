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
    Numeric,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.quotation_event import QuotationEvent
    from app.models.quotation_item import QuotationItem


class QuotationStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"


class Quotation(SQLModel, table=True):
    __tablename__ = "quotations"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "quotation_number", name="uq_workspace_quotation_number"
        ),
        CheckConstraint("subtotal >= 0", name="check_quotation_subtotal_positive"),
        CheckConstraint("tax_amount >= 0", name="check_quotation_tax_amount_positive"),
        CheckConstraint("total_amount >= 0", name="check_quotation_total_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    client_id: uuid.UUID = Field(foreign_key="clients.id", nullable=False, index=True)

    quotation_number: str = Field(max_length=50, index=True)
    currency: str = Field(default="AED", max_length=3)

    subtotal: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    tax_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    status: QuotationStatus = Field(
        sa_column=Column(
            SQLEnum(QuotationStatus),
            default=QuotationStatus.DRAFT,
            nullable=False,
        )
    )
    quotation_date: date = Field(sa_column=Column(Date, nullable=False))
    valid_until: date = Field(sa_column=Column(Date, nullable=False))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    rejection_reason: Optional[str] = Field(
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

    items: list["QuotationItem"] = Relationship(back_populates="quotation")
    events: list["QuotationEvent"] = Relationship(back_populates="quotation")
