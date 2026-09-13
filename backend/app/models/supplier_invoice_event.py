import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.supplier_invoice import SupplierInvoice
    from app.models.user import User


class SupplierInvoiceEventType(str, Enum):
    """Lifecycle event types for supplier (AP) invoices.

    Mirrors the implemented supplier-invoice state machine exactly. There is
    intentionally no CANCELLED value: cancellation does not exist in the
    current lifecycle and must remain eventless.
    """

    CREATED = "CREATED"
    MATCH_SUBMITTED = "MATCH_SUBMITTED"
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    DISCREPANCY_RESOLVED = "DISCREPANCY_RESOLVED"
    APPROVED = "APPROVED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    PAYMENT_REVERSED = "PAYMENT_REVERSED"
    DEBIT_NOTE_APPLIED = "DEBIT_NOTE_APPLIED"


class SupplierInvoiceEvent(SQLModel, table=True):
    """Immutable audit row for one supplier-invoice lifecycle transition.

    Append-only by application convention: no update/delete endpoint or
    service path may mutate these rows. Amounts live on the payment,
    debit-note, and invoice rows; events carry reference IDs only.
    """

    __tablename__ = "supplier_invoice_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_invoice_id: uuid.UUID = Field(
        foreign_key="supplier_invoices.id", nullable=False, index=True
    )
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    # Event classification
    event_type: SupplierInvoiceEventType = Field(nullable=False)

    # Status tracking
    previous_status: Optional[str] = Field(default=None, max_length=50)
    new_status: str = Field(max_length=50)
    actor_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    # Compact reference-only context (< 1KB, enforced by the emitter).
    metadata_log: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, default=dict, nullable=False)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # One-directional relationships (the parent models intentionally carry
    # no back-references so their files stay untouched).
    supplier_invoice: "SupplierInvoice" = Relationship()
    actor: "User" = Relationship()
