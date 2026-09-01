"""Volume / customer sales price resolution (WP-A).

Does not commit. Preview is read-only. Explicit document unit_price skips this.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import NoReturn, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.product import Product, ProductPrice
from app.schemas.common import ErrorCode, ErrorDetail
from app.schemas.products import PriceType, ResolvedPriceResponse
from app.services.line_money import money

logger = logging.getLogger(__name__)

AED = "AED"


@dataclass(frozen=True)
class ResolvedPrice:
    unit_price: Decimal
    currency: str
    price_type: str
    min_quantity: Optional[Decimal]
    price_id: uuid.UUID


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def _raise(
    http_status: int,
    code: str,
    message: str,
    field: Optional[str] = None,
) -> NoReturn:
    raise HTTPException(
        status_code=http_status,
        detail=ErrorDetail(code=code, message=message, field=field).model_dump(),
    )


def _min_qty(row: ProductPrice) -> Decimal:
    return Decimal("0") if row.min_quantity is None else _dec(row.min_quantity)


def _best_row(
    rows: Sequence[ProductPrice], quantity: Decimal
) -> Optional[ProductPrice]:
    eligible = [row for row in rows if quantity >= _min_qty(row)]
    if not eligible:
        return None
    eligible.sort(key=lambda row: (-_min_qty(row), row.id))
    return eligible[0]


def _no_list_price() -> NoReturn:
    _raise(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.NO_LIST_PRICE,
        "Product has no matching sales price for this quantity/client",
        "product_id",
    )


class PricingService:
    """CUSTOMER_SPECIFIC → TIER_1 → DEFAULT_SALES. AED rows only."""

    @staticmethod
    async def resolve(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        client_id: Optional[uuid.UUID],
        quantity: Decimal,
    ) -> ResolvedPrice:
        await PricingService._load_product(session, workspace_id, product_id)
        await PricingService._assert_client(session, workspace_id, client_id)
        PricingService._assert_quantity(quantity)
        rows = await PricingService._aed_prices(session, workspace_id, product_id)
        winner = PricingService._pick(rows, client_id, _dec(quantity))
        if winner is None:
            _no_list_price()
        return PricingService._to_resolved(winner)

    @staticmethod
    async def preview(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        client_id: Optional[uuid.UUID],
        quantity: Decimal,
    ) -> ResolvedPriceResponse:
        product = await PricingService._load_product(session, workspace_id, product_id)
        if not product.is_active:
            _raise(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot add an inactive product",
                "product_id",
            )
        resolved = await PricingService.resolve(
            session, workspace_id, product_id, client_id, quantity
        )
        return PricingService._to_response(product_id, client_id, quantity, resolved)

    @staticmethod
    async def _load_product(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> Product:
        result = await session.execute(
            select(Product).where(
                Product.id == product_id,
                Product.workspace_id == workspace_id,
                Product.deleted_at.is_(None),
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            _raise(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Product not found")
        return product

    @staticmethod
    async def _assert_client(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: Optional[uuid.UUID],
    ) -> None:
        if client_id is None:
            return
        result = await session.execute(
            select(Client.id).where(
                Client.id == client_id,
                Client.workspace_id == workspace_id,
                Client.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            _raise(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Client not found")

    @staticmethod
    def _assert_quantity(quantity: Decimal) -> None:
        if _dec(quantity) <= 0:
            _raise(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "quantity must be greater than 0",
                "quantity",
            )

    @staticmethod
    async def _aed_prices(
        session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductPrice]:
        result = await session.execute(
            select(ProductPrice).where(
                ProductPrice.workspace_id == workspace_id,
                ProductPrice.product_id == product_id,
                ProductPrice.currency == AED,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _pick(
        rows: Sequence[ProductPrice],
        client_id: Optional[uuid.UUID],
        quantity: Decimal,
    ) -> Optional[ProductPrice]:
        if client_id is not None:
            customer = [
                row
                for row in rows
                if row.price_type == PriceType.CUSTOMER_SPECIFIC.value
                and row.client_id == client_id
            ]
            found = _best_row(customer, quantity)
            if found is not None:
                return found
        tier = [
            row
            for row in rows
            if row.price_type == PriceType.TIER_1.value and row.client_id is None
        ]
        found = _best_row(tier, quantity)
        if found is not None:
            return found
        listed = [
            row
            for row in rows
            if row.price_type == PriceType.DEFAULT_SALES.value and row.client_id is None
        ]
        return _best_row(listed, quantity)

    @staticmethod
    def _to_resolved(row: ProductPrice) -> ResolvedPrice:
        logger.info(
            "price_resolved",
            extra={
                "product_id": str(row.product_id),
                "price_type": row.price_type,
                "workspace_id": str(row.workspace_id),
            },
        )
        return ResolvedPrice(
            unit_price=money(_dec(row.price)),
            currency=AED,
            price_type=row.price_type,
            min_quantity=row.min_quantity,
            price_id=row.id,
        )

    @staticmethod
    def _to_response(
        product_id: uuid.UUID,
        client_id: Optional[uuid.UUID],
        quantity: Decimal,
        resolved: ResolvedPrice,
    ) -> ResolvedPriceResponse:
        return ResolvedPriceResponse(
            product_id=product_id,
            client_id=client_id,
            quantity=money(_dec(quantity)),
            unit_price=resolved.unit_price,
            currency=resolved.currency,
            price_type=resolved.price_type,
            min_quantity=resolved.min_quantity,
            price_id=resolved.price_id,
        )
