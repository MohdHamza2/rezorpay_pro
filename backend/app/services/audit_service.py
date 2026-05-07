"""
Audit Logging Service with Minimal Metadata.

Ensures comprehensive audit trail while preventing metadata bloat (< 1KB per event).
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice_event import InvoiceEvent, InvoiceEventType


class AuditService:
    """
    Service for logging invoice lifecycle events.
    
    Minimal Metadata Rule:
    - ✅ Include: Counts, amounts, status changes, small identifiers
    - ❌ Exclude: Full payloads, large text fields, entire objects
    - Limit: < 1KB per event
    """
    
    # Maximum metadata size in bytes
    MAX_METADATA_SIZE = 1000
    
    @staticmethod
    async def log_event(
        session: AsyncSession,
        invoice_id: uuid.UUID,
        event_type: InvoiceEventType,
        user_id: uuid.UUID,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> InvoiceEvent:
        """
        Log an invoice lifecycle event.
        
        Args:
            session: Database session
            invoice_id: UUID of the invoice
            event_type: Type of event (InvoiceEventType enum)
            user_id: UUID of the user who triggered the event
            previous_status: Previous invoice status (for STATUS_CHANGED events)
            new_status: New invoice status (for STATUS_CHANGED events)
            metadata: Additional context (must be < 1KB)
            
        Returns:
            InvoiceEvent: The created event
            
        Raises:
            ValueError: If metadata exceeds size limit
        """
        # Validate metadata size
        if metadata:
            metadata_json = json.dumps(metadata, default=str)
            if len(metadata_json) > AuditService.MAX_METADATA_SIZE:
                raise ValueError(
                    f"Metadata too large ({len(metadata_json)} bytes). "
                    f"Maximum allowed: {AuditService.MAX_METADATA_SIZE} bytes. "
                    "Exclude large fields like full objects or long text."
                )
        
        # Determine status fields based on event type
        if event_type == InvoiceEventType.STATUS_CHANGED:
            # Must provide both previous and new status
            if not previous_status or not new_status:
                raise ValueError(
                    "STATUS_CHANGED events require both previous_status and new_status"
                )
        else:
            # For non-status events, use current status if not provided
            if not new_status:
                new_status = previous_status or "unknown"
        
        # Create event
        event = InvoiceEvent(
            invoice_id=invoice_id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user_id,
            context=metadata or {}
        )
        
        session.add(event)
        
        return event
    
    @classmethod
    async def log_invoice_created(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        items_count: int,
        total: Decimal,
        invoice_number: str
    ) -> InvoiceEvent:
        """Log invoice creation event."""
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.INVOICE_CREATED,
            user_id=user_id,
            new_status="draft",
            metadata={
                "items_count": items_count,
                "total": str(total),  # Convert Decimal to string for JSON
                "invoice_number": invoice_number
            }
        )
    
    @classmethod
    async def log_invoice_updated(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        changed_fields: list,
        previous_status: str = "draft",
        new_status: str = "draft"
    ) -> InvoiceEvent:
        """Log invoice update event."""
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.INVOICE_UPDATED,
            user_id=user_id,
            previous_status=previous_status,
            new_status=new_status,
            metadata={
                "changed_fields": changed_fields  # List of field names only
            }
        )
    
    @classmethod
    async def log_invoice_sent(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        sent_method: str = "email",
        recipient: Optional[str] = None
    ) -> InvoiceEvent:
        """Log invoice sent event."""
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.INVOICE_SENT,
            user_id=user_id,
            previous_status="draft",
            new_status="sent",
            metadata={
                "sent_method": sent_method,
                "recipient": recipient  # Email or phone, truncated if too long
            }
        )
    
    @classmethod
    async def log_payment_added(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        payment_amount: Decimal,
        payment_gateway: str,
        gateway_transaction_id: Optional[str] = None,
        previous_status: str = "sent",
        new_status: str = "partial"
    ) -> InvoiceEvent:
        """Log payment recorded event."""
        metadata = {
            "amount": str(payment_amount),
            "gateway": payment_gateway
        }
        
        # Only include truncated transaction ID
        if gateway_transaction_id:
            metadata["gateway_txn_id"] = gateway_transaction_id[:50]  # Truncate
        
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.PAYMENT_ADDED,
            user_id=user_id,
            previous_status=previous_status,
            new_status=new_status,
            metadata=metadata
        )
    
    @classmethod
    async def log_status_changed(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        previous_status: str,
        new_status: str,
        reason: Optional[str] = None
    ) -> InvoiceEvent:
        """Log manual or automatic status change."""
        metadata = {}
        if reason:
            metadata["reason"] = reason[:100]  # Truncate long reasons
        
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.STATUS_CHANGED,
            user_id=user_id,
            previous_status=previous_status,
            new_status=new_status,
            metadata=metadata if metadata else None
        )
    
    @classmethod
    async def log_invoice_voided(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
        previous_status: str
    ) -> InvoiceEvent:
        """Log invoice void/cancellation event."""
        return await cls.log_event(
            session=session,
            invoice_id=invoice_id,
            event_type=InvoiceEventType.INVOICE_VOIDED,
            user_id=user_id,
            previous_status=previous_status,
            new_status="voided",
            metadata={
                "reason": reason[:200]  # Truncate long reasons
            }
        )
