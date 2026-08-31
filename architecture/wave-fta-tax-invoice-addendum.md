# FTA Tax Invoice — Architecture Addendum (Gaps 1–2)

**Date:** 2026-08-31
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Invoice` / `InvoiceItem` / `InvoiceService` / `InvoicePDF`. Do **not** create `TaxInvoice` or a second invoice table.
**After WP-A–C:** quotations → LPO (gaps 4–5). Not this slice: WhatsApp, OCR, Peppol, credit-control engine, credit notes, delivery notes, PDC PUT.

Wave 3 Product Master is shipped. Catalog lines may now carry `product_id`. This addendum is **Gap 1 (FTA tax invoice)** + **Gap 2 (line VAT math + default 5% + `product_id`)**.

Copy the Wave 3 split: **WP-A API → WP-B UI → WP-C browser E2E**. Do not start WP-B until WP-A pytest is green.

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| `backend/app/models/invoice.py` | Header: `issue_date`, `due_date`, `currency`, `subtotal`/`tax_amount`/`total_amount` Numeric(12,2). **No** supply_date, snapshots, discounts. |
| `backend/app/models/invoice_item.py` | `description`, `quantity` Numeric(10,2), `unit_price`, `tax_rate` **NOT NULL default 0**, `total_price`. **No** product_id, discount, line_net, line tax_amount. |
| `InvoiceService.create_invoice` | `tax_rate` missing → **0**. `total_price = qty * price * (1 + rate/100)` (**gross**). |
| `InvoiceService._recalculate_totals` | `subtotal = Σ qty*price` (**net**), `tax = Σ net * rate/100`, **no quantize**. Line gross vs header net **disagree**. |
| `schemas/invoices.py` | `tax_rate` default **0**; no `product_id`; `Currency` includes USD; **no** `amount_paid`/`balance_due` on `InvoiceResponse` (model properties exist; GET does not `selectinload` payments). |
| `frontend/.../InvoicePDF.tsx` | Title **`INVOICE`**. Seller TRN if present. No seller address, no buyer TRN/address, no supply date, no line VAT/discount, line “Total” = `total_price`. |
| `Client.tax_id` | Buyer TRN storage. **Do not add `clients.trn`.** |
| `Workspace.trn`, `default_tax_rate=5.00` | Seller TRN + VAT default. **No** workspace address/IBAN. |
| Alembic HEAD | `06c9b4b1dcda`. New revision **must** `down_revision = "06c9b4b1dcda"`. Never edit `d3e4c7fdb29f` or any prior file. |

State machine (**unchanged**): DRAFT → SENT via `POST /invoices/{id}/send`; edit/delete DRAFT only; payments immutable; overpay 400; gapless `INV-YYYY-XXXX`.

---

## 1. ASCII — line → totals → PDF

```
                    InvoiceItem (DRAFT, service-owned math)
  quantity, unit_price, discount_percent XOR discount_amount
  tax_rate (resolved, never null)
  product_id?  → snapshots: sku_snapshot, uom_id, description default
           │
           │  ROUND_HALF_UP to 0.01 AED (fils) PER LINE, then SUM
           ▼
  extended     = money(qty * unit_price)
  disc         = money(discount_amount) OR money(extended * pct/100)
  line_net     = money(extended - disc)          → stored line_net
  line_vat     = money(line_net * tax_rate/100)  → stored tax_amount
  total_price  = money(line_net + line_vat)      → GROSS (keep column name)
           │
           ▼
  Invoice.subtotal    = Σ line_net
  Invoice.tax_amount  = Σ line_vat
  Invoice.total_amount= money(subtotal + tax_amount)

  SEND (DRAFT→SENT) hard-fail FTA fields; freeze snapshots
           │
           ▼
  PDF "Tax Invoice"  ← snapshots if SENT else live workspace+client
       seller name/address/TRN
       buyer name/address/TRN (STANDARD)
       INV-YYYY-XXXX, issue_date, supply_date, due_date
       lines: desc, SKU?, qty, UOM?, unit, discount, net, VAT%, VAT AED, gross
       sums: subtotal (excl VAT), VAT 5%, total AED, paid, balance
