import os

files_to_fix = [
    'frontend/src/pages/DebitNoteDetail.tsx', 
    'frontend/src/pages/DebitNoteForm.tsx', 
    'frontend/src/pages/DebitNotes.tsx', 
    'frontend/src/pages/debitNoteHelpers.ts', 
    'frontend/src/api/debitNotes.ts',
    'frontend/src/pages/DebitNoteStatusBadge.tsx',
    'frontend/src/components/pdf/TaxDebitNotePDF.tsx',
]

def fix_file(f):
    if not os.path.exists(f): return
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Fix api imports
    content = content.replace('../api/taxDebitNotes', '../api/debitNotes')
    # Fix helper imports
    content = content.replace('./taxDebitNoteHelpers', './debitNoteHelpers')
    # Fix CSS imports
    content = content.replace('TaxDebitNotes.module.css', 'DebitNotes.module.css')
    # Fix component exports
    content = content.replace('TaxDebitNoteDetail', 'DebitNoteDetail')
    content = content.replace('TaxDebitNoteForm', 'DebitNoteForm')
    content = content.replace('TaxDebitNotes', 'DebitNotes')
    content = content.replace('TaxDebitNoteStatusBadge', 'DebitNoteStatusBadge')
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)

for f in files_to_fix:
    fix_file(f)

print("All files fixed safely")
