# Bilingual Document PDFs (EN+AR) — Architecture Addendum (Gap 13 / §4.10)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live client-side `@react-pdf/renderer` documents (`InvoicePDF`, `CreditNotePDF`, `QuotationPDF`, `LpoPDF`, `DeliveryNotePDF`, `StatementPDF`) and their HTML previews. Do **not** add a server PDF route, mutate invoice/CN money or snapshots, change send gates, or invent `*_ar` columns.
**Depends on:** volume/customer pricing A–C on master (`baae8a66b81248ce3e3d01e1a64d2e66f82cfa45`), PDC pending-until-clear, AR Account Statement, tax credit notes (`b8d5f0c3a216`), DN, credit HOLD, LPO, quotes, FTA tax invoices, Product Master.
**After this WP A–C:** electrical spec columns (amp/mm²) if still open, then debit notes. Not this slice: Peppol, WhatsApp, server-side PDF, re-pricing SENT, PDC, volume pricing changes, certified translator workflow.

Copy split: **WP-A (font + shared labels + tiny pytest) → WP-B UI/PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green. **Alembic: no.**

UAE electrical wholesale expects **Tax Invoice / فاتورة ضريبية** (and the other five sales PDFs) to show Arabic **labels**. English remains the legal language (Cabinet Decision 74/2023). This WP is **chrome + layout + an embedded Arabic font**, not a certified translation product and not a full body translation of line descriptions.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| All six PDFs | `fontFamily: 'Helvetica'`. **No** `Font.register`. Helvetica **cannot** render Arabic (tofu / missing glyphs). |
| Titles (PDF `Text` + HTML preview `data-testid`) | **Tax Invoice** (`pdf-title`), **Tax Credit Note** (`cn-pdf-title`), **Quotation** (`quotation-pdf-title`), **LPO** (`lpo-pdf-title` — **not** “Purchase Order Acknowledgement”), **Delivery Note** (`dn-pdf-title`), **Account Statement** (`statement-pdf-title`). |
| Playwright | Exact `toHaveText` on those EN strings (`fta-tax-invoice`, `credit-notes`, `quotations`, `lpos`, `delivery-notes`, `ar-statement`). Isolation specs do not assert titles. |
| FTA addendum | English Tax Invoice is legal; **Arabic PDF deferred to this gap**. |
| CN addendum | PDF English only; title **Tax Credit Note**. |
| AR addendum | Title **Account Statement**; Arabic `كشف حساب` deferred; **no** server `/ar-statement.pdf`. |
| Paper §4.10 LPO | Title EN “Purchase Order Acknowledgement” / AR `إشعار أمر شراء`. **Live EN is `LPO`.** Do not retitle EN. |
| `Workspace` / `Client` / `Product` | `name`, `address`, `trn`/`tax_id` English only. **No** `name_ar`, `address_ar`, `legal_name_ar`. Wave 3 explicitly rejected product `name_ar`. |
| Invoice/CN snapshots | `seller_name_snapshot`, `seller_address_snapshot`, `buyer_*` English strings. No `*_ar` snapshots. |
| Alembic HEAD | **`b8d5f0c3a216`** (`b8d5f0c3a216_add_credit_notes.py`). PDC, AR statement, and volume pricing added **no** revision. This slice adds **none**. Later WPs (electrical specs / debit notes) must `down_revision = "b8d5f0c3a216"` until HEAD moves. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC/pricing history. |
| Stack | `@react-pdf/renderer` **^4.6.1**. Vite 8; Playwright `npm run dev` on **5173**; API Docker **8000**; Postgres **5434**. **No** frontend unit-test runner (no vitest). |
| Fonts in repo | **None** today (`*.ttf` / `*.otf` absent). |
| T15 (gaps) | Vendor font from **repo**; **no user-uploaded fonts**; no runtime CDN. |

CLAUDE.md: Decimal money **unchanged**; wrapper `{success, data, error}` **unchanged**; isolation **404 not 403**; never SQLite; payments immutable; SENT invoices not editable.

---

## 1. ASCII — client rebuild, shared titles, one font

