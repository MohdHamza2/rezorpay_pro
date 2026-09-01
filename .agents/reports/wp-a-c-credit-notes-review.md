# WP-A–C Tax Credit Notes — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full tax credit-notes slice — WP-A API+Alembic, W2 balance nit, WP-B UI/PDF, WP-C Playwright. Review only. No git commit. No feature work (no P0 money leak or payment mutation found).
**Specs:** `architecture/wave-credit-notes-addendum.md`, `.agents/reports/wp-a-credit-notes-review.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

May commit when asked. No P0 tenant leak, money leak, or payment mutation on the credit-note path.

Issue posts AR (`invoices.amount_credited`); payments are never inserted, updated, or deleted. `balance_due = max(0, total − paid − credited)`. PAID + CN stays PAID and parks `clients.credit_balance`. `GET /invoices/{id}/balance` now splits `amount_paid` / `amount_credited` (W2 fixed). UI does not label a credit note as a payment. PDF title is **Tax Credit Note**; Tax Invoice PDF is unchanged. Playwright (claimed 16 passed) covers unpaid issue + AR panel cash vs credited + cross-tenant 404.

Nits that keep this off `APPROVE_CN_A_C`: concurrent two-DRAFT issue still untested; invoice **list** still omits `amount_credited` (Credited column is always "—"); addendum WP-C PAID browser path was de-scoped (API pytest covers it); leftover WP-A W1/W3/W4.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 | **PASS.** `get_visible` filters `id` + `workspace_id` + `deleted_at IS NULL`. Cross-workspace GET and `/issue` → 404 (pytest + Playwright). Create from other-workspace invoice → 404. List filters `workspace_id`. JWT workspace from auth, never body. Frontend `isHttpNotFound` keys off **HTTP 404** (W1 wrapper code may be `HTTP_ERROR`). No CN JSON leaked. |
| 2 | Decimal; `CREDIT_EXCEEDS_REMAINING` | **PASS.** CN/invoice/client money is `Numeric(12, 2)`. Lines use `apply_line_money` / `money()` (ROUND_HALF_UP fils). Qty > remaining → 400. Header `cn.total > invoice.total − Σ ISSUED` → 400 `CREDIT_EXCEEDS_REMAINING` `field=total_amount` (pytest sequential two-DRAFT issue). Extra keys 422. Mismatched `unit_price` 422. Omit `tax_rate` copies invoice line 5%. Frontend form caps qty at remaining; header 400 is pytest-only. |
| 3 | Payments never mutated | **PASS.** Credit-note service/support never import `Payment` and never `session.delete` a payment. Issue writes `invoices.amount_credited` + optional `clients.credit_balance` only. Unpaid/full-credit tests: payment row count unchanged / still 0. PAID + CN: payment count unchanged. Pre-existing PDC `PUT …/payments/{id}` is untouched and unused by this slice. |
| 4 | Gapless CN counter | **PASS.** `CreditNoteNumberService` `SELECT FOR UPDATE` on `credit_note_counters` `(workspace_id, year)`; format `CN-YYYY-XXXX`; savepoint on first-year insert. Does not touch `invoice_counters`. Unique `(workspace_id, credit_note_number)` includes soft-deleted rows. Soft-delete sets `deleted_at` only; delete `0001` → next is `0002`. Concurrent create uniqueness tested (8 threads). Failed create rolls back with the session. |
| 5 | `balance_due` formula; UI not labeling CN as payment | **PASS.** `Invoice.balance_due` / `InvoiceService.calculate_balance_due` = `max(0, total − SUCCESS paid − amount_credited)` (quantize fils). `GET /balance` `total_paid` is cash-only (`amount_paid`); `amount_credited` is separate (W2 fixed; pytest). Invoice AR panel: “Amount paid (cash)” vs “Amount credited (credit notes)” vs “Balance due”; copy “not cash payments”. List column “Paid (cash)”. Credit Notes page: “not cash payments and not delivery notes”. Frontend never calls `GET /invoices/{id}/balance`. |
| 6 | PDF Tax Credit Note | **PASS.** `CreditNotePDF` / HTML preview title **Tax Credit Note**; original invoice number + issue date; seller/buyer TRN snapshots (live fallback on DRAFT); Helvetica; English. Download filename `TaxCreditNote_CN-…`. Playwright asserts `cn-pdf-title` = Tax Credit Note and invoice `pdf-title` absent. `InvoicePDF` still **Tax Invoice**. |
| 7 | Playwright AR panel | **PASS (claimed run, not re-run here).** `credit-notes.spec.ts`: after issue, list paid AED 0.00 / due AED 105.00; AR panel paid 0 / credited 105 / due 105; “not cash payments”. Isolation spec: workspace B GET → 404 not 403. Frontend report: **16 passed** (product + FTA + quote + LPO + HOLD + DN + CN). PAID + `credit_balance` browser path **not** in Playwright (see W8). |
| 8 | Alembic linear | **PASS.** `b8d5f0c3a216` `down_revision = "a7c4e9d2b105"` only. No other revision parented on DN HEAD. Chain LPO → credit HOLD → DN → CN. Tables `credit_note_counters`, `credit_notes`, `credit_note_items`, `credit_note_events`; `invoices.amount_credited`; `clients.credit_balance`; `ALTER TYPE invoiceeventtype ADD VALUE IF NOT EXISTS 'CREDIT_NOTE_ISSUED'`. DN/credit/LPO/FTA history not rewritten. |
| 9 | Concurrent issue nit still untested? | **YES — still untested (W3).** Same-CN sequential re-issue → 200, `amount_credited` unchanged (pytest). Two DRAFTs over remaining → sequential second issue 400 `CREDIT_EXCEEDS_REMAINING` (pytest). **Missing:** two full DRAFTs issued together (threads) → one 200, one 400, `amount_credited` equals one CN. HTTP path still serializes via invoice `FOR UPDATE` + remaining recompute; service still does not re-lock the CN (router does). |
| 10 | Issue never HOLD | **PASS.** `issue` / `create` / `update_draft` do not call `assert_not_hold`. Invoice **send** still does. After `_post_ar`, `CreditControlService.evaluate` (may leave HOLD). HOLD client (COD 0) issue 200; exposure drops (pytest). Create/PUT never blocked. |

---

## Findings

### Critical (P0)

None. Cross-tenant CN id is 404 with no payload leak. Issue does not insert, update, or delete payment rows. Header remaining + invoice row lock prevent double-post of AR on the HTTP issue path. PAID is not reopened to PARTIALLY_PAID. Balance endpoint no longer treats credits as cash.

### Warning

**W1 — Isolation 404 wrapper code is still `HTTP_ERROR` (carried from WP-A)**
`_load_or_404` raises `HTTPException(404, "Credit note not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no CN JSON leaked. Parent invoice 404s via `raise_error` correctly use `NOT_FOUND`. WP-B/C treat **HTTP 404** (`isHttpNotFound`, Playwright `status() === 404`). Not a leak.

**W3 — Concurrent two-DRAFT issue untested; service trusts the router lock**
`CreditNoteService.issue` does not re-`SELECT FOR UPDATE` the CN. The router does (`for_update=True`). Same-CN double-issue is covered sequentially. Two-DRAFT **sequential** over-credit is covered. Missing: two full DRAFTs issued **together**. A future internal caller that passes an unlocked DRAFT identity-map object could double-post AR. Defense in depth: lock inside the service. **Still open from WP-A.**

**W4 — Absolute `discount_amount` copied unscaled on partial qty (API)**
`build_item` copies the full invoice-line `discount_amount` even when CN qty is a subset. `apply_line_money` then takes that amount against the smaller extended. Partial credit can under-credit, or 400 if `discount_amount > extended`. Percent discounts scale. Tests use zero `discount_amount`. WP-B line picker requires amount-discount lines to credit remaining qty in full — UI mitigates; API still allows the awkward path.

**W5 — Alembic pytest uses env `DATABASE_URL`, not `_test`**
`test_alembic_upgrade_head_and_check` runs `alembic upgrade head` / `check` with `cwd=backend`. That is the app database from `.env`, while the rest of the module uses `{DATABASE_URL}_test` + `create_all`. Harmless if already at head; not isolated.

**W7 — Invoice list omits `amount_credited`; Credited column is always "—"**
`InvoiceResponse` has `amount_credited`. `InvoiceListItem` still does not. List GET therefore cannot populate the new “Credited” column; UI shows "—" even after an issued CN. `balance_due` and `amount_paid` on the list **are** correct (model column + payments selectinload). AR panel uses GET invoice and shows credited. Not a money leak; the list column is misleading.

**W8 — Addendum WP-C PAID browser path not shipped**
Addendum §11: pay in full → CN → invoice still PAID, `credit_balance` > 0. WP-C plan explicitly de-scoped this (“API pytest covers it”). `test_paid_invoice_cn_stays_paid_parks_credit_balance` asserts status PAID, `balance_due` 0, payment count unchanged, GET client + `/clients/{id}/credit` `credit_balance`. Clients UI shows read-only unapplied credit. No auto-apply (out of WP). Coverage gap only.

### Info

**I1 — Tests not re-run in this pass**
Static review. Pytest: 14 functions in `test_credit_notes.py` (13 WP-A + W2 balance). Combined CN+invoices claimed 39 after W2; earlier CN+invoices+credit_control 55. Playwright 16 passed taken from `.agents/reports/frontend-execution-report.md`.

**I2 — `issue_date` not confirmed on issue**
Spec: default UTC today; set/confirm on issue. Shipped: create uses `issue_date or utc_today()`; `freeze_snapshots` does not refresh it. A DRAFT opened yesterday and issued today keeps yesterday’s date. `original_invoice_number` / `original_issue_date` are set. PDF shows stored `issue_date`.

**I4 — Mid-file schema imports**
`serialize` / `serialize_list_item` import schemas inside the functions (`E402` vs CLAUDE.md). Same cycle-avoidance as invoices/DN. Not a runtime bug.

**I5 — Test file length**
`backend/tests/test_credit_notes.py` is ~592 lines. Spec “files < 500” is aimed at app modules (service 280, support 398, router 176 — under).

**I6 — CN year is `datetime.now().year`, not UTC**
Matches `InvoiceNumberService`. `utc_today()` is used for dates. Fine except around New Year vs UTC.

**I7 — Coverage gaps (logic present)**
PUT/DELETE other-workspace 404 (same `_load_or_404`); list `?invoice_id=` isolation (workspace filter → empty); OVERDUE parent; PARTIAL + CN leftover `credit_balance`; extra key on issue body 422; `invoice_item_id` from another invoice 422. Invoice void with ISSUED CNs still allowed (spec).

**I8 — Pre-existing payment PUT (PDC status)**
`PUT /invoices/{id}/payments/{id}` can change `Payment.status` / `pdc_status`. This slice did not add it and does not call it. CLAUDE.md immutability lock is older; PDC mutation is older. Next PDC-truth wave should own it — do not treat CN as having introduced mutability.

**I9 — Client PUT cannot set `credit_balance`**
`ClientUpdate` `extra="forbid"` has no `credit_balance`. Only issue over-credit increments it. GET client + GET `/clients/{id}/credit` expose it. No apply UI.

**I10 — `issued_qty_map` / `issued_header_total` filter by `invoice_id`, not `workspace_id`**
Invoice UUIDs are globally unique; parent load already scoped the workspace. Defense in depth only.

**I11 — Remaining-qty UI is N+1 + `per_page` 100**
`issuedCreditQtyMap` lists ISSUED CNs then GETs each. Backend still enforces remaining on create/issue.

**I12 — Stale invoice-service docstring**
Module comment still says source of truth is `total − payments` and omits credited. Implementation is the new formula.

---

## Spec lock vs shipped

| Lock | Shipped |
|---|---|
| `CN-YYYY-XXXX` via `credit_note_counters` + `FOR UPDATE` at create | `CreditNoteNumberService`; savepoint on first-year insert |
| DRAFT → ISSUED (issue posts AR); no `/apply` | `CreditNoteService.issue` + `_post_ar`; no apply route |
| Issue idempotent 200 | Status short-circuit after CN lock (router `FOR UPDATE`) |
| Remaining = invoice total − Σ ISSUED; qty per invoice line | `issued_header_total` / `issued_qty_map`; DRAFT does not reserve |
| Frozen invoice-line money | `assert_frozen` + `build_item` + `apply_line_money` |
| `balance_due = max(0, total − paid − credited)` | Invoice property + `calculate_balance_due`; payments use it |
| Balance API cash vs credit | `amount_paid` / `total_paid` cash; `amount_credited` separate |
| PAID + CN → stay PAID + `credit_balance` | `determine_status_from_balance` + `credit_increment`; pytest |
| Issue never `CREDIT_HOLD` | No `assert_not_hold`; evaluate after post |
| Snapshots from invoice (live fallback, no FTA hard-fail) | `freeze_snapshots`; `_load_send_context` does not FTA-block |
| Alembic from `a7c4e9d2b105` | `b8d5f0c3a216` |
| UI `/credit-notes`; PDF **Tax Credit Note** | Routes under AuthGuard; Helvetica EN; Invoice PDF unchanged |
| Playwright issue + AR + 404 | `credit-notes.spec.ts` + `credit-note-isolation.spec.ts` |
| Playwright PAID + `credit_balance` | **Not in e2e**; pytest + Clients column |

Router prefix `/credit-notes` under `/api/v1`. Pagination on list. Extra keys 422 on create/update/issue. No debit notes.

---

## WP-B / WP-C notes (not blockers)

- Isolation: HTTP 404, not `error.code === "NOT_FOUND"` (W1). Shipped.
- Invoice detail/AR: `amount_credited` + adjusted `balance_due`; do not use GET balance `total_paid`. Shipped; list GET still omits credited (W7).
- Client: read-only `credit_balance`; no apply UI. Shipped.
- PDF title **Tax Credit Note**; original INV + date; snapshot TRNs; English; Helvetica. Tax Invoice unchanged. Shipped.
- Amount-discount lines: UI requires full remaining qty (W4).
- Playwright: unpaid SENT issue + AR panel + 404. PAID path leftover (W8).

---

## Next remaining UAE gap (do not implement this review)

Pick **AR statement PDF (gap 12)**.

`clients.credit_balance` is now parked with no apply path and no customer-facing document that lists tax invoices, cash, and tax credit notes together. The addendum’s post A–C order is AR statement → PDC bounce → volume pricing. PDC truth (gap 11) still matters (`PUT` payment status is pre-existing and out of this slice). Volume pricing (gap 8) is catalog. Bilingual PDF is explicitly out of this WP (English-only lock).

Do **not** start debit notes, WhatsApp, Peppol, negative payments, or auto-apply `credit_balance` until the statement exists.

---

## Memory

Intended pattern keys: `review-cn-issue-locks`, `review-cn-list-omits-amount-credited`, `review-cn-playwright-paid-path-untested`, `review-404-http-error-wrapper`.
