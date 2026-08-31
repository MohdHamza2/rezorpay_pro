"""Product Master business rules (WP-1).

UOM conversion semantic (locked): one (1) unit of ``to_uom`` equals
``conversion_factor`` units of the product's **base UOM**. Example: base = MTR,
``to_uom`` = DRUM, ``conversion_factor`` = 500 → 1 DRUM = 500 MTR. Matches the
live comment ``1 BOX = 10 PCS`` when base is PCS and ``to_uom`` is BOX.

Implied FROM UOM is ``Product.base_uom_id``. There is no ``from_uom_id`` column.
Multi-hop conversion resolution is deferred (not WP-1).

This service does not commit; the router commits after a successful call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, NoReturn, Optional, Sequence, Tuple, Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.product import (
    Brand,
    Category,
    Product,
    ProductIdentifier,
    ProductPrice,
    ProductUOMConversion,
    UnitOfMeasure,
)
from app.schemas.common import PaginationMeta
from app.schemas.products import (
    BrandCreate,
    BrandUpdate,
    CategoryCreate,
    CategoryUpdate,
    PriceType,
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
    UnitOfMeasureCreate,
    UnitOfMeasureUpdate,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=SQLModel)

_CONVERSION_BASE_MSG = (
    "One (1) unit of to_uom equals conversion_factor units of the product's "
    "base UOM. to_uom_id must differ from the product base UOM."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _http(code: int, message: str) -> NoReturn:
    raise HTTPException(status_code=code, detail=message)


def _not_found(label: str) -> NoReturn:
    _http(status.HTTP_404_NOT_FOUND, f"{label} not found")


def _conflict(message: str) -> NoReturn:
    _http(status.HTTP_409_CONFLICT, message)


def _bad_request(message: str) -> NoReturn:
    _http(status.HTTP_400_BAD_REQUEST, message)


def _pagination(total: int, page: int, per_page: int) -> PaginationMeta:
    pages = (total + per_page - 1) // per_page if total else 0
    return PaginationMeta(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


def _enum_value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _min_qty_key(quantity: Optional[Decimal]) -> Decimal:
    return Decimal("0") if quantity is None else quantity


class ProductService:
    """All Product Master validation, uniqueness, and isolation rules."""

    # ----- generic lookups -----

    @staticmethod
    async def _get_live(
        session: AsyncSession,
        model: Type[T],
        entity_id: uuid.UUID,
        workspace_id: uuid.UUID,
        label: str,
    ) -> T:
        result = await session.execute(
            select(model).where(
                model.id == entity_id,  # type: ignore[attr-defined]
                model.workspace_id == workspace_id,  # type: ignore[attr-defined]
                model.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            _not_found(label)
        return row

    @staticmethod
    async def _paginated(
        session: AsyncSession,
        stmt,
        page: int,
        per_page: int,
    ) -> Tuple[list, PaginationMeta]:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = (await session.execute(count_stmt)).scalar_one()
        result = await session.execute(
            stmt.offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), _pagination(total, page, per_page)

    @staticmethod
    async def _flush_or_conflict(session: AsyncSession, message: str) -> None:
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            _conflict(message)

    @staticmethod
    async def _name_taken(
        session: AsyncSession,
        model: Type[T],
        workspace_id: uuid.UUID,
        name: str,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> bool:
        stmt = select(model).where(
            model.workspace_id == workspace_id,  # type: ignore[attr-defined]
            model.name == name,  # type: ignore[attr-defined]
            model.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)  # type: ignore[attr-defined]
        found = (await session.execute(stmt)).scalar_one_or_none()
        return found is not None

    @staticmethod
    async def _require_uom(
        session: AsyncSession, uom_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> UnitOfMeasure:
        return await ProductService._get_live(
            session, UnitOfMeasure, uom_id, workspace_id, "Unit of measure"
        )

    @staticmethod
    async def _require_optional_category(
        session: AsyncSession,
        category_id: Optional[uuid.UUID],
        workspace_id: uuid.UUID,
    ) -> None:
        if category_id is None:
            return
        await ProductService._get_live(
            session, Category, category_id, workspace_id, "Category"
        )

    @staticmethod
    async def _require_optional_brand(
        session: AsyncSession,
        brand_id: Optional[uuid.UUID],
        workspace_id: uuid.UUID,
    ) -> None:
        if brand_id is None:
            return
        await ProductService._get_live(session, Brand, brand_id, workspace_id, "Brand")

    @staticmethod
    async def _load_category_maybe(
        session: AsyncSession,
        category_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Optional[Category]:
        result = await session.execute(
            select(Category).where(
                Category.id == category_id,
                Category.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _walk_live_ancestors(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        start_id: Optional[uuid.UUID],
        seen: set[uuid.UUID],
    ) -> None:
        current = start_id
        depth = 0
        while current is not None:
            if current in seen:
                _bad_request("Circular category parent is not allowed")
            seen.add(current)
            ancestor = await ProductService._load_category_maybe(
                session, current, workspace_id
            )
            if ancestor is None or ancestor.deleted_at is not None:
                return
            current = ancestor.parent_id
            depth += 1
            if depth > 50:
                _bad_request("Circular category parent is not allowed")

    @staticmethod
    async def _assert_acyclic_parent(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        category_id: Optional[uuid.UUID],
        parent_id: uuid.UUID,
    ) -> None:
        if category_id is not None and parent_id == category_id:
            _bad_request("Category cannot be its own parent")
        immediate = await ProductService._get_live(
            session, Category, parent_id, workspace_id, "Category"
        )
        seen = {category_id} if category_id is not None else set()
        seen.add(parent_id)
        await ProductService._walk_live_ancestors(
            session, workspace_id, immediate.parent_id, seen
        )

    @staticmethod
    async def _require_live_product(
        session: AsyncSession, product_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Product:
        return await ProductService._get_live(
            session, Product, product_id, workspace_id, "Product"
        )

    @staticmethod
    def _to_conversion_response(
        row: ProductUOMConversion, base_uom_id: uuid.UUID
    ) -> ProductUOMConversionResponse:
        payload = ProductUOMConversionResponse.model_validate(row)
        return payload.model_copy(update={"base_uom_id": base_uom_id})

    # ----- Category -----

    @staticmethod
    async def list_categories(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        page: int,
        per_page: int,
        search: Optional[str] = None,
    ) -> Tuple[Sequence[Category], PaginationMeta]:
        stmt = select(Category).where(
            Category.workspace_id == workspace_id, Category.deleted_at.is_(None)
        )
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(Category.name.ilike(term), Category.description.ilike(term))
            )
        stmt = stmt.order_by(Category.name)
        return await ProductService._paginated(session, stmt, page, per_page)

    @staticmethod
    async def get_category(
        session: AsyncSession, workspace_id: uuid.UUID, category_id: uuid.UUID
    ) -> Category:
        return await ProductService._get_live(
            session, Category, category_id, workspace_id, "Category"
        )

    @staticmethod
    async def create_category(
        session: AsyncSession, workspace_id: uuid.UUID, data: CategoryCreate
    ) -> Category:
        if await ProductService._name_taken(session, Category, workspace_id, data.name):
            _conflict("Category name already exists")
        if data.parent_id is not None:
            await ProductService._assert_acyclic_parent(
                session, workspace_id, None, data.parent_id
            )
        category = Category(workspace_id=workspace_id, **data.model_dump())
        session.add(category)
        await ProductService._flush_or_conflict(session, "Category name already exists")
        logger.info("category.created", extra={"workspace_id": str(workspace_id)})
        return category

    @staticmethod
    async def update_category(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        category_id: uuid.UUID,
        data: CategoryUpdate,
    ) -> Category:
        category = await ProductService.get_category(session, workspace_id, category_id)
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates and await ProductService._name_taken(
            session, Category, workspace_id, updates["name"], exclude_id=category_id
        ):
            _conflict("Category name already exists")
        if "parent_id" in updates and updates["parent_id"] is not None:
            await ProductService._assert_acyclic_parent(
                session, workspace_id, category_id, updates["parent_id"]
            )
        for field, value in updates.items():
            setattr(category, field, value)
        category.updated_at = _now()
        await session.flush()
        return category

    @staticmethod
    async def delete_category(
        session: AsyncSession, workspace_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        category = await ProductService.get_category(session, workspace_id, category_id)
        category.deleted_at = _now()
        category.updated_at = _now()
        await session.flush()

    # ----- Brand -----

    @staticmethod
    async def list_brands(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        page: int,
        per_page: int,
        search: Optional[str] = None,
    ) -> Tuple[Sequence[Brand], PaginationMeta]:
        stmt = select(Brand).where(
            Brand.workspace_id == workspace_id, Brand.deleted_at.is_(None)
        )
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(Brand.name.ilike(term), Brand.description.ilike(term))
            )
        stmt = stmt.order_by(Brand.name)
        return await ProductService._paginated(session, stmt, page, per_page)

    @staticmethod
    async def get_brand(
        session: AsyncSession, workspace_id: uuid.UUID, brand_id: uuid.UUID
    ) -> Brand:
        return await ProductService._get_live(
            session, Brand, brand_id, workspace_id, "Brand"
        )

    @staticmethod
    async def create_brand(
        session: AsyncSession, workspace_id: uuid.UUID, data: BrandCreate
    ) -> Brand:
        if await ProductService._name_taken(session, Brand, workspace_id, data.name):
            _conflict("Brand name already exists")
        brand = Brand(workspace_id=workspace_id, **data.model_dump())
        session.add(brand)
        await ProductService._flush_or_conflict(session, "Brand name already exists")
        return brand

    @staticmethod
    async def update_brand(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        brand_id: uuid.UUID,
        data: BrandUpdate,
    ) -> Brand:
        brand = await ProductService.get_brand(session, workspace_id, brand_id)
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates and await ProductService._name_taken(
            session, Brand, workspace_id, updates["name"], exclude_id=brand_id
        ):
            _conflict("Brand name already exists")
        for field, value in updates.items():
            setattr(brand, field, value)
        brand.updated_at = _now()
        await session.flush()
        return brand

    @staticmethod
    async def delete_brand(
        session: AsyncSession, workspace_id: uuid.UUID, brand_id: uuid.UUID
    ) -> None:
        brand = await ProductService.get_brand(session, workspace_id, brand_id)
        brand.deleted_at = _now()
        brand.updated_at = _now()
        await session.flush()

    # ----- UOM -----

    @staticmethod
    async def list_uoms(
        session: AsyncSession, workspace_id: uuid.UUID, page: int, per_page: int
    ) -> Tuple[Sequence[UnitOfMeasure], PaginationMeta]:
        stmt = (
            select(UnitOfMeasure)
            .where(
                UnitOfMeasure.workspace_id == workspace_id,
                UnitOfMeasure.deleted_at.is_(None),
            )
            .order_by(UnitOfMeasure.code)
        )
        return await ProductService._paginated(session, stmt, page, per_page)

    @staticmethod
    async def get_uom(
        session: AsyncSession, workspace_id: uuid.UUID, uom_id: uuid.UUID
    ) -> UnitOfMeasure:
        return await ProductService._require_uom(session, uom_id, workspace_id)

    @staticmethod
    async def _uom_code_taken(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        code: str,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> bool:
        stmt = select(UnitOfMeasure).where(
            UnitOfMeasure.workspace_id == workspace_id, UnitOfMeasure.code == code
        )
        if exclude_id is not None:
            stmt = stmt.where(UnitOfMeasure.id != exclude_id)
        found = (await session.execute(stmt)).scalar_one_or_none()
        return found is not None

    @staticmethod
    async def create_uom(
        session: AsyncSession, workspace_id: uuid.UUID, data: UnitOfMeasureCreate
    ) -> UnitOfMeasure:
        if await ProductService._uom_code_taken(session, workspace_id, data.code):
            _conflict("Unit of measure code already exists")
        uom = UnitOfMeasure(workspace_id=workspace_id, **data.model_dump())
        session.add(uom)
        await ProductService._flush_or_conflict(
            session, "Unit of measure code already exists"
        )
        return uom

    @staticmethod
    async def update_uom(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        uom_id: uuid.UUID,
        data: UnitOfMeasureUpdate,
    ) -> UnitOfMeasure:
        uom = await ProductService.get_uom(session, workspace_id, uom_id)
        updates = data.model_dump(exclude_unset=True)
        if "code" in updates and await ProductService._uom_code_taken(
            session, workspace_id, updates["code"], exclude_id=uom_id
        ):
            _conflict("Unit of measure code already exists")
        for field, value in updates.items():
            setattr(uom, field, value)
        uom.updated_at = _now()
        await session.flush()
        return uom

    @staticmethod
    async def delete_uom(
        session: AsyncSession, workspace_id: uuid.UUID, uom_id: uuid.UUID
    ) -> None:
        uom = await ProductService.get_uom(session, workspace_id, uom_id)
        product_ref = (
            await session.execute(
                select(Product.id)
                .where(
                    Product.workspace_id == workspace_id,
                    Product.base_uom_id == uom_id,
                    Product.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        conversion_ref = (
            await session.execute(
                select(ProductUOMConversion.id)
                .join(Product, Product.id == ProductUOMConversion.product_id)
                .where(
                    ProductUOMConversion.to_uom_id == uom_id,
                    Product.workspace_id == workspace_id,
                    Product.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if product_ref is not None or conversion_ref is not None:
            _bad_request("Cannot delete unit of measure that is in use")
        uom.deleted_at = _now()
        uom.updated_at = _now()
        await session.flush()

    # ----- Product -----

    @staticmethod
    async def _sku_taken(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        sku: str,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> bool:
        stmt = select(Product).where(
            Product.workspace_id == workspace_id, Product.internal_sku == sku
        )
        if exclude_id is not None:
            stmt = stmt.where(Product.id != exclude_id)
        found = (await session.execute(stmt)).scalar_one_or_none()
        return found is not None

    @staticmethod
    async def _validate_product_refs(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        base_uom_id: uuid.UUID,
        category_id: Optional[uuid.UUID],
        brand_id: Optional[uuid.UUID],
    ) -> None:
        await ProductService._require_uom(session, base_uom_id, workspace_id)
        await ProductService._require_optional_category(
            session, category_id, workspace_id
        )
        await ProductService._require_optional_brand(session, brand_id, workspace_id)

    @staticmethod
    async def list_products(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        page: int,
        per_page: int,
        search: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        brand_id: Optional[uuid.UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[Sequence[Product], PaginationMeta]:
        stmt = select(Product).where(
            Product.workspace_id == workspace_id, Product.deleted_at.is_(None)
        )
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Product.internal_sku.ilike(term),
                    Product.name.ilike(term),
                    Product.description.ilike(term),
                )
            )
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if brand_id is not None:
            stmt = stmt.where(Product.brand_id == brand_id)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        stmt = stmt.order_by(Product.name)
        return await ProductService._paginated(session, stmt, page, per_page)

    @staticmethod
    async def _child_rows(
        session: AsyncSession, product: Product
    ) -> Tuple[List[ProductIdentifier], List[ProductUOMConversion], List[ProductPrice]]:
        ident = (
            (
                await session.execute(
                    select(ProductIdentifier).where(
                        ProductIdentifier.product_id == product.id,
                        ProductIdentifier.workspace_id == product.workspace_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        conv = (
            (
                await session.execute(
                    select(ProductUOMConversion).where(
                        ProductUOMConversion.product_id == product.id,
                        ProductUOMConversion.workspace_id == product.workspace_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        prices = (
            (
                await session.execute(
                    select(ProductPrice).where(
                        ProductPrice.product_id == product.id,
                        ProductPrice.workspace_id == product.workspace_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(ident), list(conv), list(prices)

    @staticmethod
    async def get_product_detail(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductDetailResponse:
        product = await ProductService._require_live_product(
            session, product_id, workspace_id
        )
        identifiers, conversions, prices = await ProductService._child_rows(
            session, product
        )
        base = ProductResponse.model_validate(product)
        return ProductDetailResponse(
            **base.model_dump(),
            identifiers=[
                ProductIdentifierResponse.model_validate(row) for row in identifiers
            ],
            conversions=[
                ProductService._to_conversion_response(row, product.base_uom_id)
                for row in conversions
            ],
            prices=[ProductPriceResponse.model_validate(row) for row in prices],
        )

    @staticmethod
    async def create_product(
        session: AsyncSession, workspace_id: uuid.UUID, data: ProductCreate
    ) -> Product:
        if await ProductService._sku_taken(session, workspace_id, data.internal_sku):
            _conflict("Product SKU already exists")
        await ProductService._validate_product_refs(
            session,
            workspace_id,
            data.base_uom_id,
            data.category_id,
            data.brand_id,
        )
        product = Product(workspace_id=workspace_id, **data.model_dump())
        session.add(product)
        await ProductService._flush_or_conflict(session, "Product SKU already exists")
        logger.info("product.created", extra={"workspace_id": str(workspace_id)})
        return product

    @staticmethod
    async def _conversion_count(session: AsyncSession, product_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(ProductUOMConversion)
            .where(ProductUOMConversion.product_id == product_id)
        )
        return int(result.scalar_one())

    @staticmethod
    async def update_product(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        data: ProductUpdate,
    ) -> Product:
        product = await ProductService._require_live_product(
            session, product_id, workspace_id
        )
        updates = data.model_dump(exclude_unset=True)
        if "internal_sku" in updates and await ProductService._sku_taken(
            session, workspace_id, updates["internal_sku"], exclude_id=product_id
        ):
            _conflict("Product SKU already exists")
        if "base_uom_id" in updates and updates["base_uom_id"] != product.base_uom_id:
            if await ProductService._conversion_count(session, product_id) > 0:
                _bad_request(
                    "Cannot change base_uom_id while conversions exist. "
                    "Delete conversions first."
                )
        next_uom = updates.get("base_uom_id", product.base_uom_id)
        next_cat = (
            updates["category_id"] if "category_id" in updates else product.category_id
        )
        next_brand = updates["brand_id"] if "brand_id" in updates else product.brand_id
        await ProductService._validate_product_refs(
            session, workspace_id, next_uom, next_cat, next_brand
        )
        for field, value in updates.items():
            setattr(product, field, value)
        product.updated_at = _now()
        await ProductService._flush_or_conflict(session, "Product SKU already exists")
        return product

    @staticmethod
    async def _hard_delete_children(session: AsyncSession, product: Product) -> None:
        identifiers, conversions, prices = await ProductService._child_rows(
            session, product
        )
        for row in (*identifiers, *conversions, *prices):
            await session.delete(row)

    @staticmethod
    async def delete_product(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        product = await ProductService._require_live_product(
            session, product_id, workspace_id
        )
        await ProductService._hard_delete_children(session, product)
        product.deleted_at = _now()
        product.updated_at = _now()
        await session.flush()
        logger.info("product.soft_deleted", extra={"product_id": str(product_id)})

    # ----- Identifiers -----

    @staticmethod
    async def list_identifiers(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> List[ProductIdentifier]:
        await ProductService._require_live_product(session, product_id, workspace_id)
        result = await session.execute(
            select(ProductIdentifier).where(
                ProductIdentifier.product_id == product_id,
                ProductIdentifier.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_identifier(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        data: ProductIdentifierCreate,
    ) -> ProductIdentifier:
        await ProductService._require_live_product(session, product_id, workspace_id)
        ident_type = str(_enum_value(data.type))
        existing = (
            await session.execute(
                select(ProductIdentifier).where(
                    ProductIdentifier.workspace_id == workspace_id,
                    ProductIdentifier.type == ident_type,
                    ProductIdentifier.value == data.value,
                )
            )
        ).scalar_one_or_none()
        if existing:
            _conflict("Product identifier already exists")
        row = ProductIdentifier(
            workspace_id=workspace_id,
            product_id=product_id,
            type=ident_type,
            value=data.value,
        )
        session.add(row)
        await ProductService._flush_or_conflict(
            session, "Product identifier already exists"
        )
        return row

    @staticmethod
    async def delete_identifier(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        identifier_id: uuid.UUID,
    ) -> None:
        await ProductService._require_live_product(session, product_id, workspace_id)
        result = await session.execute(
            select(ProductIdentifier).where(
                ProductIdentifier.id == identifier_id,
                ProductIdentifier.product_id == product_id,
                ProductIdentifier.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            _not_found("Product identifier")
        await session.delete(row)
        await session.flush()

    # ----- Conversions -----

    @staticmethod
    async def list_conversions(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> List[ProductUOMConversionResponse]:
        product = await ProductService._require_live_product(
            session, product_id, workspace_id
        )
        result = await session.execute(
            select(ProductUOMConversion).where(
                ProductUOMConversion.product_id == product_id,
                ProductUOMConversion.workspace_id == workspace_id,
            )
        )
        return [
            ProductService._to_conversion_response(row, product.base_uom_id)
            for row in result.scalars().all()
        ]

    @staticmethod
    async def create_conversion(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        data: ProductUOMConversionCreate,
    ) -> ProductUOMConversionResponse:
        """Persist a per-product conversion vs the product's base UOM.

        Semantic: 1 to_uom = conversion_factor × base UOM. Body must not send
        from_uom_id (rejected at schema). Multi-hop resolve is not implemented.
        """
        product = await ProductService._require_live_product(
            session, product_id, workspace_id
        )
        if data.to_uom_id == product.base_uom_id:
            _bad_request(_CONVERSION_BASE_MSG)
        await ProductService._require_uom(session, data.to_uom_id, workspace_id)
        existing = (
            await session.execute(
                select(ProductUOMConversion).where(
                    ProductUOMConversion.product_id == product_id,
                    ProductUOMConversion.to_uom_id == data.to_uom_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            _conflict("Conversion for this to_uom_id already exists")
        row = ProductUOMConversion(
            workspace_id=workspace_id,
            product_id=product_id,
            to_uom_id=data.to_uom_id,
            conversion_factor=data.conversion_factor,
        )
        session.add(row)
        await ProductService._flush_or_conflict(
            session, "Conversion for this to_uom_id already exists"
        )
        return ProductService._to_conversion_response(row, product.base_uom_id)

    @staticmethod
    async def delete_conversion(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        conversion_id: uuid.UUID,
    ) -> None:
        await ProductService._require_live_product(session, product_id, workspace_id)
        result = await session.execute(
            select(ProductUOMConversion).where(
                ProductUOMConversion.id == conversion_id,
                ProductUOMConversion.product_id == product_id,
                ProductUOMConversion.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            _not_found("Product conversion")
        await session.delete(row)
        await session.flush()

    # ----- Prices -----

    @staticmethod
    async def list_prices(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> List[ProductPrice]:
        await ProductService._require_live_product(session, product_id, workspace_id)
        result = await session.execute(
            select(ProductPrice).where(
                ProductPrice.product_id == product_id,
                ProductPrice.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _assert_price_unique(
        session: AsyncSession, product_id: uuid.UUID, data: ProductPriceCreate
    ) -> None:
        price_type = str(_enum_value(data.price_type))
        if price_type == PriceType.DEFAULT_SALES.value:
            found = (
                await session.execute(
                    select(ProductPrice).where(
                        ProductPrice.product_id == product_id,
                        ProductPrice.price_type == PriceType.DEFAULT_SALES.value,
                    )
                )
            ).scalar_one_or_none()
            if found:
                _conflict("DEFAULT_SALES price already exists for this product")
            return
        if price_type == PriceType.TIER_1.value:
            found = (
                await session.execute(
                    select(ProductPrice).where(
                        ProductPrice.product_id == product_id,
                        ProductPrice.price_type == PriceType.TIER_1.value,
                        ProductPrice.min_quantity == data.min_quantity,
                    )
                )
            ).scalar_one_or_none()
            if found:
                _conflict("TIER_1 price already exists for this min_quantity")
            return
        rows = (
            (
                await session.execute(
                    select(ProductPrice).where(
                        ProductPrice.product_id == product_id,
                        ProductPrice.price_type == PriceType.CUSTOMER_SPECIFIC.value,
                        ProductPrice.client_id == data.client_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        new_min = _min_qty_key(data.min_quantity)
        for row in rows:
            if _min_qty_key(row.min_quantity) == new_min:
                _conflict(
                    "Customer-specific price already exists for this client "
                    "and quantity"
                )

    @staticmethod
    async def create_price(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        data: ProductPriceCreate,
    ) -> ProductPrice:
        await ProductService._require_live_product(session, product_id, workspace_id)
        if data.client_id is not None:
            await ProductService._get_live(
                session, Client, data.client_id, workspace_id, "Client"
            )
        await ProductService._assert_price_unique(session, product_id, data)
        row = ProductPrice(
            workspace_id=workspace_id,
            product_id=product_id,
            price_type=str(_enum_value(data.price_type)),
            currency=data.currency,
            price=data.price,
            client_id=data.client_id,
            min_quantity=data.min_quantity,
        )
        session.add(row)
        await session.flush()
        return row

    @staticmethod
    async def delete_price(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        price_id: uuid.UUID,
    ) -> None:
        await ProductService._require_live_product(session, product_id, workspace_id)
        result = await session.execute(
            select(ProductPrice).where(
                ProductPrice.id == price_id,
                ProductPrice.product_id == product_id,
                ProductPrice.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            _not_found("Product price")
        await session.delete(row)
        await session.flush()