```
  GET invoice | CN | quote | LPO | DN | ar-statement
           │  (existing JSON; no new fields this WP)
           ▼
  pdfTitles.ts + pdfLabels.ts     ← WP-A contract (EN+AR chrome)
  pdfFonts.ts Font.register       ← repo TTF, once
           │
           ├─ HTML preview (Playwright)   dual title: EN testid exact, AR sibling
           └─ @react-pdf Document         same constants; Helvetica EN + Noto AR
                      │
                      ▼
              blob download (not stored; no server route)
```

Every download still rebuilds from GET, same as FTA/CN/AR. Snapshots still win when SENT/ISSUED.

---

## 2. Decisions (architect lock)

### 2.1 Documents in scope — **all six** (same WP)

Shared `pdfTitles.ts` + one `Font.register` is cheaper than a later second font/title pass. **Do not** ship FTA+CN only and leave quote/LPO/DN/statement English-only.

| Doc | File | Preview | EN title (**unchanged**) | AR title | EN testid (**unchanged**) | AR testid (**new**) |
|---|---|---|---|---|---|---|
| Tax Invoice | `InvoicePDF.tsx` | `InvoicePdfPreview.tsx` | `Tax Invoice` | `فاتورة ضريبية` | `pdf-title` | `pdf-title-ar` |
| Tax Credit Note | `CreditNotePDF.tsx` | `CreditNotePdfPreview.tsx` | `Tax Credit Note` | `إشعار دائن ضريبي` | `cn-pdf-title` | `cn-pdf-title-ar` |
| Quotation | `QuotationPDF.tsx` | `QuotationPdfPreview.tsx` | `Quotation` | `عرض سعر` | `quotation-pdf-title` | `quotation-pdf-title-ar` |
| LPO | `LpoPDF.tsx` | `LpoPdfPreview.tsx` | `LPO` | `أمر شراء محلي` | `lpo-pdf-title` | `lpo-pdf-title-ar` |
| Delivery Note | `DeliveryNotePDF.tsx` | `DeliveryNotePdfPreview.tsx` | `Delivery Note` | `إذن تسليم` | `dn-pdf-title` | `dn-pdf-title-ar` |
| Account Statement | `StatementPDF.tsx` | `StatementPdfPreview.tsx` **and** `ArStatement.tsx` `h2` | `Account Statement` | `كشف حساب` | `statement-pdf-title` | `statement-pdf-title-ar` |

**LPO AR:** paper’s `إشعار أمر شراء` matches “Purchase Order Acknowledgement”. Live EN is **`LPO`**. Lock AR **`أمر شراء محلي`** (local purchase order). Do **not** retitle the PDF `Purchase Order Acknowledgement`.

### 2.2 Stored `*_ar` names — **B) No Alembic**

**No** `workspaces.name_ar` / `address_ar`, **no** `clients.name_ar` / `address_ar`, **no** `products.name_ar`, **no** snapshot `_ar` columns, **no** Settings/client form fields for Arabic legal names.

**Justification:**

1. This WP is **labels + layout**, not a certified translation product (user lock). FTA already shipped English as the legal Tax Invoice (Cabinet Decision 74/2023). Arabic *legal party names* are a later product (forms, validation, SENT snapshot freeze, CN copy-from-invoice). Doing that here would require Alembic from `b8d5f0c3a216` **and** snapshot columns so SENT PDFs cannot drift — out of slice.
2. Wave 3 already rejected product `name_ar`. Party-name AR without product AR still leaves line descriptions English; a half schema is worse than static labels.
3. T15 + YAGNI: no user-uploaded fonts, no extra PII columns, no migration risk on CN/DN/FTA history.

**PDF behavior:** party names, addresses, TRNs, SKUs, and line `description` stay **English** (live or snapshot). Titles, table headers, and chrome labels are bilingual. If an Arabic name is ever stored later, a future WP prints it; omit AR name when unset.

### 2.3 Alembic — **NO**

