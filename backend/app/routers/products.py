import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session
from app.auth.dependencies import get_current_workspace_id
from app.models.product import Category, Brand, UnitOfMeasure, Product
from app.schemas.products import (
    CategoryCreate, CategoryResponse,
    BrandCreate, BrandResponse,
    UnitOfMeasureCreate, UnitOfMeasureResponse,
    ProductCreate, ProductResponse
)
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/products", tags=["Product Master"])

@router.get("/categories", response_model=SuccessResponse[List[CategoryResponse]])
async def list_categories(session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    result = await session.execute(select(Category).where(Category.workspace_id == workspace_id, Category.deleted_at.is_(None)))
    return SuccessResponse(data=result.scalars().all())

@router.post("/categories", response_model=SuccessResponse[CategoryResponse])
async def create_category(data: CategoryCreate, session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    cat = Category(workspace_id=workspace_id, **data.model_dump())
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return SuccessResponse(data=cat)

@router.get("/brands", response_model=SuccessResponse[List[BrandResponse]])
async def list_brands(session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    result = await session.execute(select(Brand).where(Brand.workspace_id == workspace_id, Brand.deleted_at.is_(None)))
    return SuccessResponse(data=result.scalars().all())

@router.post("/brands", response_model=SuccessResponse[BrandResponse])
async def create_brand(data: BrandCreate, session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    brand = Brand(workspace_id=workspace_id, **data.model_dump())
    session.add(brand)
    await session.commit()
    await session.refresh(brand)
    return SuccessResponse(data=brand)

@router.get("/uom", response_model=SuccessResponse[List[UnitOfMeasureResponse]])
async def list_uom(session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    result = await session.execute(select(UnitOfMeasure).where(UnitOfMeasure.workspace_id == workspace_id, UnitOfMeasure.deleted_at.is_(None)))
    return SuccessResponse(data=result.scalars().all())

@router.post("/uom", response_model=SuccessResponse[UnitOfMeasureResponse])
async def create_uom(data: UnitOfMeasureCreate, session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    uom = UnitOfMeasure(workspace_id=workspace_id, **data.model_dump())
    session.add(uom)
    await session.commit()
    await session.refresh(uom)
    return SuccessResponse(data=uom)

@router.get("", response_model=SuccessResponse[List[ProductResponse]])
async def list_products(session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    result = await session.execute(select(Product).where(Product.workspace_id == workspace_id, Product.deleted_at.is_(None)))
    return SuccessResponse(data=result.scalars().all())

@router.post("", response_model=SuccessResponse[ProductResponse])
async def create_product(data: ProductCreate, session: AsyncSession = Depends(get_session), workspace_id: uuid.UUID = Depends(get_current_workspace_id)):
    product = Product(workspace_id=workspace_id, **data.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return SuccessResponse(data=product)
