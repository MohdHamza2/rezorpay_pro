import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime, Date, Numeric, String, CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class PaymentMethod(str, Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    PDC = "PDC"
    CREDIT_CARD = "CREDIT_CARD"


class PDCStatus(str, Enum):
    RECEIVED = "RECEIVED"
    DEPOSITED = "DEPOSITED"
    CLEARED = "CLEARED"
    BOUNCED = "BOUNCED"
    RETURNED = "RETURNED"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_payment_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    invoice_id: uuid.UUID = Field(foreign_key="invoices.id", nullable=False, index=True)

    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    payment_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    payment_method: PaymentMethod = Field(default=PaymentMethod.BANK_TRANSFER)
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)

    # Method-Specific Fields
    reference_number: Optional[str] = Field(
        default=None, max_length=100
    )  # Cheque # or Txn ID
    bank_name: Optional[str] = Field(default=None, max_length=255)

    # PDC Specific Fields
    pdc_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    pdc_status: Optional[PDCStatus] = Field(default=None)

    # Optional legacy Gateway field
    gateway_transaction_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), unique=True, nullable=True, index=True),
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    invoice: "Invoice" = Relationship(back_populates="payments")
