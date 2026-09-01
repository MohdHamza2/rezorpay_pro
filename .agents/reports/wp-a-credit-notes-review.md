# WP-A Tax Credit Notes — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0 money leak, payment mutation, or tenant leak).
**Spec:** `architecture/wave-credit-notes-addendum.md`, `.agents/reports/architect-credit-notes-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B UI + Tax Credit Note PDF **may start**.

No P0 tenant leak on CN GET/list/issue. No payment INSERT/UPDATE/DELETE on the issue path. Money is `Numeric(12, 2)` + shared `line_money.money()` / `apply_line_money` — not `float`. PAID + CN stays PAID and parks `clients.credit_balance`; `balance_due = max(0, total − paid − credited)`. Issue is never `CREDIT_HOLD`. Alembic is a linear new revision on DN HEAD `a7c4e9d2b105`. Pytest was **not re-run** in this review pass; `test_credit_notes.py` has **13** functions covering spec §10. Combined **55 passed** is taken from `.agents/reports/backend-execution-report.md` (CN 13 + invoices 25 + credit_control 17).

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 | **PASS.** `get_visible` filters `id` + `workspace_id` + `deleted_at IS NULL`. Cross-workspace GET and `/issue` → 404 (tested). Create from other-workspace invoice → 404 (tested). Parent `load_parent_invoice` and `lock_client` both require JWT workspace. List filters `workspace_id`. JWT workspace from auth deps, never from body. |
| 2 | Decimal `money()`; `CREDIT_EXCEEDS_REMAINING` | **PASS.** CN/invoice/client money columns `Numeric(12, 2)`. Lines use `apply_line_money`; headers `money(subtotal + tax)`. Omit `tax_rate` copies the invoice line (5% tested). Qty > remaining → 400. Header `cn.total > invoice.total − Σ ISSUED` → 400 `CREDIT_EXCEEDS_REMAINING` `field=total_amount`. Extra keys 422. Mismatched `unit_price` 422. |
| 3 | Never update/delete payments | **PASS.** Credit-note service/support never import `Payment` or `session.delete` a payment. Issue posts `invoices.amount_credited` + optional `clients.credit_balance` only. Unpaid/full-credit tests assert payment row count unchanged / still 0. Pre-existing PDC `PUT …/payments/{id}` is untouched (I8). |
| 4 | Gapless CN; separate counter; no rewind on soft-delete | **PASS.** `CreditNoteNumberService` `SELECT FOR UPDATE` on `credit_note_counters` `(workspace_id, year)`; format `CN-YYYY-XXXX`; savepoint on first-year insert. Does not touch `invoice_counters`. Unique `(workspace_id, credit_note_number)` includes soft-deleted rows. `soft_delete` sets `deleted_at` only. Test: delete `0001` → next is `0002`. Concurrent create uniqueness tested (8 threads). Failed create is uncommitted → counter rolls back with the session. |
| 5 | DRAFT-only PUT/DELETE; issue idempotent 200 | **PASS.** `assert_draft` → 403 `INVALID_STATE`. ISSUED PUT/DELETE tested. Router `GET … FOR UPDATE` then `issue()`: already ISSUED returns the same row, skips `_post_ar`. Second issue → 200, `amount_credited` unchanged (tested). No `/apply`. Create 201, issue default 200. |
| 6 | `balance_due` formula; PAID + CN not reopened | **PASS.** `Invoice.balance_due` / `InvoiceService.calculate_balance_due` = `max(0, total − SUCCESS paid − amount_credited)` (quantize fils). `determine_status_from_balance`: DRAFT/CANCELLED unchanged; `credit_owing > 0 or balance == 0` → **PAID** (does not compare paid vs original total). Unpaid SENT + CN shrinks due (SENT or OVERDUE). Full unpaid CN → PAID, no payment inserted. PAID + CN → PAID, `balance_due` 0, `credit_balance` += CN total (tested). Payment after CN uses new due; overpay 400 `PAYMENT_EXCEEDS_BALANCE`. |
| 7 | Issue never `CREDIT_HOLD` | **PASS.** `issue` / `create` / `update_draft` do not call `assert_not_hold`. Invoice **send** still does. After `_post_ar`, `CreditControlService.evaluate` (may leave HOLD). HOLD client issue 200; exposure drops (tested). |
| 8 | Invoice line amounts frozen | **PASS.** `build_item` copies `unit_price` / `tax_rate` / discounts / description / `product_id` from `InvoiceItem`. `assert_frozen` 422 on mismatch. No writes to `invoice_items` or invoice `total_amount`/`subtotal`. SENT invoice PUT remains DRAFT-only (unchanged). |
| 9 | Alembic linear | **PASS.** `b8d5f0c3a216` `down_revision = "a7c4e9d2b105"` only. No other revision parented on DN HEAD. Chain is single-file linear through LPO → credit HOLD → DN → CN. Tables `credit_note_counters`, `credit_notes`, `credit_note_items`, `credit_note_events`; `invoices.amount_credited`; `clients.credit_balance`; `ALTER TYPE invoiceeventtype ADD VALUE IF NOT EXISTS 'CREDIT_NOTE_ISSUED'`. DN/credit/LPO/FTA history not rewritten. |
| 10 | Concurrent issue doesn't double-credit | **PASS (HTTP path).** Same CN: router `FOR UPDATE` then ISSUED short-circuit. Two DRAFTs over remaining: invoice `FOR UPDATE`, then `assert_cn_remaining` vs Σ ISSUED, then status flush + `issued_header_total` cache. `credit_increment` uses unpaid-before this CN (not absolute `credit_balance`). Sequential same-CN idempotency tested; **two-DRAFT concurrent issue is not in pytest** (W3). |

---

## Findings

### Critical (P0)

None. Cross-tenant CN id is 404 with no payload leak. Cross-tenant parent invoice is 404. Issue does not insert, update, or delete payment rows. Header remaining + invoice row lock prevent double-post of AR on the HTTP issue path. PAID is not reopened to PARTIALLY_PAID.

### Warning

**W1 — Isolation 404 wrapper code is `HTTP_ERROR`**
`_load_or_404` raises `HTTPException(404, "Credit note not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no CN JSON leaked. Parent invoice 404s via `raise_error` correctly use `NOT_FOUND`. WP-B must treat **HTTP 404**, not only `error.code === "NOT_FOUND"`.

**W2 — `GET /invoices/{id}/balance` `total_paid` treats credits as payments**
`total_paid = invoice.total_amount - balance_due`. After a CN, `balance_due` already subtracts `amount_credited`, so this endpoint inflates `total_paid` by the credited amount. Payment **recording** uses `InvoiceService.calculate_balance_due` (correct). GET invoice exposes `amount_paid`, `amount_credited`, and `balance_due` separately (correct). WP-B must not use this balance endpoint’s `total_paid` as cash received.

**W3 — Concurrent two-DRAFT issue untested; service trusts the router lock**
`CreditNoteService.issue` does not re-`SELECT FOR UPDATE` the CN. The router does (`for_update=True`). Same-CN double-issue is covered sequentially. Missing: two full DRAFTs issued together → one 200, one 400 `CREDIT_EXCEEDS_REMAINING`, `amount_credited` equals one CN (mirror DN last-units test). A future internal caller that passes an unlocked DRAFT identity-map object could double-post AR. Defense in depth: lock inside the service.

**W4 — Absolute `discount_amount` is copied unscaled on partial qty**
Spec says copy frozen discounts from the invoice line. `build_item` copies the full line `discount_amount` even when CN qty is a subset. `apply_line_money` then takes that amount against the smaller extended. Partial credit can under-credit, or 400 if `discount_amount > extended`. Percent discounts scale. Tests use zero `discount_amount`. WP-B line picker: prefer percent, or full-line qty when the parent uses amount discounts.

**W5 — Alembic pytest uses env `DATABASE_URL`, not `_test`**
`test_alembic_upgrade_head_and_check` runs `alembic upgrade head` / `check` with `cwd=backend`. That is the app database from `.env`, while the rest of the module uses `{DATABASE_URL}_test` + `create_all`. Harmless if already at head; not isolated.

**W6 — Issue reloads the invoice without `FOR UPDATE` in the second SELECT**
`load_parent_invoice(..., for_update=True)` then `load_invoice_with_payments` (no `with_for_update`). PostgreSQL holds the row lock until commit, so this is not a double-credit hole. Clearer to keep `FOR UPDATE` on the payments reload so the lock is obvious in code.

### Info

**I1 — Pytest not re-run here**
13 functions in `test_credit_notes.py` map to spec §10 (concurrent unique numbers folded into the first test). 55 combined claimed in `backend-execution-report.md`. This pass is static.

**I2 — `issue_date` not confirmed on issue**
Spec: default UTC today; set/confirm on issue. Shipped: create uses `issue_date or utc_today()`; `freeze_snapshots` does not refresh it. A DRAFT opened yesterday and issued today keeps yesterday’s date. `original_invoice_number` / `original_issue_date` are set. WP-B PDF should show stored `issue_date`.

**I3 — `InvoiceListItem` omits `amount_credited`**
Spec requires it on `InvoiceResponse` (present). List still has `balance_due` with payments selectinloaded, so AR display can be correct without the extra column. Invoice detail should show `amount_credited`.

**I4 — Mid-file schema imports**
`serialize` / `serialize_list_item` import schemas inside the functions (`E402` vs CLAUDE.md). Same cycle-avoidance as invoices/DN. Not a runtime bug.

**I5 — Test file length**
`backend/tests/test_credit_notes.py` is ~554 lines. Spec “files < 500” is aimed at app modules (service 280, support 398, router 176 — under). Tests are slightly over.

**I6 — CN year is `datetime.now().year`, not UTC**
Matches `InvoiceNumberService`. `utc_today()` is used for dates. Fine except around New Year vs UTC.

**I7 — Coverage gaps (logic present)**
PUT/DELETE other-workspace 404 (same `_load_or_404` as GET); list `?invoice_id=` isolation (workspace filter → empty, not a leak); OVERDUE parent; PARTIAL + CN leftover `credit_balance`; extra key on issue body 422; `invoice_item_id` from another invoice in-workspace 422. Code paths exist.

**I8 — Pre-existing payment PUT (PDC status)**
`PUT /invoices/{id}/payments/{id}` can change `Payment.status` / `pdc_status`. WP-A did not add it and did not call it. CLAUDE.md immutability lock is older; PDC mutation is older. Do not treat WP-A as having introduced mutability.

**I9 — Client PUT cannot set `credit_balance`**
`ClientUpdate` `extra="forbid"` has no `credit_balance`. Only issue over-credit increments it. GET client + GET `/clients/{id}/credit` expose it. No auto-apply (out of WP).

---

## Spec lock vs shipped

| Lock | Shipped |
|---|---|
| `CN-YYYY-XXXX` via `credit_note_counters` + `FOR UPDATE` at create | `CreditNoteNumberService`; savepoint on first-year insert |
| DRAFT → ISSUED (issue posts AR); no `/apply` | `CreditNoteService.issue` + `_post_ar` |
| Issue idempotent 200 | Status short-circuit after CN lock |
| Remaining = invoice total − Σ ISSUED; qty per invoice line | `issued_header_total` / `issued_qty_map`; DRAFT does not reserve |
| Frozen invoice-line money | `assert_frozen` + `build_item` + `apply_line_money` |
| `balance_due = max(0, total − paid − credited)` | Invoice property + `calculate_balance_due` |
| PAID + CN → stay PAID + `credit_balance` | `determine_status_from_balance` + `credit_increment` |
| Issue never `CREDIT_HOLD` | No `assert_not_hold`; evaluate after post |
| Snapshots from invoice (live fallback, no FTA hard-fail) | `freeze_snapshots` |
| Alembic from `a7c4e9d2b105` | `b8d5f0c3a216` |

Router prefix `/credit-notes` under `/api/v1`. Pagination on list. Extra keys 422 on create/update/issue.

---

## WP-B notes (not blockers)

- Isolation toasts: use HTTP status 404 (W1 `HTTP_ERROR` vs `NOT_FOUND`).
- Invoice detail: `amount_credited` + adjusted `balance_due`; do not use GET balance `total_paid` (W2).
- Client: show `credit_balance` (read-only; no apply UI).
- PDF title **Tax Credit Note**; original INV number + issue date; snapshot TRNs; English; Helvetica. Tax Invoice PDF unchanged.
- Create from invoice: line picker with remaining qty; DRAFT-only edit; issue action.
- Absolute invoice-line `discount_amount` + partial qty is awkward (W4).
- Do not start WP-C Playwright until WP-B build + issue reduces invoice `balance_due` / PAID path parks `credit_balance`.

---

## Memory

Intended pattern keys (documented here; claude-flow `memory store` was not executed from this pass): `review-cn-issue-locks`, `review-balance-endpoint-credits-as-paid`, `review-404-http-error-wrapper`.
