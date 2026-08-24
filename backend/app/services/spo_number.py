"""
Gapless Supplier Purchase Order (SPO) number generation service.

Mirrors InvoiceNumberService: uses row-level locking (FOR UPDATE) on the
workspace/year counter inside the transaction so concurrent SPO creates cannot
collide or leave gaps. The counter is only committed alongside the SPO insert,
so a rolled-back transaction leaves no gap.

Format: SPO-2026-000001 (workspace-scoped, year-based).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.spo_counter import SPOCounter


class SPONumberService:
    """Service for generating gapless, workspace-scoped SPO numbers."""

    @staticmethod
    async def generate_spo_number(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        year: Optional[int] = None,
    ) -> str:
        """
        Generate a unique, gapless SPO number for the workspace.

        The counter row is locked with FOR UPDATE inside the caller's transaction
        and only increments when the SPO successfully commits.
        """
        if year is None:
            year = datetime.now().year

        # Lock the counter row with FOR UPDATE (prevents race conditions)
        result = await session.execute(
            select(SPOCounter)
            .where(SPOCounter.workspace_id == workspace_id)
            .where(SPOCounter.year == year)
            .with_for_update()  # <-- CRITICAL: row-level lock
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            # First SPO for this workspace/year - create counter
            counter = SPOCounter(workspace_id=workspace_id, year=year, last_number=0)
            session.add(counter)

        counter.last_number += 1
        return f"SPO-{year}-{counter.last_number:06d}"
