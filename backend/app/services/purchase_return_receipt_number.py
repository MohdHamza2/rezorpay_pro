"""Purchase Return Receipt Number Service — Wave 31 Item 2.8.

Gapless counter for return receipts (RRN-YYYY-XXXX).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.purchase_return import PurchaseReturnReceiptCounter


class PurchaseReturnReceiptNumberService:
    @staticmethod
    async def generate_receipt_number(
        session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> str:
        counter = await PurchaseReturnReceiptNumberService._get_or_create_counter(
            session, workspace_id
        )
        counter.last_number += 1
        await session.flush()
        return f"RRN-{counter.year}-{counter.last_number:04d}"

    @staticmethod
    async def _get_or_create_counter(
        session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> PurchaseReturnReceiptCounter:
        current_year = datetime.now(timezone.utc).year

        result = await session.execute(
            select(PurchaseReturnReceiptCounter)
            .where(
                PurchaseReturnReceiptCounter.workspace_id == workspace_id,
                PurchaseReturnReceiptCounter.year == current_year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = PurchaseReturnReceiptCounter(
                workspace_id=workspace_id,
                year=current_year,
                last_number=0,
            )
            session.add(counter)
            await session.flush()

        return counter


purchase_return_receipt_number_service = PurchaseReturnReceiptNumberService()
