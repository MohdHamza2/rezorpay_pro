"""Supplier ↔ product link CRUD — Wave 31 Item 2.4.

Manages the ``SupplierProduct`` relationship rows (supplier-specific SKU,
lead time, MOQ). Follows the product-child CRUD conventions: workspace +
parent scoping on every operation, 404 for foreign/deleted/mismatched
resources, IntegrityError → 409 backstop, hard-delete of the link row only.

Scope notes (locked):
- Linking is master-data CRUD and is NOT gated on supplier status: ACTIVE,
  INACTIVE, and HOLD suppliers may all carry product links.
- No upper bounds, no SKU-uniqueness rules beyond the (supplier, product)
  pair constraint, and no cross-checks against SPO/GRN/SI quantities.
- No consumer reads these rows yet (RFQ/SI matching do not use them);
  this service only persists and serves the links themselves.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException, status

from app.models.product import Product
from app.models.supplier import Supplier, SupplierProduct
from app.schemas.suppliers import SupplierProductCreate


class SupplierProductService:
    @staticmethod
    async def _require_live_supplier(
        session: AsyncSession, supplier_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Supplier:
        result = await session.execute(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.workspace_id == workspace_id,
                Supplier.deleted_at.is_(None),
            )
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
            )
        return supplier

    @staticmethod
    async def _require_live_product(
        session: AsyncSession, product_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Product:
        result = await session.execute(
            select(Product).where(
                Product.id == product_id,
                Product.workspace_id == workspace_id,
                Product.deleted_at.is_(None),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
            )
        return product

    @staticmethod
    async def list_links(
        session: AsyncSession, workspace_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierProduct]:
        await SupplierProductService._require_live_supplier(
            session, supplier_id, workspace_id
        )
        result = await session.execute(
            select(SupplierProduct)
            .where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.workspace_id == workspace_id,
            )
            .order_by(SupplierProduct.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_link(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_id: uuid.UUID,
        data: SupplierProductCreate,
    ) -> SupplierProduct:
        await SupplierProductService._require_live_supplier(
            session, supplier_id, workspace_id
        )
        await SupplierProductService._require_live_product(
            session, data.product_id, workspace_id
        )
        existing = (
            await session.execute(
                select(SupplierProduct).where(
                    SupplierProduct.supplier_id == supplier_id,
                    SupplierProduct.product_id == data.product_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier product link already exists",
            )
        row = SupplierProduct(
            workspace_id=workspace_id,
            supplier_id=supplier_id,
            product_id=data.product_id,
            supplier_sku=data.supplier_sku,
            lead_time_days=data.lead_time_days,
            moq=data.moq,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier product link already exists",
            )
        return row

    @staticmethod
    async def delete_link(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> None:
        await SupplierProductService._require_live_supplier(
            session, supplier_id, workspace_id
        )
        await SupplierProductService._require_live_product(
            session, product_id, workspace_id
        )
        result = await session.execute(
            select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == product_id,
                SupplierProduct.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplier product link not found",
            )
        await session.delete(row)
        await session.flush()