```

---

## 2. FTA PDF / legal fields vs live commercial PDF

FTA Art. 59 **standard tax invoice** (B2B electrical default):

| # | Required particular | Live PDF | This WP |
|---|---|---|---|
| 1 | Words **“Tax Invoice”** | `"INVOICE"` | **Change title** |
| 2 | Sequential number | `INV-YYYY-XXXX` | Keep gapless |
| 3 | Issue date | `issue_date` | Keep |
| 4 | Date of supply if different | missing | `supply_date` (always print; may equal issue) |
| 5 | Seller name | `workspace.name` | Keep |
| 6 | Seller **address** | missing | **`workspaces.address` + snapshot** |
| 7 | Seller **TRN** (15 digits) | optional print | **Hard-fail send** if invalid |
| 8 | Buyer name | `client.name` | Keep |
| 9 | Buyer address | not printed (`client.address` exists) | Print; **hard-fail STANDARD send** if empty |
| 10 | Buyer TRN if registered | not printed (`tax_id`) | Print; **hard-fail STANDARD send** if invalid |
| 11 | Description, qty, unit price | yes | + SKU/UOM if catalog line |
| 12 | Discount | no | **Line** discount; VAT on net after discount |
| 13 | VAT rate + VAT **AED** | header tax only; lines no rate | Per line + header |
| 14 | Gross payable AED | total | Keep; **send requires currency AED** |

**Simplified** tax invoice (FTA): seller name/address/TRN, issue date, description, total incl VAT. Still titled **Tax Invoice**. Buyer TRN/address optional.

English-only is legal (Cabinet Decision 74/2023). **Arabic PDF deferred** (gap 13) — Helvetica cannot render Arabic; do not block this WP on a font pack.

IBAN / logo / WhatsApp: optional print if present. **IBAN column deferred** (gap 14 remainder).

---

## 3. Send hard-fails (`POST /invoices/{id}/send`)

Send remains **status-only** (no email). `DRAFT → SENT` only after **all** checks. HTTP **400** `FTA_SEND_BLOCKED` (add to `ErrorCode`) with `error.field` set. Do **not** 403 for missing TRN (403 stays INVALID_STATE for non-DRAFT).

**Always (both STANDARD and SIMPLIFIED):**

1. Invoice DRAFT, not deleted, JWT workspace.
2. `currency == "AED"`.
3. ≥ 1 line; `total_amount >= 0`.
4. **Workspace TRN:** `workspace.trn` matches `^100[0-9]{12}$` (exactly 15 digits, starts with `100`). Strip spaces. Null/invalid → fail `field=workspace.trn`.
5. **Workspace address:** `workspace.address` non-empty after strip → fail `field=workspace.address`.
6. **Workspace name** non-empty (already required).
7. **Client name** non-empty.

**Kind (no client override in this WP):**

```
if client.tax_id stripped matches TRN regex:
    kind = STANDARD
elif invoice.total_amount > Decimal("10000.00"):
    kind = STANDARD
else:
    kind = SIMPLIFIED
```

**If STANDARD additionally:**

8. Buyer TRN: `client.tax_id` must match the same regex → `field=client.tax_id`.
9. Buyer address: `client.address` non-empty → `field=client.address`.

**If SIMPLIFIED:** buyer TRN/address **not** required. PDF omits buyer TRN row if null; still prints buyer name.

On success: set `invoice_kind`, write snapshots (§6), then existing `mark_as_sent`. Cross-workspace send stays **404**.

**Create/PUT** do **not** require TRN (drafts allowed). Tests that only create drafts stay green. **`test_payment_is_workspace_isolated` currently sends without TRN — WP-A must update that fixture** (PUT workspace TRN+address; PUT client `tax_id`+address) rather than weaken send.

---

## 4. Line math (service owns it; router must not compute)

`ROUND_HALF_UP`, `quantize(Decimal("0.01"))` **per line**, then sum. Never float. `from decimal import Decimal, ROUND_HALF_UP`.

```
money(x) = x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

