# AR Aging + Customer Statement PDF — Architecture Addendum (Gap 12 / Phase 8)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Invoice.balance_due` / `InvoiceService.determine_status_from_balance`, immutable `Payment` (SUCCESS vs PENDING), `CreditNote` ISSUED posting, `clients.credit_balance`, `CreditControlService.aging_buckets` + `GET /clients/{id}/credit`, client-side `@react-pdf/renderer` (Tax Invoice / Tax Credit Note). Do **not** invent a second AR ledger, mutate invoices/payments/CNs, or title this PDF Tax Invoice / Tax Credit Note.
**Depends on:** Tax credit notes A–C (`b5a755e`), credit HOLD (`e8e00f5`), FTA tax invoices, LPO, quotes, Product Master, delivery notes.
**After this WP A–C:** PDC bounce/truth (gap 11 / Phase 9), then volume pricing (gap 8). Not this slice: bilingual/Arabic PDF, debit notes, WhatsApp, Peppol, refunds as negative payments, mutating payments, invoice-list `amount_credited`.

Copy the CN/DN split: **WP-A API+pytest → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green. **Alembic: no.**

UAE electrical wholesale: Net 30 / 45 / 60 collections need a **customer account statement** — tax invoices, cleared cash, and tax credit notes on one page, plus parked unapplied credit. It is a **commercial AR document**, not an FTA tax invoice and not a Tax Credit Note.

---

## 0. Runtime truth (lock against live code — do not invent a second ledger)

| Source | Truth |
|---|---|
| `Invoice.balance_due` | `money(max(0, total − amount_paid − amount_credited))`. `amount_paid` = Σ payments with `status == SUCCESS` only. |
| `InvoiceService.determine_status_from_balance` | DRAFT/CANCELLED untouched. Else PAID if credit_owing > 0 or balance 0; else OVERDUE / PARTIALLY_PAID / SENT. |
| `PaymentService.record_payment` | **Always inserts `PaymentStatus.SUCCESS`**, including `payment_method=PDC`. SUCCESS PDC **does** reduce `balance_due` today. Bounce/clear/deposit **do not exist**. Do **not** fix that here (Phase 9). |
| `PUT .../payments/{id}` | Live status/pdc_status patch exists. **Do not call it from this WP.** Do not add bounce endpoints. |
| Credit notes | ISSUED posts `invoices.amount_credited` and may increment `clients.credit_balance`. DRAFT CNs are not AR. Payments never updated/deleted on issue. |
| `CreditControlService` | Open AR = status ∈ `{SENT, PARTIALLY_PAID, OVERDUE}`. `aging_buckets`: `current`, `days_1_30`, `days_31_60`, `days_61_90`, `days_90_plus` from `due_date` vs a date, summing live `balance_due`. `credit_balance` is returned beside buckets, **not inside them**. |
| `GET /clients/{id}/credit` | Aging JSON already. Isolation **404**. Any JWT member. |
| `InvoiceListItem` | Has `amount_paid` / `balance_due`; **omits `amount_credited`**. Out of this WP. |
| PDF | Invoice title **Tax Invoice**; CN title **Tax Credit Note**; Helvetica; English; **client-side** `@react-pdf/renderer`; **no** server PDF route. |
| Dashboard `/dashboard/stats` | Outstanding sum exists; **no** `overdue_aed` / `pdc_outstanding`. Do not extend this WP. |
| Roles | Sales GETs use `get_current_user` (OWNER / ADMIN / MEMBER). No statement-specific RBAC today. |
| Alembic HEAD | **`b8d5f0c3a216`** (`b8d5f0c3a216_add_credit_notes.py`). This slice adds **no** revision. Later WPs must `down_revision = "b8d5f0c3a216"` until HEAD moves. Never rewrite CN/DN/credit/LPO/FTA history. |

CLAUDE.md: Decimal `Numeric(12,2)`; payments immutable; wrapper `{success, data, error}`; list pagination is for lists; isolation **404 not 403**; never SQLite.

---

## 1. ASCII — generated statement (query, not a table)

