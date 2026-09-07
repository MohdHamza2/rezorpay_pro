"""Email Engine schemas — Wave 26 (Phase 5)."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.email_log import EmailStatus


class EmailSendRequest(BaseModel):
    to_email: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=255)
    body_html: str = Field(..., min_length=1, description="HTML body of the email")
    bcc: Optional[List[EmailStr]] = Field(
        default=None, max_length=20, description="Optional BCC recipients"
    )
    linked_entity_type: Optional[str] = Field(
        default=None, max_length=50, description="Audit reference type"
    )
    linked_entity_id: Optional[UUID] = Field(
        default=None, description="Audit reference id (workspace-validated)"
    )


class EmailResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    from_email: str
    to_email: str
    bcc: List[str]
    subject: str
    status: EmailStatus
    simulated: bool
    resend_message_id: Optional[str] = None
    error_message: Optional[str] = None
    linked_entity_type: Optional[str] = None
    linked_entity_id: Optional[UUID] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailWebhookRequest(BaseModel):
    type: str = Field(
        ..., description="Resend webhook event name, e.g. email.delivered"
    )
    data: dict = Field(..., description="Webhook payload; data.id is the message id")
