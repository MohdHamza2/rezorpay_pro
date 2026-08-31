# Quotations — Architecture Addendum (Gap 4)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Invoice` / `InvoiceItem` / `InvoiceService` / `InvoiceNumberService` / FTA line math. Do **not** create a second billing engine, a `TaxInvoice` table, or a quote-only money formula.
**Depends on:** FTA tax invoice WP-A–C (`371eabf`) and Product Master (`9bc745b`).
**After this WP A–C:** LPO / customer purchase order (gap 5). Not this slice: WhatsApp, OCR, Peppol, credit HOLD, credit notes, delivery notes, Arabic PDF, enquiry, public customer-accept links.

Copy the FTA split: **WP-A API+Alembic+tests → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| Live backend | **No** `quotations` model, router, or table. `app.include_router` has invoices/products/clients, not quotes. |
| `InvoiceService.create_invoice` | Allocates `INV-YYYY-XXXX`, FTA `money()` line math, optional `product_id`, AED-only. Returns **DRAFT**. Does **not** run FTA send gates. |
| `InvoiceNumberService` | `SELECT FOR UPDATE` on `invoice_counters`. Do **not** reuse this table for quotes. |
| `invoices` | No `quotation_id` today. Add it this WP. |
| `InvoicePDF.tsx` | Title **Tax Invoice**. Do **not** retitle it for quotes — new `QuotationPDF`. |
| `Layout.tsx` | Sales nav: Clients, Invoices. Add Quotations in WP-B. |
| Paper `state-machines.md` §2 | Broader quote machine (REVISED, CANCELLED, SENT→CONVERTED, daily expiry job). **This WP trims** — see §14. |
| Paper `api-contracts.md` `POST /quotations` | Includes `enquiry_id`, email/WhatsApp send, public accept. **Out.** |
| Alembic HEAD | `c8e1a4f2b6d0` (`c8e1a4f2b6d0_fta_tax_invoice_fields.py`). New revision **must** `down_revision = "c8e1a4f2b6d0"`. Never edit FTA or Product Master revisions. |

Invoice state machine **unchanged**. Convert creates a **DRAFT** invoice; FTA send checks still run only on `POST /invoices/{id}/send`.

---

## 1. ASCII — quote lifecycle → DRAFT invoice

```
                    Quotation (commercial offer, NOT a tax invoice)
  quotation_number QUO-YYYY-XXXX   (operational sequence, not FTA-gapless)
  valid_until = quotation_date + 14 days (default)
  lines: same shape as InvoiceItem (qty, price, XOR discount, tax inherit 5%,
         optional product_id → sku_snapshot, uom_id)
           │
           │  same money() as invoices: ROUND_HALF_UP fils PER LINE, then SUM
           ▼
  line_net / line_vat / total_price (gross)
  header subtotal = Σ line_net; tax_amount = Σ line_vat; total = money(sum)

  DRAFT ──/send──► SENT ──/accept──► ACCEPTED ──/convert-to-invoice──► CONVERTED
                     │                    │
                     │ /reject            │  InvoiceService.create_invoice(...)
                     ▼                    ▼
                  REJECTED          DRAFT invoice INV-YYYY-XXXX
                  (terminal)        quotation_id set; FTA snapshots NULL
                                    send checks wait until invoice /send

  SENT + valid_until < today (UTC date) ──on-read──► EXPIRED (terminal for convert)
```

PDF title is **Quotation**. Invoice PDF stays **Tax Invoice**.

---

## 2. Number format — lock

**Format:** `QUO-YYYY-XXXX` (4-digit year, 4-digit sequence, e.g. `QUO-2026-0001`).

**Mechanism:** clone `InvoiceCounter` / `InvoiceNumberService`:

- Table `quotation_counters` — composite PK `(workspace_id, year)`, `last_number`.
- `QuotationNumberService.generate_quotation_number` uses `SELECT FOR UPDATE` inside the create transaction.
- Increment only commits with the quotation row. Failed create rolls back (no consumed number).
- Soft-delete does **not** rewind the counter (same as invoices).

**Do not** reuse `invoice_counters`. Quote numbers and tax-invoice numbers are different sequences.

### Why sequential FOR UPDATE even though quotes are not FTA tax invoices

UAE VAT sequential / gapless numbering applies to **tax invoices and credit notes**, not quotations. Electrical wholesale quotes are commercial offers.

We still use the counter because:

1. Traders file quotes as `QUO-2026-0045`; uniqueness per workspace/year is operationally required.
2. The counter + row lock already exists (INV, SPO). Do not invent UUID-as-number or a second generator style.
3. Rollback-on-fail avoids duplicate numbers under concurrent create.

