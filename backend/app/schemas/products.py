"""Product Master Pydantic schemas (WP-1).

Write bodies use extra='forbid' so unknown keys (hs_code, from_uom_id,
electrical spec fields) return 422. Money, tax, reorder, and conversion
factor fields are Decimal — never float.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdentifierType(str, Enum):
    """Allow-list for ProductIdentifier.type (DB column remains str)."""

    MPN = "MPN"
    BARCODE = "BARCODE"
    SUPPLIER_CODE = "SUPPLIER_CODE"
    EAN = "EAN"
    UPC = "UPC"
    CUSTOMER_CODE = "CUSTOMER_CODE"


class PriceType(str, Enum):
    """Allow-list for ProductPrice.price_type (DB column remains str)."""

    DEFAULT_SALES = "DEFAULT_SALES"
    TIER_1 = "TIER_1"
    CUSTOMER_SPECIFIC = "CUSTOMER_SPECIFIC"


class StrictModel(BaseModel):
    """Request body that rejects unknown keys with 422."""

    model_config = ConfigDict(extra="forbid")


# ---------- Category ----------


class CategoryCreate(StrictModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class CategoryUpdate(StrictModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


# ---------- Brand ----------


class BrandCreate(StrictModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class BrandUpdate(StrictModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class BrandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


# ---------- Unit of measure ----------


class UnitOfMeasureCreate(StrictModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class UnitOfMeasureUpdate(StrictModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class UnitOfMeasureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


# ---------- Product ----------


class ProductCreate(StrictModel):
    internal_sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    base_uom_id: uuid.UUID
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    brand_id: Optional[uuid.UUID] = None
    is_active: bool = True
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    reorder_level: Optional[Decimal] = Field(
        None, ge=0, max_digits=12, decimal_places=2
    )


class ProductUpdate(StrictModel):
    internal_sku: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    brand_id: Optional[uuid.UUID] = None
    base_uom_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    reorder_level: Optional[Decimal] = Field(
        None, ge=0, max_digits=12, decimal_places=2
    )


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    internal_sku: str
    name: str
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    brand_id: Optional[uuid.UUID] = None
    base_uom_id: uuid.UUID
    is_active: bool
    tax_rate: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime


# ---------- Identifier ----------


class ProductIdentifierCreate(StrictModel):
    type: IdentifierType
    value: str = Field(..., min_length=1, max_length=255)

    @field_validator("value", mode="before")
    @classmethod
    def strip_value(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("value must be non-empty")
            return stripped
        return value


class ProductIdentifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    product_id: uuid.UUID
    type: str
    value: str


# ---------- UOM conversion ----------


class ProductUOMConversionCreate(StrictModel):
    """Create body: to_uom_id + conversion_factor only. from_uom_id is forbidden."""

    to_uom_id: uuid.UUID
    conversion_factor: Decimal = Field(..., gt=0, max_digits=14, decimal_places=6)


class ProductUOMConversionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    product_id: uuid.UUID
    to_uom_id: uuid.UUID
    conversion_factor: Decimal
    base_uom_id: Optional[uuid.UUID] = None


# ---------- Price ----------


class ProductPriceCreate(StrictModel):
    price_type: PriceType
    currency: Literal["AED"] = "AED"
    price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    client_id: Optional[uuid.UUID] = None
    min_quantity: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def validate_price_type_rules(self) -> "ProductPriceCreate":
        if self.price_type == PriceType.DEFAULT_SALES:
            if self.client_id is not None:
                raise ValueError("client_id must be null for DEFAULT_SALES")
            if self.min_quantity is not None:
                raise ValueError("min_quantity must be omitted for DEFAULT_SALES")
        elif self.price_type == PriceType.TIER_1:
            if self.client_id is not None:
                raise ValueError("client_id must be null for TIER_1")
            if self.min_quantity is None or self.min_quantity <= 0:
                raise ValueError("min_quantity is required and must be > 0 for TIER_1")
        elif self.price_type == PriceType.CUSTOMER_SPECIFIC:
            if self.client_id is None:
                raise ValueError("client_id is required for CUSTOMER_SPECIFIC")
        return self


class ProductPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    product_id: uuid.UUID
    price_type: str
    currency: str
    price: Decimal
    client_id: Optional[uuid.UUID] = None
    min_quantity: Optional[Decimal] = None


class ResolvedPriceResponse(BaseModel):
    """One winning sales price for staff invoice/quote/LPO forms."""

    product_id: uuid.UUID
    client_id: Optional[uuid.UUID] = None
    quantity: Decimal
    unit_price: Decimal
    currency: str = "AED"
    price_type: str
    min_quantity: Optional[Decimal] = None
    price_id: uuid.UUID


class ProductDetailResponse(ProductResponse):
    """GET /products/{id} only — children embedded, no stock."""

    identifiers: List[ProductIdentifierResponse] = Field(default_factory=list)
    conversions: List[ProductUOMConversionResponse] = Field(default_factory=list)
    prices: List[ProductPriceResponse] = Field(default_factory=list)
