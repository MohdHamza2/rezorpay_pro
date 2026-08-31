# Customer LPO (CPO) — Architecture Addendum (Gap 5)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Quotation` / `QuotationService.convert_to_invoice` / `Invoice` / `InvoiceService` / `line_money.py` / FTA send rules. Do **not** create a second AR engine, a parallel invoice table, or a customer-PO money formula.
**Depends on:** Quotes A–C (`921892f`), FTA tax invoice (`371eabf`), Product Master (`9bc745b`).
**After this WP A–C:** credit HOLD (gap 6) then delivery notes (gap 7). Not this slice: OCR of scanned POs, WhatsApp, Peppol, credit notes, Arabic PDF, supplier SPO/GRN changes.

Copy the quotes split: **WP-A API+Alembic+tests → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

UAE name: **LPO**. Code: `CustomerPurchaseOrder`. Routes: `/customer-purchase-orders`. UI label: **LPO**. This is **inbound customer demand**, not a supplier SPO (do not reuse `spo_*` tables, counters, or routers).

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| Live backend | **No** customer PO / LPO model or router. `quotations` and `invoices` are live. `main.py` mounts `/quotations`. |
| `QuotationService.convert_to_invoice` | ACCEPTED → one **DRAFT** invoice via `InvoiceService.create_invoice`; quote `CONVERTED`; unique `invoices.quotation_id`. Idempotent 200. LPO convert **was skipped**. |
| `Invoice.quotation_id` | Nullable **unique** FK. Walk-in quote→invoice keeps this. LPO invoices must **not** set `quotation_id` (would block partial invoices). |
| `InvoiceService.create_invoice` | `quotation_id=` optional. No `customer_purchase_order_id` yet. FTA math; **no** send gates. |
| `line_money.py` | Shared `money()` / `apply_line_money`. LPO lines **must** import this. |
| `InvoicePDF` / `QuotationPDF` | Titles **Tax Invoice** / **Quotation**. New LPO PDF; do **not** retitle either. |
| `Layout.tsx` | Sales: Clients, Quotations, Invoices. Supplier nav already has “Purchase Orders” = **SPO**. Customer LPO label must be **LPO**. |
| Paper `state-machines.md` §3 | RECEIVED→CONFIRMED (credit), PARTIALLY_INVOICED, CLOSED. **This WP trims** — see §14. |
| Paper `api-contracts.md` `/confirm` + OCR | Credit HOLD and OCR **out**. |
| Alembic HEAD | `cb01b6bef962` (`cb01b6bef962_add_quotations.py`). New revision **must** `down_revision = "cb01b6bef962"`. Never rewrite quotes/FTA/product revisions. |

Invoice payments, overpay 400, gapless `INV-YYYY-XXXX`, and FTA send gates **unchanged**. Partial LPO invoices are still normal tax invoices when sent.

---

## 1. ASCII — quote → LPO → many DRAFT invoices

```
  Quotation ACCEPTED
       │
       │  POST /quotations/{id}/convert-to-lpo     (mutex with convert-to-invoice)
       ▼
  LPO  LPO-YYYY-XXXX     customer_po_number = contractor's own PO (external)
       quotation_id?     optional (manual LPO has none)
       lines: invoice shape + quantity_ordered + quantity_invoiced
               │
  DRAFT ──/receive──► RECEIVED ──POST .../invoices──► PARTIAL ──(remaining 0)──► INVOICED
    │                    │                              │
    │ PUT/DELETE         │ /cancel if invoiced=0        │ more /invoices
    │                    ▼                              ▼
    └── /cancel → CANCELLED              InvoiceService.create_invoice
                                         DRAFT INV-…  customer_purchase_order_id set
                                         quotation_id NULL
                                         FTA send waits until POST /invoices/{id}/send

  remaining[line] = quantity_ordered − Σ invoice_item.qty
      (invoices not deleted, status ≠ CANCELLED)
  remaining < requested  → 400 cannot over-invoice
```

**Not a tax invoice.** PDF title **LPO**. Supplier SPO / GRN stay untouched.

---

## 2. Number format — lock

**Internal number:** `LPO-YYYY-XXXX` (e.g. `LPO-2026-0001`).

