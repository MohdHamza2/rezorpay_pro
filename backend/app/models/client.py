import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    Integer,
    Numeric,
    Text,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.credit_status_event import CreditStatus

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.invoice import Invoice


class Client(SQLModel, table=True):
    __tablename__ = "clients"

    __table_args__ = (
        CheckConstraint(
            "credit_limit IS NULL OR credit_limit >= 0",
            name="check_client_credit_limit_nonneg",
        ),
        CheckConstraint(
            "payment_terms_days IN (0, 30, 45, 60)",
            name="check_client_payment_terms_days",
        ),
        CheckConstraint(
            "credit_balance >= 0", name="check_client_credit_balance_nonneg"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    name: str = Field(max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    tax_id: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    credit_limit: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    payment_terms_days: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    credit_status: CreditStatus = Field(
        default=CreditStatus.ACTIVE,
        sa_column=Column(
            SAEnum(CreditStatus, name="creditstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    credit_status_changed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    credit_status_changed_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    credit_balance: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(12, 2), nullable=False, server_default="0"),
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
    deleted_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Relationships
    workspace: Optional["Workspace"] = Relationship(back_populates="clients")
    invoices: list["Invoice"] = Relationship(back_populates="client")
