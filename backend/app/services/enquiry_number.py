import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.enquiry_counter import EnquiryCounter


class EnquiryNumberService:
    @staticmethod
    async def generate_enquiry_number(
        session: AsyncSession, workspace_id: uuid.UUID
    ) -> str:
        """
        Generate gapless enquiry number using FOR UPDATE locking.
        """
        year = datetime.now(timezone.utc).year
        result = await session.execute(
            select(EnquiryCounter)
            .where(
                EnquiryCounter.workspace_id == workspace_id,
                EnquiryCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            counter = EnquiryCounter(workspace_id=workspace_id, year=year, last_number=1)
            session.add(counter)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(EnquiryCounter)
                    .where(
                        EnquiryCounter.workspace_id == workspace_id,
                        EnquiryCounter.year == year,
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