HEAD stays **`b8d5f0c3a216`**. No new revision. No API schema diffs. `doc_type_label` on AR statement stays English (`Opening balance`, `Tax Invoice`, `Payment`, `Payment (pending)`, `Tax Credit Note`). WP-B maps AR for **display only** via `pdfLabels.ts`.

### 2.4 Server PDF — **NO**

Do not add `GET .../pdf`. Do not add WeasyPrint/reportlab. Evidence: invoices, CNs, quotes, LPO, DN, statement are all client-side today.

---

## 3. Font (T15)

### 3.1 Vendor

| Lock | Value |
|---|---|
| Face | **Noto Naskh Arabic Regular** (OFL-1.1). Naskh, not Noto Sans, for document chrome. |
| Path | `frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf` |
| License | `frontend/src/assets/fonts/OFL.txt` (SIL OFL 1.1 text from the same Noto package) |
| Weights | **Regular only.** Do not commit the full family, variable `[wght]` file, or a 20MB zip. |
| Size gate | **50 KiB ≤ file ≤ 2 MiB** (pytest). Typical Regular TTF is a few hundred KiB. |
| Runtime | **Repo asset only.** No `fonts.googleapis.com` / `fonts.gstatic.com` / jsDelivr. No `@font-face` from a CDN. No user upload, no Settings “custom font”, no `logo_url`-style font URL. |
| Source for the coder | Official Noto Arabic / `notofonts` OFL package (hinted TTF Regular). Commit the binary + OFL. Do not fetch at runtime. |

Vite already emits `.ttf` as a static asset; no `vite.config` change required unless build fails (then `assetsInclude: ['**/*.ttf']` only).

### 3.2 Register (`frontend/src/components/pdf/pdfFonts.ts`) — WP-A

```
import { Font } from '@react-pdf/renderer';
import notoUrl from '../../assets/fonts/NotoNaskhArabic-Regular.ttf?url';

const FAMILY = 'NotoNaskhArabic';

export function registerPdfFonts(): void {
  // idempotent
  Font.register({ family: FAMILY, src: notoUrl });
  Font.registerHyphenationCallback((word) => [word]); // Arabic must not hyphenate
}

export const PDF_FONT_AR = FAMILY;
export const PDF_FONT_EN = 'Helvetica';
```

- Import `pdfFonts.ts` (call `registerPdfFonts()`) from every `*PDF.tsx` module **and** from each `download*Pdf` / `pdf().toBlob()` path (Invoice download lives in `Invoices.tsx` — register there too).
- **Page default** stays `fontFamily: 'Helvetica'` (EN copy, Western digits, money).
- Arabic `Text` nodes set `fontFamily: PDF_FONT_AR`. Do **not** set `fontWeight: 'bold'` on AR text (no Bold file).
- `src` must be the **Vite `?url` import**, never a `https://` string.

### 3.3 HTML preview `@font-face` — WP-B

Playwright asserts the **HTML preview**, not the PDF binary. Load the **same TTF** via CSS `@font-face` (`pdfBilingual.module.css`) so AR glyphs are not a system-font accident and not a network font.

---

## 4. Layout

**Do not** set `direction: 'rtl'` on `Page` or the preview root. Do **not** mirror columns. Money, qty, dates, invoice numbers stay **Western digits** (`toFixed(2)`, existing `INV-`/`CN-`/`QUO-`/`LPO-`/`DN-` strings). Never convert to Eastern Arabic numerals (`٠١٢٣`).

### 4.1 Dual title line

Under the seller/status header, a **full-width row**:

```
[ Tax Invoice                              فاتورة ضريبية ]
   Helvetica, left                         Noto, right, dir rtl
```

`flexDirection: 'row'`, `justifyContent: 'space-between'`. EN left, AR right. Same pattern on HTML preview.

**Playwright exact-match lock:** put the **existing** `data-testid` on an **EN-only** node whose text is **exactly** the live EN title. Put AR on a **sibling** with the new `*-ar` testid. Do **not** concatenate both languages into the EN testid node (`toHaveText('Tax Invoice')` would fail).

