"""
PDF DocumentRenderer — Wave 27 (Phase 5) WhatsApp PDF delivery.

An internal, EN-only server-side byte generator. Adds NO HTTP PDF route.
Consumes the SAME canonical service/API data dicts the client renderers use
(snapshot-winning when SENT/ISSUED). It prints values VERBATIM from `data`
and never recomputes money (`total = subtotal + vat` is service math).

- `build_sections(document, data)` is a pure, deterministic testability seam:
  it maps the data dict onto a flat list of `Section` models. Financial-
  integrity tests assert the sections exactly.
- `render(document, data)` maps sections onto a reportlab PDF (bytes +
  filename + content_type).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from fastapi import status
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.common import ErrorCode
from app.services.customer_po_support import raise_error

SUPPORTED_DOCUMENTS = ("INVOICE", "QUOTATION", "AR_STATEMENT")


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _money(value: object) -> str:
    """Existing 2-dp Decimal -> '1234.50' string. Never recomputes anything."""
    if value is None or value == "":
        return ""
    return format(Decimal(str(value)), ".2f")


def _iso(value: object) -> str:
    """Date/datetime -> ISO date string; passthrough for existing strings."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _safe_filename(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", _text(value).strip()) or "document"


@dataclass(frozen=True)
class Section:
    """One deterministic block of a rendered document.

    ``kind`` selects the page layout: title | company | party | meta |
    opening | lines | totals | notes.
    """

    kind: str
    title: str = ""
    fields: Tuple[Tuple[str, str], ...] = ()
    columns: Tuple[str, ...] = ()
    rows: Tuple[Tuple[str, ...], ...] = ()
    note: Optional[str] = None


@dataclass
class RenderedDocument:
    data: bytes
    filename: str
    content_type: str = "application/pdf"


