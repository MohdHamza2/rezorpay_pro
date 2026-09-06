"""
Supplier Debit Note Models — Wave 23 (Phase 4).

A supplier debit note (SDN) records money the supplier owes us — a credit
against an approved supplier invoice's `balance_due`. It is auto-created
(ISSUED) when a purchase return is dispatched, or created manually.

Unlike a payment it NEVER touches `amount_paid`/`paid_at` and never flips an
invoice to PAID; apply only reduces `balance_due`. Applied notes are
permanent and show on the supplier statement as a credit.
"""

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class SupplierDebitNoteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"


class SupplierDebitNote(SQLModel, table=True):
    __tablename__ = "supplier_debit_notes"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "dn_number", name="uq_supplier_dn_workspace_number"
        ),
        CheckConstraint("amount > 0", name="chk_sdn_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", index=True)
    purchase_return_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="purchase_returns.id", index=True
    )

    dn_number: str = Field(sa_column=Column(Text, nullable=False, index=True))
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    status: SupplierDebitNoteStatus = Field(
        sa_column=Column(
            SAEnum(SupplierDebitNoteStatus, name="supplierdebitnotestatus"),
            default=SupplierDebitNoteStatus.DRAFT,
            nullable=False,
        )
    )

    source_type: str = Field(default="MANUAL", max_length=20)
    issue_date: date

    applied_invoice_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="supplier_invoices.id", index=True
    )
    reason: Optional[str] = Field(sa_column=Column(Text), default=None)
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    applied_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )


class SupplierDebitNoteCounter(SQLModel, table=True):
    """Workspace-scoped gapless counter for supplier debit notes (SDN-YYYY-XXXX)."""

    __tablename__ = "supplier_debit_note_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id",
        primary_key=True,
        nullable=False,
    )
    year: int = Field(primary_key=True, nullable=False)
    last_number: int = Field(default=0, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    def generate_number(self) -> str:
        """Generate formatted supplier debit note number: SDN-2026-0001"""
        return f"SDN-{self.year}-{self.last_number:04d}"