**Mechanism:** clone quotation/invoice counters — table `lpo_counters` composite PK `(workspace_id, year)`, `LpoNumberService` + `SELECT FOR UPDATE`. Do **not** reuse `invoice_counters`, `quotation_counters`, or `spo_counters`. Soft-delete does **not** rewind. Failed create rolls back.

**Customer’s number:** `customer_po_number` `String(100)` nullable — the contractor’s own PO (`ADNOC-PO-8821`, `PO-001`). This is **not** our sequence. Blank/whitespace → store `NULL`.

**Unique:** partial unique index `(workspace_id, client_id, customer_po_number)` **where `customer_po_number IS NOT NULL`**. Two clients may both send `PO-001`. Same client + same number → **409** `CONFLICT`. Not unique globally.

### Why LPO-YYYY-XXXX and not the customer’s PO as primary key

1. Customer PO numbers collide across clients and get reused/revised.
2. Traders still file an internal LPO number next to QUO/INV.
3. UAE VAT gapless rules apply to **tax invoices**, not customer POs — this sequence is **operational**, like `QUO-YYYY-XXXX`, not legally gapless.

Prefix **LPO-** (UI name), not `CPO-`. Table/code remain `customer_purchase_orders` / `CustomerPurchaseOrder`.

---

## 3. State machine — lock

Enum `CustomerPurchaseOrderStatus`:

`DRAFT | RECEIVED | PARTIAL | INVOICED | CANCELLED`

**Not in this WP:** `CONFIRMED` (credit check), `CLOSED`, `PARTIALLY_INVOICED` (use `PARTIAL`), `FULLY_INVOICED` (use `INVOICED`).

```
                    ┌──────────────┐
                    │    DRAFT     │  PUT / DELETE; convert-from-quote lands here
                    └──────┬───────┘
                 /receive  │  /cancel or DELETE
                           ▼
                    ┌──────────────┐
                    │   RECEIVED   │  lines frozen; can invoice remaining
                    └──────┬───────┘
           /invoices │     │ /cancel only if quantity_invoiced = 0 all lines
                     ▼     ▼
              PARTIAL    CANCELLED (terminal)
                     │
           /invoices │  (when remaining = 0)
                     ▼
                 INVOICED
            (not terminal: void/delete of invoices
             recalculates back to PARTIAL or RECEIVED)
```

### Transitions

| From | To | How |
|---|---|---|
| (create) | DRAFT | `POST /customer-purchase-orders` or quote `convert-to-lpo` |
| DRAFT | RECEIVED | `POST /{id}/receive` — ≥ 1 line, AED |
| DRAFT | CANCELLED | `POST /{id}/cancel` `{reason?}` **or** `DELETE` soft-delete (pick one path for DRAFT: **DELETE = soft-delete**, `/cancel` from RECEIVED only — see below) |
| RECEIVED | PARTIAL | First `/invoices` that leaves remaining > 0 |
| RECEIVED | INVOICED | `/invoices` that consumes all remaining |
| RECEIVED | CANCELLED | `POST /{id}/cancel` if no countable invoices |
| PARTIAL | INVOICED | Further `/invoices` until remaining 0 |
| PARTIAL / INVOICED | PARTIAL / RECEIVED | Side effect of invoice void or DRAFT delete (recalc) |

**DRAFT cancel vs delete:** same as quotes — `DELETE` soft-deletes DRAFT. `POST /cancel` is **RECEIVED only** (and RECEIVED with zero countable invoices). Do not add a CANCELLED enum row for soft-deleted drafts (they have `deleted_at`).

### Recalc after every invoice create / void / DRAFT delete

```
if status in (CANCELLED,) or deleted: leave
elif all lines remaining == 0 and has_countable_invoice: INVOICED
elif any quantity_invoiced > 0: PARTIAL
elif status was DRAFT: stay DRAFT
else: RECEIVED
```

Count **countable** invoices: `deleted_at IS NULL` and `status != CANCELLED`. DRAFT invoices **count** (blocks concurrent over-invoice).

### Forbidden (403 `INVALID_STATE` unless noted)