```
  JWT workspace + client_id
           │
           ▼
  GET /clients/{id}/ar-statement?from=&to=&as_of=
           │
           │  read-only queries (no INSERT/UPDATE on invoices, payments, CNs, clients)
           │
           ├─ Tax invoices   issue_date in [from,to]
           │                 status ∈ {SENT, PARTIALLY_PAID, PAID, OVERDUE}
           │                 deleted_at IS NULL          → DEBIT  total_amount
           │
           ├─ Payments       payment_date::date in range
           │                 parent invoice in the invoice set above
           │                 SUCCESS → CREDIT amount     (cleared cash)
           │                 PENDING → memo line         (NOT cleared cash)
           │
           ├─ Tax credit notes  issue_date in range
           │                    ISSUED, deleted_at IS NULL
           │                    parent invoice in the invoice set
           │                    → CREDIT total_amount     (never labelled Payment)
           │
           ├─ Opening        reconstructed from the same rules with date < from
           │
           └─ Aging          CreditControlService.open_ar_invoices
                             + aging_buckets(invoices, as_of)
                             outstanding = live balance_due
                             credit_balance parked, not a bucket
           │
           ▼
  JSON { header, opening, lines, totals, aging, credit_balance }
           │
           ▼  WP-B only
  StatementPDF.tsx   title "Account Statement"
                     NOT Tax Invoice, NOT Tax Credit Note
```

No `ar_statements` row is written when the owner prints.

---

## 2. Document vs ledger — Alembic **NO**

**Decision: generated statement only.** Query invoices + SUCCESS payments + ISSUED credit notes + live `clients.credit_balance`. Rebuild PDF from GET JSON (same as Tax Invoice / Tax Credit Note).

**No `ar_statements` table. No new columns. No Alembic in this slice.**

Justification:

1. The ledger **already exists**: `invoices` (incl. `amount_credited`), immutable `payments`, ISSUED `credit_notes`, `clients.credit_balance`. A persisted statement header would be a **second AR book** that can drift from those rows.
2. An Account Statement is **not** an FTA tax document. Sequential numbering / 5-year VAT record-keeping applies to Tax Invoices and Tax Credit Notes, which already persist. Printing a collections PDF does not create a tax series.
3. Live Invoice/CN PDFs are **not** stored at send; every download rebuilds. Matching that pattern avoids a new binary store and a fake “issued on date X” audit table.
4. `credit_balance` is a **live cache**, not a dated subledger. Snapshotting it onto a statement row would freeze a number the next CN/payment can change, inviting “the PDF disagrees with GET client”.

If a later WP needs “we emailed this PDF on date X”, add an **outbound-comms** table then — not an AR ledger — with `down_revision` from **then** HEAD. Not now.

**Identity (must hold when `[from,to]` covers all surviving activity):**

```
closing_running = exposure − credit_balance
```

`exposure` = Σ live `balance_due` of SENT / PARTIALLY_PAID / OVERDUE (same as HOLD). `credit_balance` is parked unapplied credit from PAID+CN. Do not invent another formula.

---

## 3. What appears on the statement

### 3.1 Include

| Line | When | Debit | Credit | Notes |
|---|---|---|---|---|
| Opening balance | Always first row | amount if opening > 0 | amount if opening < 0 | Reconstructed; see §4 |
| Tax Invoice | `issue_date` ∈ `[from, to]`, status ∈ **SENT / PARTIALLY_PAID / PAID / OVERDUE**, `deleted_at` null | `total_amount` | 0 | Number `INV-YYYY-XXXX` |
| Payment (cleared) | `payment_date` date ∈ range, `status=SUCCESS`, parent invoice in the include-set | 0 | `amount` | Doc type **Payment**. Method printed (CASH / BANK_TRANSFER / CHEQUE / **PDC** / CREDIT_CARD). |
| Payment (pending) | same dates, `status=PENDING` | 0 | **0** | Doc type **Payment (pending)**. Amount in `pending_amount` only. Not in `totals.paid`. |
| Tax Credit Note | `issue_date` ∈ range, `status=ISSUED`, `deleted_at` null, parent invoice in the include-set | 0 | `total_amount` | Doc type **Tax Credit Note**. Number `CN-YYYY-XXXX`. Reference original invoice number. **Never** a Payment line. |

**PAID invoices belong on the activity list** (they billed; cash usually follows). They do **not** belong in aging buckets (`balance_due` is 0).

**OVERDUE** invoices belong on both the activity list (if `issue_date` in range) and aging (live `balance_due`).

### 3.2 Exclude