Call this **operationally sequential**, not legally gapless. Do not add FTA language to the quote PDF or send path.

---

## 3. State machine — lock

Enum `QuotationStatus`:

`DRAFT | SENT | ACCEPTED | REJECTED | EXPIRED | CONVERTED`

**Not in this WP:** `REVISED`, `CANCELLED` (quotes are not tax documents; DRAFT uses soft-delete).

```
                         ┌─────────────────────────────────────────┐
                         │                 DRAFT                    │
                         │         PUT / DELETE allowed             │
                         └───────────┬─────────────────────────────┘
                               /send │
                                     ▼
                         ┌─────────────────────────────────────────┐
                         │                 SENT                     │
                         │     on-read: valid_until < today         │
                         │              → EXPIRED                   │
                         └──┬──────────┬──────────┬────────────────┘
                    /accept │  /reject │          │ (expiry)
                            ▼          ▼          ▼
                     ACCEPTED      REJECTED    EXPIRED
                        │         (terminal)  (terminal)
         /convert-to-   │
         invoice        ▼
                    CONVERTED  (terminal; invoice_id on invoices.quotation_id)
```

### Transitions

| From | To | How |
|---|---|---|
| DRAFT | SENT | `POST /quotations/{id}/send` |
| DRAFT | (gone) | `DELETE` soft-delete (`deleted_at`) |
| SENT | ACCEPTED | `POST /quotations/{id}/accept` |
| SENT | REJECTED | `POST /quotations/{id}/reject` optional `{reason}` |
| SENT | EXPIRED | On-read (GET/list/accept/reject/convert) when `valid_until < UTC today` |
| ACCEPTED | CONVERTED | `POST /quotations/{id}/convert-to-invoice` |

### Forbidden (403 `INVALID_STATE` unless noted)

- PUT / DELETE unless DRAFT (and not deleted).
- Send unless DRAFT, ≥ 1 line, AED.
- Accept / reject unless SENT (after applying on-read expiry).
- Convert unless ACCEPTED. **SENT cannot convert** (WP-B: Accept then Convert).
- Convert EXPIRED / REJECTED / DRAFT → 403 `INVALID_STATE`.
- Un-send, un-reject, un-expire: no reverse transitions.
- No email / WhatsApp on send. Status-only, like invoice send.

### Convert once (idempotent)

- First convert (ACCEPTED): create DRAFT invoice, set `invoices.quotation_id`, set quote `CONVERTED`. HTTP **201** with `InvoiceResponse`.
- Later convert (already CONVERTED): **do not** create a second invoice. HTTP **200** with the existing invoice (`invoices.quotation_id == quote.id`, including if that invoice is later CANCELLED). Unique on `invoices.quotation_id` enforces one invoice per quote.
- If that invoice is **soft-deleted**: still do not recreate. **409** `CONFLICT` with `error.field=quotation_id` and message that the quote was already converted. User creates a new invoice manually.

Lock convert with `SELECT FOR UPDATE` on the quotation row (same transaction as invoice create).

---

## 4. Line model — reuse invoice shape

**Reuse**, do not thin.

`quotation_items` columns match live `invoice_items` (minus `invoice_id`):

| Column | Type | Notes |
|---|---|---|
| `product_id` | UUID FK `products.id` nullable, index | Optional. Other-workspace → **404**. Inactive → **400**. |
| `uom_id` | UUID FK `units_of_measure.id` nullable | Copied from product `base_uom_id` when catalog line |
| `sku_snapshot` | `String(100)` nullable | From `product.internal_sku` |
| `description` | `String(500)` NOT NULL | Required if no `product_id` |
| `quantity` | Numeric(10,2) | `> 0` (live invoice qty) |
| `unit_price` | Numeric(12,2) | Required if no `product_id`; else DEFAULT_SALES or body override |
| `tax_rate` | Numeric(5,2) NOT NULL | Omit on write → product.tax_rate else workspace `default_tax_rate` **5.00** |
| `discount_percent` / `discount_amount` | same as invoice | XOR; both > 0 → **422** |
| `line_net` | Numeric(12,2) | after discount, excl VAT |
| `tax_amount` | Numeric(12,2) | line VAT |
| `total_price` | Numeric(12,2) | **gross** = net + VAT |

**Math:** import / extract the live helpers. **Do not fork.**

Preferred: extract `money()`, XOR discount, `_apply_line_money` into `app/services/line_money.py` and call from `InvoiceService` and `QuotationService`. If extract is too large for this WP, `QuotationService` **must** import `money` and `_apply_line_money` from `invoice_service` (same ROUND_HALF_UP fils). Header totals = Σ line_net, Σ line_vat, `money(subtotal + tax)`.

