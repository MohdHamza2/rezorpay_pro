import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.invoice_event import InvoiceEvent
    from app.models.quotation_event import QuotationEvent
    from app.models.customer_purchase_order_event import CustomerPurchaseOrderEvent


class UserRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", nullable=False)

    email: str = Field(
        sa_column=Column(String(255), unique=True, nullable=False, index=True)
    )
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(max_length=255)
    role: UserRole = Field(default=UserRole.MEMBER)
    is_active: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Relationships
    workspace: Optional["Workspace"] = Relationship(back_populates="users")
    invoice_events: list["InvoiceEvent"] = Relationship(
        back_populates="changed_by_user"
    )
    quotation_events: list["QuotationEvent"] = Relationship(
        back_populates="changed_by_user"
    )
    customer_purchase_order_events: list["CustomerPurchaseOrderEvent"] = Relationship(
        back_populates="changed_by_user"
    )
