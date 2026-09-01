# WP-A–C Bilingual PDF — code review (font/labels + six PDFs/previews + Playwright)

**Date:** 2026-09-01
**Scope:** `architecture/wave-bilingual-pdf-addendum.md` FULL (WP-A/B/C, §2.1 titles, §3 font, §4 layout, §5 labels, §7 pytest, §8 Playwright); `.agents/reports/wp-a-bilingual-pdf-review.md`; `.claude/CLAUDE.md` money/isolation.
**Review only.** No feature work. No git commit.

## Verdict

**APPROVE_WITH_NITS**

No P0: no CDN/runtime font, no user-upload font, EN title strings byte-identical on EN-only testids, no Alembic / `*_ar` columns, no server PDF route, money/snapshots/send gates untouched.

**Slice may be committed when asked** (bilingual files only — see Commit).

## P0s

None.

## Checklist

| # | Lock | Result |
|---|---|---|
| 1 | EN titles byte-identical on EN-only testid nodes | **Pass.** `PDF_TITLES` EN matches addendum §5.1 / live strings. `HtmlDualTitle` puts `enTestId` on the EN `h2`/`h3`/`span` only; AR is a sibling. Playwright still `toHaveText` (not `toContainText`) on `pdf-title` → `Tax Invoice`, `cn-pdf-title` → `Tax Credit Note`, `quotation-pdf-title` → `Quotation`, `lpo-pdf-title` → `LPO`, `dn-pdf-title` → `Delivery Note`, `statement-pdf-title` → `Account Statement`. |
| 2 | AR titles exact §2.1 on sibling `*-ar` | **Pass.** `pdfTitles.ts` AR is byte-for-byte §2.1. Previews: `pdf-title-ar` `فاتورة ضريبية`, `cn-pdf-title-ar` `إشعار دائن ضريبي`, `quotation-pdf-title-ar` `عرض سعر`, `lpo-pdf-title-ar` `أمر شراء محلي`, `dn-pdf-title-ar` `إذن تسليم`, `statement-pdf-title-ar` `كشف حساب`. Playwright asserts those exact strings. PDF `PdfDualTitle` uses the same `PDF_TITLES` constants. No hardcoded AR in the six `*PDF.tsx` files. |
| 3 | LPO stays `LPO` / `أمر شراء محلي` (not PO Acknowledgement) | **Pass.** No `Purchase Order Acknowledgement`, no paper AR `إشعار أمر شراء`. `LpoPDF` / `LpoPdfPreview` / Playwright `toHaveText('LPO')`. LPO VAT column EN stayed **`VAT`** (not `VAT AED`); AR from `vatAed`. |
| 4 | Font repo TTF, `Font.register`, no CDN, no user upload | **Pass.** `frontend/src/assets/fonts/` is Regular TTF + `OFL.txt` only. TTF **247,336** bytes (50 KiB–2 MiB). Magic `\x00\x01\x00\x00`. Name table contains **Noto Naskh Arabic** (not Sans). Hinted (`fpgm`); no `fvar`. OFL.txt: SIL OFL 1.1 from notofonts/arabic (`SIL OPEN FONT LICENSE`). `pdfFonts.ts`: Vite `?url` import, `Font.register({ family: 'NotoNaskhArabic', src: notoUrl })`, hyphenation `[word]`, idempotent, `PDF_FONT_EN = 'Helvetica'`. No `fonts.googleapis` / `fonts.gstatic` / `http://` / `https://` / jsDelivr under `frontend/src` (except OFL license URLs in `OFL.txt`). CSS `@font-face` uses the same relative TTF. No user-upload / Settings font. `registerPdfFonts()` at every `*PDF.tsx` module load and every `pdf().toBlob()` path including `Invoices.tsx`. AR `Text` uses `PDF_FONT_AR` with `fontWeight: 'normal'` (no Bold file). |
| 5 | No `direction:rtl` on Page; Western digits | **Pass.** All six `Page` styles: Helvetica + padding only. Preview roots have no `dir=rtl`. RTL is only on AR siblings (HTML `dir="rtl"` + CSS `.arTitle` / `.arLabel`). Money still `toFixed(2)` / `formatMoney`. No Eastern Arabic numerals `٠١٢٣`. Invoice numbers stay `INV-`/`CN-`/`QUO-`/`LPO-`/`DN-`. |
| 6 | No `name_ar` columns; no new Alembic | **Pass.** `workspace.py` / `client.py` / `product.py`: no `name_ar` / `address_ar`. No snapshot `*_ar`. No Alembic file has `down_revision = "b8d5f0c3a216"` (HEAD remains **`b8d5f0c3a216`**). Credit-notes revision file still present. No `*_bilingual*` / `*_name_ar*` revision. `git diff` of `backend/app` and `backend/alembic` is empty. Pytest: **6 passed**. |
| 7 | No server PDF; money/snapshots/send gates untouched | **Pass.** No `GET .../pdf`, WeasyPrint, or reportlab in `backend/app`. Downloads still client `pdf().toBlob()` blobs. `Invoices.tsx` diff is **+2 lines** (`import registerPdfFonts` + call before `toBlob`). `snapOrLive` / CN `snapFirst` still English snapshots. Send-blocked spec and invoice send UI unaltered. Isolation still 404 not 403. |
| 8 | Line descriptions not translated | **Pass.** Lines print `item.description` / notes / shipping / vehicle / driver / SKU / TRN digits / status badges in English. Chrome only from `PDF_LABELS`. Statement Type: EN from JSON `doc_type_label` + AR mapped by `doc_type` (`statementTypeAr`), not by translating JSON. |
| 9 | Playwright EN asserts kept; isolation unchanged | **Pass (source).** All six EN title `toHaveText` remain exact. Isolation specs (`fta-isolation`, `credit-note-isolation`, `quotation-isolation`, `lpo-isolation`, `delivery-note-isolation`, `ar-statement-isolation`, plus product/credit/pdc/volume) have **zero diff** and still assert 404, not titles. FTA preview: request watcher rejects `fonts.googleapis.com` / `fonts.gstatic.com`; optional `font-family` `/NotoNaskhArabic/`. Coder claimed **24/24** `npm run test:e2e`; suite has 24 `test()` cases. This review did **not** re-run Playwright. |
| 10 | Statement page + preview both AR | **Pass.** `ArStatement.tsx` page `HtmlDualTitle` `enAs="h2"`; `StatementPdfPreview` `enAs="h3"`. Playwright scopes page via `h2[data-testid="statement-pdf-title"] + [data-testid="statement-pdf-title-ar"]` and preview via `statement-pdf-preview` locator; re-asserts page titles while preview is open so the two nodes do not collide. |

