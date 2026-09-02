# Tax Debit Notes — Architecture Addendum (sales FTA counterpart to CN)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Invoice` / `InvoiceItem` / `InvoiceService.calculate_balance_due` / `amount_credited` / `clients.credit_balance` / `CreditNote` remaining / immutable `Payment` / `CreditControlService` exposure / AR statement query / bilingual `pdfTitles.ts`. Do **not** PUT a SENT invoice, insert negative payments, UPDATE/DELETE payment rows, invent a second AR ledger, or reuse delivery-note `DN-YYYY-XXXX`.
**Depends on:** Electrical spec columns A–C on master (`3a9c389ad47a9eb81c24f94eb326b4a0973ff2ae`, Alembic `1a30af047312`), bilingual PDF, volume/customer pricing, PDC pending-until-clear, AR Account Statement, tax credit notes (`b8d5f0c3a216`), delivery notes (`DN-YYYY-XXXX` taken), credit HOLD, LPO, quotes, FTA tax invoices, Product Master.
**After this WP A–C:** e-invoice field pack / Peppol **readiness** if still open, then email/WhatsApp. Not this slice: Peppol XML, WhatsApp inbox, bilingual party `*_ar` names, rewriting delivery notes, purchase AP debit notes, warehouse sales-return receiving.

Copy the CN split: **WP-A API+Alembic+pytest → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green. **Alembic: YES.**

UAE: a **tax debit note** increases consideration on an already-issued tax invoice (price or qty too low). It must reference the original invoice number/date, show seller and buyer TRN, and VAT at the same line rates. It is the FTA counterpart of a **Tax Credit Note**. It is **not** a Delivery Note (`DN-YYYY-XXXX`), **not** a Tax Credit Note, **not** a Tax Invoice, and **not** a supplier AP debit memo.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| Delivery notes | Number **`DN-YYYY-XXXX`**, `dn_counters`, routes `/delivery-notes`, PDF title **Delivery Note**, testid `dn-pdf-title`. **Prefix taken.** |
| Credit notes | `CN-YYYY-XXXX`, `credit_note_counters`, DRAFT→ISSUED posts AR, **no** `/apply`. PUT/DELETE DRAFT only. Issue idempotent 200. `SELECT FOR UPDATE` CN + invoice. MEMBER+ (`get_current_user`, **no** ADMIN gate). Never `CREDIT_HOLD`. |
| `Invoice.balance_due` | `money(max(0, total − amount_paid − amount_credited))`. **No** `amount_debited`. |
| `InvoiceService.calculate_credit_owing` | `max(0, −(total − credited − paid))`. PAID+CN stays PAID; parks `clients.credit_balance`. |
| Payments | Immutable insert. Overpay if `amount > balance_due` → 400. Amount `> 0` only. PDC clear uses the same `balance_due`. |
| CN remaining | Line: `invoice_item.quantity − Σ ISSUED CN qty`. Header: `invoice.total_amount − Σ ISSUED CN.total`. **Does not see debit notes** (none exist). |
| HOLD exposure | Σ `balance_due` of SENT / PARTIALLY_PAID / OVERDUE. `assert_not_hold` on invoice **send** and DN **confirm**. CN issue is never blocked. |
| AR statement | Tax Invoice DEBIT `total_amount`; Tax Credit Note CREDIT `total_amount`; opening = billed − paid − credited. **No** debit-note doc type. |
| Paper `domain-model.md` DebitNote | **Purchase AP** (`supplier_invoice_id`, `PURCHASE_RETURN`, number `DN-YYYY-XXXX`). **Out of this WP.** |
| Gaps NOT-in-MVP | “Purchase returns / debit notes / sales return warehouse workflow (CN + ADMIN adjust instead)”. This WP carves **sales tax debit notes** only — the remaining FTA correction path after CN (undercharge). |
| T-list | T1 isolation 404; T5 double-apply (CN used issue+lock, not `/apply`); T11 gapless counters; T13 snapshot freeze; T17 “issue CN = ADMIN” **was not implemented** — live CN issue is MEMBER+. |
| `pdfTitles.ts` | Has `taxCreditNote` / `deliveryNote`. **No** tax debit note title. |
| Layout | Sales: … Delivery Notes, Invoices, Credit Notes. **No** Debit Notes. |
| Alembic HEAD | **`1a30af047312`** (`1a30af047312_add_product_electrical_specs.py`). New revision **must** `down_revision = "1a30af047312"`. Never rewrite specs/CN/DN/credit/LPO/FTA/AR/PDC/pricing/PDF history. |
| Stack | Docker API **8000**, Postgres **5434**, Vite Playwright **5173**. **Never SQLite.** Wrapper `{success, data, error}`. Decimal never float. |

