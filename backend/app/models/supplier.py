import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    Text,
    Numeric,
    Boolean,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class Supplier(SQLModel, table=True):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "supplier_code", name="uq_workspace_supplier_code"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    supplier_code: str = Field(max_length=50, index=True)
    name: str = Field(max_length=255, index=True)
    trade_name: Optional[str] = Field(default=None, max_length=255)
    trn: Optional[str] = Field(default=None, max_length=50)  # Tax Registration Number

    # Commercial Terms
    credit_limit: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2))
    )
    payment_terms: str = Field(default="CASH", max_length=50)  # e.g. CASH, NET30, NET60
    status: str = Field(default="ACTIVE", max_length=20)  # ACTIVE, INACTIVE, HOLD
    rating: Optional[str] = Field(default=None, max_length=50)

    # Address Info
    address: Optional[str] = Field(default=None, sa_column=Column(Text))
    city: Optional[str] = Field(default=None, max_length=100)
    country: Optional[str] = Field(default=None, max_length=100)

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


class SupplierContact(SQLModel, table=True):
    __tablename__ = "supplier_contacts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )

    name: str = Field(max_length=255)
    title: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    is_primary: bool = Field(default=False, sa_column=Column(Boolean))


class SupplierBankAccount(SQLModel, table=True):
    __tablename__ = "supplier_bank_accounts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )

    bank_name: str = Field(max_length=255)
    account_name: str = Field(max_length=255)
    account_number: str = Field(max_length=100)
    iban: Optional[str] = Field(default=None, max_length=100)
    swift_code: Optional[str] = Field(default=None, max_length=50)
    currency: str = Field(default="AED", max_length=3)
    is_primary: bool = Field(default=False, sa_column=Column(Boolean))


class SupplierDocument(SQLModel, table=True):
    __tablename__ = "supplier_documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )

    document_type: str = Field(
        max_length=50
    )  # e.g. TRADE_LICENSE, VAT_CERTIFICATE, CONTRACT
    document_url: str = Field(max_length=1000)
    expiry_date: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class SupplierProduct(SQLModel, table=True):
    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    supplier_id: uuid.UUID = Field(
        foreign_key="suppliers.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)

    supplier_sku: Optional[str] = Field(default=None, max_length=100)
    lead_time_days: Optional[int] = Field(default=None)
    moq: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2))
    )  # Minimum Order Quantity

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
