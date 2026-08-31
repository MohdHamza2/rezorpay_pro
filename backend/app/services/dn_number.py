"""Operational delivery-note number generation (DN-YYYY-XXXX).

Clones LPO/quote counters. Delivery notes are not tax invoices —
this sequence is uniqueness, not legal gapless numbering.
Soft-delete does not rewind. Failed create rolls back with the transaction.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.dn_counter import DnCounter


class DnNumberService:
    """SELECT FOR UPDATE counter for workspace/year DN numbers."""

    @staticmethod
    async def generate_dn_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """Generate DN-YYYY-XXXX inside the caller's transaction."""
        if year is None:
            year = datetime.now().year

        result = await session.execute(
            select(DnCounter)
            .where(DnCounter.workspace_id == workspace_id)
            .where(DnCounter.year == year)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            try:
                async with session.begin_nested():
                    counter = DnCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()
            except IntegrityError:
                result = await session.execute(
                    select(DnCounter)
                    .where(DnCounter.workspace_id == workspace_id)
                    .where(DnCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_number += 1
        return f"DN-{year}-{counter.last_number:04d}"