class DocumentRenderer:
    @staticmethod
    def build_sections(document: str, data: dict) -> list[Section]:
        """Pure, deterministic mapping from the canonical data dict to sections."""
        if document not in SUPPORTED_DOCUMENTS:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.UNSUPPORTED_DOCUMENT,
                f"Unsupported document type '{document}' for PDF rendering",
                field="linked_entity_type",
            )
        if document == "INVOICE":
            return DocumentRenderer._invoice_sections(data)
        if document == "QUOTATION":
            return DocumentRenderer._quotation_sections(data)
        return DocumentRenderer._statement_sections(data)

    @classmethod
    def render(cls, document: str, data: dict) -> RenderedDocument:
        """Render `data` to PDF bytes. Unsupported document -> 400."""
        sections = cls.build_sections(document, data)
        return RenderedDocument(
            data=cls._render_pdf(sections),
            filename=cls.filename_for(document, data),
        )

    @staticmethod
    def filename_for(document: str, data: dict) -> str:
        if document == "INVOICE":
            return f"{_safe_filename(data.get('invoice_number'))}.pdf"
        if document == "QUOTATION":
            return f"{_safe_filename(data.get('quotation_number'))}.pdf"
        return f"Account-Statement-{_iso(data.get('from'))}_{_iso(data.get('to'))}.pdf"

    # ---------- section builders (pure) ----------

    @staticmethod
    def _invoice_sections(data: dict) -> list[Section]:
        seller = data.get("seller") or {}
        buyer = data.get("buyer") or {}
        lines = data.get("lines") or []
        sections = [
            Section("title", "TAX INVOICE"),
            Section(
                "company",
                "",
                (
                    ("Business", _text(seller.get("name"))),
                    ("TRN", _text(seller.get("trn"))),
                    ("Address", _text(seller.get("address"))),
                ),
            ),
            Section(
                "party",
                "Billed To",
                (
                    ("Name", _text(buyer.get("name"))),
                    ("TRN", _text(buyer.get("trn"))),
                    ("Address", _text(buyer.get("address"))),
                ),
            ),
            Section(
                "meta",
                "Details",
                (
                    ("Invoice Number", _text(data.get("invoice_number"))),
                    ("Currency", _text(data.get("currency"))),
                    ("Issue Date", _iso(data.get("issue_date"))),
                    ("Supply Date", _iso(data.get("supply_date"))),
                    ("Due Date", _iso(data.get("due_date"))),
                ),
            ),
        ]
        rows = tuple(
            (
                _text(line.get("description")),
                _money(line.get("quantity")),
                _text(line.get("uom")),
                _money(line.get("unit_price")),
                _money(line.get("tax_rate")),
                _money(line.get("line_net")),
                _money(line.get("tax_amount")),
                _money(line.get("total_price")),
            )
            for line in lines
        )
        sections.append(
            Section(
                "lines",
                "Items",
                (),
                (
                    "Description",
                    "Qty",
                    "UOM",
                    "Unit Price",
                    "Tax Rate",
                    "Net",
                    "VAT",
                    "Total",
                ),
                rows,
            )
        )
        sections.append(
            Section(
                "totals",
                "Summary",
                (
                    ("Subtotal", _money(data.get("subtotal"))),
                    ("VAT", _money(data.get("tax_amount"))),
                    ("Total", _money(data.get("total_amount"))),
                ),
            )
        )
        if data.get("notes"):
            sections.append(Section("notes", "Notes", note=_text(data.get("notes"))))
        return sections

    @staticmethod
    def _quotation_sections(data: dict) -> list[Section]:
        seller = data.get("seller") or {}
        buyer = data.get("buyer") or {}
        lines = data.get("lines") or []
        sections = [
            Section("title", "QUOTATION"),
            Section(
                "company",
                "",
                (
                    ("Business", _text(seller.get("name"))),
                    ("TRN", _text(seller.get("trn"))),
                    ("Address", _text(seller.get("address"))),
                ),
            ),
            Section(
                "party",
                "Quoted To",
                (
                    ("Name", _text(buyer.get("name"))),
                    ("TRN", _text(buyer.get("trn"))),
                    ("Address", _text(buyer.get("address"))),
                ),
            ),
            Section(
                "meta",
                "Details",
                (
                    ("Quotation Number", _text(data.get("quotation_number"))),
                    ("Currency", _text(data.get("currency"))),
                    ("Quotation Date", _iso(data.get("quotation_date"))),
                    ("Valid Until", _iso(data.get("valid_until"))),
                ),
            ),
        ]
        rows = tuple(
            (
                _text(line.get("description")),
                _money(line.get("quantity")),
                _text(line.get("uom")),
                _money(line.get("unit_price")),
                _money(line.get("tax_rate")),
                _money(line.get("line_net")),
                _money(line.get("tax_amount")),
                _money(line.get("total_price")),
            )
            for line in lines
        )
        sections.append(
            Section(
                "lines",
                "Items",
                (),
                (
                    "Description",
                    "Qty",
                    "UOM",
                    "Unit Price",
                    "Tax Rate",
                    "Net",
                    "VAT",
                    "Total",
                ),
                rows,
            )
        )
        sections.append(
            Section(
                "totals",
                "Summary",
                (
                    ("Subtotal", _money(data.get("subtotal"))),
                    ("VAT", _money(data.get("tax_amount"))),
                    ("Total", _money(data.get("total_amount"))),
                ),
            )
        )
        if data.get("notes"):
            sections.append(Section("notes", "Notes", note=_text(data.get("notes"))))
        return sections

    @staticmethod
    def _statement_sections(data: dict) -> list[Section]:
        client = data.get("client") or {}
        workspace = data.get("workspace") or {}
        lines = data.get("lines") or []
        totals = data.get("totals") or {}
        sections = [
            Section("title", "ACCOUNT STATEMENT"),
            Section(
                "company",
                "",
                (
                    ("Business", _text(workspace.get("name"))),
                    ("TRN", _text(workspace.get("trn"))),
                    ("Address", _text(workspace.get("address"))),
                ),
            ),
            Section(
                "party",
                "Client",
                (
                    ("Name", _text(client.get("name"))),
                    ("TRN", _text(client.get("tax_id"))),
                    ("Address", _text(client.get("address"))),
                ),
            ),
            Section(
                "meta",
                "Period",
                (
                    ("From", _iso(data.get("from"))),
                    ("To", _iso(data.get("to"))),
                    ("As Of", _iso(data.get("as_of"))),
                    ("Currency", _text(data.get("currency"))),
                ),
            ),
            Section(
                "opening",
                "Opening Balance",
                (("Opening Balance", _money(data.get("opening_balance"))),),
            ),
        ]
        rows = tuple(
            (
                _iso(line.get("date")),
                _text(line.get("doc_type_label")),
                _text(line.get("number")),
                _text(line.get("reference")),
                _money(line.get("debit")),
                _money(line.get("credit")),
                _money(line.get("running_balance")),
            )
            for line in lines
        )
        sections.append(
            Section(
                "lines",
                "Activity",
                (),
                (
                    "Date",
                    "Type",
                    "Number",
                    "Reference",
                    "Debit",
                    "Credit",
                    "Balance",
                ),
                rows,
            )
        )
        sections.append(
            Section(
                "totals",
                "Totals",
                (
                    ("Period Invoiced", _money(totals.get("billed"))),
                    ("Period Payments", _money(totals.get("paid"))),
                    ("Period Credit Notes", _money(totals.get("credited"))),
                    ("Period Debit Notes", _money(totals.get("debited"))),
                    ("Pending Payments", _money(totals.get("pending"))),
                    ("Closing Balance", _money(totals.get("closing_running"))),
                    ("Amount Due Now", _money(data.get("amount_due_now"))),
                    ("Credit Balance", _money(data.get("credit_balance"))),
                ),
            )
        )
        return sections

    # ---------- reportlab mapping ----------

    @staticmethod
    def _render_pdf(sections: Sequence[Section]) -> bytes:
        buf = io.BytesIO()
        styles = getSampleStyleSheet()
        header_style = styles["BodyText"].clone("TableHeader")
        header_style.fontName = "Helvetica-Bold"
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title="InvoiceSaaS Document",
        )
        story: list = []
        for section in sections:
            if section.kind == "title":
                story.append(Paragraph(section.title, styles["Title"]))
                story.append(Spacer(1, 6 * mm))
                continue
            if section.kind == "lines":
                story.append(Paragraph(section.title, styles["Heading2"]))
                header = [Paragraph(col, header_style) for col in section.columns]
                body = [
                    [Paragraph(cell, styles["BodyText"]) for cell in row]
                    for row in section.rows
                ]
                table = Table([header, *body], repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 4 * mm))
                continue
            if section.kind == "notes":
                if section.note:
                    story.append(Paragraph(section.note, styles["Italic"]))
                continue
            # company / party / meta / opening / totals
            if section.title:
                story.append(Paragraph(section.title, styles["Heading2"]))
            field_rows = [
                [
                    Paragraph(label, styles["BodyText"]),
                    Paragraph(value, styles["BodyText"]),
                ]
                for label, value in section.fields
            ]
            if field_rows:
                table = Table(field_rows, colWidths=[45 * mm, None])
                table.setStyle(
                    TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white]),
                        ]
                    )
                )
                story.append(table)
            story.append(Spacer(1, 4 * mm))
        doc.build(story)
        return buf.getvalue()