No header-level quote discount (FTA deferred header discount; keep line-only).

---

## 5. Validity and expiry

| Field | Lock |
|---|---|
| `quotation_date` | Date NOT NULL; default UTC today if omitted |
| `valid_until` | Date NOT NULL; default `quotation_date + 14 days` if omitted |
| Rule | `valid_until >= quotation_date` else **422** |
| Default 14 days | UAE electrical quotes are typically 7–14 days. Lock **14**. |

**Expiry: on-read, not a job this WP.**

No Celery/Redis expiry worker (OVERDUE job is also not wired). On GET, list, accept, reject, convert:

1. `SELECT FOR UPDATE` the row when mutating.
2. If `status == SENT` and `valid_until < date.today()` (UTC date, same as invoice dates): set `EXPIRED`, persist, emit event.
3. List may bulk-update `SENT` rows in the workspace that are past `valid_until` before filtering.

Optional nightly job: **out**. Document only.

EXPIRED cannot accept, reject, or convert.

---

## 6. Convert to DRAFT invoice

Call **`InvoiceService.create_invoice`**. Do not insert `Invoice` / `InvoiceItem` rows in `QuotationService` by hand.

### Copy

| Quote | Invoice |
|---|---|
| `client_id` | same |
| `currency` | AED (already required) |
| lines | each item dict: `description`, `quantity`, `unit_price` (**explicit, frozen**), `tax_rate` (**stored resolved**), `discount_percent`, `discount_amount`, `product_id` if still active in workspace else **omit** (ad-hoc line; keep description; SKU may prefix description if useful) |
| `notes` | `"Converted from {quotation_number}."` plus original notes if any |

### Set by convert (not copied)

| Invoice field | Value |
|---|---|
| `invoice_number` | new `INV-YYYY-XXXX` via `InvoiceNumberService` |
| `status` | **DRAFT** |
| `issue_date` | UTC today |
| `supply_date` | UTC today |
| `due_date` | today + 30 days (UX default only; gap 3 credit terms still deferred) |
| `quotation_id` | quote.id |
| `invoice_kind` + snapshots | **null** (DRAFT) |

### Do **not** run on convert

- FTA send gates (workspace TRN, address, STANDARD buyer TRN).
- Invoice send / email.
- Re-price from `DEFAULT_SALES` (pass explicit `unit_price` so `_line_unit_price` does not replace frozen quote prices).
- Credit HOLD.
- LPO / CPO create.

Invoice totals are **recomputed** by `InvoiceService` (same formula). Do not copy header totals blindly.

`InvoiceResponse` gains optional `quotation_id`. GET invoice does not need to embed the quote.

---

## 7. Convert to LPO — skip this WP

**Do not** mount `POST /quotations/{id}/convert-to-cpo` or any LPO stub (no 501 litter).

Next after quotes A–C: gap 5 LPO addendum. `state-machines.md` SENT→CPO is deferred with LPO.

Walk-in / counter sales: quote → accept → convert-to-invoice (this WP) **or** create invoice directly (already live). LPO is the contractor path, later.

---

## 8. PDF (WP-B)

New `frontend/src/components/pdf/QuotationPDF.tsx` (clone layout from `InvoicePDF`, **do not** change Tax Invoice title).

| | Quote PDF | Invoice PDF |
|---|---|---|
| Title | **Quotation** | Tax Invoice (unchanged) |
| Number | `QUO-YYYY-XXXX` | `INV-YYYY-XXXX` |
| Dates | quotation date, **valid until** | issue, supply, due |
| VAT lines | yes (same columns: net, VAT%, VAT, gross) — commercial estimate | FTA tax invoice |
| Seller TRN/address | print **if present**; **not** required to send the quote | required to send |
| Language | **English only** | English only (Arabic still deferred) |
| Watermark | EXPIRED / REJECTED if those statuses | CANCELLED if voided |

Client-side `@react-pdf/renderer` on download. Not stored at send. Rebuild from GET payload.

---

## 9. Schema (Alembic **yes**)

New revision, `down_revision = "c8e1a4f2b6d0"`. PostgreSQL ENUM + tables. Never rewrite history.

### `quotation_counters`

Same shape as `invoice_counters`: `workspace_id` PK FK, `year` PK, `last_number` NOT NULL default 0, timestamps.

