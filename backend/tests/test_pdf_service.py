"""Wave 27 — PDF DocumentRenderer tests.

Verifies the deterministic section seam: values are printed VERBATIM (money is
NEVER recomputed — total = subtotal + VAT is service math), filenames derive
from canonical numbers, render() produces a real `%PDF-` byte stream, and
unsupported documents 400 with UNSUPPORTED_DOCUMENT.

IMPORTANT financial-integrity assertion (addendum §5): the renderer trusts
`data` — every money field below intentionally violates the arithmetic
relationship to prove nothing recomputes.
"""

from fastapi import HTTPException

from app.services.pdf_service import DocumentRenderer

INVOICE_DATA = {
    "invoice_number": "INV-2026-0123",
    "currency": "AED",
    "issue_date": "2026-09-01",
    "supply_date": "2026-09-01",
    "due_date": "2026-10-01",
    "seller": {"name": "BizCo", "trn": "1001234567000003", "address": "Dubai"},
    "buyer": {"name": "ClientCo", "trn": "1009876543000009", "address": "Abu Dhabi"},
    "lines": [
        {
            "description": "Widget",
            "quantity": "2",
            "uom": "EA",
            "unit_price": "50.00",
            "tax_rate": "5.00",
            "line_net": "100.00",
            "tax_amount": "5.00",
            "total_price": "105.00",
        }
    ],
    # INTENTIONALLY non-arithmentic: 999 + 7 != 1066. If output equals the
    # recomputed total the renderer is corrupting business data.
    "subtotal": "999.00",
    "tax_amount": "7.00",
    "total_amount": "1066.00",
    "notes": "Thank you",
}

QUOTATION_DATA = {
    "quotation_number": "QTN-2026-0007",
    "currency": "AED",
    "quotation_date": "2026-09-01",
    "valid_until": "2026-10-01",
    "seller": {"name": "BizCo", "trn": "1001234567000003", "address": "Dubai"},
    "buyer": {"name": "ClientCo", "trn": None, "address": None},
    "lines": [],
    "subtotal": "0.00",
    "tax_amount": "0.00",
    "total_amount": "0.00",
    "notes": None,
}

STATEMENT_DATA = {
    "from": "2026-08-01",
    "to": "2026-08-31",
    "as_of": "2026-08-31",
    "currency": "AED",
    "workspace": {"name": "BizCo", "trn": "1001234567000003", "address": "Dubai"},
    "client": {
        "name": "ClientCo",
        "tax_id": "1009876543000009",
        "address": "Abu Dhabi",
    },
    "opening_balance": "1500.00",
    "lines": [
        {
            "date": "2026-08-05",
            "doc_type_label": "Invoice",
            "number": "INV-2026-0100",
            "reference": "",
            "debit": "500.00",
            "credit": "0.00",
            "running_balance": "2000.00",
        }
    ],
    "totals": {
        "billed": "500.00",
        "paid": "0.00",
        "credited": "0.00",
        "debited": "0.00",
        "pending": "500.00",
        "closing_running": "2000.00",
    },
    "amount_due_now": "2000.00",
    "credit_balance": "0.00",
}


def _sections(document, data):
    return {s.kind: s for s in DocumentRenderer.build_sections(document, data)}


def test_invoice_sections_shape_and_verbatim_values():
    sections = _sections("INVOICE", INVOICE_DATA)
    assert set(sections) == {
        "title",
        "company",
        "party",
        "meta",
        "lines",
        "totals",
        "notes",
    }
    assert sections["title"].title == "TAX INVOICE"
    assert dict(sections["company"].fields)["Business"] == "BizCo"
    assert dict(sections["meta"].fields)["Invoice Number"] == "INV-2026-0123"
    assert dict(sections["meta"].fields)["Due Date"] == "2026-10-01"
    assert sections["lines"].columns == (
        "Description",
        "Qty",
        "UOM",
        "Unit Price",
        "Tax Rate",
        "Net",
        "VAT",
        "Total",
    )
    assert sections["lines"].rows[0] == (
        "Widget",
        "2.00",
        "EA",
        "50.00",
        "5.00",
        "100.00",
        "5.00",
        "105.00",
    )
    totals = dict(sections["totals"].fields)
    # The core anti-recompute guarantee.
    assert totals == {"Subtotal": "999.00", "VAT": "7.00", "Total": "1066.00"}
    assert sections["notes"].note == "Thank you"


def test_invoice_omits_notes_when_absent():
    data = {k: v for k, v in INVOICE_DATA.items() if k != "notes"}
    sections = _sections("INVOICE", data)
    assert "notes" not in sections


def test_quotation_sections():
    sections = _sections("QUOTATION", QUOTATION_DATA)
    assert sections["title"].title == "QUOTATION"
    assert dict(sections["party"].fields) == {
        "Name": "ClientCo",
        "TRN": "",
        "Address": "",
    }
    assert dict(sections["totals"].fields)["Total"] == "0.00"
    assert "notes" not in sections


def test_statement_sections_with_totals():
    sections = _sections("AR_STATEMENT", STATEMENT_DATA)
    assert sections["title"].title == "ACCOUNT STATEMENT"
    assert dict(sections["party"].fields)["Name"] == "ClientCo"
    assert dict(sections["meta"].fields)["From"] == "2026-08-01"
    assert dict(sections["opening"].fields) == {"Opening Balance": "1500.00"}
    assert sections["lines"].rows[0][1] == "Invoice"
    totals = dict(sections["totals"].fields)
    assert totals["Closing Balance"] == "2000.00"
    assert totals["Amount Due Now"] == "2000.00"
    assert totals["Credit Balance"] == "0.00"


def test_render_produces_pdf_and_filename():
    rendered = DocumentRenderer.render("INVOICE", INVOICE_DATA)
    assert rendered.data[:5] == b"%PDF-"
    assert rendered.content_type == "application/pdf"
    assert rendered.filename == "INV-2026-0123.pdf"
    assert (
        DocumentRenderer.render("QUOTATION", QUOTATION_DATA).filename
        == "QTN-2026-0007.pdf"
    )
    stmt = DocumentRenderer.render("AR_STATEMENT", STATEMENT_DATA)
    assert stmt.filename == "Account-Statement-2026-08-01_2026-08-31.pdf"


def test_unsupported_document_rejected():
    try:
        DocumentRenderer.build_sections("CREDIT_NOTE", {})
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["code"] == "UNSUPPORTED_DOCUMENT"
    else:
        raise AssertionError("expected HTTPException")


def test_required_pdf_data_is_ascii_en_only():
    # No Arabic glyph dependency: reportlab's built-in Helvetica renders the
    # EN content and simply skips unsupported glyphs instead of raising.
    rendered = DocumentRenderer.render("INVOICE", INVOICE_DATA)
    assert len(rendered.data) > 1000
    assert rendered.data.startswith(b"%PDF-")
    assert rendered.data.rstrip().endswith(b"%%EOF")