| Document | Why |
|---|---|
| **DRAFT invoices** | Not AR; not a tax invoice yet. |
| **CANCELLED invoices** | Voided; no synthetic void line exists. Excluding the debit avoids overstating billed. **Also exclude payments and CNs whose `invoice_id` is CANCELLED or deleted** so a credit cannot appear without its invoice. Aging already excludes CANCELLED (`AR_STATUSES`). |
| Soft-deleted invoices (`deleted_at`) | Soft-delete only; not on statements. |
| **DRAFT credit notes** | Not posted. |
| Quotations / LPO / delivery notes | Not AR. |
| Payments `FAILED` / `CANCELLED` / `REFUNDED` | Audit-only; omit (do not invent refunds this WP). |
| Workspace-wide other clients | Isolation. |

### 3.3 CANCELLED — why exclude from lines (not “show as a zero line”)

Void is already a terminal invoice status. There is no matching “void credit” document. Showing CANCELLED as a debit would force a fake reversing line or leave billed inflated. Collectors do not chase voided tax invoices. Legal Tax Credit Notes on a later-voided invoice remain available on the CN module; this **Account Statement** follows the live AR set, not FTA reprint of every tax artefact.

---

## 4. Opening, running, closing, parked credit

All money via `line_money.money()` (`ROUND_HALF_UP`, 0.01). Never float.

Let **S** be the include-set of invoices for this client in this workspace: `deleted_at IS NULL` and status ∈ `{SENT, PARTIALLY_PAID, PAID, OVERDUE}`.

```
billed_before   = Σ inv.total_amount          for inv in S, issue_date < from
paid_before     = Σ p.amount                  SUCCESS, p.invoice in S, payment_date::date < from
credited_before = Σ cn.total_amount           ISSUED, cn.invoice in S, issue_date < from, deleted_at null

opening_balance = money(billed_before − paid_before − credited_before)
# may be negative (unapplied CN credit exceeds open AR)
```

Period totals (same filters, dates ∈ `[from, to]` inclusive):

```
totals.billed    = Σ invoice totals in range
totals.paid      = Σ SUCCESS payment amounts in range     # never CN
totals.credited  = Σ ISSUED CN totals in range            # never cash
totals.pending   = Σ PENDING payment amounts in range     # not in paid
```

Running balance starts at `opening_balance`. Each activity line:

```
running = money(running + debit − credit)
```

PENDING lines: debit 0, credit 0 → running unchanged.

```
totals.closing_running = last running_balance
# equals money(opening + billed − paid − credited)
```

**Footer (live, not reconstructed as-of a past day):**

| Field | Source | Label |
|---|---|---|
| `amount_due_now` | `CreditControlService` exposure (Σ live `balance_due` of open AR) | Amount due now |
| `credit_balance` | `clients.credit_balance` | Unapplied credit |
| `aging` | §5 | Aging |

`credit_balance` is **not** a statement line and **not** an aging bucket. Do not add it into `totals.paid`. WP-B must not render it as “Paid”.

**`as_of` does not rewrite history.** Activity uses `from`/`to`. Aging day-count uses `as_of`. Outstanding **amounts** are **live** `balance_due` (user lock). True point-in-time outstanding (ignore payments after `as_of`) is **out** — that would still be generated, but it would disagree with GET invoice / GET credit and is deferred.

Wide-range pytest: `from=2000-01-01`, `to=as_of=today` → `closing_running == money(amount_due_now − credit_balance)`.

---

## 5. Aging buckets — reuse live helper, do not fork

Paper (`uae-electrical-architecture-gaps` §4.9) wanted `current, 1-30, 31-45, 46-60, 61-90, 90+`. **Reject the 45-day split.**

**Lock: identical to live `aging_buckets` in `credit_control_service.py`:**

```
days_overdue = (as_of − due_date).days

days_overdue <= 0  → current          # not yet due (Net 0/30/45/60 still here)
1..30              → days_1_30
31..60             → days_31_60
61..90             → days_61_90
> 90               → days_90_plus
```

```
outstanding = live Invoice.balance_due
            = money(max(0, total − SUCCESS paid − ISSUED credited))
```

| Invoice | In buckets? |
|---|---|
| SENT / PARTIALLY_PAID / OVERDUE, `balance_due > 0` | Yes |
| PAID (`balance_due` 0) | **No** |
| CANCELLED / DRAFT / deleted | **No** |
| `credit_balance` | **No** (header/footer only) |

Implementation: call `CreditControlService.open_ar_invoices` + `aging_buckets(invoices, as_of)`. Do **not** copy-paste a second bucket function. When `as_of == utc_today()`, `data.aging.buckets` **must equal** `GET /clients/{id}/credit` `buckets` (and `amount_due_now == exposure`).

