# Architect note — Bilingual document PDFs EN+AR (Gap 13)

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-bilingual-pdf-addendum.md`

## Alembic

**NO.** Live `Workspace` / `Client` / `Product` have no `name_ar` / `address_ar`. Option **B**: static AR **labels** only; party names stay English. English Tax Invoice is already legal (FTA WP; Cabinet Decision 74/2023). Arabic legal names would need Settings + client form + SENT/CN snapshot columns so frozen PDFs cannot drift — out of this labels/layout slice. HEAD stays **`b8d5f0c3a216`**. Later WPs `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC/pricing history.

## Docs in scope

**All six** (shared `pdfTitles.ts` + one `Font.register` is cheaper than a second pass):

| EN (live, do not change) | AR |
|---|---|
| Tax Invoice | فاتورة ضريبية |
| Tax Credit Note | إشعار دائن ضريبي |
| Quotation | عرض سعر |
| LPO | أمر شراء محلي |
| Delivery Note | إذن تسليم |
| Account Statement | كشف حساب |

LPO: paper wanted “Purchase Order Acknowledgement” / `إشعار أمر شراء`. Live title is **`LPO`**. AR locked to **`أمر شراء محلي`**, not the paper acknowledgement phrasing.

## Font

`frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf` + `OFL.txt`. `@react-pdf/renderer` `Font.register` family `NotoNaskhArabic` via Vite `?url`. Helvetica remains page default (EN + Western digits / AED). No CDN, no user upload (T15). Regular only; pytest size **≤ 2 MiB**. Hyphenation callback returns `[word]`.

## Layout

EN left, AR right on a **dual title row**. Stacked EN/AR table headers. **Do not** `direction: rtl` the page. Money stays `toFixed(2)`. CANCELLED/EXPIRED/REJECTED/DRAFT watermarks keep EN; AR second line yes (`ملغى` / `منتهي` / `مرفوض` / `مسودة`).

Playwright: keep existing `toHaveText` on EN testids. Put AR on **sibling** `*-ar` testids so exact EN match does not break.

## WP split (A not skipped)

Empty WP-A would stall the coordinator (no API). **Keep A** as the contract gate:

- **A** Vendor font + `pdfFonts.ts` + `pdfTitles.ts` + `pdfLabels.ts` + `backend/tests/test_bilingual_pdf_assets.py` (filesystem; no DB). No PDF retitling yet. No Alembic.
- **B** Wire all six PDFs + previews + statement `h2`. `npm run build`.
- **C** Add AR title asserts on existing specs; keep EN asserts; isolation unchanged. Docker 8000 / Postgres 5434 / Vite 5173. Never SQLite. Password 8+. No network font.

No server PDF route. No invoice/CN money, snapshots, or send-gate changes.

Out: electrical specs, debit notes, Peppol, WhatsApp, certified translator, line-description translation.
