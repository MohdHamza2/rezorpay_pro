"""Gapless Supplier Debit Note (SDN) number generation service.

Format: SDN-2026-0001 (workspace-scoped, year-based, 4-digit). Mirrors
GRNNumberService: SELECT FOR UPDATE + IntegrityError retry, increments only
when the caller's transaction commits.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.supplier_debit_note import SupplierDebitNoteCounter


class SupplierDebitNoteNumberService:
    @staticmethod
    async def generate_debit_note_number(
        session: AsyncSession, workspace_id: uuid.UUID
    ) -> str:
        year = datetime.now(timezone.utc).year
        result = await session.execute(
            select(SupplierDebitNoteCounter)
            .where(
                SupplierDebitNoteCounter.workspace_id == workspace_id,
                SupplierDebitNoteCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = SupplierDebitNoteCounter(
                workspace_id=workspace_id, year=year, last_number=1
            )
            session.add(counter)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(SupplierDebitNoteCounter)
                    .where(
                        SupplierDebitNoteCounter.workspace_id == workspace_id,
                        SupplierDebitNoteCounter.year == year,
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