`as_of` default = UTC today. `as_of` after UTC today → **422** `VALIDATION_ERROR` `field=as_of`. Past `as_of` is allowed: **days** use that date; **amounts stay live** (documented on PDF: “Outstanding amounts are current; aging days vs as-of”).

Sum of five buckets = `amount_due_now` = exposure.

---

## 6. PDC in this WP (label only — do not fix truth)

Live: `record_payment` sets `status=SUCCESS` for every method, including PDC. SUCCESS reduces `balance_due` immediately. Phase 9 will stop treating uncleared PDC as cash.

| Payment | `cleared_cash` | Credit column | `totals.paid` | PDF / JSON label |
|---|---|---|---|---|
| `status=SUCCESS`, method CASH/BANK/CHEQUE/CARD | true | amount | yes | **Payment** + method |
| `status=SUCCESS`, method **PDC** | true | amount | yes | **Payment** + method **PDC**. Footer note: *“PDC recorded as SUCCESS reduces outstanding until bounce/clear (later wave).”* Do **not** call it “cleared bank cash”; do call it SUCCESS payment. |
| `status=PENDING` (any method, incl. PDC) | **false** | **0** | **no** | **Payment (pending)** — “not cleared”. Amount in `pending_amount`. Aging already ignores PENDING (`amount_paid` SUCCESS-only). |

WP-A pytest: insert/update a row to PENDING (existing PUT or session in test) and assert it is **not** in `totals.paid` and `cleared_cash is false`. Do **not** add `/pdc/deposit|clear|bounce|return`.

Aging uses whatever live `balance_due` is (SUCCESS PDC already netted). Do not compute a parallel “PDC-excluded balance” here.

---

## 7. API

Base `/api/v1`. JWT. Wrapper `{success, data, error}`. Extra unknown **body** keys N/A (GET). Cross-tenant or missing client → **404** `NOT_FOUND` (same as `GET /clients/{id}`), **never 403**. CREDIT_HOLD does **not** block this GET.

```
GET /clients/{client_id}/ar-statement?from=&to=&as_of=
```

| Query | Lock |
|---|---|
| `from` | **Required** `date`. Period start (inclusive). |
| `to` | **Required** `date`. Period end (inclusive). |
| `as_of` | Optional `date`. Default UTC today. Not after UTC today. |

`from > to` → **422** `field=from`. `(to − from).days > 366` → **422** `DATE_RANGE_TOO_LONG` `field=to` (add `ErrorCode`).

**No pagination.** One document. If activity lines (excluding the opening row) **> 2000** → **400** `STATEMENT_TOO_LARGE` `field=to` — shorten the range. Do not silently truncate.

**No** `GET .../ar-statement.pdf`. **No** `Accept: application/pdf` branch. Evidence: invoices and CNs have no server PDF; WP-B renders `@react-pdf/renderer` from this JSON. Adding WeasyPrint/reportlab would be a new stack.

**No** `GET /reports/ar-aging` this WP (workspace-wide report deferred). **No** dashboard field pack this WP.

**Roles:** OWNER, ADMIN, and **MEMBER** — same as `GET /clients/{id}/credit` and GET invoice. Printing a statement is collections, not void/CN-issue. Do not require ADMIN.

### 7.1 `data` shape (conceptual)

```json
{
  "client": {
    "id": "...",
    "name": "...",
    "tax_id": "...",
    "address": "..."
  },
  "workspace": {
    "name": "...",
    "trn": "...",
    "address": "..."
  },
  "currency": "AED",
  "from": "2026-01-01",
  "to": "2026-09-01",
  "as_of": "2026-09-01",
  "opening_balance": "0.00",
  "lines": [
    {
      "date": "2026-01-01",
      "doc_type": "OPENING",
      "doc_type_label": "Opening balance",
      "number": null,
      "reference": null,
      "payment_method": null,
      "payment_status": null,
      "cleared_cash": null,
      "pending_amount": "0.00",
      "debit": "0.00",
      "credit": "0.00",
      "running_balance": "0.00"
    }
  ],
  "totals": {
    "billed": "210.00",
    "paid": "50.00",
    "credited": "105.00",
    "pending": "0.00",
    "closing_running": "55.00"
  },
  "amount_due_now": "55.00",
  "credit_balance": "0.00",
  "aging": {
    "as_of": "2026-09-01",
    "buckets": {
      "current": "55.00",
      "days_1_30": "0.00",
      "days_31_60": "0.00",
      "days_61_90": "0.00",
      "days_90_plus": "0.00"
    }
  }
}
```