```
<div class="dualTitle">
  <span data-testid="pdf-title">Tax Invoice</span>
  <span data-testid="pdf-title-ar" lang="ar" dir="rtl">فاتورة ضريبية</span>
</div>
```

Move the testid off the wrapping `h3`/`h2` onto the EN `span` if needed. Existing specs keep `toHaveText('Tax Invoice')` etc. **without** rewriting to `toContainText`.

`ArStatement.tsx` page `h2` and `StatementPdfPreview` both use `statement-pdf-title` today — apply the same sibling pattern on **both**.

### 4.2 Table headers

Stacked **EN on top, AR below** inside each existing column `View` (smaller AR, `PDF_FONT_AR`). Do not add columns. Do not RTL the table.

### 4.3 Chrome labels

Bilingual the **chrome** (BILL TO, Invoice No, Qty, VAT, footer). **Do not** translate `item.description`, notes, shipping address, vehicle, driver, SKU, TRN digits, or status enum badges (`SENT`, `DRAFT`, …).

### 4.4 Watermarks

EN strings **stay** (`CANCELLED`, `EXPIRED`, `REJECTED`, `DRAFT`). Optional AR second line (lock **yes**, same watermark style, Noto, no extra letter-spacing that breaks Arabic):

| EN | AR |
|---|---|
| CANCELLED | ملغى |
| EXPIRED | منتهي |
| REJECTED | مرفوض |
| DRAFT | مسودة |

Status **badge** stays English enum.

### 4.5 Footer

Replace “English only” (CN / statement) with:

- EN: `Amounts in AED. Labels are bilingual; this is not a certified Arabic translation.`
- AR: `المبالغ بالدرهم الإماراتي. الترجمة للعناوين فقط وليست ترجمة معتمدة.`

Keep “Generated by InvoiceSaaS” in English (product name).

---

## 5. Label contract (`pdfTitles.ts` + `pdfLabels.ts`) — WP-A

Exact UTF-8. WP-B imports these; do not hard-code AR strings in six files.

### 5.1 `PDF_TITLES`

```ts
export const PDF_TITLES = {
  taxInvoice: { en: 'Tax Invoice', ar: 'فاتورة ضريبية' },
  taxCreditNote: { en: 'Tax Credit Note', ar: 'إشعار دائن ضريبي' },
  quotation: { en: 'Quotation', ar: 'عرض سعر' },
  lpo: { en: 'LPO', ar: 'أمر شراء محلي' },
  deliveryNote: { en: 'Delivery Note', ar: 'إذن تسليم' },
  accountStatement: { en: 'Account Statement', ar: 'كشف حساب' },
} as const;
```

### 5.2 Required chrome (`pdfLabels.ts`)

Use these AR strings (stacked under EN):