CLAUDE.md: payments immutable; overpay 400; SENT not editable; gapless FOR UPDATE; isolation 404; Alembic-only schema.

---

## 1. ASCII — issue posts AR (no second apply)

```
  Tax Invoice  SENT | PARTIALLY_PAID | PAID | OVERDUE
       │  (not DRAFT, not CANCELLED)
       │
       ▼
  TaxDebitNote  TDN-YYYY-XXXX     DRAFT (PUT / DELETE)
       │  lines = subset of invoice lines; money() same as invoices
       │  frozen unit_price / tax_rate / discounts from invoice line
       │  qty > 0; NO cap vs invoice.total (undercharge may exceed original)
       │
       │  POST /{id}/issue     never CREDIT_HOLD (FTA correction, not new send)
       │  freeze TDN snapshots from invoice snapshots
       ▼
  ISSUED  (posted — no separate /apply)
       │
       │  invoices.amount_debited += TDN.total_amount
       │  net_billed  = total − credited + debited
       │  balance_due = max(0, net_billed − paid)
       │  unpark clients.credit_balance by shrink of credit_owing
       │  never INSERT negative Payment; never UPDATE/DELETE payments
       ▼
  if paid < net_billed:   SENT | PARTIALLY_PAID | OVERDUE  (recalc)
                          PAID + debit with balance_due > 0 → REOPEN
  if paid == net_billed:  PAID
  if paid > net_billed:   stay PAID; credit_owing shrinks; unpark credit_balance
                          invoice.balance_due stays 0
```

PDF title **Tax Debit Note**. Invoice PDF stays **Tax Invoice**. Credit Note PDF stays **Tax Credit Note**. Delivery Note PDF stays **Delivery Note**.

---

## 2. Scope lock — sales tax DN vs purchase AP vs out

| Document | This WP |
|---|---|
| **Sales tax debit note** on a SENT+ tax invoice (undercharge) | **In.** Mirror CN. |
| Purchase AP debit note (`supplier_invoices`, paper `DebitNote`, GRN/PRN) | **Out.** Do not create `supplier_id` / `purchase_return_id` columns. |
| Warehouse sales-return receiving / stock reverse of DN ISSUE | **Out.** CN already handles sales-return **AR**. Stock return stays later (gaps: CN + ADMIN adjust). |
| Using prefix `DN-YYYY-XXXX` | **Forbidden** (delivery notes). |
| Implementing paper `domain-model.md` DebitNote | **Forbidden.** |

Gaps listed purchase DN and sales-return warehouse as one later bullet, and CN as the sales-return money path. After CN shipped, **undercharge had no legal document**. That is this slice.

---

## 3. Number format — lock

**Format:** `TDN-YYYY-XXXX` (e.g. `TDN-2026-0001`).

**Mechanism:** `tax_debit_note_counters` composite PK `(workspace_id, year)` + `TaxDebitNoteNumberService` `SELECT FOR UPDATE`. Clone `CreditNoteNumberService`. Allocate **at create** (same as `INV-` / `CN-`). Soft-delete does **not** rewind. Failed create rolls back.

**Do not** reuse `invoice_counters`, `credit_note_counters`, or `dn_counters`.