`doc_type` enum: `OPENING` | `TAX_INVOICE` | `PAYMENT` | `PAYMENT_PENDING` | `TAX_CREDIT_NOTE`.

`doc_type_label` **exactly**:

| `doc_type` | `doc_type_label` |
|---|---|
| OPENING | Opening balance |
| TAX_INVOICE | Tax Invoice |
| PAYMENT | Payment |
| PAYMENT_PENDING | Payment (pending) |
| TAX_CREDIT_NOTE | Tax Credit Note |

Sort: opening row first; then `date` ASC; then type order `TAX_INVOICE`, `PAYMENT`, `PAYMENT_PENDING`, `TAX_CREDIT_NOTE`; then `number` ASC.

Serialize Decimals like existing invoice/credit responses (Pydantic Decimal). Service math always `money()`.

GET `/clients/{id}/credit` **unchanged**.

---

## 8. PDF — title lock

**Exact title string: `Account Statement`.**

Must **not** be `Tax Invoice`, `INVOICE`, `Tax Credit Note`, or Arabic `كشف حساب` (bilingual deferred).

WP-B `frontend/src/components/pdf/StatementPDF.tsx` (+ preview):

- Helvetica, English, reuse Invoice/CN page padding / header / table chrome.
- Header: workspace name, address, TRN if present; client name, address, TRN (`tax_id`) if present.
- Meta: period `from`–`to`, **as of** `as_of`, currency AED.
- Columns: **Date | Type | Number | Debit | Credit | Balance**.
- Type column uses `doc_type_label`. For Payment, show method on a second line (e.g. `PDC`). PENDING: type **Payment (pending)**; debit/credit blank or 0; do not put pending in Credit.
- Footer totals: billed, paid (SUCCESS only), credited (CN), amount due now, **Unapplied credit** (`credit_balance`).
- Aging table: the five live bucket keys with human labels Current / 1–30 / 31–60 / 61–90 / 90+.
- Footer note on PDC SUCCESS (§6).
- `data-testid="statement-pdf-title"` text **Account Statement**. Assert not Tax Invoice / Tax Credit Note.

Not stored. Rebuild from GET. DRAFT invoices never appear.

---

## 9. Module boundaries

| Layer | Owns |
|---|---|
| `routers/clients.py` (or thin `routers/ar_statements.py` mounted under `/clients`) | HTTP, 404, query validation |
| `services/ar_statement_service.py` | Assemble lines, opening, totals, cap |
| `CreditControlService.open_ar_invoices` + `aging_buckets` | Exposure + buckets — **reuse** |
| `Invoice.balance_due` / `line_money.money` | Outstanding + rounding |
| `StatementPDF.tsx` | WP-B only |

Do not put statement math in `PaymentService` or `CreditNoteService`. Do not mutate `amount_credited` / payments. Files < 500 lines; split router if `clients.py` would exceed.

Schemas: `backend/app/schemas/ar_statements.py`. Tests: `backend/tests/test_ar_statement.py`.

---

## 10. Tests — `backend/tests/test_ar_statement.py`

PostgreSQL only (never SQLite). Decimal fils. Isolation 404.

1. Missing `from` or `to` → 422. `from > to` → 422. Range > 366 days → 422 `DATE_RANGE_TOO_LONG`. `as_of` in the future → 422.
2. Other-workspace client id → **404**, not 403.
3. SENT invoice in range → one **Tax Invoice** debit = `total_amount`. DRAFT invoice in range → **omitted**. Quote / LPO / DN in range → omitted (create if fixtures exist; otherwise omit those asserts).
4. SUCCESS payment in range → **Payment** credit = amount; `totals.paid` includes it; `cleared_cash true`. ISSUED CN in range → **Tax Credit Note** credit = CN total; `totals.credited` includes it; `totals.paid` does **not**.
5. DRAFT CN omitted. CANCELLED invoice + its payments/CNs omitted. PAID invoice with `balance_due` 0 **is** listed if `issue_date` in range; **not** in aging buckets.
6. PENDING payment (set via existing PUT or test session): line **Payment (pending)**; `cleared_cash false`; credit 0; not in `totals.paid`; aging unchanged vs SUCCESS-only `balance_due`.
7. SUCCESS + `payment_method=PDC`: still in `totals.paid` (live SUCCESS); JSON `payment_method=PDC`; not labelled Tax Credit Note.
8. Aging: past-`due_date` open invoice → bucket matches `_bucket_key`; PAID excluded; CANCELLED excluded; `sum(buckets) == amount_due_now`; `credit_balance` not in buckets. `as_of=today` → buckets == `GET /clients/{id}/credit`.
9. Wide range identity: `closing_running == money(amount_due_now − credit_balance)`.
10. Opening: invoice dated before `from`, payment in range → opening includes billed, period shows payment only.
11. Hard cap: do not need 2001 real invoices if a unit test of the cap helper is cleaner; still assert the route returns 400 `STATEMENT_TOO_LARGE` when the service signals overflow (fixture or monkeypatch acceptable **only** for the cap; all money tests use real rows).
12. MEMBER token (if tests can create MEMBER) can GET 200 — or document “register OWNER is enough” and skip MEMBER if fixtures only create OWNER. Isolation still 404.
13. Do not break FTA send, payment overpay, CN issue, HOLD, `alembic check` (no new revision).

