"""
Supplier AP Payment Models — Wave 22 (Phase 4).

Mirrors the AR `Payment`/`IdempotencyKey` pair for the payable side.
Only `status=SUCCESS` counts toward a supplier invoice's `amount_paid`.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlmodel import Field, SQLModel

from app.models.payment import PaymentMethod, PaymentStatus, PDCStatus


class SupplierPayment(SQLModel, table=True):
    __tablename__ = "supplier_payments"

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_supplier_payment_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )
    supplier_invoice_id: uuid.UUID = Field(
        foreign_key="supplier_invoices.id", nullable=False, index=True
    )

    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    payment_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )

    payment_method: PaymentMethod = Field(default=PaymentMethod.BANK_TRANSFER)
    status: PaymentStatus = Field(default=PaymentStatus.SUCCESS)

    reference_number: Optional[str] = Field(default=None, max_length=100)
    bank_name: Optional[str] = Field(default=None, max_length=255)

    # PDC Specific Fields (post-dated cheque issued to a supplier)
    pdc_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    pdc_status: Optional[PDCStatus] = Field(default=None)

    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class SupplierPaymentIdempotencyKey(SQLModel, table=True):
    __tablename__ = "supplier_payment_idempotency_keys"

    # Workspace-scoped compound key (mirrors AR IdempotencyKey)
    workspace_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("workspaces.id"), primary_key=True, nullable=False)
    )

    key: str = Field(sa_column=Column(String(255), primary_key=True, nullable=False))

    supplier_payment_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("supplier_payments.id"), nullable=False, index=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=48),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return (
            f"<SupplierPaymentIdempotencyKey(workspace={self.workspace_id}, "
            f"key={self.key[:20]}...)>"
        )