### Why `TDN-` (not `DN-`, `DNTE-`, `DBN-`)

| Candidate | Why not / why |
|---|---|
| `DN-YYYY-XXXX` | **Taken** by delivery notes (`architecture/wave-delivery-notes-addendum.md` §2). Clash on every list, PDF, and staff conversation. |
| `DNTE-` | Non-standard; looks like a typo of DN. |
| `DBN-` | Reads as generic “debit memo”, including the **purchase AP** entity in `domain-model.md`. |
| **`TDN-YYYY-XXXX`** | **Tax Debit Note.** Parallel FTA series to `INV-` and `CN-`. `CN-` needed no `T` because the prefix was free; debit cannot use `DN-`. |

### Why gapless (not “operational like quotes”)

UAE VAT treats a tax debit note as a **tax document** (sequential identifier, original invoice reference, both TRNs, VAT). Cabinet Decision / Executive Regulation sequential-numbering practice applies to tax invoices **and** associated credit **and debit** notes — not to quotations, LPOs, or delivery notes.

So: **legally sequential / gapless in-app**, same FOR UPDATE contract as invoices and credit notes. Soft-deleted DRAFT still consumes a number (same INV/CN tradeoff). T11.

---

## 4. State machine — lock

Enum `TaxDebitNoteStatus`: `DRAFT | ISSUED`

**Not in this WP:** `APPLIED` (issue **is** the post), `CANCELLED` enum (DRAFT uses soft-delete). No void-of-issued TDN (ISSUED is terminal; reverse with a later **credit** note, which this WP updates remaining to allow). No `/apply`.

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
| (create) | DRAFT | `POST /debit-notes` — number allocated |
| DRAFT | ISSUED | `POST /{id}/issue` |
| DRAFT | (gone) | `DELETE` soft-delete |

**Forbidden:** PUT/DELETE unless DRAFT. Un-issue. Issue unless parent invoice allowed. **403** `INVALID_STATE`.

**Issue once:** already ISSUED → **200** same payload; do not double-post AR. `SELECT FOR UPDATE` the TDN **and** the invoice (same as CN). No `Idempotency-Key` header.

---

## 5. Parent invoice and lines

**Parent:** `invoice_id` required. Same workspace. Status ∈ {SENT, PARTIALLY_PAID, PAID, OVERDUE}. DRAFT / CANCELLED / deleted → **403** `INVALID_STATE` (404 if wrong workspace). `client_id` / `currency` copied from invoice. AED only.

**Lines:** subset of invoice items. **≥ 1 line.** Each line **must** set `invoice_item_id` on that invoice. Omit unused invoice lines. Cannot invent products. Duplicate `invoice_item_id` on one TDN → 422.

| Field | Lock |
|---|---|
| `quantity` | `> 0`. **No max vs `invoice_item.quantity`.** Undercharge may exceed original qty (billed 10m, should have been 40m → TDN qty 30). |
| Prior ISSUED TDN qty | Does **not** consume a remaining pool on the TDN itself (stacking undercharges allowed). DRAFT TDNs do not post. |
| `unit_price`, `tax_rate`, discounts | **Copy from invoice line** (frozen). Body may send them; mismatch → 422. Same `MONEY_FIELDS` / `RATE_FIELDS` as CN. |
| Math | `line_money.apply_line_money` / `money()` — same ROUND_HALF_UP fils. Do not fork. |
| Header total | **No cap** vs `invoice.total_amount`. Rejected alternatives below. |
| Price undercharge | Frozen prices (same as CN). Staff debit **additional qty × frozen unit_price** equal to the AED gap. Do not allow a different unit price. |

Concurrent issue: lock invoice row. Two **different** DRAFT TDNs may both issue (no remaining cap). Same TDN double-issue → 200, no double-post.

**Reason:** required enum `INVOICE_ERROR | PRICE_INCREASE | QTY_UNDERSTATED | ADDITIONAL_CHARGE | OTHER`. Optional `reason_notes` Text. **Do not** copy CN’s `SALES_RETURN` / `DISCOUNT` / `GOODWILL` (those decrease consideration).

