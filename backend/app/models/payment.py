import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime, Numeric, String, CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class PaymentGateway(str, Enum):
    RAZORPAY = "razorpay"
    STRIPE = "stripe"
    MANUAL = "manual"


class PaymentStatus(str, Enum):
    """
    Payment status enum.
    
    Only SUCCESS payments count toward invoice balance.
    FAILED payments are kept for audit trail but don't affect balance.
    """
    PENDING = "pending"      # Gateway processing
    SUCCESS = "success"      # ✅ Counts toward balance
    FAILED = "failed"        # ❌ Audit trail only
    CANCELLED = "cancelled"  # ❌ Cancelled before completion
    REFUNDED = "refunded"    # ❌ Subtract from total (future use)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    
    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_payment_amount_positive"),
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    invoice_id: uuid.UUID = Field(foreign_key="invoices.id", nullable=False, index=True)
    
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    gateway: Optional[PaymentGateway] = Field(default=None)
    # Nullable only for manual; backend enforces NOT NULL for external gateways
    gateway_transaction_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), unique=True, nullable=True, index=True)
    )
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    payment_date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    
    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    
    # No soft delete - immutable financial records
    
    # Relationships
    invoice: "Invoice" = Relationship(back_populates="payments")