---

## 11. WP split

### WP-A — API + pytest (**no Alembic**, no frontend)

`ArStatementService`, schemas, `GET /clients/{id}/ar-statement`, `ErrorCode` additions, `test_ar_statement.py` §10.

**Acceptance:** §10 green; no new Alembic file; cannot mistake CN for paid; PENDING not in paid; aging matches GET credit for `as_of=today`; 404 isolation; Decimal; payments/invoices/CNs row counts unchanged after GET.

### WP-B — UI + PDF

- Route `/clients/:id/statement`. Clients table: **Statement** action (do not add an empty top-level Statements nav without a workspace list API).
- Date range + as-of (defaults: `to`/`as_of` = today, `from` = first of month or today−30 — UX only; API still requires explicit query params from the page).
- On-screen lines + aging + unapplied credit. Paid vs credited vs pending visually distinct.
- Download/preview `StatementPDF`: title **Account Statement**.
- **Out:** invoice list `amount_credited` column.

**Acceptance:** `npm run build`; PDF title Account Statement; credits not shown as cash; aging matches JSON.

### WP-C — Playwright

Local API **8000**, Postgres host **5434**. Never SQLite. Password **8+** (`Passw0rd1`). Unique emails.

Happy path (`frontend/e2e/ar-statement.spec.ts`): register → FTA Settings → client → SENT tax invoice → SUCCESS payment (UI or API) → ISSUED CN → open statement for a range covering all three → **three line types**; credited ≠ paid; aging matches JSON; PDF title Account Statement.

Isolation (`ar-statement-isolation.spec.ts`): workspace B `GET /clients/{A}/ar-statement?...` → **404** not 403.

**Acceptance:** Docker API + Postgres. No debit notes, WhatsApp, email, PDC bounce, bilingual.

---

## 12. Drift vs paper

| Paper (gaps 2026-08-31) | This WP |
|---|---|
| `GET /reports/ar-aging` workspace-wide + 31–45 / 46–60 buckets | **Per-client only**; buckets **reuse live 1–30 / 31–60 / 61–90 / 90+ + current** |
| `GET /clients/{id}/statement` + `GET /clients/{id}/aging` | **One** `GET /clients/{id}/ar-statement`; keep existing `/credit` |
| Dashboard `overdue_aed`, `pdc_outstanding`, DSO | **Out** |
| Bilingual Account Statement / كشف حساب | **English only** |
| Email statement | **Out** (download) |
| Persist statement / tax-document series | **Generated JSON + client PDF; no table** |
| PDC pending excluded from paid | **Yes** if PENDING; live SUCCESS PDC **is** paid until Phase 9 |

---

## 13. NOT in this WP

PDC deposit/clear/bounce/return; changing `record_payment` to PENDING for PDC; volume pricing; bilingual/Arabic fonts; debit notes; Peppol; WhatsApp; emailing the statement; mutating/deleting payments; negative payments / refunds; auto-apply `credit_balance`; invoice list `amount_credited`; workspace-wide aging report; dashboard overdue pack; `ar_statements` table; server-side PDF; second `balance_due` formula.

---

## 14. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` (WP-A), then `frontend-execution-report.md` (WP-B). No database report unless someone mistakenly adds Alembic — **don't**.
2. Alembic **NO**. HEAD stays `b8d5f0c3a216`. Later WPs `down_revision = "b8d5f0c3a216"` until HEAD moves.
3. Reuse `aging_buckets` + live `balance_due`. CN ≠ cash. PENDING ≠ cleared cash.
4. PDF title **Account Statement**.
5. WP-A pytest green before WP-B.
6. Next after A–C: **PDC truth (gap 11)**, then volume pricing — not debit notes.
