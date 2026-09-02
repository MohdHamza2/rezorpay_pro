"""Gapless tax debit-note numbers (TDN-YYYY-XXXX).

FTA tax document sequence. SELECT FOR UPDATE on tax_debit_note_counters.
Do not reuse invoice_counters or credit_note_counters. Soft-delete does not rewind.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.tax_debit_note import TaxDebitNoteCounter


class TaxDebitNoteNumberService:
    """SELECT FOR UPDATE counter for workspace/year TDN numbers."""

    @staticmethod
    async def generate_debit_note_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """Generate TDN-YYYY-XXXX inside the caller's transaction."""
        if year is None:
            year = datetime.now().year

        result = await session.execute(
            select(TaxDebitNoteCounter)
            .where(TaxDebitNoteCounter.workspace_id == workspace_id)
            .where(TaxDebitNoteCounter.year == year)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            try:
                async with session.begin_nested():
                    counter = TaxDebitNoteCounter(
                        workspace_id=workspace_id, year=year, last_sequence=0
                    )
                    session.add(counter)
                    await session.flush()
            except IntegrityError:
                result = await session.execute(
                    select(TaxDebitNoteCounter)
                    .where(TaxDebitNoteCounter.workspace_id == workspace_id)
                    .where(TaxDebitNoteCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_sequence += 1
        return f"TDN-{year}-{counter.last_sequence:04d}"
