"""
AR Aging Service — Wave 29 (Phase 6).

Workspace-wide AR aging, a symmetric counterpart to
`supplier_payment_service.ap_aging` (AP aging, Wave 22).

Locked semantics (see `architecture/wave-reports-dashboard-addendum.md` §2.3):
- Rows = currently-open invoices: `status IN AR_STATUSES` (SENT, PARTIALLY_PAID,
  OVERDUE), `deleted_at IS NULL`, `balance_due > 0` — exactly mirroring the AP
  open set (`open_ap_invoices` applies the same `balance_due > 0` guard).
- `as_of` resolves to the literal provided date (or today); a future date is
  rejected with 422. `as_of` moves bucket boundaries / `days_overdue` only —
  it does NOT reconstruct historical balances or lifecycle status.
- Bucketing reuses the live `aging_buckets` / `_bucket_key` helpers from
  `credit_control_service` — no second implementation of the aging rules.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice
from app.schemas.common import ErrorCode
from app.services.credit_control_service import (
    AR_STATUSES,
    _bucket_key,
    aging_buckets,
    utc_today,
)
from app.services.customer_po_support import raise_error
from app.services.line_money import money

ZERO = Decimal("0.00")


async def _open_ar_invoices(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    client_id: Optional[uuid.UUID] = None,
) -> list[Invoice]:
    """Open AR = open-status invoices with a balance (mirror of AP open set).

    `Invoice.balance_due` is a computed property (`total - paid - credited +
    debited`), so the `balance_due > 0` guard cannot be expressed in SQL —
    apply it post-load, exactly mirroring the AP open-set semantics.
    """
    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(AR_STATUSES),
        )
    )
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    invoices = (await session.execute(stmt)).scalars().all()
    return [inv for inv in invoices if inv.balance_due > ZERO]


async def _client_names(
    session: AsyncSession, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Client]:
    if not ids:
        return {}
    result = await session.execute(
        select(Client).where(Client.workspace_id == workspace_id, Client.id.in_(ids))
    )
    return {c.id: c for c in result.scalars().all()}


async def ar_aging(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    as_of: Optional[date] = None,
    client_id: Optional[uuid.UUID] = None,
    view: str = "summary",
) -> dict:
    """AR aging report: summary | detail | by_customer."""
    resolved = as_of or utc_today()
    if resolved > utc_today():
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "as_of cannot be after today",
            "as_of",
        )

    if client_id is not None and view == "by_customer":
        raise_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "client_id cannot be combined with view=by_customer",
            "client_id",
        )

    invoices = await _open_ar_invoices(session, workspace_id, client_id)
    buckets = aging_buckets(invoices, resolved)
    outstanding = money(sum((inv.balance_due for inv in invoices), ZERO))

    if view == "detail":
        clients = await _client_names(
            session, workspace_id, [inv.client_id for inv in invoices]
        )
        rows = [
            {
                "client_id": inv.client_id,
                "client_name": (
                    clients.get(inv.client_id).name
                    if clients.get(inv.client_id)
                    else ""
                ),
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "issue_date": inv.issue_date,
                "due_date": inv.due_date,
                "days_overdue": max(0, (resolved - inv.due_date).days),
                "balance_due": inv.balance_due,
                "bucket": _bucket_key((resolved - inv.due_date).days),
            }
            for inv in invoices
        ]
        return {
            "as_of": resolved,
            "total_outstanding": outstanding,
            "buckets": buckets,
            "invoices": rows,
        }

    if view == "by_customer":
        per_client: dict[uuid.UUID, list[Invoice]] = {}
        for inv in invoices:
            per_client.setdefault(inv.client_id, []).append(inv)
        clients = await _client_names(session, workspace_id, list(per_client.keys()))
        rows = []
        for cid, invs in per_client.items():
            cli = clients.get(cid)
            rows.append(
                {
                    "client": {
                        "id": cid,
                        "name": cli.name if cli else "",
                    },
                    "total_outstanding": money(
                        sum((i.balance_due for i in invs), ZERO)
                    ),
                    "buckets": aging_buckets(invs, resolved),
                }
            )
        rows.sort(key=lambda r: r["client"]["name"])
        return {
            "as_of": resolved,
            "total_outstanding": outstanding,
            "buckets": buckets,
            "customers": rows,
        }

    client_ids = {inv.client_id for inv in invoices}
    return {
        "as_of": resolved,
        "client_count": len(client_ids),
        "invoice_count": len(invoices),
        "total_outstanding": outstanding,
        "buckets": buckets,
    }