- PUT unless DRAFT.
- `/receive` unless DRAFT.
- `/invoices` unless RECEIVED or PARTIAL (not DRAFT, not INVOICED with remaining 0, not CANCELLED).
- `/cancel` unless RECEIVED and zero countable invoices.
- Un-receive, un-cancel: no reverse transitions except recalc from invoice void/delete.
- Credit HOLD / `/confirm` / override: **out**.
- No email / WhatsApp.

### Quote mutex (extend live convert)

A quotation is consumed **once**:

| Already | `convert-to-invoice` | `convert-to-lpo` |
|---|---|---|
| ACCEPTED, nothing | 201 DRAFT invoice, quote CONVERTED | 201 DRAFT LPO, quote CONVERTED |
| CONVERTED + live invoice | 200 same invoice | **409** `CONFLICT` field `quotation_id` |
| CONVERTED + live LPO | **409** | 200 same LPO |
| CONVERTED + invoice soft-deleted, no LPO | **409** (existing quotes rule) | **409** |
| CONVERTED + LPO soft-deleted | **409** | **409** (do not recreate) |

`invoices.quotation_id` unique **stays**. `customer_purchase_orders.quotation_id` nullable **unique**. Convert-to-invoice must `SELECT` LPO by `quotation_id` before creating an invoice.

---

## 4. Lines — ordered vs invoiced

Reuse quotation/invoice line money shape. Extra qty columns:

| Column | Type | Notes |
|---|---|---|
| `quantity` | Numeric(10,2) `> 0` | **Ordered** qty (keep name `quantity` for line math) |
| `quantity_invoiced` | Numeric(10,2) NOT NULL default 0 | Cache; `>= 0`; never > `quantity` |
| money / tax / discount / `product_id` | same as `quotation_items` | Shared `line_money` |
| Response `quantity_remaining` | computed | `quantity - quantity_invoiced` |

**Source of truth for invoiced qty:** `SUM(invoice_items.quantity)` where `invoice_items.customer_purchase_order_item_id = line.id` and parent invoice is countable. Write `quantity_invoiced` in the same transaction after create/void/delete so list/GET do not drift.

`delivered_quantity`: **no column** (DN is gap 7).

Over-invoice: requested qty > remaining → **400** `VALIDATION_ERROR` `field=quantity`. Lock CPO row `SELECT FOR UPDATE` before summing.

Partial invoice line money:

- Copy frozen `unit_price`, `tax_rate`, `product_id` (omit if inactive → ad-hoc description).
- `discount_percent` > 0 → copy percent (scales with qty).
- `discount_amount` > 0 → pro-rate `money(discount_amount * invoice_qty / quantity_ordered)` on that call; never exceed the line’s original amount across invoices (track via remaining fraction).
- Do **not** re-price `DEFAULT_SALES`.

Header LPO totals = full **ordered** lines (not remaining). Invoice totals = invoiced slice, recomputed by `InvoiceService`.

---

## 5. Convert from quote vs manual LPO

### From ACCEPTED quote

`POST /quotations/{id}/convert-to-lpo`

- Copy `client_id`, AED, notes prefix `Converted from {quotation_number}.`, all lines (frozen prices, ordered qty = quote qty).
- `quotation_id` = quote.id.
- `customer_po_number` optional body `{ customer_po_number?, lpo_date?, expected_delivery_date?, notes? }`.
- Lands **DRAFT** so the trader can cut qty (contractors often LPO a subset) then `/receive`.
- Call `InvoiceService` **not** involved until `/invoices`.
- Quote → `CONVERTED`. Event metadata `{ "lpo_id": ... }` (reuse `QUOTATION_CONVERTED`).

SENT / DRAFT / REJECTED / EXPIRED cannot convert-to-lpo (403). Same expiry-on-read as quotes.

### Manual (no quote)

`POST /customer-purchase-orders` with `client_id` + `items[]` (same item create shape as quotes). `quotation_id` omitted. Starts **DRAFT**. Walk-in / counter sales can still `POST /invoices` with neither quote nor LPO (unchanged).

Client on convert must be the quote’s client. Other-workspace quote → 404.

---

## 6. Convert remaining → DRAFT invoice

`POST /customer-purchase-orders/{id}/invoices`

Body (extra keys 422):

