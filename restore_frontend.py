import os

def replace_in_file(src, dst, replacements):
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)

replacements = [
    ("CreditNote", "TaxDebitNote"),
    ("creditNote", "taxDebitNote"),
    ("credit-notes", "debit-notes"),
    ("credit_note", "tax_debit_note"),
    ("credit_notes", "debit_notes"),
    ("Credit Notes", "Debit Notes"),
    ("Credit Note", "Tax Debit Note"),
    ("credit note", "debit note"),
    ("Credit note", "Debit note"),
    ("credit-note", "debit-note"),
    ("CREDIT_NOTE", "TAX_DEBIT_NOTE"),
    ("cn-", "tdn-"),
    ("CN-", "TDN-"),
    ("cn_", "tdn_"),
    ("CreditNotePDF", "TaxDebitNotePDF"),
    ("creditNoteHelpers", "debitNoteHelpers"),
]

base_dir = "frontend/src"

replace_in_file(
    os.path.join(base_dir, "pages/CreditNoteDetail.tsx"),
    os.path.join(base_dir, "pages/DebitNoteDetail.tsx"),
    replacements
)
replace_in_file(
    os.path.join(base_dir, "pages/CreditNoteForm.tsx"),
    os.path.join(base_dir, "pages/DebitNoteForm.tsx"),
    replacements
)
replace_in_file(
    os.path.join(base_dir, "pages/CreditNotes.tsx"),
    os.path.join(base_dir, "pages/DebitNotes.tsx"),
    replacements
)
replace_in_file(
    os.path.join(base_dir, "pages/CreditNoteStatusBadge.tsx"),
    os.path.join(base_dir, "pages/DebitNoteStatusBadge.tsx"),
    replacements
)
replace_in_file(
    os.path.join(base_dir, "components/pdf/CreditNotePDF.tsx"),
    os.path.join(base_dir, "components/pdf/TaxDebitNotePDF.tsx"),
    replacements
)
replace_in_file(
    os.path.join(base_dir, "pages/creditNoteHelpers.ts"),
    os.path.join(base_dir, "pages/debitNoteHelpers.ts"),
    replacements
)

print("Files restored successfully")
