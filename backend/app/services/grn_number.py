"""Gapless Goods Receipt Note (GRN) number generation service.

Mirrors EnquiryNumberService/SPONumberService: SELECT FOR UPDATE on the
workspace/year counter inside the caller's transaction, incremented only when
the GRN commits, so concurrent receives cannot collide or leave gaps.

Format: GRN-2026-000001 (workspace-scoped, year-based).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.grn_counter import GRNCounter


class GRNNumberService:
    @staticmethod
    async def generate_grn_number(
        session: AsyncSession, workspace_id: uuid.UUID
    ) -> str:
        """Generate a gapless, workspace-scoped GRN number."""
        year = datetime.now(timezone.utc).year
        result = await session.execute(
            select(GRNCounter)
            .where(
                GRNCounter.workspace_id == workspace_id,
                GRNCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = GRNCounter(workspace_id=workspace_id, year=year, last_number=1)
            session.add(counter)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(GRNCounter)
                    .where(
                        GRNCounter.workspace_id == workspace_id,
                        GRNCounter.year == year,
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
