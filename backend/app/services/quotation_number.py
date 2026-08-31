"""Operational quotation number generation (QUO-YYYY-XXXX).

Clones InvoiceNumberService against quotation_counters. Quotes are not FTA
tax invoices — this sequence is uniqueness, not legal gapless numbering.
Soft-delete does not rewind. Failed create rolls back with the transaction.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.quotation_counter import QuotationCounter


class QuotationNumberService:
    """SELECT FOR UPDATE counter for workspace/year quotation numbers."""

    @staticmethod
    async def generate_quotation_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """
        Generate QUO-YYYY-XXXX inside the caller's transaction.

        The counter row is locked with FOR UPDATE. Increment only commits with
        the quotation row.
        """
        if year is None:
            year = datetime.now().year

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await session.execute(
                    select(QuotationCounter)
                    .where(QuotationCounter.workspace_id == workspace_id)
                    .where(QuotationCounter.year == year)
                    .with_for_update()
                )
                counter = result.scalar_one_or_none()

                if counter is None:
                    counter = QuotationCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()

                counter.last_number += 1
                return f"QUO-{year}-{counter.last_number:04d}"

            except IntegrityError:
                await session.rollback()
                if attempt == max_retries - 1:
                    raise
                continue