extended      = money(quantity * unit_price)
# discount: XOR — both set → 422; neither → 0
disc          = money(discount_amount) if amount else money(extended * discount_percent / 100)
if disc > extended: 400
line_net      = money(extended - disc)
line_vat      = money(line_net * tax_rate / 100)
total_price   = money(line_net + line_vat)     # GROSS; keep name
```

Header:

```
subtotal     = Σ line_net
tax_amount   = Σ line_vat
total_amount = money(subtotal + tax_amount)
```

**`tax_rate` on create/update:** optional. Resolve in service, **persist NOT NULL** (column stays NOT NULL):

1. If body `tax_rate` set → use it (`0 <= rate <= 100`).
2. Else if `product_id` and `product.tax_rate` is not null → product rate.
3. Else → `workspace.default_tax_rate` (typically **5.00**).

Do **not** leave 0 when the client omitted the field (today’s bug). Explicit `tax_rate: 0` is allowed (zero-rated line).

**Header discount:** **defer**. Line discounts only. Extra key `discount_amount` on invoice header → **422**.

Fix **both** create and PUT item-replace paths. Today PUT in `routers/invoices.py` computes gross itself — **move into `InvoiceService`**. `_recalculate_totals` must use stored `line_net` / `tax_amount` after this WP (recompute those fields first, then sum).

---

## 5. `product_id` — optional (catalog + ad-hoc)

**Decision:** **optional**. Electrical wholesale mixes SKU lines and one-off descriptions (site extras, cutting charges). Required `product_id` would block real invoices.

| Body | Rules |
|---|---|
| `product_id` set | Product JWT workspace, not deleted. Inactive → **400** cannot *add*. Copy **if omitted**: `description` ← `product.name`; `unit_price` ← `ProductPrice` `DEFAULT_SALES` (same workspace) or **422** `NO_LIST_PRICE` if none; `tax_rate` ← product then workspace; `sku_snapshot` ← `internal_sku`; `uom_id` ← `base_uom_id`. Explicit description / unit_price / tax_rate **override**. Cross-tenant or missing product → **404**. |
| `product_id` omitted | `description` required; `unit_price` required; tax inherit workspace; `sku_snapshot`/`uom_id` null. |

Do **not** run volume/`CUSTOMER_SPECIFIC` pricing in this WP (Wave 3 engine). List price only when copying.

Do **not** convert UOM on the line (qty is in the line UOM; snapshot only).

---

## 6. Alembic — **YES** (new revision from HEAD)

**File:** new `backend/alembic/versions/<rev>_fta_tax_invoice_fields.py`
**`down_revision = "06c9b4b1dcda"`** (or current HEAD if it moved; never rewrite history).

### `workspaces`

| Column | Type | Notes |
|---|---|---|
| `address` | `Text` nullable | Seller FTA address. IBAN **not** added. |

### `invoices`

| Column | Type | Notes |
|---|---|---|
| `supply_date` | `Date` NOT NULL | Backfill existing rows = `issue_date`. Default on create = `issue_date` if omitted. |
| `invoice_kind` | `String(20)` nullable | Null on DRAFT; `STANDARD` or `SIMPLIFIED` set at send. |
| `seller_trn_snapshot` | `String(15)` nullable | Written at send |
| `seller_name_snapshot` | `String(255)` nullable | |
| `seller_address_snapshot` | `Text` nullable | |
| `buyer_trn_snapshot` | `String(15)` nullable | |
| `buyer_name_snapshot` | `String(255)` nullable | |
| `buyer_address_snapshot` | `Text` nullable | |

No `quotation_id`, `cpo_id`, `retention_*`, `einvoice_*`, `vat_reported_at`, `discount_amount` (header).

### `invoice_items`

| Column | Type | Notes |
|---|---|---|
| `product_id` | UUID FK `products.id` nullable, index | |
| `uom_id` | UUID FK `units_of_measure.id` nullable | |
| `sku_snapshot` | `String(100)` nullable | |
| `discount_percent` | `Numeric(5,2)` NOT NULL default 0 | |
| `discount_amount` | `Numeric(12,2)` NOT NULL default 0 | |
| `line_net` | `Numeric(12,2)` NOT NULL default 0 | after discount, excl VAT |
| `tax_amount` | `Numeric(12,2)` NOT NULL default 0 | line VAT |

Keep `total_price` as **gross**. Keep `quantity` Numeric(10,2) (live). Check: `discount_percent >= 0`, `discount_amount >= 0`, `line_net >= 0`.

Backfill existing items in the same migration (SQL):

```
line_net = round(quantity * unit_price, 2)
tax_amount = round(line_net * tax_rate/100, 2)
total_price = line_net + tax_amount   -- may differ from old gross; acceptable for drafts
```

Existing SENT rows: best-effort backfill; new sends always snapshot.

**No new `clients` columns.** `tax_id` **is** TRN.

---

## 7. Supply date vs issue vs due

| Field | Meaning | Rules |
|---|---|---|
| `issue_date` | Tax invoice date | Required. Unchanged. |
| `supply_date` | Date of supply | Required in DB; default `issue_date`. May be **before** issue (supply then invoice within ~14 days). **May not be after `issue_date`** → 422. |
| `due_date` | Payment due | `>= issue_date` (existing validator). **No** auto Net 30/45/60 this WP (**gap 3 deferred**). Form may keep +30 days UX only. |

Warn-only 14-day FTA timing: **do not block send**. No job.

---

## 8. State machine and PDF generation

**Unchanged transitions.** SEND still DRAFT→SENT. No email.

PDF: **client-side** `@react-pdf/renderer` on download (today). **Not** generated or stored at send. Every download rebuilds from GET payload. After SENT, PDF **must use snapshot fields**, not live client/workspace (TRN/address must not drift).

GET `/invoices/{id}`: `selectinload` **items and payments** so `amount_paid` / `balance_due` are correct. Add those two to `InvoiceResponse` and `InvoiceListItem` (computed; no columns).

Optional watermark **CANCELLED** in WP-B if `status === CANCELLED`.

---

## 9. Client / workspace / credit / bilingual

| Topic | This WP |
|---|---|
| Client TRN | **`tax_id`**. Schema may add validation_alias `trn` **writing the same column**. No second column. |
| Client address | Existing. Required on STANDARD send. |
| Credit terms 30/45/60 | **Defer (gap 3).** No `credit_limit` / HOLD. |
| Workspace `address` | **In WP-A** (column) + **WP-B Settings field**. |
| Workspace IBAN | **Defer (gap 14).** |
| Arabic PDF | **Defer (gap 13).** English “Tax Invoice” only. |
| Peppol / PINT-AE | Out. |

---

## 10. API / schema diffs (live endpoints kept)

No new resource. Extra body keys → **422** (`model_config extra="forbid"` on Create/Update item and invoice).

**`InvoiceItemCreate`:** `description` optional if `product_id` (service fills); if neither product nor description → 422. `quantity`, `unit_price` (optional iff product_id and list price exists). `tax_rate` optional. `product_id` optional UUID. `discount_percent` optional default 0. `discount_amount` optional default 0. XOR discounts.

**`InvoiceItemResponse`:** + `product_id`, `uom_id`, `sku_snapshot`, `discount_percent`, `discount_amount`, `line_net`, `tax_amount` (line VAT), `tax_rate` (resolved), `total_price` (gross).

**`InvoiceCreate`:** + optional `supply_date`. `currency` **AED only** (drop USD from this schema or 422 in service — **lock: 422 if not AED** on create/update/send).

**`InvoiceResponse`:** + `supply_date`, `invoice_kind`, snapshots, `amount_paid`, `balance_due`.

**`WorkspaceResponse` / `WorkspaceUpdate`:** + `address`.

**`GET /invoices/{id}/pdf-model`:** **not required** if GET invoice + GET `/workspaces/me` + GET client suffice **and** snapshots are on the invoice after send. WP-B PDF prefers invoice snapshots when `status !== DRAFT`.

Service: all math + send checks + product copy in `InvoiceService`. Router: HTTP only. `mark_as_sent` must not skip FTA checks (call `assert_fta_sendable` first). Replace `ValueError` 500 risk with HTTPException 400.

---

## 11. Tests — `backend/tests/test_invoices.py` (+ patch isolation)

PostgreSQL only.

1. Omit line `tax_rate` → stored rate = workspace `default_tax_rate` (5.00); header `tax_amount` = 5% of net.
2. Explicit `tax_rate: 0` stays 0.
3. Decimal: qty 3, price 1.11, 5% → per-line `ROUND_HALF_UP` fils; `subtotal + tax_amount == total_amount`.
4. Line discount % : VAT on net after discount.
5. Both discount fields → 422.
6. `product_id` copies name/SKU/list price/tax; override description works; other-workspace product 404; inactive product 400.
7. Ad-hoc line (no product_id) still 201.
8. Send without workspace TRN → 400 `FTA_SEND_BLOCKED`; still DRAFT.
9. Send with invalid TRN (not 15 / not `100…`) → 400.
10. Send without workspace.address → 400.
11. STANDARD (total > 10000 or client has TRN) without client.tax_id or address → 400.
12. SIMPLIFIED (no client TRN, total ≤ 10000) send succeeds with seller TRN+address only; `invoice_kind=SIMPLIFIED`; snapshots set.
13. PUT non-DRAFT → 403 INVALID_STATE (existing).
14. Isolation: cross-workspace GET/PUT/SEND 404 (existing file).
15. Overpayment still 400 (existing payment tests).
16. Extra key on item `hs_code` → 422.
17. `supply_date > issue_date` → 422.
18. Gapless numbering still unique (`test_concurrent_numbering.py` green).
19. **Update** `test_payment_is_workspace_isolated` so send meets FTA hard-fails.

`alembic upgrade head` + `alembic check` clean.

---

## 12. WP split (recommended — same as Wave 3)

### WP-A — API (coder + Database Agent for migration)

Alembic §6, models, schemas, `InvoiceService` math + send, workspace `address` on GET/PUT `/workspaces/me`, tests §11. **No frontend.**

**Acceptance:** pytest `test_invoices.py` + isolation + concurrent numbering + existing suite; `alembic check`; send blocked without TRN; omit tax_rate → 5%; `product_id` optional; overpay 400; Decimal money.

### WP-B — UI (frontend)

- Settings: `address` + TRN (label TRN).
- Clients: label `tax_id` as TRN; address required hint for B2B.
- Invoice form: product picker (GET products), optional tax (placeholder inherit 5%), line discount, `supply_date` default issue, AED only; `?? 0` on amounts (Wave 1).
- `InvoicePDF`: title **Tax Invoice**; seller/buyer name, address, TRN; supply date; line net / VAT% / VAT / gross; discounts; snapshots when not DRAFT; CANCELLED watermark.
- Types in `api/invoices.ts` + `workspaces.ts`.

**Acceptance:** `npm run build`; create catalog line + ad-hoc line; PDF says Tax Invoice and shows 5% VAT; send error toast when TRN missing.

### WP-C — Browser E2E

Register → Settings TRN `100`+12 digits + address + tax 5% → client with TRN+address → product with DEFAULT_SALES → invoice with product_id and inherited VAT → send → PDF/download fields. Negative: send before TRN fails. Second workspace 404 on invoice URL.

**Acceptance:** local API + Postgres, not SQLite. Do not cover GRN/3-way in this E2E.

---

## 13. NOT in this slice

Quotations, LPO, DN, credit notes, enquiry, WhatsApp, email send, Peppol, Arabic font, IBAN, credit HOLD/Net terms engine, header discount, invoice_kind override, USD tax invoices, `from_uom` on lines, payment PUT/PDC (untouched).

---

## 14. Drift

| Paper | This WP |
|---|---|
| `api-contracts.md` invoice as generic commercial | FTA send gates + Tax Invoice PDF |
| `domain-model.md` new client `trn` column | Reuse `tax_id` |
| Gaps doc header discount XOR lines | **Line only** |
| Gaps doc bilingual must-have | **Defer AR** |
| Gaps doc IBAN on workspace | **Defer** |
| `InvoiceItem.total_price` as mixed gross | **Gross = net + VAT**; header subtotal = net |
| USD in `Currency` enum | **422** on invoice write/send |

---

## 15. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic from HEAD `06c9b4b1dcda` only.
3. All math in `InvoiceService`; forbid extra keys.
4. WP-A tests green before WP-B.
5. Next after A–C: quotations (gap 4), not FTA again.