### `quotations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID FK `workspaces.id` NOT NULL, index | |
| `client_id` | UUID FK `clients.id` NOT NULL, index | Same-workspace check in service |
| `quotation_number` | `String(50)` | Unique `(workspace_id, quotation_number)` |
| `status` | ENUM as above | default DRAFT |
| `currency` | `String(3)` default `AED` | Write/send/convert **AED only** → 422 |
| `quotation_date` | Date NOT NULL | |
| `valid_until` | Date NOT NULL | |
| `subtotal` / `tax_amount` / `total_amount` | Numeric(12,2) NOT NULL | checks ≥ 0 |
| `notes` | Text nullable | |
| `rejection_reason` | Text nullable | set on reject |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz nullable | soft-delete DRAFT only |

**No** `enquiry_id`, `revision_number`, `revised_from_id`, `payment_terms_days`, `delivery_terms`, `discount_amount` (header), `created_by` (use events + JWT).

### `quotation_items`

As §4. FK `quotation_id` → `quotations.id` index. Same check constraints as `invoice_items`.

### `quotation_events`

Clone `invoice_events` (per-doc table; do not stuff quotes into `invoice_events`):

Types: `QUOTATION_CREATED`, `QUOTATION_UPDATED`, `QUOTATION_SENT`, `QUOTATION_ACCEPTED`, `QUOTATION_REJECTED`, `QUOTATION_EXPIRED`, `QUOTATION_CONVERTED`.

`metadata_log` JSONB. `changed_by` FK users.

### `invoices.quotation_id`

- UUID nullable, FK `quotations.id`, **indexed**, **unique** (PostgreSQL unique allows many NULLs).
- No `quotations.converted_invoice_id` column (avoid circular FK). Hydrate `converted_invoice_id` on `QuotationResponse` via `SELECT invoices WHERE quotation_id = …`.

---

## 10. API

Base: `/api/v1`. Router prefix `/quotations`, mounted in `main.py`. Auth: `Authorization: Bearer` on **all** routes (no public accept). JWT `workspace_id` never from body.

Wrapper: `SuccessResponse` / `PaginatedResponse` (`data` array + `pagination` sibling). Errors: HTTPException → `{success: false, error: {code, message, field?}}`.

Extra body keys → **422** (`extra="forbid"`). Decimal money, never float.

Cross-tenant GET/PUT/DELETE/send/accept/reject/convert → **404** (not 403), same as invoices. Missing client/product in workspace → 404.

### Endpoints

```
POST   /quotations
GET    /quotations?status&client_id&search&page&per_page
GET    /quotations/{id}
PUT    /quotations/{id}                         DRAFT only
DELETE /quotations/{id}                         DRAFT soft-delete
POST   /quotations/{id}/send                    DRAFT → SENT
POST   /quotations/{id}/accept                  SENT → ACCEPTED
POST   /quotations/{id}/reject                  SENT → REJECTED  body { reason?: str }
POST   /quotations/{id}/convert-to-invoice      ACCEPTED → CONVERTED + DRAFT invoice
```

List: `page` default 1, `per_page` default 20 max 100. `search` matches `quotation_number`. Exclude `deleted_at` by default.

`POST /quotations` body (mirror invoice create, not api-contracts enquiry blob):

- `client_id` required
- `quotation_date` optional
- `valid_until` optional (default +14)
- `currency` optional, must be AED
- `notes` optional
- `items[]` required, ≥ 1: same as `InvoiceItemCreate` (`description` optional iff `product_id`, `tax_rate` optional, XOR discounts, `product_id` optional)

Send: empty body or `{}`. No FTA_SEND_BLOCKED. Still require AED + ≥ 1 line.

Convert response: `SuccessResponse[InvoiceResponse]` (201 first time, 200 if already CONVERTED and invoice not deleted).

Do **not** add preview-next-number endpoint unless invoices already expose one used by UI (they have service preview; skip HTTP unless WP-B needs it — WP-B can show number after create).

---

## 11. Service / module boundaries

| Layer | Owns |
|---|---|
| `routers/quotations.py` | HTTP, auth deps, wrapper, status codes |
| `services/quotation_service.py` | State machine, expiry-on-read, line math (shared), isolation |
| `services/quotation_number.py` | FOR UPDATE counter |
| `InvoiceService.create_invoice` | Convert target only |

`QuotationService.convert_to_invoice` must not duplicate invoice numbering or FTA math.

Files stay under 500 lines; split number service like invoices.

---

## 12. Tests — `backend/tests/test_quotations.py` (+ isolation)

PostgreSQL only. Never SQLite.

