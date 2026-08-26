"""
Gapless Invoice Number Generation Service.

Ensures legally compliant invoice numbering with no gaps (required in EU/GST countries).
Uses row-level locking (FOR UPDATE) inside transactions to prevent race conditions.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice_counter import InvoiceCounter


class InvoiceNumberService:
    """
    Service for generating gapless invoice numbers.

    The "No Gaps" Guarantee:
    1. Counter row is locked with FOR UPDATE inside transaction
    2. Counter only increments when invoice successfully commits
    3. If transaction fails, counter rolls back (no gap created)

    Thread-Safe: Row locking ensures sequential number generation even under concurrent load.
    Handles concurrent first-counter creation via retry on IntegrityError.
    """

    @staticmethod
    async def generate_invoice_number(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """
        Generate a unique, gapless invoice number for the workspace.

        Format: INV-2026-0001 (Workspace-scoped, year-based)

        Args:
            session: Database session (must be in transaction context)
            workspace_id: UUID of the workspace
            year: Year for the invoice (defaults to current year)

        Returns:
            str: Formatted invoice number (e.g., "INV-2026-0001")

        Raises:
            Exception: If invoice number generation fails
        """
        if year is None:
            year = datetime.now().year

        # Retry loop to handle concurrent first-counter creation
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Lock the counter row with FOR UPDATE (prevents race conditions)
                result = await session.execute(
                    select(InvoiceCounter)
                    .where(InvoiceCounter.workspace_id == workspace_id)
                    .where(InvoiceCounter.year == year)
                    .with_for_update()  # <-- CRITICAL: Row-level lock
                )
                counter = result.scalar_one_or_none()

                if counter is None:
                    # First invoice for this workspace/year - create counter
                    counter = InvoiceCounter(
                        workspace_id=workspace_id, year=year, last_number=0
                    )
                    session.add(counter)
                    await session.flush()  # Persist counter before incrementing

                # Increment counter
                counter.last_number += 1

                # Generate formatted number
                invoice_number = f"INV-{year}-{counter.last_number:04d}"

                return invoice_number

            except IntegrityError:
                # Another transaction created the counter concurrently
                # Rollback and retry with SELECT FOR UPDATE (counter now exists)
                await session.rollback()
                if attempt == max_retries - 1:
                    raise  # Max retries exceeded
                continue  # Retry

    @staticmethod
    async def get_next_number_preview(
        session: AsyncSession, workspace_id: uuid.UUID, year: Optional[int] = None
    ) -> str:
        """
        Preview the next invoice number without consuming it.

        Use this for UI display before actual invoice creation.
        Note: This does NOT lock the row, so the actual number may differ
        if another invoice is created concurrently.

        Args:
            session: Database session
            workspace_id: UUID of the workspace
            year: Year for the invoice (defaults to current year)

        Returns:
            str: Preview of next invoice number
        """
        if year is None:
            year = datetime.now().year

        # No lock - just read current state
        result = await session.execute(
            select(InvoiceCounter)
            .where(InvoiceCounter.workspace_id == workspace_id)
            .where(InvoiceCounter.year == year)
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            next_number = 1
        else:
            next_number = counter.last_number + 1

        return f"INV-{year}-{next_number:04d}"