| Key / EN (live) | AR |
|---|---|
| BILL TO: | إلى: |
| CREDIT TO: | إشعار إلى: |
| QUOTE TO: | عرض إلى: |
| CUSTOMER: | العميل: |
| DELIVER TO: | تسليم إلى: |
| CLIENT: | العميل: |
| TRN | الرقم الضريبي |
| Invoice No: | رقم الفاتورة: |
| Issue Date: | تاريخ الإصدار: |
| Supply Date: | تاريخ التوريد: |
| Due Date: | تاريخ الاستحقاق: |
| Currency: | العملة: |
| Credit Note No: | رقم الإشعار: |
| Original Invoice: | الفاتورة الأصلية: |
| Original Issue Date: | تاريخ الفاتورة الأصلية: |
| Quote No: | رقم العرض: |
| Quotation Date: | تاريخ العرض: |
| Valid Until: | صالح حتى: |
| LPO No: | رقم أمر الشراء: |
| Customer PO: | أمر شراء العميل: |
| LPO Date: | تاريخ أمر الشراء: |
| Expected Delivery: | التسليم المتوقع: |
| DN No: | رقم إذن التسليم: |
| Delivery Date: | تاريخ التسليم: |
| Vehicle: | المركبة: |
| Driver: | السائق: |
| Shipping address | عنوان الشحن |
| Notes | ملاحظات |
| Period: | الفترة: |
| As of: | كما في: |
| Description | الوصف |
| Qty | الكمية |
| Unit | السعر |
| Disc | الخصم |
| Net | الصافي |
| VAT% | ض.ق.م٪ |
| VAT AED | ض.ق.م د.إ |
| Gross | الإجمالي |
| SKU | الرمز |
| Ordered | المطلوب |
| Invoiced | المفوتر |
| Remain | المتبقي |
| Subtotal (excl. VAT): | المجموع قبل الضريبة: |
| VAT: | ضريبة القيمة المضافة: |
| Total (AED): | الإجمالي (د.إ): |
| Amount Paid: | المدفوع: |
| Balance Due: | الرصيد المستحق: |
| Credit total (AED): | إجمالي الإشعار (د.إ): |
| Date | التاريخ |
| Type | النوع |
| Number | الرقم |
| Debit | مدين |
| Credit | دائن |
| Balance | الرصيد |
| Billed: | المفوتر: |
| Paid (SUCCESS): | المدفوع: |
| Credited (tax credit notes): | الدائن (إشعارات): |
| Amount due now: | المستحق الآن: |
| Unapplied credit: | رصيد غير مطبق: |
| Aging | التقادم |
| Current | حالي |
| 1–30 / 31–60 / 61–90 / 90+ | keep Western range labels (digits) |
| Opening balance | رصيد افتتاحي |
| Payment | دفعة |
| Payment (pending) | دفعة (معلقة) |

Statement **JSON** `doc_type_label` stays EN. PDF Type column: EN label from JSON + AR from this map (by `doc_type`, not by translating JSON ad hoc).

---

## 6. Module boundaries

| Layer | Owns |
|---|---|
| `pdfFonts.ts` | `Font.register`, hyphenation callback, family constants |
| `pdfTitles.ts` / `pdfLabels.ts` | EN+AR strings only |
| `PdfDualTitle.tsx` | react-pdf dual title row (WP-B) |
| HTML dual title + `pdfBilingual.module.css` | preview / statement `h2` (WP-B) |
| Existing `*PDF.tsx` | Layout, money, snapshots — **unchanged math** |
| Backend | **Untouched** (no routers, schemas, models, Alembic) |

Files < 500 lines. All imports at top of file. No mid-file imports.

Do not change `InvoiceService`, send gates, `line_money`, `amount_credited`, payments, HOLD, pricing resolve, DN qty.

---

## 7. Tests — WP-A `backend/tests/test_bilingual_pdf_assets.py`

No PostgreSQL required for this file (no fixtures). Never SQLite. Do **not** add vitest.

Resolve repo root as parent of `backend/`.

1. `frontend/src/assets/fonts/NotoNaskhArabic-Regular.ttf` exists; size 50_000..2_000_000 bytes; TTF/OTF magic (`\x00\x01\x00\x00` or `OTTO`).
2. `frontend/src/assets/fonts/OFL.txt` exists and mentions `SIL OPEN FONT LICENSE` (case-insensitive).
3. `pdfTitles.ts` contains each of the six EN strings and six AR strings from §2.1 **exactly**.
4. `pdfFonts.ts` contains `Font.register`, `NotoNaskhArabic`, `NotoNaskhArabic-Regular.ttf`, and does **not** contain `fonts.googleapis`, `fonts.gstatic`, or `http://`.
5. `workspace.py` / `client.py` / `product.py` still have **no** `name_ar` / `address_ar`.
6. `backend/alembic/versions/` still contains `b8d5f0c3a216_add_credit_notes.py` and **no** new `*_bilingual*` / `*_name_ar*` revision file.

Existing invoice/CN/statement pytest stays green (untouched).

---

## 8. WP split

### WP-A — font + labels + pytest (**no Alembic**, no PDF layout yet)

Vendor TTF + OFL, `pdfFonts.ts`, `pdfTitles.ts`, `pdfLabels.ts`, `test_bilingual_pdf_assets.py`. **Do not** retitle the six PDFs in WP-A (so Playwright stays green if someone runs E2E early).