### Cannot debit more than … — lock **unlimited undercharge**

| Option | Verdict |
|---|---|
| Cap TDN total at `invoice.total_amount − Σ TDN` (≤ original invoice) | **Reject.** That only re-bills after credits; cannot correct “billed 100, should be 500”. |
| Cap at “remaining unbilled” | **Reject.** No such ledger. Uninvoiced delivery is a **new tax invoice**, not a debit note. |
| Unlimited undercharge (qty > 0, Numeric(10,2) / Numeric(12,2) column limits only) | **Lock.** FTA debit notes increase consideration without a statutory cap at the original invoice total. |

Do **not** add `DEBIT_EXCEEDS_REMAINING` as a header cap. Line qty ≤ 0 → 400 `VALIDATION_ERROR` `field=quantity`. Extra keys → 422.

### CN remaining — **must** see TDN (this WP)

A later Tax Credit Note must be able to reverse a TDN and must not credit more than **currently billed**. Update live `credit_note_support.py` (do **not** edit `wave-credit-notes-addendum.md`):

```
CN line remaining qty  = invoice_item.quantity + Σ ISSUED TDN qty − Σ ISSUED CN qty
CN header remaining    = invoice.total_amount + Σ ISSUED TDN.total − Σ ISSUED CN.total
```

Existing CN tests without TDNs still pass (`+ 0`). New tests: issue TDN then CN qty/header remaining includes the debit. **Do not** change CN allocate-at-create, issue-posts-AR, or PAID+CN `credit_balance` behaviour except the remaining formula and the shared `balance_due` (below).

---

## 6. Effect on the invoice — lock (one behaviour)

Add `invoices.amount_debited` Numeric(12,2) NOT NULL default 0 (cache). Recalc on issue from Σ ISSUED TDN totals. Check `>= 0`.

**Never** change `total_amount`, `subtotal`, or invoice line rows (the tax invoice stays as issued). **Never** update or delete `payments`. **Never** insert a negative `Payment`.

```
net_billed   = invoice.total_amount − amount_credited + amount_debited   # ≥ 0
amount_paid  = Σ SUCCESS payments                                        # unchanged
raw          = net_billed − amount_paid
balance_due  = money(max(0, raw))
credit_owing = money(max(0, −raw))   # paid more than net billed
```

**`Invoice.balance_due` and `InvoiceService.calculate_balance_due` / `calculate_credit_owing` must use this formula** (payments, HOLD exposure, GET invoice, PDC clear, AR statement aging). Overpay check uses the new `balance_due`.

`BalanceDueResponse` / `InvoiceResponse`: add `amount_debited` (default 0). Keep `amount_credited`. Do not fold debit into `amount_credited`.

### Status after issue (reuse overdue helper; do **not** mutate DRAFT/CANCELLED)

Same `determine_status_from_balance` as live CN, once `balance_due` / `credit_owing` include `amount_debited`:

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
| Unpaid SENT + TDN | `balance_due` **increases**; stay SENT or become OVERDUE if past due. Payments row count unchanged. |
| PARTIAL + TDN | Stay PARTIAL or OVERDUE; due grows. |
| OVERDUE + TDN | Stay OVERDUE; due grows. |
| **PAID + TDN** with `balance_due > 0` | **Reopen** PARTIALLY_PAID, or OVERDUE if past due. **Do not stay PAID** (customer now owes more; hiding it would understate AR / HOLD). |
| **PAID + TDN** still `credit_owing > 0` (debit smaller than parked over-credit on **this** invoice) | **Stay PAID.** `balance_due = 0`. Unpark `credit_balance` (below). |

CN on PAID stays PAID because cash still covers a **smaller** net bill. TDN on PAID **increases** the net bill — reopen is the inverse, not a contradiction.

### `clients.credit_balance` — unpark, never auto-apply foreign credit

