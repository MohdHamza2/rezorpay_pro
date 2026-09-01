"""Product Master HTTP router (WP-1).

HTTP only: parse request, call ProductService, commit, wrap response.
Static paths (/categories, /brands, /uom) are registered before /{product_id}.
"""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_current_workspace_id
from app.database import get_session
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.schemas.products import (
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ProductCreate,
    ProductDetailResponse,
    ProductIdentifierCreate,
    ProductIdentifierResponse,
    ProductPriceCreate,
    ProductPriceResponse,
    ProductResponse,
    ProductUOMConversionCreate,
    ProductUOMConversionResponse,
    ProductUpdate,
    ResolvedPriceResponse,
    UnitOfMeasureCreate,
    UnitOfMeasureResponse,
    UnitOfMeasureUpdate,
    normalize_voltage,
)
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Product Master"])


def _deleted() -> SuccessResponse[None]:
    return SuccessResponse[None](success=True, data=None)


def _list_voltage(
    voltage: Optional[str] = Query(None, max_length=32),
) -> Optional[str]:
    try:
        return normalize_voltage(voltage)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ---------- Categories (static path before /{product_id}) ----------


@router.get("/categories", response_model=PaginatedResponse)
async def list_categories(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    items, pagination = await ProductService.list_categories(
        session, workspace_id, page, per_page, search
    )
    return PaginatedResponse(
        data=[CategoryResponse.model_validate(row) for row in items],
        pagination=pagination,
    )


@router.post(
    "/categories",
    response_model=SuccessResponse[CategoryResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    category = await ProductService.create_category(session, workspace_id, data)
    await session.commit()
    await session.refresh(category)
    return SuccessResponse(data=CategoryResponse.model_validate(category))


@router.get(
    "/categories/{category_id}", response_model=SuccessResponse[CategoryResponse]
)
async def get_category(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    category = await ProductService.get_category(session, workspace_id, category_id)
    return SuccessResponse(data=CategoryResponse.model_validate(category))


@router.put(
    "/categories/{category_id}", response_model=SuccessResponse[CategoryResponse]
)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    category = await ProductService.update_category(
        session, workspace_id, category_id, data
    )
    await session.commit()
    await session.refresh(category)
    return SuccessResponse(data=CategoryResponse.model_validate(category))


@router.delete(
    "/categories/{category_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_category(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_category(session, workspace_id, category_id)
    await session.commit()
    return _deleted()


# ---------- Brands ----------


@router.get("/brands", response_model=PaginatedResponse)
async def list_brands(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    items, pagination = await ProductService.list_brands(
        session, workspace_id, page, per_page, search
    )
    return PaginatedResponse(
        data=[BrandResponse.model_validate(row) for row in items],
        pagination=pagination,
    )


@router.post(
    "/brands",
    response_model=SuccessResponse[BrandResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_brand(
    data: BrandCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    brand = await ProductService.create_brand(session, workspace_id, data)
    await session.commit()
    await session.refresh(brand)
    return SuccessResponse(data=BrandResponse.model_validate(brand))


@router.get("/brands/{brand_id}", response_model=SuccessResponse[BrandResponse])
async def get_brand(
    brand_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    brand = await ProductService.get_brand(session, workspace_id, brand_id)
    return SuccessResponse(data=BrandResponse.model_validate(brand))


@router.put("/brands/{brand_id}", response_model=SuccessResponse[BrandResponse])
async def update_brand(
    brand_id: UUID,
    data: BrandUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    brand = await ProductService.update_brand(session, workspace_id, brand_id, data)
    await session.commit()
    await session.refresh(brand)
    return SuccessResponse(data=BrandResponse.model_validate(brand))


@router.delete(
    "/brands/{brand_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_brand(
    brand_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_brand(session, workspace_id, brand_id)
    await session.commit()
    return _deleted()


# ---------- Units of measure ----------


@router.get("/uom", response_model=PaginatedResponse)
async def list_uom(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    items, pagination = await ProductService.list_uoms(
        session, workspace_id, page, per_page
    )
    return PaginatedResponse(
        data=[UnitOfMeasureResponse.model_validate(row) for row in items],
        pagination=pagination,
    )


@router.post(
    "/uom",
    response_model=SuccessResponse[UnitOfMeasureResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_uom(
    data: UnitOfMeasureCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    uom = await ProductService.create_uom(session, workspace_id, data)
    await session.commit()
    await session.refresh(uom)
    return SuccessResponse(data=UnitOfMeasureResponse.model_validate(uom))


@router.get("/uom/{uom_id}", response_model=SuccessResponse[UnitOfMeasureResponse])
async def get_uom(
    uom_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    uom = await ProductService.get_uom(session, workspace_id, uom_id)
    return SuccessResponse(data=UnitOfMeasureResponse.model_validate(uom))


@router.put("/uom/{uom_id}", response_model=SuccessResponse[UnitOfMeasureResponse])
async def update_uom(
    uom_id: UUID,
    data: UnitOfMeasureUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    uom = await ProductService.update_uom(session, workspace_id, uom_id, data)
    await session.commit()
    await session.refresh(uom)
    return SuccessResponse(data=UnitOfMeasureResponse.model_validate(uom))


@router.delete(
    "/uom/{uom_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_uom(
    uom_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_uom(session, workspace_id, uom_id)
    await session.commit()
    return _deleted()


# ---------- Product collection ----------


@router.get("", response_model=PaginatedResponse)
async def list_products(
    search: Optional[str] = Query(None),
    category_id: Optional[UUID] = Query(None),
    brand_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    amp_rating: Optional[Decimal] = Query(None, gt=0, max_digits=8, decimal_places=2),
    cable_size_mm2: Optional[Decimal] = Query(
        None, gt=0, max_digits=8, decimal_places=2
    ),
    cores: Optional[int] = Query(None, ge=1, le=24),
    poles: Optional[int] = Query(None, ge=1, le=4),
    voltage: Optional[str] = Depends(_list_voltage),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    items, pagination = await ProductService.list_products(
        session,
        workspace_id,
        page,
        per_page,
        search,
        category_id,
        brand_id,
        is_active,
        amp_rating,
        cable_size_mm2,
        cores,
        poles,
        voltage,
    )
    return PaginatedResponse(
        data=[ProductResponse.model_validate(row) for row in items],
        pagination=pagination,
    )


@router.post(
    "",
    response_model=SuccessResponse[ProductResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    product = await ProductService.create_product(session, workspace_id, data)
    await session.commit()
    await session.refresh(product)
    return SuccessResponse(data=ProductResponse.model_validate(product))


# ---------- Nested children (before /{product_id} item verbs is fine) ----------


@router.get(
    "/{product_id}/identifiers",
    response_model=SuccessResponse[List[ProductIdentifierResponse]],
)
async def list_identifiers(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    rows = await ProductService.list_identifiers(session, workspace_id, product_id)
    return SuccessResponse(
        data=[ProductIdentifierResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/{product_id}/identifiers",
    response_model=SuccessResponse[ProductIdentifierResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_identifier(
    product_id: UUID,
    data: ProductIdentifierCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    row = await ProductService.create_identifier(
        session, workspace_id, product_id, data
    )
    await session.commit()
    await session.refresh(row)
    return SuccessResponse(data=ProductIdentifierResponse.model_validate(row))


@router.delete(
    "/{product_id}/identifiers/{identifier_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_identifier(
    product_id: UUID,
    identifier_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_identifier(
        session, workspace_id, product_id, identifier_id
    )
    await session.commit()
    return _deleted()


@router.get(
    "/{product_id}/conversions",
    response_model=SuccessResponse[List[ProductUOMConversionResponse]],
)
async def list_conversions(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    rows = await ProductService.list_conversions(session, workspace_id, product_id)
    return SuccessResponse(data=rows)


@router.post(
    "/{product_id}/conversions",
    response_model=SuccessResponse[ProductUOMConversionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_conversion(
    product_id: UUID,
    data: ProductUOMConversionCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    payload = await ProductService.create_conversion(
        session, workspace_id, product_id, data
    )
    await session.commit()
    return SuccessResponse(data=payload)


@router.delete(
    "/{product_id}/conversions/{conversion_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_conversion(
    product_id: UUID,
    conversion_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_conversion(
        session, workspace_id, product_id, conversion_id
    )
    await session.commit()
    return _deleted()


@router.get(
    "/{product_id}/resolved-price",
    response_model=SuccessResponse[ResolvedPriceResponse],
)
async def get_resolved_price(
    product_id: UUID,
    quantity: Decimal = Query(...),
    client_id: Optional[UUID] = Query(None),
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    payload = await PricingService.preview(
        session, workspace_id, product_id, client_id, quantity
    )
    return SuccessResponse(data=payload)


@router.get(
    "/{product_id}/prices",
    response_model=SuccessResponse[List[ProductPriceResponse]],
)
async def list_prices(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    rows = await ProductService.list_prices(session, workspace_id, product_id)
    return SuccessResponse(
        data=[ProductPriceResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/{product_id}/prices",
    response_model=SuccessResponse[ProductPriceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_price(
    product_id: UUID,
    data: ProductPriceCreate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    row = await ProductService.create_price(session, workspace_id, product_id, data)
    await session.commit()
    await session.refresh(row)
    return SuccessResponse(data=ProductPriceResponse.model_validate(row))


@router.delete(
    "/{product_id}/prices/{price_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_price(
    product_id: UUID,
    price_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_price(session, workspace_id, product_id, price_id)
    await session.commit()
    return _deleted()


# ---------- Product item ----------


@router.get("/{product_id}", response_model=SuccessResponse[ProductDetailResponse])
async def get_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    detail = await ProductService.get_product_detail(session, workspace_id, product_id)
    return SuccessResponse(data=detail)


@router.put("/{product_id}", response_model=SuccessResponse[ProductResponse])
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    product = await ProductService.update_product(
        session, workspace_id, product_id, data
    )
    await session.commit()
    await session.refresh(product)
    return SuccessResponse(data=ProductResponse.model_validate(product))


@router.delete(
    "/{product_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
)
async def delete_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    workspace_id: UUID = Depends(get_current_workspace_id),
):
    await ProductService.delete_product(session, workspace_id, product_id)
    await session.commit()
    return _deleted()
