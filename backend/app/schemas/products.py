from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime


class CategoryBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BrandBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class BrandCreate(BrandBase):
    pass


class BrandResponse(BrandBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class UnitOfMeasureBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)


class UnitOfMeasureCreate(UnitOfMeasureBase):
    pass


class UnitOfMeasureResponse(UnitOfMeasureBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProductBase(BaseModel):
    internal_sku: str = Field(..., max_length=100)
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    brand_id: Optional[uuid.UUID] = None
    base_uom_id: uuid.UUID
    is_active: bool = True
    tax_rate: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None


class ProductCreate(ProductBase):
    pass


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