1. Create → `QUO-{year}-0001`; second create `0002`. Concurrent create unique (clone invoice numbering test pattern).
2. Omit line `tax_rate` → stored 5.00 (workspace default); header tax = 5% of net.
3. XOR discounts; both → 422. Extra key `hs_code` → 422. Non-AED → 422.
4. `product_id` copies name/SKU/price/tax; other-workspace product **404**; inactive **400**. Ad-hoc line 201.
5. PUT / DELETE / send non-DRAFT → **403** `INVALID_STATE`.
6. Isolation: workspace B GET/PUT/send/accept/convert workspace A id → **404**.
7. Send DRAFT → SENT; send does **not** require workspace TRN (contrast invoice send).
8. Accept then convert → invoice **DRAFT**, `quotation_id` set, new `INV-…`, line prices **equal** quote (not re-list-priced), quote **CONVERTED**. Invoice snapshots / `invoice_kind` null.
9. Convert twice → **200**, same `invoice_id`, one invoice row.
10. Convert from SENT (not accepted) → **403**. Convert from DRAFT → **403**.
11. SENT with `valid_until` yesterday → GET shows **EXPIRED**; convert → **403**; accept → **403**.
12. Reject SENT → REJECTED; convert → **403**.
13. Convert does **not** call FTA send; converted DRAFT can fail invoice send without TRN (`FTA_SEND_BLOCKED`) — quote stays CONVERTED.
14. Soft-delete DRAFT; GET 404; number not reused.
15. `alembic upgrade head` + `alembic check` clean.

Do not break `test_invoices.py` / payment isolation / concurrent INV numbering.

---

## 13. WP split

### WP-A — API + Alembic + tests

Models, migration from `c8e1a4f2b6d0`, schemas, `QuotationService` + number service, router, `invoices.quotation_id` + `InvoiceResponse.quotation_id`, convert via `InvoiceService.create_invoice`, pytest §12. **No frontend.**

**Acceptance:** tests §12 green; `alembic check`; quote send without TRN succeeds; invoice send still blocked without TRN; convert-once; expired cannot convert; DRAFT-only edit; cross-tenant 404; Decimal money.

### WP-B — UI + PDF

- `Layout.tsx` Sales: **Quotations** between Clients and Invoices (`/quotations`).
- List + filters (status, client, search).
- Form: client, dates, validity default +14, product picker, ad-hoc lines, inherit 5% tax, XOR discount, AED.
- Actions: Send, Accept, Reject (reason), Convert (enabled on ACCEPTED; SENT shows Accept first).
- Convert navigates to DRAFT invoice.
- `QuotationPDF`: title **Quotation**, valid until, not Tax Invoice. English. Helvetica.

**Acceptance:** `npm run build`; create catalog + ad-hoc lines; PDF says Quotation and shows validity; convert opens DRAFT invoice; Tax Invoice PDF unchanged.

### WP-C — Playwright

Register → client → product with DEFAULT_SALES → quotation → send → accept → convert → land on DRAFT invoice → invoice send still needs Settings TRN+address.

Negatives: second convert returns same invoice; expired quote cannot convert; other workspace quotation URL 404.

**Acceptance:** local API + Postgres, not SQLite. Do not cover LPO/GRN/WhatsApp.

---

## 14. Drift vs paper

| Paper | This WP |
|---|---|
| `state-machines.md` REVISED / revise endpoint / same-number revision | **Defer.** Copy-as-new-DRAFT later if needed. |
| `state-machines.md` SENT → CONVERTED | **No.** Accept first. |
| `state-machines.md` daily midnight expiry job | **On-read** only |
| `state-machines.md` DRAFT → CANCELLED | **Soft-delete** DRAFT; no CANCELLED enum |
| `api-contracts.md` enquiry_id, email/WhatsApp send, public accept | **Out** |
| `api-contracts.md` / gaps `convert-to-cpo` | **Skip until LPO wave** |
| Gaps `payment_terms_days`, header discount, USD quotes | **Out** (AED only) |
| Gaps bilingual “عرض سعر” | **English Quotation only** |
| Gaps `revision_number` + `revised_from_id` | **No columns** |

---

## 15. NOT in this WP

Customer PO OCR, WhatsApp, email send, Arabic font, credit HOLD / overdue engine, delivery notes, tax credit notes, Peppol, enquiry module, LPO/CPO tables or stub routes, public unauthenticated accept, quote number rewind, header discount, USD, `POST /revise`, changing invoice send rules.

---

## 16. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic **yes**, `down_revision = "c8e1a4f2b6d0"` only. Never rewrite `c8e1a4f2b6d0` / `d3e4c7fdb29f`.
3. Convert = `InvoiceService.create_invoice`. Shared line math. FTA checks stay on invoice send.
4. WP-A tests green before WP-B.
5. Next after A–C: **LPO (gap 5)**, not credit notes or WhatsApp.
