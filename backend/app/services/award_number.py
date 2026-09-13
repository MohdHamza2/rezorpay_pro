"""Gapless RFQ award number generation service.

Mirrors RFQNumberService/SPONumberService/GRNNumberService: SELECT FOR UPDATE
on the workspace/year counter inside the caller's transaction, incremented
only when the award commits, so concurrent creates cannot collide or leave
gaps.

Format: AWD-2026-000001 (workspace-scoped, year-based).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.rfq_award_counter import RFQAwardCounter


class AwardNumberService:
    @staticmethod
    async def generate_award_number(
        session: AsyncSession, workspace_id: uuid.UUID
    ) -> str:
        """Generate a gapless, workspace-scoped award number."""
        year = datetime.now(timezone.utc).year
        result = await session.execute(
            select(RFQAwardCounter)
            .where(
                RFQAwardCounter.workspace_id == workspace_id,
                RFQAwardCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = RFQAwardCounter(
                workspace_id=workspace_id, year=year, last_number=1
            )
            session.add(counter)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(RFQAwardCounter)
                    .where(
                        RFQAwardCounter.workspace_id == workspace_id,
                        RFQAwardCounter.year == year,
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
