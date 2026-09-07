"""
WhatsApp comms schemas — Wave 27 (Phase 5).

Single send payload discriminated by `kind` (text | document). Document sends
accept NO `to_number`: the recipient is derived from the linked Client's
canonicalized phone (recipient authority, locked decision). Payloads are
`extra=forbid`, so stray/unknown fields surface as 422 VALIDATION_ERROR; a
document request that smuggles `to_number` is explicitly rejected in
``_check`` below.
"""

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.whatsapp_message import (
    WhatsAppDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
)

E164_PATTERN = r"^\+[1-9]\d{7,14}$"

DOCUMENT_TYPES = Literal["INVOICE", "QUOTATION", "AR_STATEMENT"]


class WhatsAppSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "document"]

    # text payload
    to_number: Optional[str] = Field(
        default=None, pattern=E164_PATTERN, min_length=8, max_length=16
    )
    message_body: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    # optional audit reference on TEXT sends (workspace-validated at service)
    linked_entity_type: Optional[str] = Field(default=None, max_length=50)
    linked_entity_id: Optional[uuid.UUID] = None

    # document payload
    document_type: Optional[DOCUMENT_TYPES] = None
    document_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    statement_from: Optional[date] = None
    statement_to: Optional[date] = None
    caption: Optional[str] = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _check(self) -> "WhatsAppSendRequest":
        if self.kind == "text":
            if not self.to_number or not self.message_body:
                raise ValueError(
                    "TEXT sends require to_number (E.164) and message_body"
                )
            if self.document_type is not None:
                raise ValueError(
                    "TEXT sends must not carry document_type/document_id fields"
                )
            return self
        # document
        if self.document_type is None:
            raise ValueError("DOCUMENT sends require document_type")
        if self.to_number is not None:
            raise ValueError(
                "to_number is not accepted on document sends; the recipient is "
                "derived from the linked Client's phone"
            )
        if self.document_type in ("INVOICE", "QUOTATION"):
            if self.document_id is None:
                raise ValueError(
                    f"document_id is required for {self.document_type} sends"
                )
        else:
            if self.client_id is None:
                raise ValueError("client_id is required for AR_STATEMENT sends")
            if self.statement_from is None or self.statement_to is None:
                raise ValueError(
                    "statement_from and statement_to are required for "
                    "AR_STATEMENT sends"
                )
        return self


class WhatsAppMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    direction: WhatsAppDirection
    message_type: WhatsAppMessageType

    to_number: Optional[str] = None
    from_number: Optional[str] = None
    message_body: Optional[str] = None
    caption: Optional[str] = None

    document_type: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    document_filename: Optional[str] = None
    media_id: Optional[str] = None
    statement_from: Optional[date] = None
    statement_to: Optional[date] = None

    linked_entity_type: Optional[str] = None
    linked_entity_id: Optional[uuid.UUID] = None

    status: WhatsAppMessageStatus
    whatsapp_message_id: Optional[str] = None
    simulated: bool

    provider_error_code: Optional[str] = None
    provider_error_category: Optional[str] = None
    error_message: Optional[str] = None

    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    received_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime
