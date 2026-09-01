# Tax Credit Notes — Architecture Addendum (Gap 10)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Invoice` / `InvoiceItem` / `InvoiceService` / `line_money.money` / FTA snapshots / immutable `Payment` / `CreditControlService` exposure. Do **not** PUT a SENT invoice, delete payments, or invent a second AR ledger.
**Depends on:** Delivery notes A–C (`1188d84`), credit HOLD (`e8e00f5`), FTA tax invoices, LPO, quotes, Product Master.
**After this WP A–C:** AR statement (gap 12), PDC bounce (gap 11), volume pricing (gap 8). Not this slice: debit notes, WhatsApp, Arabic PDF, Peppol, refunds as negative payments.

Copy the DN split: **WP-A API+Alembic+tests → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

UAE: a **tax credit note** corrects a tax invoice (wrong price/qty, return, discount). It must reference the original invoice number/date, show seller and buyer TRN, and VAT at the same line rates (usually 5%). It is **not** a Delivery Note and **not** a quotation.

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| Invoice edit | PUT/DELETE **DRAFT only**. SENT+ is frozen. Void → CANCELLED. No credit-note model. |
| `Invoice.balance_due` | `total_amount − Σ SUCCESS payments`. **No** credited term. |
| Payments | Immutable insert. Overpay if `amount > balance_due` → 400. No negative amounts. |
| `InvoiceService.determine_status_from_balance` | PAID if balance ≤ 0; else OVERDUE / PARTIALLY_PAID / SENT. Ignores credits. |
| Credit HOLD exposure | SUM `balance_due` of SENT/PARTIALLY_PAID/OVERDUE. |
| FTA send | Snapshots + kind frozen on invoice send. AED, TRN regex. |
| Alembic HEAD | `a7c4e9d2b105` (`a7c4e9d2b105_add_delivery_notes.py`). New revision **must** `down_revision = "a7c4e9d2b105"`. Never rewrite DN/credit/LPO/FTA history. |

CLAUDE.md: payments immutable; overpay 400; SENT not editable. This WP is the **legal correction path**.

---

## 1. ASCII — issue posts AR (no second apply)

```
  Tax Invoice  SENT | PARTIALLY_PAID | PAID | OVERDUE
       │  (not DRAFT, not CANCELLED)
       │
       ▼
  CreditNote  CN-YYYY-XXXX     DRAFT (PUT / DELETE)
       │  lines = subset of invoice lines; money() same as invoices
       │  remaining = invoice.total_amount − Σ ISSUED CN.total
       │
       │  POST /{id}/issue     never CREDIT_HOLD (reduces exposure)
       │  freeze CN snapshots from invoice snapshots
       ▼
  ISSUED  (posted — no separate /apply)
       │
       │  invoices.amount_credited += CN.total_amount
       │  balance_due = max(0, total − paid − credited)
       │  never DELETE / UPDATE payment rows
       ▼
  if paid < net_billed:   SENT | PARTIALLY_PAID | OVERDUE  (recalc)
  if paid == net_billed:  PAID
  if paid > net_billed:   stay PAID; clients.credit_balance += (paid − net_billed)
                          invoice.balance_due stays 0
```

PDF title **Tax Credit Note**. Invoice PDF stays **Tax Invoice**.

---

## 2. Number format — lock

**Format:** `CN-YYYY-XXXX` (e.g. `CN-2026-0001`).

**Mechanism:** `credit_note_counters` composite PK `(workspace_id, year)` + `CreditNoteNumberService` `SELECT FOR UPDATE`. Allocate **at create** (same as `INV-YYYY-XXXX`). Soft-delete does **not** rewind. Failed create rolls back.

**Do not** reuse `invoice_counters`. Tax invoices and credit notes are different FTA series.

### Why gapless (not “operational like quotes”)

UAE VAT treats a tax credit note as a **tax document** (sequential identifier, original invoice reference, both TRNs, VAT). Cabinet Decision / Executive Regulation sequential-numbering practice applies to tax invoices **and** credit notes, not to quotations or LPOs.

So: **legally sequential / gapless in-app**, same FOR UPDATE contract as invoices. Quotes stay “operational” because they are not tax invoices. Soft-deleted DRAFT still consumes a number (same INV tradeoff).

---

## 3. State machine — lock

Enum `CreditNoteStatus`: `DRAFT | ISSUED`

**Not in this WP:** `APPLIED` (issue **is** the post), `CANCELLED` enum (DRAFT uses soft-delete). No void-of-issued CN (issue a second CN? **No** — remaining cap already spent; reverse only by not supporting un-issue). ISSUED is terminal.

```
              ┌────────────┐
              │   DRAFT    │  PUT / DELETE
              └──────┬─────┘
            /issue   │
                     ▼
              ┌────────────┐
              │   ISSUED   │  snapshots frozen; AR posted
              └────────────┘
```

| From | To | How |
|---|---|---|
| (create) | DRAFT | `POST /credit-notes` — number allocated |
| DRAFT | ISSUED | `POST /{id}/issue` |
| DRAFT | (gone) | `DELETE` soft-delete |

**Forbidden:** PUT/DELETE unless DRAFT. Un-issue. Issue unless parent invoice allowed. **403** `INVALID_STATE`.

**Issue once:** already ISSUED → **200** same payload; do not double-post AR. `SELECT FOR UPDATE` the CN **and** the invoice.

---

## 4. Parent invoice and lines

**Parent:** `invoice_id` required. Same workspace. Status ∈ {SENT, PARTIALLY_PAID, PAID, OVERDUE}. DRAFT / CANCELLED / deleted → **403** `INVALID_STATE` (404 if wrong workspace). `client_id` / `currency` copied from invoice. AED only (invoice already AED).

**Lines:** subset of invoice items. **≥ 1 line.** Each line **must** set `invoice_item_id` on that invoice.

| Field | Lock |
|---|---|
| `quantity` | `> 0`, ≤ **line remaining qty** |
| Line remaining qty | `invoice_item.quantity − Σ ISSUED CN lines on that item` |
| `unit_price`, `tax_rate`, discounts | **Copy from invoice line** (frozen). Body may send them; mismatch → 422. |
| Math | `line_money.apply_line_money` / `money()` — same ROUND_HALF_UP fils |
| Header remaining | `invoice.total_amount − Σ ISSUED CN.total_amount` |
| New CN total | Must be `≤ header remaining` else **400** `CREDIT_EXCEEDS_REMAINING` `field=total_amount` |

Omit unused invoice lines. Cannot invent products/prices. Concurrent issue: lock invoice row, recompute remaining.

**Reason:** required enum `SALES_RETURN | INVOICE_ERROR | DISCOUNT | GOODWILL | OTHER`. Optional `reason_notes` Text.

---

## 5. Effect on the invoice — lock (one behavior)

Add `invoices.amount_credited` Numeric(12,2) NOT NULL default 0 (cache). Recalc on issue from Σ ISSUED CN totals.

**Never** change `total_amount`, `subtotal`, or invoice line rows (the tax invoice stays as issued). **Never** update or delete `payments`.

```
net_billed   = invoice.total_amount − amount_credited          # ≥ 0
amount_paid  = Σ SUCCESS payments                              # unchanged
raw          = net_billed − amount_paid
balance_due  = money(max(0, raw))
credit_owing = money(max(0, −raw))   # paid more than net billed
```

**`Invoice.balance_due` and `InvoiceService.calculate_balance_due` must use this formula** (so payments, HOLD exposure, and GET invoice stay consistent). Overpay check uses the new `balance_due`.

### Status after issue (and after later payments)

Reuse overdue helper. Do **not** mutate DRAFT/CANCELLED.

```
if credit_owing > 0 or balance_due == 0:
    PAID
elif should_mark_overdue:          # due_date < today and balance_due > 0
    OVERDUE
elif amount_paid > 0:
    PARTIALLY_PAID
else:
    SENT
```

| Case | Result |
|---|---|
| Unpaid SENT + CN | `balance_due` shrinks; may stay SENT/OVERDUE or become PAID if CN covers all |
| PARTIAL + CN | May stay PARTIAL, become OVERDUE/SENT, or PAID |
| OVERDUE + CN still due | Stay OVERDUE if still past due |
| **PAID + CN** | **Stay PAID.** `balance_due = 0`. **Do not reopen PARTIALLY_PAID** (payments still cover the original cash; we do not un-apply them). Increment **`clients.credit_balance`** by `credit_owing` (the increment from this CN, not the new absolute). |
| Partial pay then CN that overshoots unpaid | Flip to PAID; add leftover to `clients.credit_balance` |

**`clients.credit_balance`:** Numeric(12,2) NOT NULL default 0. Unapplied customer credit from ISSUED CNs on over-paid / fully-paid invoices. **This WP does not auto-apply it to the next invoice** (AR statement / payments wave). GET client + GET `/clients/{id}/credit` expose it. Never a negative `Payment`.

**HOLD:** `POST /credit-notes/{id}/issue` is **never** blocked by `CREDIT_HOLD` (reduces exposure). After issue, re-evaluate credit (may leave HOLD). Create/PUT never blocked.

Invoice void with ISSUED CNs: still allowed; CNs stay ISSUED (legal). Recalc amount_credited stays; CANCELLED invoices drop out of exposure anyway.

---

## 6. Snapshots and PDF

On **issue**, copy from the **invoice snapshots** (already frozen at send). Also persist:

- `original_invoice_number`, `original_issue_date` (strings/dates; required on ISSUED)
- CN copies of seller/buyer name, address, TRN
- `invoice_kind` copy (STANDARD/SIMPLIFIED)

Do **not** re-run FTA send hard-fails on live workspace (invoice already SENT). If invoice snapshots are missing (should not happen post-FTA send), copy live workspace/client like send would, then freeze.

WP-B `CreditNotePDF.tsx`:

| | Tax Credit Note | Tax Invoice |
|---|---|---|
| Title | **Tax Credit Note** | Tax Invoice |
| Number | `CN-YYYY-XXXX` | `INV-YYYY-XXXX` |
| Reference | Original invoice number + issue date | — |
| Parties | Snapshot TRN + address both sides | Same |
| Lines | Same money columns | Same |
| Language | **English only** | English |

Helvetica. Not stored at issue; rebuild from GET. DRAFT PDF may use live client if snapshots still null.

---

## 7. Schema (Alembic **yes**)

`down_revision = "a7c4e9d2b105"`. Never rewrite history.

### `credit_note_counters`

Same shape as `invoice_counters`.

### `credit_notes`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` / `client_id` / `invoice_id` | UUID FK index | invoice indexed (many CNs per invoice) |
| `credit_note_number` | `String(50)` | Unique `(workspace_id, credit_note_number)` |
| `status` | ENUM DRAFT/ISSUED | default DRAFT |
| `currency` | `String(3)` | AED |
| `issue_date` | Date | default UTC today; set/confirm on issue |
| `reason` / `reason_notes` | enum / Text | |
| `subtotal` / `tax_amount` / `total_amount` | Numeric(12,2) | ≥ 0 |
| `original_invoice_number` | `String(50)` nullable until issue | |
| `original_issue_date` | Date nullable until issue | |
| seller/buyer snapshot columns | same as invoice | null on DRAFT |
| `invoice_kind` | `String(20)` nullable | copied on issue |
| `created_at` / `updated_at` / `deleted_at` | timestamptz | DRAFT soft-delete |

### `credit_note_items`

Invoice-item shape + `invoice_item_id` UUID FK NOT NULL + `credit_note_id`. Same checks as invoice items. `product_id` copied nullable.

### `credit_note_events`

`CN_CREATED`, `CN_UPDATED`, `CN_ISSUED`.

### Other

- `invoices.amount_credited` Numeric(12,2) NOT NULL default 0.
- `clients.credit_balance` Numeric(12,2) NOT NULL default 0.
- `InvoiceEventType.CREDIT_NOTE_ISSUED` (ALTER TYPE).
- `InvoiceResponse` + `amount_credited`; `balance_due` uses new formula.

---

## 8. API

Base `/api/v1`. Prefix `/credit-notes`. JWT. Wrapper + pagination. Extra keys **422**. Decimal. Cross-tenant **404**.

```
POST   /credit-notes
GET    /credit-notes?invoice_id&client_id&status&search&page&per_page
GET    /credit-notes/{id}
PUT    /credit-notes/{id}              DRAFT only
DELETE /credit-notes/{id}              DRAFT soft-delete
POST   /credit-notes/{id}/issue        DRAFT → ISSUED + post AR
```

**No** `/apply`. No Idempotency-Key (row lock + idempotent issue). No debit-note routes.

Create: `invoice_id`, `reason`, optional `reason_notes` / `issue_date` / `items[]` (`invoice_item_id`, `quantity`; other money fields optional but must match invoice line if sent).

Issue: empty body. Response `CreditNoteResponse` (201 create, 200 issue idempotent).

GET invoice lists CNs? Optional `credit_notes[]` `{id, number, status, total}` on GET invoice — nice, not required if list `?invoice_id=` exists.