Parked credit is the sum of per-invoice `credit_owing` increments from CN. Inverse on TDN:

```
net_before = total − amount_credited + amount_debited_before_this_TDN
unpark     = max(0, credit_owing(net_before) − credit_owing(net_before + TDN.total))
client.credit_balance = money(max(0, credit_balance − unpark))
```

- Unpaid invoice + TDN: `credit_owing` stays 0; `credit_balance` unchanged; AR increases.
- PAID + prior CN parked 200 + TDN 150: unpark 150; stay PAID if still over-credited, else reopen.
- Credit parked on **another** invoice is **not** consumed (`owing_before` on this invoice is 0). AR statement still subtracts live `credit_balance` from exposure — **no auto-apply** (CN addendum out-of-scope stays).

Never a negative `Payment`. Never increment `credit_balance` on TDN.

### HOLD — **does not block issue**

`POST /debit-notes/{id}/issue` is **never** `CREDIT_HOLD`. Create/PUT never blocked.

**Why not block (even though exposure increases):**

1. HOLD already gates **new** exposure: invoice `send`, LPO receive, DN confirm. A TDN is a **legal correction** of a tax invoice that is already SENT — the undercharge already happened.
2. FTA still requires the debit note when consideration increases. Blocking it would leave output VAT understated for a commercial collections flag.
3. CN is never blocked because it reduces exposure; TDN is not blocked because it is not a new sale. After issue, `CreditControlService.evaluate` (`CreditEventReason.EVALUATE`, same as CN — **do not** ALTER `crediteventreason`). Exposure rises; client may **enter or stay** HOLD. Subsequent **send** / DN confirm stay blocked.

Invoice void with ISSUED TDNs: still allowed; TDNs stay ISSUED (legal). CANCELLED invoices drop out of exposure anyway.

---

## 7. Snapshots and PDF

On **issue**, copy from the **invoice snapshots** (already frozen at send). Also persist:

- `original_invoice_number`, `original_issue_date` (required on ISSUED)
- TDN copies of seller/buyer name, address, TRN
- `invoice_kind` copy (STANDARD/SIMPLIFIED)

Do **not** re-run FTA send hard-fails on live workspace. If invoice snapshots are missing, copy live workspace/client like CN `freeze_snapshots`, then freeze.

WP-B `TaxDebitNotePDF.tsx` (clone `CreditNotePDF.tsx`):

| | Tax Debit Note | Tax Credit Note | Delivery Note | Tax Invoice |
|---|---|---|---|---|
| Title EN | **Tax Debit Note** | Tax Credit Note | Delivery Note | Tax Invoice |
| Title AR | **إشعار مدين ضريبي** | إشعار دائن ضريبي | إذن تسليم | فاتورة ضريبية |
| Number | `TDN-YYYY-XXXX` | `CN-YYYY-XXXX` | `DN-YYYY-XXXX` | `INV-YYYY-XXXX` |
| testid EN | **`tdn-pdf-title`** | `cn-pdf-title` | `dn-pdf-title` | `pdf-title` |
| testid AR | **`tdn-pdf-title-ar`** | `cn-pdf-title-ar` | `dn-pdf-title-ar` | `pdf-title-ar` |
| Reference | Original invoice number + issue date | Same | Parent DN/LPO/INV | — |
| Party chrome | `PDF_LABELS.debitTo` (**DEBIT TO:**) | CREDIT TO: | DELIVER TO: | BILL TO: |

Add to existing `pdfTitles.ts` / `pdfLabels.ts` (cheap; bilingual WP already registered Noto). English remains legal. Helvetica + Noto. Not stored at issue; rebuild from GET. DRAFT PDF may use live client if snapshots still null.

**Never** reuse `dn-pdf-title` or title the document Delivery Note / Tax Credit Note / Tax Invoice.

---

## 8. Schema (Alembic **yes**)

`down_revision = "1a30af047312"` only. Never rewrite history. Coder generates a **new** revision file (do not edit `1a30af047312_add_product_electrical_specs.py`).