## WP-A (font + labels + pytest)

Unchanged vs `.agents/reports/wp-a-bilingual-pdf-review.md` **APPROVE_WITH_NITS**, and re-verified this pass: TTF/OFL, titles §5.1, `pdfFonts` local register, pytest 6/6, no schema.

## WP-B (six PDFs + previews + statement `h2`)

| Surface | Dual title from `PDF_TITLES` | Helvetica page | Stacked chrome | Watermark AR | Footer §4.5 |
|---|---|---|---|---|---|
| Invoice PDF + preview | Yes | Yes | Yes (preview is still the thin FTA chrome) | CANCELLED | Yes (PDF) |
| Credit note PDF + preview | Yes | Yes | Yes | DRAFT | Yes (PDF) |
| Quotation PDF + preview | Yes | Yes | Yes | EXPIRED / REJECTED | Yes (PDF) |
| LPO PDF + preview | Yes (`LPO`) | Yes | Yes; VAT EN preserved | CANCELLED | Yes (PDF) |
| Delivery note PDF + preview | Yes | Yes | Yes | CANCELLED | Yes (PDF) |
| Statement PDF + preview + page `h2` | Yes | Yes | Yes; type AR by `doc_type` | n/a | Yes (PDF, `flow`) |

`PdfWatermark` letter-spacing stays on the EN line only (Arabic second line has none). Status badges remain English enums.