```json
{
  "items": [
    { "customer_purchase_order_item_id": "uuid", "quantity": 10.00 }
  ],
  "notes": "optional",
  "issue_date": "optional",
  "supply_date": "optional",
  "due_date": "optional"
}
```

- Omit `items` → invoice **all remaining** (> 0) lines.
- Explicit items: each qty `> 0` and `<= remaining`; unknown line id → 404; line not on this LPO → 404.
- Skip lines with remaining 0. If nothing to invoice → **400** `VALIDATION_ERROR`.

Call **`InvoiceService.create_invoice`**:

| Field | Value |
|---|---|
| `client_id` | LPO client |
| `currency` | AED |
| items | frozen price/tax/discount slice; `customer_purchase_order_item_id` on each `InvoiceItem` |
| `notes` | body notes or `Invoiced from {lpo_number}.` |
| `issue_date` / `supply_date` | today unless body |
| `due_date` | today+30 unless body (gap 3 still deferred) |
| `customer_purchase_order_id` | LPO id |
| `quotation_id` | **null** |
| snapshots / kind | null (DRAFT) |

**Do not** run FTA send gates. Each call creates a **new** invoice (not idempotent like quote convert — partials are many). Double-submit is serialized by LPO row lock; second call with no remaining → 400.

**PUT on LPO-linked invoices is forbidden** (403). Change qty by deleting the DRAFT invoice (releases remaining) and posting `/invoices` again.

`InvoiceService.create_invoice` gains `customer_purchase_order_id: Optional[UUID] = None`. `_add_items` / `_resolve_line` persist `customer_purchase_order_item_id` when provided (do not treat as unknown extra).

After create/void/`DELETE` DRAFT: `CustomerPurchaseOrderService.recalc_invoiced(session, lpo_id)`. **Router invoice delete must go through a service method** that calls recalc (today it only sets `deleted_at`). Void already in `InvoiceService.void_invoice` — add the hook there.

---

## 7. PDF (WP-B)

New `frontend/src/components/pdf/LpoPDF.tsx` (clone quotation layout).

| | LPO PDF | Tax Invoice |
|---|---|---|
| Title | **LPO** | Tax Invoice |
| Number | `LPO-YYYY-XXXX` | `INV-YYYY-XXXX` |
| External | `customer_po_number` if set | — |
| Quote ref | quotation_number if linked | — |
| Dates | LPO date, expected delivery? | issue / supply / due |
| Lines | ordered qty, unit, net, VAT, gross; print invoiced / remaining | invoice qty |
| Language | **English only** | English |
| Watermark | CANCELLED | CANCELLED |

Seller TRN/address print if present; **not** required to receive an LPO. Not stored at receive; rebuild from GET.

---

## 8. Schema (Alembic **yes**)

New revision, `down_revision = "cb01b6bef962"`. Never rewrite history.

### `lpo_counters`

Same shape as `quotation_counters`.

### `customer_purchase_orders`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID FK index | |
| `client_id` | UUID FK index | |
| `quotation_id` | UUID FK `quotations.id` nullable **unique** | |
| `lpo_number` | `String(50)` | Unique `(workspace_id, lpo_number)` |
| `customer_po_number` | `String(100)` nullable | Partial unique with client |
| `status` | ENUM above | default DRAFT |
| `currency` | `String(3)` default AED | write/receive/invoice **AED** → 422 |
| `lpo_date` | Date NOT NULL | default UTC today |
| `expected_delivery_date` | Date nullable | if set, `>= lpo_date` else 422 |
| `subtotal` / `tax_amount` / `total_amount` | Numeric(12,2) | ordered totals; ≥ 0 |
| `notes` | Text nullable | |
| `cancellation_reason` | Text nullable | |
| `created_at` / `updated_at` / `deleted_at` | timestamptz | DRAFT soft-delete |

**No** `payment_terms_days`, `retention_percent`, `document_url`, `confirmed_by`, `delivered_quantity`.

### `customer_purchase_order_items`

Quotation item columns + `quantity_invoiced` default 0. Check `quantity_invoiced >= 0`. FK `customer_purchase_order_id`.

### `customer_purchase_order_events`

Clone quotation events. Types: `CPO_CREATED`, `CPO_UPDATED`, `CPO_RECEIVED`, `CPO_INVOICE_CREATED`, `CPO_CANCELLED`, `CPO_RECALC`. `changed_by` + `metadata_log` JSONB.