### `tax_debit_note_counters`

Same shape as `credit_note_counters`.

### `tax_debit_notes`

Python model **`TaxDebitNote`** (not paper purchase `DebitNote`). Table name must not pretend to be AP.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` / `client_id` / `invoice_id` | UUID FK index | invoice indexed (many TDNs per invoice) |
| `debit_note_number` | `String(50)` | Unique `(workspace_id, debit_note_number)`; value `TDN-YYYY-XXXX` |
| `status` | ENUM DRAFT/ISSUED | default DRAFT |
| `currency` | `String(3)` | AED |
| `issue_date` | Date | default UTC today; set/confirm on issue |
| `reason` / `reason_notes` | enum / Text | §5 reasons |
| `subtotal` / `tax_amount` / `total_amount` | Numeric(12,2) | ≥ 0 |
| `original_invoice_number` | `String(50)` nullable until issue | |
| `original_issue_date` | Date nullable until issue | |
| seller/buyer snapshot columns | same as credit_notes / invoices | null on DRAFT |
| `invoice_kind` | `String(20)` nullable | copied on issue |
| `created_at` / `updated_at` / `deleted_at` | timestamptz | DRAFT soft-delete |

### `tax_debit_note_items`

Same shape as `credit_note_items` + `invoice_item_id` UUID FK NOT NULL + `tax_debit_note_id`. Same checks. `product_id` copied nullable. `quantity` Numeric(10,2) `> 0`.

### `tax_debit_note_events`

`TDN_CREATED`, `TDN_UPDATED`, `TDN_ISSUED`.

### Other

- `invoices.amount_debited` Numeric(12,2) NOT NULL default 0 + check `>= 0`.
- `InvoiceEventType.DEBIT_NOTE_ISSUED` (`ALTER TYPE … ADD VALUE IF NOT EXISTS`).
- `InvoiceResponse` + `amount_debited`; `balance_due` uses new formula.
- `BalanceDueResponse.amount_debited`.
- CN remaining queries join ISSUED `tax_debit_notes` / items (WP-A).
- **No** new `clients` column.

---

## 9. API

Base `/api/v1`. Prefix **`/debit-notes`**. JWT. Wrapper + pagination. Extra keys **422**. Decimal. Cross-tenant **404** (never 403 for IDOR). T1.

```
POST   /debit-notes
GET    /debit-notes?invoice_id&client_id&status&search&page&per_page
GET    /debit-notes/{id}
PUT    /debit-notes/{id}              DRAFT only
DELETE /debit-notes/{id}              DRAFT soft-delete
POST   /debit-notes/{id}/issue        DRAFT → ISSUED + post AR
```

**No** `/apply`. No Idempotency-Key. No `/delivery-notes` changes. No supplier debit routes.

Create: `invoice_id`, `reason`, optional `reason_notes` / `issue_date` / `items[]` (`invoice_item_id`, `quantity`; other money fields optional but must match invoice line if sent).

Issue: empty body (`extra="forbid"`). Response `TaxDebitNoteResponse` (201 create, 200 issue idempotent).

**Roles:** mirror **live CN** — OWNER / ADMIN / **MEMBER** may create, edit DRAFT, issue. Do not invent ADMIN-only (T17 paper was not applied to CN; do not apply it only on TDN).

---

## 10. Module boundaries

| Layer | Owns |
|---|---|
| `routers/debit_notes.py` | HTTP `/debit-notes` |
| `services/tax_debit_note_service.py` | state, issue post, unpark |
| `services/tax_debit_note_number.py` | FOR UPDATE `TDN-YYYY-XXXX` |
| `services/tax_debit_note_support.py` | frozen lines, snapshots, events |
| `InvoiceService.calculate_balance_due` / `calculate_credit_owing` / status | include `amount_debited` |
| `credit_note_support` remaining | add ISSUED TDN qty/header |
| `PaymentService` / `PdcService` | uses new balance_due (no other change) |
| `CreditControlService` | no block on issue; `evaluate` after |
| `ArStatementService` | ISSUED TDN = **DEBIT** line `TAX_DEBIT_NOTE`; opening/period totals include debited |

Do not fork `money()`. Files < 500 lines. Register router in `main.py` next to credit notes. Export models in `models/__init__.py`.

### AR statement (necessary integration — do not rewrite `wave-ar-statement-addendum.md`)

- `StatementDocType.TAX_DEBIT_NOTE` label **Tax Debit Note**.
- Activity: ISSUED TDN `issue_date` in range, parent invoice in include-set → **debit** `total_amount`, credit 0, number `TDN-YYYY-XXXX`, reference original INV. Never labelled Payment or Tax Credit Note.
- Opening: `billed + debited_before − paid − credited` (dates `< from`).
- Period totals: add `debited`. Identity `closing_running = exposure − credit_balance` still holds because exposure uses live `balance_due`.
- Sort key: after TAX_INVOICE, before PAYMENT / TAX_CREDIT_NOTE (stable, documented).
- WP-B statement PDF: print the new doc type; do not retitle Account Statement.

---

## 11. Tests — `backend/tests/test_debit_notes.py`

PostgreSQL only (`invoicesaas_test`). Never SQLite. Also extend `test_credit_notes.py` remaining after TDN (or cover that remaining in this file). Keep FTA send, payment immutability, LPO, DN confirm, HOLD send, CN PAID+credit_balance tests green.

1. Create → `TDN-{year}-0001`; second `0002`. Number **must not** match `DN-\d{4}-\d{4}`. Concurrent unique.
2. Parent DRAFT / CANCELLED → 403. Other-workspace invoice → 404.
3. Qty `<= 0` → 400/422. Extra key 422. Non-matching `unit_price` → 422. Duplicate `invoice_item_id` → 422.
4. TDN total **greater than** invoice `total_amount` **allowed** (undercharge).
5. Omit `tax_rate` on body → stored rate = invoice line (5%).
6. PUT/DELETE ISSUED → 403. Soft-delete DRAFT; number not reused.
7. Issue on unpaid SENT: `amount_debited` set; `balance_due` = total + TDN; invoice still SENT (or OVERDUE). Payments row count unchanged. **No** payment INSERT/UPDATE/DELETE.
8. PAID invoice + TDN: invoice **reopens** PARTIALLY_PAID (or OVERDUE); `balance_due` = TDN total; **no** payment deleted. `credit_balance` unchanged if no prior CN park.
9. PAID + CN (parked credit) + smaller TDN: stay PAID; `credit_balance` decreases by TDN total; `balance_due` 0.
10. Second issue → 200; `amount_debited` unchanged (no double).
11. After TDN, payment `amount > new balance_due` → 400. Payment = new balance → PAID.
12. HOLD client: issue TDN **200** (not `CREDIT_HOLD`). Exposure **rises** on evaluate.
13. After TDN, CN remaining qty/header includes TDN (can credit the extra billed qty). CN without TDN still capped at original.
14. Isolation workspace B 404 on GET/PUT/DELETE/issue. MEMBER can issue (register user is OWNER; add a MEMBER token if CN tests do — otherwise same auth as CN create/issue).
15. AR GET statement: ISSUED TDN appears as `TAX_DEBIT_NOTE` debit, not Payment / Tax Credit Note.
16. `alembic upgrade head` + `alembic check` clean; revision parent `1a30af047312`.

---

## 12. WP split

### WP-A — API + Alembic + tests

Models, migration from **`1a30af047312`**, number + service, `amount_debited`, `balance_due` / owing hooks, CN remaining update, AR statement query, pytest §11. **No frontend.**

**Acceptance:** §11 green; `alembic check`; TDN may exceed invoice total; PAID+TDN reopens when due > 0; parked credit unparks; payments untouched; HOLD does not block issue; Decimal; 404 isolation; numbers are `TDN-` not `DN-`.

### WP-B — UI + PDF

- Layout Sales & Customers: **Debit Notes** at `/debit-notes`, **after Credit Notes**, not beside Delivery Notes. `data-testid="nav-debit-notes"`. Label **Debit Notes** (PDF title stays Tax Debit Note — same pattern as Credit Notes vs Tax Credit Note).
- Routes: list, `/debit-notes/new?invoice_id=`, `/:id`, `/:id/edit`. Clone Credit Notes pages; do not share Delivery Notes components.
- Invoice AR panel: show `amount_debited`; list TDNs; `data-testid="invoice-create-tdn"`. Hint: debit notes **increase** balance due.
- `TaxDebitNotePDF` + preview: title **Tax Debit Note** / **إشعار مدين ضريبي**; original INV; snapshot TRNs. `tdn-pdf-title` exact.
- Statement UI: new line type. Do not rename Account Statement.
- Invoice list `balance_due` already uses GET; must rise after issue.

**Acceptance:** `npm run build`; issue **increases** invoice `balance_due`; Tax Invoice / Tax Credit Note / Delivery Note PDFs unchanged.

### WP-C — Playwright — `frontend/e2e/debit-notes.spec.ts`

Register → FTA Settings → client → invoice send → debit note issue → invoice `balance_due` **increases**. PDF title **Tax Debit Note** (and AR sibling). Not Delivery Note / Tax Credit Note / Tax Invoice. Other workspace TDN URL **404**.

Optional second flow: pay in full → TDN → invoice **PARTIALLY_PAID** (or OVERDUE), not stay PAID.

**Acceptance:** local API Docker **8000** + Postgres **5434** + Vite **5173**. Never SQLite. Do not rewrite `delivery-notes.spec.ts` / `credit-notes.spec.ts` except if CN remaining UI must show TDN-adjusted remaining (only if that form is opened in this spec).

---

## 13. Drift vs paper / gaps

| Paper / gaps | This WP |
|---|---|
| DebitNote is AP / purchase return / `DN-YYYY-XXXX` | **Sales tax TDN-** only; AP out |
| DRAFT→ISSUED→APPLIED + `/apply` | **Issue posts**; no apply (mirror live CN) |
| Allocate number at issue | **At create** (INV/CN pattern) |
| CN + ADMIN adjust instead of any debit note | **CN stays** for overcharge/returns; **TDN** for undercharge |
| T17 issue CN = ADMIN | Mirror **live CN** (MEMBER+) |
| Purchase returns / warehouse sales return | **Out** |
| Bilingual party `*_ar` | **Out**; chrome titles only via `pdfTitles.ts` |

---

## 14. NOT in this WP

Purchase AP debit notes, supplier credit notes, Peppol XML / ASP, e-invoice field pack (next), WhatsApp inbox, email send, bilingual party names, delivery-note stock ISSUE/cancel, mutating payments / refunds, auto-apply `credit_balance` to other invoices, rewriting SENT invoices, rewriting DN/CN/FTA/AR/PDC/pricing/PDF **addendum files**, `hs_code` / `vat_category`.

---

## 15. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md` (and frontend report in WP-B).
2. Alembic **yes**, `down_revision = "1a30af047312"` only. New file. Never edit `1a30af047312_add_product_electrical_specs.py` or CN/DN revisions.
3. Number **`TDN-YYYY-XXXX`**. Never `DN-YYYY-XXXX`.
4. `balance_due = max(0, total − paid − credited + debited)`. Payments immutable.
5. PAID + TDN with due > 0 → **reopen** PARTIALLY_PAID/OVERDUE. Unpark `credit_balance` by owing delta only.
6. HOLD does **not** block issue. MEMBER+ like CN.
7. CN remaining includes ISSUED TDN. PDF title **Tax Debit Note**.
8. WP-A tests green before WP-B.
9. Next after A–C: **e-invoice field pack / Peppol readiness**, not WhatsApp XML, not rewriting delivery notes.
