"""Gapless Purchase Return (PRN) number generation service.

Format: PRN-2026-0001 (workspace-scoped, year-based, 4-digit). Mirrors
GRNNumberService: SELECT FOR UPDATE + IntegrityError retry, increments only
when the caller's transaction commits.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.purchase_return import PurchaseReturnCounter


class PurchaseReturnNumberService:
    @staticmethod
    async def generate_purchase_return_number(
        session: AsyncSession, workspace_id: uuid.UUID
    ) -> str:
        year = datetime.now(timezone.utc).year
        result = await session.execute(
            select(PurchaseReturnCounter)
            .where(
                PurchaseReturnCounter.workspace_id == workspace_id,
                PurchaseReturnCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = PurchaseReturnCounter(
                workspace_id=workspace_id, year=year, last_number=1
            )
            session.add(counter)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(PurchaseReturnCounter)
                    .where(
                        PurchaseReturnCounter.workspace_id == workspace_id,
                        PurchaseReturnCounter.year == year,
                    )
                    .with_for_update()
                )
                counter = result.scalar_one()
                counter.last_number += 1
                await session.flush()
        else:
            counter.last_number += 1
            await session.flush()

        return counter.generate_number()
