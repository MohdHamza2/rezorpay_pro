"""Wave 28 — UAE VAT Compliance Pack export (read-only aggregation).

No writes, no Alembic, no FX conversion. Sales/CN/TDN amounts are AED by
construction; the input summary aggregates AED supplier invoices only, while
non-AED supplier invoices stay listed in `purchase_invoices.csv` and surface
in the manifest `warnings`. Supplier `invoice_date` business dates are rendered
in Gulf Standard Time (fixed UTC+4, no DST) — never the driver-UTC `.date()`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.models.client import Client
from app.models.credit_note import CreditNote, CreditNoteStatus
from app.models.credit_note_item import CreditNoteItem
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.supplier import Supplier
from app.models.supplier_invoice import (
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierInvoiceStatus,
)
from app.models.tax_debit_note import (
    TaxDebitNote,
    TaxDebitNoteItem,
    TaxDebitNoteStatus,
)
from app.models.workspace import Workspace
from app.services.ar_statement_service import (
    assert_from_not_after_to,
    assert_range_not_too_long,
    in_period,
)
from app.services.line_money import money

logger = logging.getLogger(__name__)

AED = "AED"
ZERO = Decimal("0.00")

# Gulf Standard Time — fixed UTC+4, no DST (stdlib fixed offset; no tzdata).
GST = timezone(timedelta(hours=4))

OUTPUT_INVOICE_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)

FILES = [
    "sales_invoices.csv",
    "invoice_lines.csv",
    "credit_notes.csv",
    "tax_debit_notes.csv",
    "purchase_invoices.csv",
    "vat_summary.csv",
]
EXCLUDED_STATUSES_TEXT = (
    "DRAFT invoices / DRAFT credit notes / DRAFT TDN / "
    "CANCELLED invoices / CANCELLED supplier invoices"
)


def business_date(value: datetime) -> date:
    """GST calendar date of a stored timestamptz instant.

    The asyncpg driver returns timestamptz as UTC; naive values assumed UTC.
    Never `.date()` the UTC value for a compliance window — an off-hour Gulf
    timestamp would shift a calendar day.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(GST).date()


async def _scalars(session: AsyncSession, statement):
    result = await session.execute(statement)
    return list(result.scalars().all())


async def _load_invoices(session: AsyncSession, workspace_id: UUID) -> list[Invoice]:
    return await _scalars(
        session,
        select(Invoice)
        .where(Invoice.workspace_id == workspace_id)
        .where(Invoice.deleted_at.is_(None))
        .where(Invoice.status.in_(OUTPUT_INVOICE_STATUSES)),
    )


async def _load_credit_notes(
    session: AsyncSession, workspace_id: UUID
) -> list[CreditNote]:
    return await _scalars(
        session,
        select(CreditNote)
        .where(CreditNote.workspace_id == workspace_id)
        .where(CreditNote.status == CreditNoteStatus.ISSUED)
        .where(CreditNote.deleted_at.is_(None)),
    )


async def _load_debit_notes(
    session: AsyncSession, workspace_id: UUID
) -> list[TaxDebitNote]:
    return await _scalars(
        session,
        select(TaxDebitNote)
        .where(TaxDebitNote.workspace_id == workspace_id)
        .where(TaxDebitNote.status == TaxDebitNoteStatus.ISSUED)
        .where(TaxDebitNote.deleted_at.is_(None)),
    )


async def _load_supplier_invoices(
    session: AsyncSession, workspace_id: UUID
) -> list[SupplierInvoice]:
    return await _scalars(
        session,
        select(SupplierInvoice)
        .where(SupplierInvoice.workspace_id == workspace_id)
        .where(SupplierInvoice.status != SupplierInvoiceStatus.CANCELLED),
    )


async def _load_client_map(
    session: AsyncSession, client_ids: set[UUID]
) -> dict[UUID, Client]:
    if not client_ids:
        return {}
    clients = await _scalars(session, select(Client).where(Client.id.in_(client_ids)))
    return {client.id: client for client in clients}


async def _load_supplier_map(
    session: AsyncSession, supplier_ids: set[UUID]
) -> dict[UUID, Supplier]:
    if not supplier_ids:
        return {}
    suppliers = await _scalars(
        session, select(Supplier).where(Supplier.id.in_(supplier_ids))
    )
    return {supplier.id: supplier for supplier in suppliers}


