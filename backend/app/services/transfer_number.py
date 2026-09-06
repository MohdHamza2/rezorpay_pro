"""Operational stock transfer number generation (ST-YYYY-XXXX).

Clones the DN/LPO counter pattern: FOR UPDATE lock, IntegrityError
first-insert race retry, incremented only on the caller's commit.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.stock_transfer import StockTransferCounter


class TransferNumberService:
    """SELECT FOR UPDATE counter for workspace/year stock transfer numbers."""

    @staticmethod
    async def generate_transfer_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """Generate ST-YYYY-XXXX inside the caller's transaction."""
        if year is None:
            year = datetime.now().year

        result = await session.execute(
            select(StockTransferCounter)
            .where(StockTransferCounter.workspace_id == workspace_id)
            .where(StockTransferCounter.year == year)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            try:
                async with session.begin_nested():
                    counter = StockTransferCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()
            except IntegrityError:
                result = await session.execute(
                    select(StockTransferCounter)
                    .where(StockTransferCounter.workspace_id == workspace_id)
                    .where(StockTransferCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_number += 1
        return f"ST-{year}-{counter.last_number:04d}"
