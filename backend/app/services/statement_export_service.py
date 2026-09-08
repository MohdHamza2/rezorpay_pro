"""Wave 30 item 1.3 — Statement export (PDF / CSV) presentation layer.

Pure presentation over the canonical statement dict produced by
``ar_statement_service.get_statement`` / ``supplier_statement_service.get_statement``.
The caller passes that one dict through unchanged (get_statement is invoked
exactly once per request); this module NEVER re-queries the ledger and NEVER
recomputes opening / closing / totals / aging / amount-due. Every figure is read
verbatim from the caller's dict, so the JSON, PDF, and CSV views are the same
numbers for the same inputs by construction.

PDF: rendered by the single ``DocumentRenderer`` (``AP_STATEMENT`` added as a
document type — no second PDF implementation).
CSV: deterministic 4-block flatten of the dict (metadata, activity, totals,
aging buckets) with a utf-8-sig BOM and CRLF row endings.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.services.pdf_service import DocumentRenderer

CSV_ACTIVITY_HEADER = [
    "Date",
    "Type",
    "Number",
    "Reference",
    "Payment Method",
    "Payment Status",
    "Pending",
    "Debit",
    "Credit",
    "Balance",
]

# 1:1 mapping to the shared statement line dict keys (AR + AP identical).
ACTIVITY_COLUMNS = [
    "date",
    "doc_type_label",
    "number",
    "reference",
    "payment_method",
    "payment_status",
    "pending_amount",
    "debit",
    "credit",
    "running_balance",
]

BUCKET_ROWS = [
    ("Aging Current", "current"),
    ("Aging 1-30 Days", "days_1_30"),
    ("Aging 31-60 Days", "days_31_60"),
    ("Aging 61-90 Days", "days_61_90"),
    ("Aging 90+ Days", "days_90_plus"),
]


@dataclass(frozen=True)
class StatementExport:
    data: bytes
    filename: str
    media_type: str


def _iso(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _entity(statement: dict) -> dict:
    return statement.get("client") or statement.get("supplier") or {}


def to_csv(statement: dict, kind: str) -> str:
    """Deterministic flatten of a statement dict into CSV text (4 blocks)."""
    entity = _entity(statement)
    workspace = statement.get("workspace") or {}
    lines = statement.get("lines") or []
    totals = statement.get("totals") or {}
    aging = (statement.get("aging") or {}).get("buckets") or {}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    # Block 0 — metadata (exact order, locked)
    writer.writerow(
        ["Statement Type", "AR_STATEMENT" if kind == "ar" else "AP_STATEMENT"]
    )
    writer.writerow(["Entity ID", _csv_cell(entity.get("id"))])
    writer.writerow(["Entity Name", _csv_cell(entity.get("name"))])
    writer.writerow(["Workspace", _csv_cell(workspace.get("name"))])
    writer.writerow(["Workspace TRN", _csv_cell(workspace.get("trn"))])
    writer.writerow(["Currency", _csv_cell(statement.get("currency"))])
    writer.writerow(["Period From", _csv_cell(statement.get("from"))])
    writer.writerow(["Period To", _csv_cell(statement.get("to"))])
    writer.writerow(["As Of", _csv_cell(statement.get("as_of"))])
    writer.writerow([])
    # Block 1 — activity (one row per line, order preserved; first = OPENING)
    writer.writerow(CSV_ACTIVITY_HEADER)
    for line in lines:
        writer.writerow([_csv_cell(line.get(column)) for column in ACTIVITY_COLUMNS])
    writer.writerow([])
    # Block 2 — totals (AR-only rows omitted when the key is absent)
    writer.writerow(["Total Billed", _csv_cell(totals.get("billed"))])
    writer.writerow(["Total Paid", _csv_cell(totals.get("paid"))])
    writer.writerow(["Total Credited", _csv_cell(totals.get("credited"))])
    if "debited" in totals:
        writer.writerow(["Total Debited", _csv_cell(totals.get("debited"))])
    writer.writerow(["Total Pending", _csv_cell(totals.get("pending"))])
    writer.writerow(["Closing Balance", _csv_cell(totals.get("closing_running"))])
    writer.writerow(["Amount Due Now", _csv_cell(statement.get("amount_due_now"))])
    if "credit_balance" in statement:
        writer.writerow(["Credit Balance", _csv_cell(statement.get("credit_balance"))])
    writer.writerow([])
    # Block 3 — aging buckets (fixed order, locked labels)
    for label, key in BUCKET_ROWS:
        writer.writerow([label, _csv_cell(aging.get(key))])
    return buffer.getvalue()


def _period_stamp(statement: dict) -> str:
    return f"{_iso(statement.get('from'))}_to_{_iso(statement.get('to'))}"


def filename_for(kind: str, statement: dict, ext: str) -> str:
    """Deterministic, PII-free filename: only the entity id + period."""
    entity_id = _entity(statement).get("id") or "unknown"
    prefix = "ar-statement" if kind == "ar" else "ap-statement"
    return f"{prefix}-{entity_id}-{_period_stamp(statement)}.{ext}"


def export_statement(kind: str, statement: dict, fmt: str) -> StatementExport:
    """Render one get_statement() dict to PDF or CSV bytes + download metadata."""
    if fmt == "csv":
        text = to_csv(statement, kind)
        return StatementExport(
            data=("\ufeff" + text).encode("utf-8"),
            filename=filename_for(kind, statement, "csv"),
            media_type="text/csv; charset=utf-8",
        )
    document = "AR_STATEMENT" if kind == "ar" else "AP_STATEMENT"
    rendered = DocumentRenderer.render(document, statement)
    return StatementExport(
        data=rendered.data,
        filename=filename_for(kind, statement, "pdf"),
        media_type=rendered.content_type,
    )
