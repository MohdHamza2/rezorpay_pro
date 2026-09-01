"""Gapless tax credit-note numbers (CN-YYYY-XXXX).

FTA tax document sequence. SELECT FOR UPDATE on credit_note_counters.
Do not reuse invoice_counters. Soft-delete does not rewind.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.credit_note_counter import CreditNoteCounter


class CreditNoteNumberService:
    """SELECT FOR UPDATE counter for workspace/year CN numbers."""

    @staticmethod
    async def generate_credit_note_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """Generate CN-YYYY-XXXX inside the caller's transaction."""
        if year is None:
            year = datetime.now().year

        result = await session.execute(
            select(CreditNoteCounter)
            .where(CreditNoteCounter.workspace_id == workspace_id)
            .where(CreditNoteCounter.year == year)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            try:
                async with session.begin_nested():
                    counter = CreditNoteCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()
            except IntegrityError:
                result = await session.execute(
                    select(CreditNoteCounter)
                    .where(CreditNoteCounter.workspace_id == workspace_id)
                    .where(CreditNoteCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_number += 1
        return f"CN-{year}-{counter.last_number:04d}"
