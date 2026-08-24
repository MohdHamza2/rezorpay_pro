from datetime import datetime, timezone
from typing import Optional, List
import uuid

from sqlalchemy import Column, DateTime, String, Numeric
from decimal import Decimal
from sqlmodel import Field, Relationship, SQLModel


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(
        sa_column=Column(
            String(255),
            unique=True,
            index=True,
            nullable=False,
        )
    )
    
    
    # Wave 2 Workspace Settings
    trn: Optional[str] = Field(default=None, max_length=50)
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    whatsapp_number: Optional[str] = Field(default=None, max_length=50)
    default_tax_rate: Decimal = Field(default=Decimal('5.00'), sa_column=Column(Numeric(5, 2), nullable=False))
    credit_limit_default: Decimal = Field(default=Decimal('0.00'), sa_column=Column(Numeric(12, 2), nullable=False))
    credit_hold_days: int = Field(default=90)
    
    # SPO Configuration
    over_receipt_tolerance_percent: Decimal = Field(default=Decimal('2.00'), sa_column=Column(Numeric(5, 2), nullable=False))
    spo_amendment_approval_threshold: Decimal = Field(default=Decimal('0.00'), sa_column=Column(Numeric(12, 2), nullable=False))
    
    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    # Relationships
    users: List["User"] = Relationship(back_populates="workspace")
    clients: List["Client"] = Relationship(back_populates="workspace")
    invoices: List["Invoice"] = Relationship(back_populates="workspace")
