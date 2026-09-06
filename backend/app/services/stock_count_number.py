"""Operational stock count number generation (SC-YYYY-XXXX).

Clones the transfer counter pattern: FOR UPDATE lock, IntegrityError
first-insert race retry, incremented only on the caller's commit.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.stock_count import StockCountCounter


class StockCountNumberService:
    """SELECT FOR UPDATE counter for workspace/year stock count numbers."""

    @staticmethod
    async def generate_count_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """Generate SC-YYYY-XXXX inside the caller's transaction."""
        if year is None:
            year = datetime.now().year

        result = await session.execute(
            select(StockCountCounter)
            .where(StockCountCounter.workspace_id == workspace_id)
            .where(StockCountCounter.year == year)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            try:
                async with session.begin_nested():
                    counter = StockCountCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()
            except IntegrityError:
                result = await session.execute(
                    select(StockCountCounter)
                    .where(StockCountCounter.workspace_id == workspace_id)
                    .where(StockCountCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_number += 1
        return f"SC-{year}-{counter.last_number:04d}"