## WP-C (Playwright)

EN exact matches kept. AR `toHaveText` added on the six `*-ar` testids. Statement page vs preview scoped. Isolation files untouched. Font CDN watch on FTA spec is **stricter than spec** (whole test, not only while preview is open) — acceptable.

## Nits

1. **`pdfLabels.ts` has no pytest** (WP-A). §7 omits it; chrome AR is gated only by source + Playwright titles, not by a labels-file test.
2. **Alembic test is filename-pattern, not `alembic heads`.** A new revision not named `*_bilingual*` / `*_name_ar*` would still pass. Live graph: nothing revises `b8d5f0c3a216`.
3. **`test_pdf_fonts_register_local_ttf_not_cdn` is string-contains.** Does not require `?url`, hyphenation `[word]`, `PDF_FONT_EN = 'Helvetica'`, or ban `https://` / jsDelivr. Source has the first three and no CDN URLs.
4. **Title pytest is substring `in text`**, not `en: '…'` field match. `pdfTitles.ts` is eight lines, equivalent today.
5. **react-pdf AR nodes omit `direction: 'rtl'`.** Spec §4.1 asks Noto + right + dir rtl on the AR title. HTML siblings set `dir="rtl"`. `PdfDualTitle` / `pdfChrome` use `fontFamily: PDF_FONT_AR` + `textAlign: 'right'` only. Playwright does not parse the PDF binary — shaping on download is unverified. Not a P0 (P0 list is CDN / EN-string / Alembic / server PDF / money).
6. **`HtmlStackedLine` `testId` wraps EN+AR** (`pdf-seller-trn`, `cn-pdf-seller-trn`, `cn-pdf-original-invoice`, `statement-pdf-billed`, …). Current specs use `toContainText` or do not exact-match those nodes. Title testids are correctly EN-only.
7. **HTML preview chrome EN is not always `PDF_LABELS.en`.** Invoice preview `Bill to:` vs PDF `BILL TO:`; DN preview `Customer:` vs PDF `DELIVER TO:`. Titles are locked; this is leftover thin-preview copy.
8. **Account Statement page totals keep pre-PDF EN** (`Billed`, `Paid (SUCCESS payments)` without colons) while PDF uses `PDF_LABELS` (`Billed:`, `Paid (SUCCESS):`). Money `data-testid`s stay on the amount spans — Playwright `toHaveText('AED 50.00')` is safe. Intentional vs WP-A mapping note.
9. **Commit hygiene:** do not stage `frontend/dist/`, pytest `__pycache__`, `.claude-flow` tmp/stats, `.ruff_cache`.

Not P0 / not blocking commit of the slice: font is in-repo Noto Naskh Arabic Regular; six EN+AR titles match §2.1; EN Playwright exact matches are intact; no schema; no server PDF; send/money untouched.

## Commit

**Yes — this slice may be committed when asked.**

Include: `frontend/src/assets/fonts/` (TTF + OFL), `frontend/src/components/pdf/*` bilingual modules + six PDFs/previews, `frontend/src/pages/Invoices.tsx`, `frontend/src/pages/ArStatement.tsx`, `frontend/e2e/{fta-tax-invoice,credit-notes,quotations,lpos,delivery-notes,ar-statement}.spec.ts`, `backend/tests/test_bilingual_pdf_assets.py`, this report.

Exclude: `frontend/dist/`, caches, `.claude-flow` policy tmp, secrets.

## Next remaining UAE gap (do not implement)

**Electrical spec columns** (`amp_rating`, `cable_size_mm2`, cores, poles, `specs`) are still open — `backend/app/models/product.py` has none of them; Wave 3 addendum rejected them for Product Master. Then **debit notes** (no `DebitNote` model). **Peppol / PINT-AE stays later.** Later Alembic must `down_revision = "b8d5f0c3a216"` until HEAD moves.
