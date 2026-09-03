import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enquiry import EnquirySource, EnquiryStatus


class EnquiryItemBase(BaseModel):
    product_id: Optional[uuid.UUID] = None
    description: str
    quantity_requested: Decimal
    uom_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class EnquiryItemCreate(EnquiryItemBase):
    pass


class EnquiryItemRead(EnquiryItemBase):
    id: uuid.UUID
    enquiry_id: uuid.UUID

    class Config:
        from_attributes = True


class EnquiryBase(BaseModel):
    client_id: Optional[uuid.UUID] = None
    source: EnquirySource = EnquirySource.MANUAL
    
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_email: Optional[str] = None
    
    items_description: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    
    notes: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None


class EnquiryCreate(EnquiryBase):
    items: List[EnquiryItemCreate] = []


class EnquiryUpdate(BaseModel):
    client_id: Optional[uuid.UUID] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_email: Optional[str] = None
    items_description: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None


class EnquiryStatusUpdate(BaseModel):
    status: EnquiryStatus


class EnquiryRead(EnquiryBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    enquiry_number: str
    status: EnquiryStatus
    created_at: datetime
    updated_at: datetime
    
    items: List[EnquiryItemRead] = []

    class Config:
        from_attributes = True


class EnquiryListResponse(BaseModel):
    items: List[EnquiryRead]
    total: int
    page: int
    size: int