**Acceptance:** pytest file §7 green; no new Alembic; no `*_ar` columns; font ≤ 2 MiB; titles module has all six AR strings.

### WP-B — UI / PDF / preview (after A green)

- Import `registerPdfFonts()`; dual title; stacked headers; chrome from `pdfLabels`; watermark AR; footer copy; HTML `@font-face` + sibling AR testids.
- `npm run build` green.
- Money, snapshots, SENT gates, JSON `doc_type_label`: **unchanged**.

**Acceptance:** all six PDFs + six previews (+ statement page `h2`) show EN+AR titles from `PDF_TITLES`; Helvetica default; AR nodes use Noto; no CDN font.

### WP-C — Playwright

Local API **8000**, Postgres host **5434**, UI **5173**. Never SQLite. Password **8+** (`Passw0rd1`). Unique emails.

**Keep** every existing EN `toHaveText` (do not switch them to `toContainText`). **Add** AR exact asserts on the new `*-ar` testids:

- `fta-tax-invoice.spec.ts`: `pdf-title-ar` → `فاتورة ضريبية` (and EN `pdf-title` still `Tax Invoice`).
- `credit-notes.spec.ts`: `cn-pdf-title-ar` → `إشعار دائن ضريبي`.
- `quotations.spec.ts`: `quotation-pdf-title-ar` → `عرض سعر`.
- `lpos.spec.ts`: `lpo-pdf-title-ar` → `أمر شراء محلي`.
- `delivery-notes.spec.ts`: `dn-pdf-title-ar` → `إذن تسليم`.
- `ar-statement.spec.ts`: `statement-pdf-title-ar` → `كشف حساب` on page and preview (scope locators so two nodes do not collide).

Isolation specs **unchanged** (404, not titles).

Font: while the FTA preview is open, page requests must **not** hit `fonts.googleapis.com` or `fonts.gstatic.com`. Optional: computed `font-family` on `pdf-title-ar` includes `NotoNaskhArabic`. Do **not** parse the downloaded PDF binary in Playwright.

**Acceptance:** Docker API + Postgres; EN titles still exact; Arabic visible on tax invoice preview; no network font.

---

## 9. Drift vs paper

| Paper (gaps §4.10 / domain `name_ar`) | This WP |
|---|---|
| LPO title “Purchase Order Acknowledgement” / `إشعار أمر شراء` | Live EN **`LPO`** / AR **`أمر شراء محلي`** |
| Workspace/client/product `name_ar` | **Out** (option B, labels only) |
| Flip document RTL | **No** — EN left, AR right on the title row only |
| Certified Arabic translation | **Out** |
| Line description translation | **Out** |
| Server-side PDF | **Out** |
| FTA pair first, rest later | **Reject** — all six in this WP |

---

## 10. NOT in this WP

Electrical spec columns (amp/mm²); debit notes; Peppol / PINT-AE; WhatsApp; certified translator workflow; full body translation; `*_ar` schema; snapshot AR names; user-uploaded fonts; CDN fonts; Eastern Arabic numerals; `direction: rtl` on `Page`; server PDF route; invoice/CN money or send-gate changes; re-pricing SENT; PDC; volume pricing; IBAN; changing Playwright EN exact titles to a different EN string.

---

## 11. Coder checklist

1. Report first: `.agents/reports/frontend-execution-report.md` (WP-A/B). No database report — **no Alembic**. Tiny pytest may be noted in `backend-execution-report.md`.
2. Alembic **NO**. HEAD stays `b8d5f0c3a216`. Later WPs `down_revision = "b8d5f0c3a216"` until HEAD moves.
3. EN titles **byte-identical** to live strings. AR titles **exactly** §2.1. LPO stays `LPO`.
4. Noto from repo; `Font.register`; Helvetica for EN/money; no CDN; no user fonts (T15).
5. EN testid node remains exact EN; AR is a sibling testid.
6. WP-A pytest green before WP-B. WP-C does not drop EN asserts.
7. Next after A–C: **electrical specs if still open**, then debit notes — not Peppol.