### Invoice columns

- `invoices.customer_purchase_order_id` UUID nullable FK, **indexed, not unique**.
- `invoice_items.customer_purchase_order_item_id` UUID nullable FK, indexed.
- Keep `invoices.quotation_id` unique as today.

`InvoiceResponse` + `customer_purchase_order_id`. `QuotationResponse` may add `converted_lpo_id` computed (like `converted_invoice_id`).

---

## 9. API

Base `/api/v1`. Prefix `/customer-purchase-orders`. JWT on all. Wrapper `SuccessResponse` / `PaginatedResponse`. Extra keys **422**. Decimal. Cross-tenant **404** not 403.

```
POST   /customer-purchase-orders
GET    /customer-purchase-orders?status&client_id&search&page&per_page
GET    /customer-purchase-orders/{id}
PUT    /customer-purchase-orders/{id}              DRAFT only
DELETE /customer-purchase-orders/{id}              DRAFT soft-delete
POST   /customer-purchase-orders/{id}/receive      DRAFT → RECEIVED
POST   /customer-purchase-orders/{id}/cancel       RECEIVED, zero invoices
POST   /customer-purchase-orders/{id}/invoices     remaining → DRAFT invoice

POST   /quotations/{id}/convert-to-lpo            ACCEPTED → DRAFT LPO
```

List `search` matches `lpo_number` or `customer_po_number`. `page` default 1, `per_page` default 20 max 100.

GET LPO includes items with `quantity_invoiced` / `quantity_remaining` and a compact `invoices[]` `{ id, invoice_number, status, total_amount }` (countable only).

Convert-to-lpo response: `SuccessResponse[CustomerPurchaseOrderResponse]` 201 first / 200 idempotent.

`/invoices` response: `SuccessResponse[InvoiceResponse]` **201** always when created.

Do **not** mount `/confirm`, `/delivery-notes`, convert-to-cpo aliases, or 501 stubs.

Existing `GET /invoices?client_id` may add optional `customer_purchase_order_id` filter (small, useful). Not required if GET LPO embeds invoices.

---

## 10. Module boundaries

| Layer | Owns |
|---|---|
| `routers/customer_purchase_orders.py` | HTTP, wrapper |
| `routers/quotations.py` | add convert-to-lpo only |
| `services/customer_po_service.py` | state, remaining, recalc, isolation |
| `services/lpo_number.py` | FOR UPDATE `LPO-YYYY-XXXX` |
| `InvoiceService` | create + void/delete hooks + persist `cpo` FKs |
| `QuotationService` | mutex with LPO; convert-to-lpo |

Do not insert `Invoice` rows inside the CPO service except via `InvoiceService.create_invoice`. Do not modify SPO/GRN. Files < 500 lines (split support module like `quotation_support.py`).

---

## 11. Tests — `backend/tests/test_customer_purchase_orders.py`

PostgreSQL only.

1. Manual create → `LPO-{year}-0001`; second `0002`. Concurrent unique.
2. `customer_po_number` duplicate same client → 409; different client OK.
3. Line tax inherit 5%; XOR discounts 422; extra key 422; non-AED 422.
4. Isolation: workspace B 404 on A’s LPO (GET/PUT/receive/invoices/cancel).
5. PUT/DELETE/receive non-DRAFT → 403. Soft-delete DRAFT; number not reused.
6. Quote ACCEPTED convert-to-lpo → DRAFT LPO, quote CONVERTED, lines frozen. Second convert-to-lpo → 200 same id.
7. Convert-to-invoice after LPO → 409. Convert-to-lpo after quote→invoice → 409.
8. Convert-to-lpo from SENT/DRAFT → 403.
9. Receive then `/invoices` omit items → one DRAFT invoice, all qty, `quotation_id` null, `customer_purchase_order_id` set; LPO **INVOICED**; FTA snapshots null; invoice send without TRN still `FTA_SEND_BLOCKED`.
10. Receive; invoice qty 40 of 100 → LPO **PARTIAL**; remaining 60; second invoice 60 → **INVOICED**. Third `/invoices` → 400.
11. Over-invoice qty 101 of 100 → 400; LPO unchanged.
12. Concurrent two `/invoices` for full remaining: one 201, one 400 (or 201+400); never qty_invoiced > ordered.
13. Delete DRAFT invoice → remaining restored; LPO back to RECEIVED (or PARTIAL).
14. Void SENT invoice (after FTA-valid send in test) → remaining restored; recalc status.
15. PUT on LPO-linked invoice → 403.
16. `/cancel` RECEIVED with invoice → 403; without → CANCELLED; `/invoices` after cancel → 403.
17. `alembic upgrade head` + `alembic check` clean.