---

## 9. Module boundaries

| Layer | Owns |
|---|---|
| `routers/credit_notes.py` | HTTP |
| `services/credit_note_service.py` | state, remaining, issue post |
| `services/credit_note_number.py` | FOR UPDATE |
| `InvoiceService.calculate_balance_due` / status | include `amount_credited` |
| `PaymentService` | uses new balance_due (no other change) |
| `CreditControlService` | no block on issue; re-evaluate after |

Do not fork `money()`. Files < 500 lines.

---

## 10. Tests — `backend/tests/test_credit_notes.py`

PostgreSQL only.

1. Create → `CN-{year}-0001`; second `0002`. Concurrent unique.
2. Parent DRAFT / CANCELLED → 403. Other-workspace invoice → 404.
3. Line qty > remaining → 400. Header total > remaining → 400 `CREDIT_EXCEEDS_REMAINING`. Extra key 422. Non-matching unit_price → 422.
4. Omit `tax_rate` on body → stored rate = invoice line (5%).
5. PUT/DELETE ISSUED → 403. Soft-delete DRAFT; number not reused.
6. Issue on unpaid SENT: `amount_credited` set; `balance_due` = total − CN; invoice still SENT (or OVERDUE if past due). Payments row count unchanged.
7. Issue covering full unpaid → invoice **PAID**; `balance_due` 0; no payment inserted.
8. PAID invoice + CN: invoice stays **PAID**; `balance_due` 0; `clients.credit_balance` increases; **no** payment deleted or updated.
9. Second issue → 200; `amount_credited` unchanged (no double).
10. After CN, payment `amount > new balance_due` → 400. Payment = new balance → PAID.
11. HOLD client: issue CN **200** (not `CREDIT_HOLD`). Exposure drops on evaluate.
12. Isolation workspace B 404. `alembic upgrade head` + `alembic check` clean.

Do not break FTA send, payment immutability, LPO remaining, DN ISSUE, credit HOLD send/receive.

---

## 11. WP split

### WP-A — API + Alembic + tests

Models, migration from `a7c4e9d2b105`, number + service, balance_due/status hooks, `credit_balance`, pytest §10. **No frontend.**

**Acceptance:** §10 green; `alembic check`; cannot credit > remaining; PAID+CN parks `credit_balance` and does not reopen PARTIAL; payments untouched; HOLD does not block issue; Decimal; 404 isolation.

### WP-B — UI + PDF

- Layout Sales: **Credit Notes** (`/credit-notes`) near Invoices.
- Create from invoice (line picker, remaining qty). Issue action. DRAFT-only edit.
- Invoice detail: show `amount_credited` / adjusted `balance_due`; link to CNs.
- `CreditNotePDF`: title **Tax Credit Note**; original INV number/date; snapshot TRNs. English.
- Client: show `credit_balance` (no apply UI).

**Acceptance:** `npm run build`; issue reduces invoice balance; Tax Invoice PDF unchanged.

### WP-C — Playwright

Register → FTA Settings → client → invoice send → credit note issue → invoice `balance_due` drops. PAID path: pay in full → CN → invoice still PAID, client credit_balance > 0. Other workspace CN URL 404.

**Acceptance:** local API + Postgres. No debit notes, WhatsApp, AR PDF.

---

## 12. Drift vs paper

| Paper | This WP |
|---|---|
| DRAFT→ISSUED→APPLIED + `/apply` | **Issue posts**; no apply |
| Allocate number at issue | **At create** (INV pattern) |
| CN on PAID → reject or refund payment | **Stay PAID + `credit_balance`** |
| Auto-apply credit to next invoice | **Out** |
| Bilingual title | **English only** |
| CANCELLED issued CN | **No**; DRAFT soft-delete only |

---

## 13. NOT in this WP

Debit notes, supplier credit notes, WhatsApp, Arabic font, Peppol, negative payments / refunds, auto-apply `credit_balance`, AR statement PDF, PDC bounce, invoice PUT on SENT, DN/LPO qty changes from SALES_RETURN (stock return is later).

---

## 14. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic **yes**, `down_revision = "a7c4e9d2b105"` only.
3. `balance_due = max(0, total − paid − credited)`. Payments immutable.
4. PAID + CN → `credit_balance`, not PARTIALLY_PAID.
5. WP-A tests green before WP-B.
6. Next after A–C: **AR statement / PDC / volume pricing**, not debit notes.
