import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import status
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enquiry import Enquiry, EnquiryStatus
from app.models.enquiry_item import EnquiryItem
from app.models.quotation import Quotation
from app.schemas.common import ErrorCode
from app.schemas.enquiry import EnquiryCreate, EnquiryUpdate
from app.services.enquiry_number import EnquiryNumberService
from app.services.quotation_service import QuotationService


def raise_error(status_code: int, code: ErrorCode, msg: str) -> None:
    from fastapi import HTTPException
    raise HTTPException(status_code=status_code, detail={"code": code.value if hasattr(code, "value") else str(code), "message": msg})


class EnquiryService:
    @staticmethod
    async def get_visible(
        session: AsyncSession,
        enquiry_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Optional[Enquiry]:
        query = (
            select(Enquiry)
            .options(selectinload(Enquiry.items))
            .where(Enquiry.id == enquiry_id)
            .where(Enquiry.workspace_id == workspace_id)
            .where(Enquiry.deleted_at.is_(None))
        )
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: EnquiryCreate,
    ) -> Enquiry:
        # Check WhatsApp deduplication
        if data.whatsapp_message_id:
            result = await session.execute(
                select(Enquiry).where(
                    Enquiry.workspace_id == workspace_id,
                    Enquiry.whatsapp_message_id == data.whatsapp_message_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        number = await EnquiryNumberService.generate_enquiry_number(
            session, workspace_id
        )

        enquiry = Enquiry(
            workspace_id=workspace_id,
            enquiry_number=number,
            client_id=data.client_id,
            source=data.source,
            status=EnquiryStatus.NEW,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_whatsapp=data.contact_whatsapp,
            contact_email=data.contact_email,
            items_description=data.items_description,
            whatsapp_message_id=data.whatsapp_message_id,
            notes=data.notes,
            assigned_to=data.assigned_to,
        )
        session.add(enquiry)
        await session.flush()

        for item_data in data.items:
            item = EnquiryItem(
                enquiry_id=enquiry.id,
                product_id=item_data.product_id,
                description=item_data.description,
                quantity_requested=item_data.quantity_requested,
                uom_id=item_data.uom_id,
                notes=item_data.notes,
            )
            session.add(item)

        await session.flush()

        query = (
            select(Enquiry)
            .options(selectinload(Enquiry.items))
            .where(Enquiry.id == enquiry.id)
        )
        result = await session.execute(query)
        return result.scalar_one()

    @staticmethod
    async def update(
        session: AsyncSession,
        enquiry: Enquiry,
        user_id: uuid.UUID,
        data: EnquiryUpdate,
    ) -> Enquiry:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(enquiry, field, value)

        enquiry.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return enquiry

    @staticmethod
    async def convert_to_quotation(
        session: AsyncSession,
        enquiry: Enquiry,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Tuple[Quotation, bool]:
        """Convert enquiry to quotation. Returns (quotation, created)."""
        if enquiry.status == EnquiryStatus.CLOSED:
            raise_error(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot convert a closed enquiry.",
            )

        if not enquiry.client_id:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Enquiry must be associated with a client before converting to quotation.",
            )

        # Map enquiry items to quotation items format
        items_data = []
        for item in enquiry.items:
            items_data.append(
                {
                    "product_id": item.product_id,
                    "description": item.description,
                    "quantity": item.quantity_requested,
                    "uom_id": item.uom_id,
                    "unit_price": "0",  # Prices to be filled in later
                    "tax_rate": "0",
                }
            )
            
        # Also include raw description as a fallback item if there are no structured items
        if not items_data and enquiry.items_description:
            items_data.append(
                {
                    "description": f"FROM ENQUIRY: {enquiry.items_description}",
                    "quantity": "1",
                    "unit_price": "0",
                    "tax_rate": "0",
                }
            )

        if not items_data:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.VALIDATION_ERROR,
                "Cannot convert enquiry with no items or description.",
            )

        quotation = await QuotationService.create(
            session=session,
            workspace_id=workspace_id,
            client_id=enquiry.client_id,
            user_id=user_id,
            quotation_date=None,
            valid_until=None,
            currency="AED",
            notes=f"Converted from Enquiry {enquiry.enquiry_number}\n{enquiry.notes or ''}",
            items=items_data,
        )

        enquiry.status = EnquiryStatus.QUOTED
        enquiry.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return quotation, True