Do not break `test_quotations.py` convert-once, `test_invoices.py`, SPO tests.

---

## 12. WP split

### WP-A — API + Alembic + tests

Models, migration from `cb01b6bef962`, schemas, number + CPO service, quotation mutex + convert-to-lpo, invoice FKs + recalc hooks, pytest §11. **No frontend.**

**Acceptance:** §11 green; `alembic check`; cannot over-invoice; many DRAFT invoices per LPO; quote convert mutex; FTA send still only on invoice send; cross-tenant 404; Decimal.

### WP-B — UI + PDF

- Layout Sales: **LPO** between Quotations and Invoices (`/customer-purchase-orders` or `/lpos` — lock path **`/lpos`** in the SPA, API still `/customer-purchase-orders`).
- List/filters; form (manual + from quote); show customer PO number; ordered vs invoiced vs remaining.
- Actions: Receive, Cancel, Invoice remaining (qty inputs), Convert to LPO on accepted quote (next to Convert to invoice).
- Invoice remaining navigates to DRAFT invoice. Disable Convert to invoice if already LPO.
- `LpoPDF`: title **LPO**, not Tax Invoice. English.

**Acceptance:** `npm run build`; quote→LPO→partial invoice→second invoice; Tax Invoice and Quotation PDFs unchanged; SPO “Purchase Orders” nav unchanged.

### WP-C — Playwright

Register → client → product → quote send/accept → convert LPO → receive → invoice 50% → invoice rest → send first invoice still requires Settings TRN+address.

Negatives: over-invoice rejected; other workspace LPO URL 404; convert-to-invoice after LPO fails.

**Acceptance:** local API + Postgres. No OCR, WhatsApp, DN, SPO.

---

## 13. Contrast with supplier SPO (do not copy)

| | Customer LPO | Supplier SPO |
|---|---|---|
| Party | Client (AR) | Supplier (AP) |
| Number | `LPO-YYYY-XXXX` | `SPO-YYYY-000001` (6-digit, live) |
| Next doc | Tax invoice (partial OK) | GRN then supplier invoice |
| Stock | **not this WP** | on_order / GRN |
| Credit HOLD | **out** | N/A |

Do not share models, enums, or PDF components.

---

## 14. Drift vs paper

| Paper | This WP |
|---|---|
| `CPO-YYYY-XXXX` | **`LPO-YYYY-XXXX`** |
| RECEIVED → CONFIRMED (credit) | **No CONFIRMED**; `/receive` only |
| PARTIALLY_INVOICED / FULLY_INVOICED / CLOSED | **PARTIAL / INVOICED**; no CLOSED |
| `/confirm` override_reason | **Out** (gap 6) |
| `delivered_quantity` / `/delivery-notes` | **Out** (gap 7) |
| `retention_percent`, `document_url` | **No columns** |
| Quote convert-to-cpo only | **Also manual LPO**; mutex with convert-to-invoice |

---

## 15. NOT in this WP

OCR of scanned POs, WhatsApp, email, Arabic, credit HOLD / `CREDIT_HOLD` / `/confirm`, delivery notes / stock ISSUE, tax credit notes, Peppol, enquiry, supplier SPO/GRN/RFQ changes, header discount, USD, invoice_kind override, public customer portal.

---

## 16. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic **yes**, `down_revision = "cb01b6bef962"` only.
3. Partial invoice = `InvoiceService.create_invoice`; FTA checks stay on invoice send.
4. Recalc invoiced qty on invoice void and DRAFT delete.
5. WP-A tests green before WP-B.
6. Next after A–C: **credit HOLD (gap 6)**, then delivery notes — not WhatsApp.
