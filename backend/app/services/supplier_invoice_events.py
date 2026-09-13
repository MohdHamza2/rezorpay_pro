"""Supplier-invoice event emission helper — Wave 31 Item 2.6.

Dedicated AP-side helper (the AR ``AuditService`` contract stays untouched).
Events are staged with ``session.add`` only: they commit or roll back together
with the business mutation that describes them. This helper never commits,
never opens a transaction, and never alters financial or business state.
"""

import json
import uuid
from typing import Any, Dict, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.supplier_invoice_event import (
    SupplierInvoiceEvent,
    SupplierInvoiceEventType,
)

# Maximum metadata size in bytes (mirrors the AR AuditService discipline).
MAX_METADATA_SIZE = 1000


async def emit_event(
    session: AsyncSession,
    supplier_invoice_id: uuid.UUID,
    workspace_id: uuid.UUID,
    event_type: SupplierInvoiceEventType,
    actor_id: uuid.UUID,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SupplierInvoiceEvent:
    """Stage one immutable lifecycle event in the current transaction.

    Raises ``ValueError`` when metadata exceeds the size boundary. The caller
    owns commit/rollback; a failed mutation leaves no event row behind.
    """
    payload = metadata or {}
    encoded = json.dumps(payload, default=str)
    if len(encoded) > MAX_METADATA_SIZE:
        raise ValueError(
            f"Metadata too large ({len(encoded)} bytes). "
            f"Maximum allowed: {MAX_METADATA_SIZE} bytes. "
            "Store reference IDs only, never snapshots."
        )
    event = SupplierInvoiceEvent(
        supplier_invoice_id=supplier_invoice_id,
        workspace_id=workspace_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=new_status,
        actor_id=actor_id,
        metadata_log=payload,
    )
    session.add(event)
    return event