async def _load_children(session, model, fk_column, parent_ids: Sequence[UUID]):
    if not parent_ids:
        return []
    return await _scalars(session, select(model).where(fk_column.in_(parent_ids)))


def buyer_name(note, clients: dict[UUID, Client]) -> Optional[str]:
    snapshot = getattr(note, "buyer_name_snapshot", None)
    if snapshot:
        return snapshot
    client = clients.get(note.client_id)
    return client.name if client else None


def buyer_trn(note, clients: dict[UUID, Client]) -> Optional[str]:
    snapshot = getattr(note, "buyer_trn_snapshot", None)
    if snapshot:
        return snapshot
    client = clients.get(note.client_id)
    return client.tax_id if client else None


def _bucket(buckets: dict[Decimal, list], rate: Decimal) -> list:
    if rate not in buckets:
        buckets[rate] = [ZERO, ZERO, 0]
    return buckets[rate]


def _fmt_cell(value) -> str:
    """CSV cell rendering: 2dp decimals, ISO dates, '' for None."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _csv_text(headers: list[str], rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_fmt_cell(row.get(column)) for column in headers])
    return buffer.getvalue()


async def build_report(
    session: AsyncSession,
    workspace: Workspace,
    period_from: date,
    period_to: date,
) -> dict:
    """Assemble the full pack payload (manifest + six datasets). Read-only."""
    assert_from_not_after_to(period_from, period_to)
    assert_range_not_too_long(period_from, period_to)

    invoices = [i for i in await _load_invoices(session, workspace.id)]
    invoices = [i for i in invoices if in_period(i.issue_date, period_from, period_to)]
    invoices.sort(key=lambda i: (i.issue_date, i.invoice_number, str(i.id)))

    credit_notes = [
        cn
        for cn in await _load_credit_notes(session, workspace.id)
        if in_period(cn.issue_date, period_from, period_to)
    ]
    credit_notes.sort(key=lambda cn: (cn.issue_date, cn.credit_note_number, str(cn.id)))

    tax_debit_notes = [
        t
        for t in await _load_debit_notes(session, workspace.id)
        if in_period(t.issue_date, period_from, period_to)
    ]
    tax_debit_notes.sort(key=lambda t: (t.issue_date, t.debit_note_number, str(t.id)))

    supplier_invoices = [
        si
        for si in await _load_supplier_invoices(session, workspace.id)
        if in_period(business_date(si.invoice_date), period_from, period_to)
    ]
    supplier_invoices.sort(
        key=lambda si: (
            business_date(si.invoice_date),
            si.supplier_invoice_number,
            str(si.id),
        )
    )

    client_ids = {i.client_id for i in invoices}
    client_ids |= {cn.client_id for cn in credit_notes}
    client_ids |= {t.client_id for t in tax_debit_notes}
    clients = await _load_client_map(session, client_ids)

    supplier_ids = {si.supplier_id for si in supplier_invoices}
    suppliers = await _load_supplier_map(session, supplier_ids)

    invoice_items = await _load_children(
        session, InvoiceItem, InvoiceItem.invoice_id, [i.id for i in invoices]
    )
    cn_items = await _load_children(
        session,
        CreditNoteItem,
        CreditNoteItem.credit_note_id,
        [c.id for c in credit_notes],
    )
    tdn_items = await _load_children(
        session,
        TaxDebitNoteItem,
        TaxDebitNoteItem.tax_debit_note_id,
        [t.id for t in tax_debit_notes],
    )
    si_items = await _load_children(
        session,
        SupplierInvoiceItem,
        SupplierInvoiceItem.supplier_invoice_id,
        [si.id for si in supplier_invoices],
    )

    sales_rows: list[dict] = []
    for inv in invoices:
        sales_rows.append(
            {
                "invoice_number": inv.invoice_number,
                "issue_date": inv.issue_date,
                "supply_date": inv.supply_date,
                "due_date": inv.due_date,
                "invoice_kind": inv.invoice_kind,
                "status": inv.status.value,
                "currency": inv.currency,
                "client_name": buyer_name(inv, clients),
                "client_trn": buyer_trn(inv, clients),
                "subtotal": inv.subtotal,
                "tax_amount": inv.tax_amount,
                "total_amount": inv.total_amount,
                "seller_trn": inv.seller_trn_snapshot or workspace.trn,
            }
        )

    number_of = {inv.id: inv.invoice_number for inv in invoices}
    line_rows: list[dict] = []
    for item in sorted(
        invoice_items, key=lambda it: (number_of[it.invoice_id], str(it.id))
    ):
        line_rows.append(
            {
                "invoice_number": number_of[item.invoice_id],
                "description": item.description,
                "sku_snapshot": item.sku_snapshot,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "tax_rate": item.tax_rate,
                "discount_amount": item.discount_amount,
                "line_net": item.line_net,
                "tax_amount": item.tax_amount,
                "total_price": item.total_price,
            }
        )

    credit_rows: list[dict] = []
    for cn in credit_notes:
        credit_rows.append(
            {
                "credit_note_number": cn.credit_note_number,
                "issue_date": cn.issue_date,
                "original_invoice_number": cn.original_invoice_number,
                "reason": cn.reason.value,
                "status": cn.status.value,
                "client_name": buyer_name(cn, clients),
                "client_trn": buyer_trn(cn, clients),
                "subtotal": cn.subtotal,
                "tax_amount": cn.tax_amount,
                "total_amount": cn.total_amount,
            }
        )

    debit_rows: list[dict] = []
    for t in tax_debit_notes:
        debit_rows.append(
            {
                "debit_note_number": t.debit_note_number,
                "issue_date": t.issue_date,
                "original_invoice_number": t.original_invoice_number,
                "reason": t.reason,
                "status": t.status,
                "client_name": buyer_name(t, clients),
                "client_trn": buyer_trn(t, clients),
                "subtotal": t.subtotal,
                "tax_amount": t.tax_amount,
                "total_amount": t.total_amount,
            }
        )

    purchase_rows: list[dict] = []
    for si in supplier_invoices:
        supplier = suppliers.get(si.supplier_id)
        purchase_rows.append(
            {
                "supplier_invoice_number": si.supplier_invoice_number,
                "invoice_date": business_date(si.invoice_date),
                "supplier_name": supplier.name if supplier else None,
                "supplier_trn": supplier.trn if supplier else None,
                "currency": si.currency,
                "subtotal": si.subtotal,
                "vat_amount": si.vat_amount,
                "total_amount": si.total_amount,
                "status": si.status.value,
            }
        )

    # vat_summary — line level, per-rate buckets (addendum §4).
    output: dict[Decimal, list] = {}
    for item in invoice_items:
        bucket = _bucket(output, item.tax_rate)
        bucket[0] += item.line_net
        bucket[1] += item.tax_amount
        bucket[2] += 1
    for item in cn_items:
        bucket = _bucket(output, item.tax_rate)
        bucket[0] -= item.line_net
        bucket[1] -= item.tax_amount
        bucket[2] += 1
    for item in tdn_items:
        bucket = _bucket(output, item.tax_rate)
        bucket[0] += item.total_price - item.tax_amount
        bucket[1] += item.tax_amount
        bucket[2] += 1

    aed_supplier_ids = {si.id for si in supplier_invoices if si.currency == AED}
    input_buckets: dict[Decimal, list] = {}
    for item in si_items:
        if item.supplier_invoice_id not in aed_supplier_ids:
            continue
        if item.currency != AED:
            continue
        bucket = _bucket(input_buckets, item.vat_rate)
        bucket[0] += item.total_price - item.vat_amount
        bucket[1] += item.vat_amount
        bucket[2] += 1

    summary_rows: list[dict] = []
    for rate in sorted(output):
        taxable, vat, count = output[rate]
        summary_rows.append(
            {
                "direction": "output",
                "tax_rate": rate,
                "count": count,
                "taxable_amount": money(taxable),
                "vat_amount": money(vat),
            }
        )
    for rate in sorted(input_buckets):
        taxable, vat, count = input_buckets[rate]
        summary_rows.append(
            {
                "direction": "input",
                "tax_rate": rate,
                "count": count,
                "taxable_amount": money(taxable),
                "vat_amount": money(vat),
            }
        )

    output_tax = money(
        sum(
            (row["vat_amount"] for row in summary_rows if row["direction"] == "output"),
            ZERO,
        )
    )
    input_tax = money(
        sum(
            (row["vat_amount"] for row in summary_rows if row["direction"] == "input"),
            ZERO,
        )
    )
    net_tax = money(output_tax - input_tax)

    settings = get_settings()
    non_aed = sorted(
        si.supplier_invoice_number for si in supplier_invoices if si.currency != AED
    )

    manifest = {
        "generator": "InvoiceSaaS VAT Compliance Pack",
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"from": period_from.isoformat(), "to": period_to.isoformat()},
        "org": {
            "name": workspace.name,
            "trn": settings.VAT_ORG_TRN or workspace.trn or "",
            "address": workspace.address or "",
        },
        "currency": AED,
        "warnings": {"non_aed_supplier_invoices": non_aed},
        "summary": {
            "output_tax": f"{output_tax:.2f}",
            "input_tax": f"{input_tax:.2f}",
            "net_tax": f"{net_tax:.2f}",
        },
        "files": FILES,
        "excluded": {"statuses": EXCLUDED_STATUSES_TEXT},
    }

    logger.info(
        "vat_compliance_generated",
        extra={
            "workspace_id": str(workspace.id),
            "from": period_from.isoformat(),
            "to": period_to.isoformat(),
            "sales_invoices": len(sales_rows),
            "supplier_invoices": len(purchase_rows),
            "non_aed_supplier_invoices": len(non_aed),
        },
    )

    return {
        "manifest": manifest,
        "sales_invoices": sales_rows,
        "invoice_lines": line_rows,
        "credit_notes": credit_rows,
        "tax_debit_notes": debit_rows,
        "purchase_invoices": purchase_rows,
        "vat_summary": summary_rows,
    }


def csv_text(payload: dict) -> dict[str, str]:
    """Render the six CSVs + manifest.json as file contents."""
    return {
        "sales_invoices.csv": _csv_text(
            [
                "invoice_number",
                "issue_date",
                "supply_date",
                "due_date",
                "invoice_kind",
                "status",
                "currency",
                "client_name",
                "client_trn",
                "subtotal",
                "tax_amount",
                "total_amount",
                "seller_trn",
            ],
            payload["sales_invoices"],
        ),
        "invoice_lines.csv": _csv_text(
            [
                "invoice_number",
                "description",
                "sku_snapshot",
                "quantity",
                "unit_price",
                "tax_rate",
                "discount_amount",
                "line_net",
                "tax_amount",
                "total_price",
            ],
            payload["invoice_lines"],
        ),
        "credit_notes.csv": _csv_text(
            [
                "credit_note_number",
                "issue_date",
                "original_invoice_number",
                "reason",
                "status",
                "client_name",
                "client_trn",
                "subtotal",
                "tax_amount",
                "total_amount",
            ],
            payload["credit_notes"],
        ),
        "tax_debit_notes.csv": _csv_text(
            [
                "debit_note_number",
                "issue_date",
                "original_invoice_number",
                "reason",
                "status",
                "client_name",
                "client_trn",
                "subtotal",
                "tax_amount",
                "total_amount",
            ],
            payload["tax_debit_notes"],
        ),
        "purchase_invoices.csv": _csv_text(
            [
                "supplier_invoice_number",
                "invoice_date",
                "supplier_name",
                "supplier_trn",
                "currency",
                "subtotal",
                "vat_amount",
                "total_amount",
                "status",
            ],
            payload["purchase_invoices"],
        ),
        "vat_summary.csv": _csv_text(
            [
                "direction",
                "tax_rate",
                "count",
                "taxable_amount",
                "vat_amount",
            ],
            payload["vat_summary"],
        ),
        "manifest.json": json.dumps(payload["manifest"], indent=2),
    }


def build_zip(payload: dict) -> bytes:
    """In-memory ZIP of the six CSVs + manifest.json (ZIP_DEFLATED)."""
    content = csv_text(payload)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES + ["manifest.json"]:
            archive.writestr(name, content[name])
    return buffer.getvalue()
