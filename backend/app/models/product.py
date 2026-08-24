import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column, DateTime, Text, Numeric, Boolean, UniqueConstraint
from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    parent_id: Optional[uuid.UUID] = Field(default=None, foreign_key="categories.id")

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


class Brand(SQLModel, table=True):
    __tablename__ = "brands"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

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


class UnitOfMeasure(SQLModel, table=True):
    __tablename__ = "units_of_measure"
    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_workspace_uom_code"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    code: str = Field(max_length=50, index=True)
    name: str = Field(max_length=255)

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


class Product(SQLModel, table=True):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "internal_sku", name="uq_workspace_internal_sku"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    internal_sku: str = Field(max_length=100, index=True)
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    category_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="categories.id", index=True
    )
    brand_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="brands.id", index=True
    )
    base_uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id", index=True)

    is_active: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true")
    )
    tax_rate: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    reorder_level: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )

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


class ProductIdentifier(SQLModel, table=True):
    __tablename__ = "product_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "type", "value", name="uq_product_identifier_type_value"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)

    type: str = Field(max_length=50)  # e.g. BARCODE, MPN, SUPPLIER_CODE
    value: str = Field(max_length=255, index=True)


class ProductUOMConversion(SQLModel, table=True):
    __tablename__ = "product_uom_conversions"
    __table_args__ = (
        UniqueConstraint("product_id", "to_uom_id", name="uq_product_uom_conversion"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)

    to_uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id", nullable=False)
    conversion_factor: Decimal = Field(
        sa_column=Column(Numeric(14, 6), nullable=False)
    )  # e.g. 1 BOX = 10 PCS


class ProductPrice(SQLModel, table=True):
    __tablename__ = "product_prices"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)

    price_type: str = Field(
        max_length=50
    )  # e.g. DEFAULT_SALES, TIER_1, CUSTOMER_SPECIFIC
    currency: str = Field(max_length=3, default="AED")
    price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    # Optional constraints if price is specific
    client_id: Optional[uuid.UUID] = Field(default=None, foreign_key="clients.id")
    min_quantity: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2))
    )
