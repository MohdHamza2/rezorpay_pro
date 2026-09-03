import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.enquiry_item import EnquiryItem
    from app.models.user import User
    from app.models.workspace import Workspace


class EnquiryStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    QUOTED = "QUOTED"
    CLOSED = "CLOSED"


class EnquirySource(str, Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    WALK_IN = "WALK_IN"
    MANUAL = "MANUAL"


class Enquiry(SQLModel, table=True):
    __tablename__ = "enquiries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", index=True, nullable=False
    )
    client_id: Optional[uuid.UUID] = Field(
        foreign_key="clients.id", index=True, nullable=True
    )

    enquiry_number: str = Field(sa_column=Column(String(50), nullable=False))
    status: str = Field(default=EnquiryStatus.NEW, nullable=False)
    source: str = Field(default=EnquirySource.MANUAL, nullable=False)

    # Contact details for unverified/new leads
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_email: Optional[str] = None

    items_description: Optional[str] = None  # Raw request description
    whatsapp_message_id: Optional[str] = Field(
        sa_column=Column(String(255), unique=True, nullable=True)
    )  # Deduplication

    notes: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = Field(foreign_key="users.id", nullable=True)

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )

    # Relationships
    workspace: Optional["Workspace"] = Relationship()
    client: Optional["Client"] = Relationship(back_populates="enquiries")
    assigned_user: Optional["User"] = Relationship()
    items: List["EnquiryItem"] = Relationship(
        back_populates="enquiry",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
