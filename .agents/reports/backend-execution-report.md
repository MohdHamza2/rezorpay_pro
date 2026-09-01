# Backend Execution Report
*Wave 1: Bug Fix + Core Sync*

---

## 2026-09-01 — WP-A Payment / PDC truth + bounce (implemented)

**Spec:** `architecture/wave-pdc-addendum.md` WP-A. Architect note: `.agents/reports/architect-pdc-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Done

- `PaymentService.record_payment`: `method=PDC` always inserts `PENDING` + `RECEIVED` (today/past included), ignores body `pdc_status`, requires `pdc_date` (422 `field=pdc_date`). Does not reduce `balance_due` or flip PAID. CASH/BANK/CARD/CHEQUE stay SUCCESS. CHEQUE ignores `pdc_date`. HOLD never blocks POST. Overpay still 400 `PAYMENT_EXCEEDS_BALANCE` via `raise_error`. Date default `utc_today()`.
- PUT `/invoices/{id}/payments/{id}` → 405 `METHOD_NOT_ALLOWED` after workspace invoice 404.
- Four POSTs: `.../pdc/deposit|clear|bounce|return`. OWNER/ADMIN; MEMBER 403 `INSUFFICIENT_PERMISSIONS`. Isolation 404. SELECT FOR UPDATE invoice then payment. Amount/method/dates never rewritten. Bounce → FAILED + `evaluate(..., PAYMENT)`. Clear reuses `InvoiceService.calculate_balance_due` / `update_status_from_payments`. Over-clear 400, no `credit_balance` park. Historical SUCCESS PDC: clear 200 no-op, bounce 403.
- AR statement math unchanged. `test_success_pdc_in_paid` now deposit+clear so SUCCESS PDC still lists as Payment.

### Files

- `backend/app/schemas/common.py` — `METHOD_NOT_ALLOWED`
- `backend/app/schemas/payments.py` — `PdcActionRequest`
- `backend/app/services/payment_service.py` — PDC insert path
- `backend/app/services/pdc_service.py` — four transitions
- `backend/app/routers/payments.py` — PUT 405 + four POSTs
- `backend/app/services/__init__.py` — export `PdcService`
- `backend/tests/test_pdc.py` — addendum §12 (17 tests)
- `backend/tests/test_ar_statement.py` — `test_success_pdc_in_paid`

### Endpoints

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/invoices/{id}/payments` | PDC→PENDING+RECEIVED; still Idempotency-Key |
| PUT | `/api/v1/invoices/{id}/payments/{id}` | 405 (404 if invoice not in workspace) |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/deposit` | RECEIVED→DEPOSITED |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/clear` | DEPOSITED→CLEARED/SUCCESS |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/bounce` | DEPOSITED→BOUNCED/FAILED |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/return` | RECEIVED→RETURNED/CANCELLED |

### ErrorCodes added

- `METHOD_NOT_ALLOWED` (405)

Existing reused: `VALIDATION_ERROR`, `PAYMENT_EXCEEDS_BALANCE`, `INVALID_STATE`, `INSUFFICIENT_PERMISSIONS`, `NOT_FOUND`.

### Pytest (PostgreSQL `_test`)

- `tests/test_pdc.py`: **17 passed**
- `tests/test_ar_statement.py`: **13 passed**
- Combined: **30 passed**, 0 failed
- Related overpay/HOLD/isolation: 4 passed

`alembic heads`: **`b8d5f0c3a216`**. `alembic check`: No new upgrade operations detected. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A Payment / PDC truth + bounce (planned BEFORE code)

**Spec:** `architecture/wave-pdc-addendum.md` WP-A. Architect note: `.agents/reports/architect-pdc-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Locked

- Alembic **NO**. HEAD stays **`b8d5f0c3a216`**. No new columns/tables. Later WPs `down_revision = "b8d5f0c3a216"` until HEAD moves.
- `method=PDC`: require `pdc_date` (422 `VALIDATION_ERROR` `field=pdc_date`). Insert **always** `PENDING` + `RECEIVED` (today/past included). Ignore body `pdc_status`. Does **not** reduce `balance_due`. Must **not** flip invoice PAID.
- CASH / BANK_TRANSFER / CREDIT_CARD / **CHEQUE** still immediate SUCCESS. CHEQUE is not on the PDC machine (bounce → 403 `INVALID_STATE`).
- HOLD never blocks POST payment. Bounce calls `CreditControlService.evaluate(..., PAYMENT)`. Date gates use `CreditControlService.utc_today()`, not naive `date.today()`.
- Overpay at insert: amount > `InvoiceService.calculate_balance_due` → 400 `PAYMENT_EXCEEDS_BALANCE`. PENDING does not consume the cap. `/pdc/clear` same 400; do **not** park `credit_balance`.
- Four POSTs (OWNER/ADMIN; MEMBER 403 `INSUFFICIENT_PERMISSIONS`): `POST /api/v1/invoices/{invoice_id}/payments/{payment_id}/pdc/deposit|clear|bounce|return`. Empty body. No Idempotency-Key. Idempotent 200 if already in target. Rate-limit 10/minute.
- RECEIVED→DEPOSITED if `pdc_date <= utc_today()` else 400 `field=pdc_date`. Stays PENDING.
- DEPOSITED→CLEARED: status SUCCESS, FOR UPDATE invoice, `update_status_from_payments`. If amount > live `balance_due` → 400. Reuse existing balance formula.
- DEPOSITED→BOUNCED: status FAILED; amount unchanged; evaluate PAYMENT. Not PENDING.
- RECEIVED→RETURNED: CANCELLED. Return from DEPOSITED → 403 `INVALID_STATE`.
- Illegal (RECEIVED→clear, CHEQUE→bounce, CLEARED→bounce, etc.) → **403 INVALID_STATE** (not 409).
- Historical SUCCESS PDC: leave rows; `/pdc/clear` 200 no-op; bounce 403.
- PUT `/invoices/{id}/payments/{id}` → **405 METHOD_NOT_ALLOWED** (add ErrorCode). Other-workspace invoice → **404** first, never 405.
- Isolation: missing invoice/payment or other workspace → **404 NOT_FOUND**, never 403. Load invoice by id+workspace then payment by id+invoice_id.
- SELECT FOR UPDATE invoice **and** payment on transitions. Amount/method/payment_date/pdc_date never UPDATE. No DELETE route. POST create still requires Idempotency-Key.
- Errors via `raise_error` / `ErrorCode` (wrapper `{success,false,error}`). AR statement math **not** forked; patch `test_success_pdc_in_paid`.

### Files (planned)

- `backend/app/schemas/common.py` — `METHOD_NOT_ALLOWED`
- `backend/app/schemas/payments.py` — empty `PdcActionRequest` (`extra=forbid`)
- `backend/app/services/payment_service.py` — PDC insert PENDING+RECEIVED
- `backend/app/services/pdc_service.py` — four transitions
- `backend/app/routers/payments.py` — PUT 405 + four POSTs
- `backend/app/services/__init__.py` — export `PdcService`
- `backend/tests/test_pdc.py` — addendum §12 (17 bullets)
- `backend/tests/test_ar_statement.py` — `test_success_pdc_in_paid`

### Out

Frontend, Playwright, Alembic, git commit, volume pricing, bilingual, debit notes, CLEARED→BOUNCED, rewriting historical SUCCESS PDC, parking over-clear into `credit_balance`.

---

## 2026-09-01 — WP-A AR aging + Account Statement API (implemented)

**Spec:** `architecture/wave-ar-statement-addendum.md` WP-A. No UI/PDF/Playwright. **No Alembic.** No git commit.

### Done

- Generated `GET /api/v1/clients/{client_id}/ar-statement?from=&to=&as_of=` over live invoices / SUCCESS payments / ISSUED CNs / `clients.credit_balance`. Read-only: no INSERT/UPDATE/DELETE on those rows.
- Reuses `CreditControlService.open_ar_invoices` + `aging_buckets`. `amount_due_now` = exposure. `credit_balance` parked, not in buckets or `totals.paid`. `as_of=today` buckets match GET `/clients/{id}/credit`.
- Isolation **404** `NOT_FOUND` (never 403). CREDIT_HOLD does not block. OWNER/ADMIN/MEMBER via `get_current_user`.
- CN never in `totals.paid`. PENDING = Payment (pending), not cleared, not in paid. SUCCESS PDC is in paid with method PDC.
- Cap helper `assert_activity_cap` (monkeypatch `ACTIVITY_LINE_CAP` in the overflow test only).

### Files

- `backend/app/schemas/ar_statements.py`
- `backend/app/services/ar_statement_service.py`
- `backend/app/routers/clients.py` — GET on clients router (file stays well under 500 lines)
- `backend/app/schemas/common.py` — `DATE_RANGE_TOO_LONG`, `STATEMENT_TOO_LARGE`
- `backend/app/services/__init__.py`
- `backend/tests/test_ar_statement.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_ar_statement.py`: **13 passed**, 0 failed

`alembic heads` / `alembic current`: **`b8d5f0c3a216`**. No new revision. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A AR aging + Account Statement API (planned BEFORE code)

**Spec:** `architecture/wave-ar-statement-addendum.md` WP-A. Architect note: `.agents/reports/architect-ar-statement-note.md`. Backend + pytest only. No UI/PDF/Playwright. **No Alembic.** No git commit.

### Locked

- Generated GET only: live invoices + SUCCESS payments + ISSUED CNs + `clients.credit_balance`. No `ar_statements` table, no new columns. HEAD stays **`b8d5f0c3a216`**.
- `GET /api/v1/clients/{client_id}/ar-statement?from=&to=&as_of=`. `from`/`to` required. `as_of` optional, default UTC today. `as_of` after today → 422. `from > to` → 422. `(to-from).days > 366` → 422 `DATE_RANGE_TOO_LONG`. Activity lines (excl. opening) > 2000 → 400 `STATEMENT_TOO_LARGE`.
- Isolation: other-workspace client → **404** `NOT_FOUND`, never 403. CREDIT_HOLD does not block. Roles: OWNER/ADMIN/MEMBER via `get_current_user` (same as GET client / GET credit).
- Reuse `CreditControlService.open_ar_invoices` + `aging_buckets`. Do not fork buckets. `as_of=today` buckets must equal GET `/clients/{id}/credit`. `amount_due_now` = exposure. `credit_balance` parked, not a bucket, not in `totals.paid`.
- Include-set S: `deleted_at` null, status SENT/PARTIALLY_PAID/PAID/OVERDUE. Exclude DRAFT/CANCELLED invoices (+ their payments/CNs), DRAFT CNs, quotes/LPO/DN, FAILED/CANCELLED/REFUNDED payments.
- CN amounts never in `totals.paid`. PENDING not in paid (`cleared_cash` false). SUCCESS PDC **is** in `totals.paid`; method PDC; not labelled Tax Credit Note.
- GET is read-only: do not mutate invoices, payments, CNs, or `credit_balance`. No server PDF. No pagination. Do not change GET `/clients/{id}/credit`. Do not add PDC bounce/clear/deposit. Do not change `record_payment`.
- `doc_type` + exact `doc_type_label` from addendum §7.1. Sort: opening first; date ASC; TAX_INVOICE, PAYMENT, PAYMENT_PENDING, TAX_CREDIT_NOTE; number ASC. All money via `money()` ROUND_HALF_UP.

### Files (planned)

- `backend/app/schemas/ar_statements.py`
- `backend/app/services/ar_statement_service.py`
- `backend/app/routers/clients.py` (GET on clients router; file stays well under 500 lines)
- `backend/app/schemas/common.py` — `DATE_RANGE_TOO_LONG`, `STATEMENT_TOO_LARGE`
- `backend/app/services/__init__.py`
- `backend/tests/test_ar_statement.py` — addendum §10, PostgreSQL `_test`

### Out

Frontend, Playwright, Alembic, git commit, PDC truth, bilingual, debit notes, invoice-list `amount_credited`, dashboard overdue.

---

## 2026-09-01 — WP-A W2 GET /invoices/{id}/balance credits-as-cash (implemented)

**Nit:** W2 in `.agents/reports/wp-a-credit-notes-review.md`. Backend only. No Alembic rewrite. No git commit.

### Done

- `GET /invoices/{id}/balance` no longer sets `total_paid = total − balance_due` (that treated issued CNs as cash).
- Response now exposes `amount_paid` (SUCCESS payments only) and `amount_credited` separately.
- `total_paid` is cash-only (same as `amount_paid`).
- `balance_due` stays `max(0, total − paid − credited)` via `InvoiceService.calculate_balance_due`.
- Pytest: unpaid CN → `total_paid`/`amount_paid` stay 0; partial payment + CN → `total_paid` equals cash, not cash+credit.

### Files

- `backend/app/schemas/payments.py` — `BalanceDueResponse` + `amount_paid` / `amount_credited`
- `backend/app/routers/payments.py` — `_balance_payload`
- `backend/tests/test_credit_notes.py` — `_get_balance`; unpaid GET `/balance` asserts; `test_balance_endpoint_does_not_treat_credits_as_paid`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_notes.py`: **14 passed**
- `tests/test_invoices.py`: **25 passed**
- Combined: **39 passed, 0 failed**

black + ruff clean on touched files.

---

## 2026-09-01 — WP-A W2 GET /invoices/{id}/balance credits-as-cash (planned BEFORE code)

**Nit:** W2 in `.agents/reports/wp-a-credit-notes-review.md`. Backend only. No Alembic rewrite. No git commit.

### Locked

- `GET /invoices/{id}/balance` must not treat credit notes as cash.
- Expose `amount_paid` (SUCCESS payments only) and `amount_credited` separately.
- Keep `total_paid` as cash received: same as `amount_paid`, never `total_amount − balance_due`.
- `balance_due` stays `max(0, total − paid − credited)`.
- Pytest: after an issued CN, `total_paid` / `amount_paid` are not inflated by the credited amount.
- Files: `backend/app/schemas/payments.py`, `backend/app/routers/payments.py`, `backend/tests/test_credit_notes.py`.

---

## 2026-09-01 — WP-A Tax Credit Notes API (planned BEFORE code)

**Spec:** `architecture/wave-credit-notes-addendum.md` WP-A. Architect note: `.agents/reports/architect-credit-notes-note.md`. No UI/PDF/Playwright. No git commit.

### Locked

- `CreditNoteNumberService` SELECT FOR UPDATE `CN-YYYY-XXXX` on `credit_note_counters` at create. Gapless. Soft-delete does not rewind.
- Parent invoice SENT/PARTIALLY_PAID/PAID/OVERDUE only. DRAFT/CANCELLED → 403 `INVALID_STATE`. Other workspace → 404.
- Lines ≥ 1, each `invoice_item_id`. Qty ≤ remaining vs ISSUED CNs. Frozen `unit_price`/`tax_rate`/discounts (mismatch 422). Header total ≤ `invoice.total − Σ ISSUED CN.total` else 400 `CREDIT_EXCEEDS_REMAINING` `field=total_amount`. Same `money()`.
- DRAFT → ISSUED posts AR. No `/apply`. No PUT/DELETE after ISSUED. Soft-delete DRAFT only. Issue idempotent 200. SELECT FOR UPDATE CN + invoice.
- `balance_due = money(max(0, total − paid − credited))`. Never mutate payment rows or invoice line money.
- Unpaid/partial: shrink due; PAID if remainder covered. PAID + CN: stay PAID; increment `clients.credit_balance` by this CN’s over-credit. No auto-apply.
- Issue never `CREDIT_HOLD`. Re-evaluate after issue. Create/PUT never blocked.
- FTA snapshots on issue from invoice snapshots (live fallback like send, no FTA hard-fail).
- Tests: `backend/tests/test_credit_notes.py` §10 + invoices/payments/credit_control regression. PostgreSQL `_test`.

### Files (planned)

- `backend/app/models/credit_note_counter.py`, `credit_note.py`, `credit_note_item.py`, `credit_note_event.py`
- `backend/alembic/versions/b8d5f0c3a216_add_credit_notes.py` (`down_revision = "a7c4e9d2b105"`)
- `backend/app/services/credit_note_number.py`, `credit_note_support.py`, `credit_note_service.py`
- `backend/app/schemas/credit_notes.py`, `routers/credit_notes.py`, `main.py`
- Invoice/client/payment hooks: `invoice.py`, `invoice_event.py`, `invoice_service.py`, `schemas/invoices.py`, `client.py`, `schemas/clients.py`, `credit_control_service.py`
- `backend/tests/test_credit_notes.py`

---

## 2026-09-01 — WP-A Tax Credit Notes API (implemented)

**Spec:** addendum WP-A. No UI/PDF/Playwright. No git commit.

### Done

- `CreditNoteNumberService` SELECT FOR UPDATE `CN-YYYY-XXXX` via `credit_note_counters` (savepoint on first-year insert race). Soft-delete does not rewind.
- Parent SENT/PARTIALLY_PAID/PAID/OVERDUE only. DRAFT/CANCELLED → 403. Other workspace → 404.
- Frozen invoice-line money; omit `tax_rate` copies invoice 5%. Qty > remaining → 400. Header > remaining → 400 `CREDIT_EXCEEDS_REMAINING`. Extra keys 422.
- DRAFT → ISSUED posts AR (`amount_credited`, `balance_due = max(0, total − paid − credited)`). Idempotent issue 200. PUT/DELETE ISSUED → 403. No `/apply`.
- PAID + CN stays PAID; over-credit increments `clients.credit_balance`. Payments never updated/deleted. Issue never `CREDIT_HOLD`.
- FTA snapshots copied on issue from invoice (live fallback, no FTA hard-fail).

### Files

- models: `credit_note_counter.py`, `credit_note.py`, `credit_note_item.py`, `credit_note_event.py` + invoice/client/invoice_event/user
- `backend/alembic/versions/b8d5f0c3a216_add_credit_notes.py`
- `credit_note_number.py`, `credit_note_support.py`, `credit_note_service.py`
- `schemas/credit_notes.py`, `routers/credit_notes.py`, `main.py`
- `invoice_service.py` balance/status, `credit_control_service.py` aging `credit_balance`
- `backend/tests/test_credit_notes.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_notes.py`: **13 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_credit_control.py`: **17 passed**
- Combined: **55 passed, 0 failed**

`alembic upgrade head` + `alembic check` clean. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A Delivery Notes API (planned BEFORE code)

**Spec:** `architecture/wave-delivery-notes-addendum.md` WP-A. Architect note: `.agents/reports/architect-delivery-notes-note.md`. No UI/PDF/Playwright. No git commit.

### Locked

- `DnNumberService` SELECT FOR UPDATE `DN-YYYY-XXXX` on `dn_counters`.
- XOR parent: exactly one of LPO or invoice. Both/neither 422. Over-deliver 400. LPO remaining = ordered − CONFIRMED DN qty (not invoiced). Invoice remaining = invoice qty − CONFIRMED DN qty.
- State: DRAFT → CONFIRMED (ISSUE −qty) → CANCELLED (ISSUE +qty, `reference_type=DN_CANCEL`). DRAFT soft-delete. Confirm idempotent 200. `/cancel` CONFIRMED only.
- Catalog `product_id` required to move stock; ad-hoc confirm with no ledger. Must reference parent line. Inactive product 400. Other-workspace 404.
- HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` via `CreditControlService.assert_not_hold` + `CreditEventReason.DN_CONFIRM`. Create/PUT never blocked.
- `inventory_ledger.py`: GRN-style FOR UPDATE + bin, filter `workspace_id`. Never float. Never call adjust from DN.
- Tighten `POST /inventory/adjust`: OWNER/ADMIN; reason allow-list; notes min 3; workspace 404; MEMBER 403. Keep endpoint.
- LPO GET: `quantity_delivered` / `quantity_undelivered`.
- Tests: `backend/tests/test_delivery_notes.py` §13 + GRN/inventory regression + credit HOLD confirm. PostgreSQL `_test`.

### Files (planned)

- `backend/app/models/dn_counter.py`, `delivery_note.py`, `delivery_note_item.py`, `delivery_note_event.py`
- `backend/alembic/versions/a7c4e9d2b105_add_delivery_notes.py` (`down_revision = "9f3a7c2e1d04"`)
- `backend/app/services/dn_number.py`, `inventory_ledger.py`, `delivery_note_support.py`, `delivery_note_service.py`
- `backend/app/schemas/delivery_notes.py`, `routers/delivery_notes.py`, `main.py`
- `backend/app/routers/inventory.py` + `schemas/inventory.py` adjust tighten
- `backend/tests/test_delivery_notes.py`

---

## 2026-09-01 — WP-A Delivery Notes API (implemented)

**Spec:** addendum WP-A. No UI/PDF/Playwright. No git commit.

### Done

- `DnNumberService` SELECT FOR UPDATE `DN-YYYY-XXXX` via `dn_counters` (savepoint on first-year insert race).
- XOR parent: LPO remaining = ordered − CONFIRMED DN qty (independent of `quantity_invoiced`). Invoice remaining = invoice qty − CONFIRMED DN qty. Both/neither 422. Over-deliver 400.
- DRAFT → CONFIRMED posts `ISSUE` (−qty, `reference_type=DN`). Cancel CONFIRMED posts `ISSUE` (+qty, `DN_CANCEL`) and restores `quantity_delivered`. Confirm idempotent 200. DRAFT soft-delete. DN never calls adjust.
- HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` + `DN_CONFIRM`. Create/PUT never blocked.
- `POST /inventory/adjust`: OWNER/ADMIN; reason allow-list + notes; workspace 404; MEMBER 403.
- LPO GET: `quantity_delivered` / `quantity_undelivered`.

### Files

- models: `dn_counter.py`, `delivery_note.py`, `delivery_note_item.py`, `delivery_note_event.py` + CPO item / inventory / credit enum / user
- `backend/alembic/versions/a7c4e9d2b105_add_delivery_notes.py`
- `dn_number.py`, `inventory_ledger.py`, `delivery_note_support.py`, `delivery_note_service.py`
- `schemas/delivery_notes.py`, `routers/delivery_notes.py`, `main.py`, `routers/inventory.py`
- `backend/tests/test_delivery_notes.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_delivery_notes.py`: **14 passed**
- `tests/test_grn.py`: **2 passed**
- `tests/test_credit_control.py`: **17 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_invoices.py`: **25 passed**
- Combined: **75 passed, 0 failed**

`alembic upgrade head` + `alembic check` clean. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A credit nits W1/W2/W4 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-credit-control-review.md` W1, optional W2, test for FTA-valid HOLD send. Spec: `architecture/wave-credit-control-addendum.md` §6–7. Backend only. No UI. No Alembic rewrite. No git commit. Skip client-list in-memory pagination (W3).

### Bugs / nits

1. **W1 — SENT→OVERDUE not persisted on send/evaluate.** GET/list invoices flip; `mark_as_sent` always writes SENT (even when `due_date` is already yesterday). `evaluate` recomputes HOLD from due_date/balance but never calls `apply_overdue_*`. Send of a past-due tax invoice can return SENT until the next GET/list.
2. **Test gap — FTA-valid HOLD send.** Code order is FTA then `assert_not_hold`. Need an explicit test: HOLD client + valid workspace TRN/address → send 400 `CREDIT_HOLD` (not `FTA_SEND_BLOCKED`), invoice stays DRAFT.
3. **W2 (optional, few lines) — no row lock on HOLD check.** Concurrent first SENDs on COD can both see exposure 0. Addendum does not forbid `SELECT FOR UPDATE`. Lock invoice on send + client during `assert_not_hold`.

### Planned

1. After DRAFT→SENT snapshots, call `apply_overdue_invoice` so past-due + `balance_due > 0` persists OVERDUE on the send path. Never flip PAID/CANCELLED/DRAFT (`FLIP_STATUSES` only).
2. `evaluate` bulk-flips this client's SENT/PARTIALLY_PAID rows matching the overdue predicate (same as list/GET on-read) before snapshot. GET `/clients/{id}/credit` and other evaluate callers persist OVERDUE.
3. Pytest: send of already-past-due invoice returns OVERDUE; evaluate (credit GET) flips a backdated SENT row; PAID/CANCELLED still untouched; FTA-valid HOLD send is 400 CREDIT_HOLD.
4. Send: `SELECT FOR UPDATE` on the invoice row. `assert_not_hold`: `SELECT FOR UPDATE` on the client row before evaluate.

### Files

- `backend/app/services/credit_control_service.py`
- `backend/app/services/invoice_service.py`
- `backend/app/routers/invoices.py`
- `backend/tests/test_credit_control.py`
- this report

---

## 2026-09-01 — WP-A credit nits W1/W2/W4 (implemented)

**Spec:** addendum §6–7. No UI. No Alembic rewrite. No git commit. W3 client-list pagination skipped.

### Done

- `evaluate` calls `apply_overdue_client` before snapshot so GET credit / send HOLD check persist SENT/PARTIALLY_PAID → OVERDUE. Predicate unchanged: not deleted, `FLIP_STATUSES` only, `due_date < UTC today`, `balance_due > 0`. PAID/CANCELLED/DRAFT never flipped.
- `mark_as_sent` sets SENT then `apply_overdue_invoice` so a past-due send response is OVERDUE, not SENT.
- Send loads the invoice `SELECT FOR UPDATE`. `assert_not_hold` locks the client row before evaluate (W2, addendum does not forbid).
- Tests: send of yesterday-due invoice returns OVERDUE; credit evaluate flips a backdated SENT row and leaves PAID; FTA-valid HOLD send is 400 `CREDIT_HOLD` (not `FTA_SEND_BLOCKED`).

### Files

- `backend/app/services/credit_control_service.py`
- `backend/app/services/invoice_service.py`
- `backend/app/routers/invoices.py`
- `backend/tests/test_credit_control.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_control.py`: **17 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- Combined: **64 passed, 0 failed**

black + ruff clean on the touched files.

---

## 2026-09-01 — WP-A Credit HOLD / overdue API (planned BEFORE code)

**Spec:** `architecture/wave-credit-control-addendum.md` WP-A. Architect note: `.agents/reports/architect-credit-control-note.md`.

### Locked

- `CreditControlService`: exposure SUM (SENT+PARTIALLY_PAID+OVERDUE, SUCCESS payments, Decimal), evaluate HOLD/WARNING/ACTIVE, persist status+`credit_status_events`, `assert_not_hold`.
- Invoice SEND always blocked on HOLD (after FTA). LPO `/receive` blocked iff `block_po_on_hold`. DRAFT create, quote convert, payments not blocked.
- OVERDUE on-read + payment status lock: past-due partial stays OVERDUE. Never mutate PAID/CANCELLED.
- Replace quote/LPO convert hardcoded +30 with `issue_date + client.payment_terms_days`.
- `GET /clients/{id}/credit` aging JSON. `CREDIT_HOLD` is 400. Isolation 404. Extra keys 422.
- Tests: `backend/tests/test_credit_control.py` + existing invoices/payments/LPO isolation. PostgreSQL `_test`. No UI/Playwright. No git commit.

### Files (planned)

- `backend/app/models/client.py`, `credit_status_event.py`, `models/__init__.py`, `invoice.py` (composite index only)
- `backend/alembic/versions/*_add_client_credit_control.py` (`down_revision = "59084165d346"`)
- `backend/app/services/credit_control_service.py`
- invoice send + payment status + LPO receive + quote/LPO due_date
- `backend/app/schemas/clients.py`, `common.py`, `routers/clients.py`, `workspaces.py`
- `backend/tests/test_credit_control.py` (+ quotation due_date default 0)

---

## 2026-09-01 — WP-A Credit HOLD / overdue API (implemented)

**Revision:** `9f3a7c2e1d04` (`down_revision = "59084165d346"`). No UI. No git commit.

### Done

- Client credit fields + `credit_status_events`. NULL limit inherits workspace default; 0 = COD; >0 cap.
- `CreditControlService`: Decimal exposure of SENT+PARTIALLY_PAID+OVERDUE (SUCCESS payments). HOLD if exposure > effective_limit OR oldest overdue days > hold_days. WARNING never blocks. Auto both directions.
- Invoice SEND always 400 `CREDIT_HOLD` after FTA. LPO `/receive` blocked iff `block_po_on_hold`. DRAFT create, quote convert, payments allowed.
- OVERDUE on-read (GET/list) and payment recalc. Partial past-due stays OVERDUE. PAID/CANCELLED never flipped.
- Quote/LPO convert `due_date` = issue + `payment_terms_days` (default 0 → same day).
- `GET /clients/{id}/credit` aging JSON. Extra keys 422. Isolation 404.

### Files

- `backend/app/models/client.py`, `credit_status_event.py`, `invoice.py`, `models/__init__.py`
- `backend/alembic/versions/9f3a7c2e1d04_add_client_credit_control.py`
- `backend/app/services/credit_control_service.py`, `invoice_service.py`, `payment_service.py`, `customer_po_service.py`, `quotation_service.py`
- `backend/app/schemas/clients.py`, `common.py`
- `backend/app/routers/clients.py`, `invoices.py`, `workspaces.py`
- `backend/tests/test_credit_control.py`, `tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_control.py`: **15 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_quotations.py`: **20 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- Combined: **82 passed, 0 failed**

`alembic check`: No new upgrade operations detected. black + ruff clean.

---

## 2026-09-01 — WP-A customer LPO nit W1 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-customer-lpo-review.md` warning **W1**. Backend only. No UI. No Alembic rewrite. No git commit.

### Bug

`_resolve_slices` compares each requested qty to the line’s remaining **before this request**. Repeating the same `customer_purchase_order_item_id` in one `POST .../invoices` body (e.g. 60 + 60 against remaining 100) both pass; `InvoiceService` writes qty 120. `recalc_invoiced` then clamps `quantity_invoiced` to ordered qty, so GET LPO looks clean while the tax invoice over-states qty. Concurrent POSTs stay serialized by LPO `SELECT FOR UPDATE` — do not weaken that.

### Planned

1. Per-request remaining accumulator in `_resolve_slices`: each occurrence of a line id consumes leftover qty. Second occurrence that exceeds leftover → **400** `VALIDATION_ERROR` `field=quantity` **before** invoice create. Lines already fully invoiced before this POST still skip (spec remaining 0).
2. Pytest: two allocations of the same `customer_purchase_order_item_id` in one POST that exceed ordered qty → 400; LPO `quantity_invoiced` cache unchanged; no invoice created.

### Files

- `backend/app/services/customer_po_service.py`
- `backend/tests/test_customer_lpos.py`

### Verification

`pytest tests/test_customer_lpos.py tests/test_quotations.py tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` on PostgreSQL `_test`. black + ruff.

---

## 2026-09-01 — WP-A customer LPO nit W1 (implemented)

Backend only. No UI. No Alembic rewrite. No git commit. Concurrent LPO `SELECT FOR UPDATE` on `/invoices` unchanged.

### Done

`_resolve_slices` keeps a per-request leftover map. Each occurrence of a line id consumes leftover qty. Qty that exceeds leftover → **400** `VALIDATION_ERROR` `field=quantity` before `InvoiceService.create_invoice`. Lines already fully invoiced before this POST still skip (spec remaining 0). Duplicate 60+60 against ordered 100 is rejected; `quantity_invoiced` cache stays 0.

### Files

- `backend/app/services/customer_po_service.py`
- `backend/tests/test_customer_lpos.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `_test`)

- `tests/test_customer_lpos.py`: **17 passed** (includes `test_duplicate_line_ids_over_invoice_400_cache_unchanged`)
- `tests/test_quotations.py`: **20 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **71 passed, 0 failed** (72.37s)

black + ruff clean.

---

## 2026-09-01 — WP-A Customer LPO API (planned BEFORE code)

**Spec:** `architecture/wave-customer-lpo-addendum.md` WP-A. Architect note: `.agents/reports/architect-customer-lpo-note.md`.

### Locked

- Router `/api/v1/customer-purchase-orders` (JWT). Convert `POST /quotations/{id}/convert-to-lpo`. No `/confirm`, no UI/PDF.
- States: DRAFT → RECEIVED → PARTIAL → INVOICED. CANCELLED from RECEIVED with zero countable invoices. DRAFT DELETE = soft-delete.
- Internal `LPO-YYYY-XXXX` via `lpo_counters` + SELECT FOR UPDATE. `customer_po_number` unique per (workspace, client) when set.
- Lines: `quantity` vs `quantity_invoiced`; remaining = ordered − SUM countable (DRAFT counts; CANCELLED/deleted do not). Over-invoice 400. Shared `line_money`.
- Quote convert ACCEPTED → DRAFT LPO frozen lines. Mutex with convert-to-invoice 409. Idempotent 200. Manual LPO without quotation_id allowed.
- `POST .../invoices` → `InvoiceService.create_invoice` DRAFT; many invoices per LPO; `quotation_id` null. FTA send waits. Recalc on void and DRAFT delete. PUT forbidden on LPO-linked invoices.
- Wrapper pagination. Extra keys 422. Decimal AED. Cross-tenant 404.
- Tests: `backend/tests/test_customer_lpos.py` + quotation convert mutex. PostgreSQL `_test`.

### Out

WP-B UI/PDF, WP-C Playwright, OCR, credit HOLD, delivery notes, SPO/GRN changes.

---

## 2026-09-01 — WP-A Customer LPO API (implemented)

**Revision:** `59084165d346` (`down_revision = "cb01b6bef962"`). Partial invoices use `InvoiceService.create_invoice`. Shared `line_money`. FTA send stays on invoice `/send`. No UI/PDF. No git commit.

### Done

- Models + Alembic: `lpo_counters`, `customer_purchase_orders`, `customer_purchase_order_items`, `customer_purchase_order_events`, `invoices.customer_purchase_order_id` (indexed, not unique), `invoice_items.customer_purchase_order_item_id`. Unique `customer_purchase_orders.quotation_id`. Partial unique customer PO number per client.
- Number `LPO-YYYY-XXXX` via `LpoNumberService` SELECT FOR UPDATE. Prefix LPO- not CPO-.
- States: DRAFT → RECEIVED (`/receive`) → PARTIAL → INVOICED. CANCELLED from RECEIVED with zero countable invoices. DRAFT soft-delete. Recalc on invoice create/void/DRAFT delete.
- Quote `POST /quotations/{id}/convert-to-lpo` ACCEPTED → DRAFT LPO, frozen lines, quote CONVERTED. Idempotent 200. Mutex 409 with convert-to-invoice.
- `POST /customer-purchase-orders/{id}/invoices` → many DRAFT invoices, `quotation_id` null. Over-invoice 400. PUT on LPO-linked invoices 403.
- Router mounted at `/api/v1/customer-purchase-orders`. JWT, wrapper pagination, extra keys 422, AED, cross-tenant 404.

### Files

- `backend/app/models/lpo_counter.py`
- `backend/app/models/customer_purchase_order.py`
- `backend/app/models/customer_purchase_order_item.py`
- `backend/app/models/customer_purchase_order_event.py`
- `backend/app/schemas/customer_purchase_orders.py`
- `backend/app/services/lpo_number.py`
- `backend/app/services/customer_po_support.py`
- `backend/app/services/customer_po_service.py`
- `backend/app/routers/customer_purchase_orders.py`
- `backend/app/main.py`, quotation/invoice services and routers
- `backend/tests/test_customer_lpos.py`, `backend/tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_customer_lpos.py`: **16 passed**
- `tests/test_quotations.py`: **20 passed** (includes convert mutex)
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **70 passed, 0 failed** (68.45s)

black + ruff clean. `alembic check`: No new upgrade operations detected.

---

## 2026-09-01 — WP-A review nits W1–W3 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-quotations-review.md` (APPROVE_WITH_NITS). Backend only. No UI. No Alembic rewrite. No git commit.

### Planned

1. **W1 Expiry persist on 403:** `accept` / `reject` / `convert` apply on-read EXPIRED and **commit that write** before the illegal action returns 403. Today the router commits only on success, so HTTPException rolls back EXPIRED and the row stays SENT until GET/list.
2. **W3 Converted-invoice hydration:** `map_converted_ids` and `existing_converted_invoice` must filter `Invoice.workspace_id` to the JWT workspace (same as the quote). Unique `quotation_id` is not enough.
3. **W2 Inactive-product copy:** Quote create/update `_resolve_line` must not say “invoice”. Use quotation/line wording. Invoice path unchanged.

### Tests / quality

- Extend `tests/test_quotations.py`: persist EXPIRED after accept/reject/convert without a prior GET (read status from PostgreSQL, not GET — GET would expire on-read and hide the bug). Assert inactive-product 400 message mentions quotation, not invoice.
- `pytest tests/test_quotations.py tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` on PostgreSQL `_test`.
- black + ruff.

---

## 2026-09-01 — WP-A review nits W1–W3 (implemented)

No Alembic rewrite. No UI. No git commit.

### Done

1. **W1:** `expire_if_due` / `_load_and_expire` persist SENT→EXPIRED **before** accept/reject/convert. Router commits that write, then the action 403s `INVALID_STATE`. Illegal-action rollback no longer undoes expiry. Tests read status from PostgreSQL (not GET).
2. **W3:** `map_converted_ids` and `existing_converted_invoice` filter `Invoice.workspace_id` to the JWT workspace. Convert create uses the same workspace id.
3. **W2:** Quote `_resolve_line(..., line_owner="quotation")` → “Cannot add an inactive product to a quotation line”. Invoice path still says “an invoice”.

### Files

- `backend/app/routers/quotations.py`
- `backend/app/services/quotation_service.py`
- `backend/app/services/quotation_support.py`
- `backend/app/services/invoice_service.py`
- `backend/tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_quotations.py`: **18 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **52 passed, 0 failed** (51.03s)

black + ruff clean.

---

## 2026-09-01 — WP-A Quotations API (planned BEFORE code)

**Spec:** `architecture/wave-quotations-addendum.md` WP-A. Architect note: `.agents/reports/architect-quotations-note.md`.

### Locked

- Router `/api/v1/quotations` (JWT on all routes). No public accept. No LPO stubs. No PDF/UI.
- States: DRAFT → SENT → ACCEPTED | REJECTED | EXPIRED. Convert **only ACCEPTED** → CONVERTED.
- Convert calls `InvoiceService.create_invoice` (DRAFT invoice, frozen line prices, notes prefix `Converted from QUO-…`, issue/supply=today, due=today+30). FTA send gates stay on invoice `/send`.
- Convert once: unique `invoices.quotation_id`. Second convert HTTP 200 same invoice. Soft-deleted invoice → 409, do not recreate.
- On-read expiry (`valid_until` default quotation_date + 14 days). Number `QUO-YYYY-XXXX` via new counter + SELECT FOR UPDATE.
- Shared `money()` ROUND_HALF_UP (extract `line_money.py`). Extra keys 422. AED Decimal. Cross-tenant 404.
- Tests: `backend/tests/test_quotations.py` against PostgreSQL `_test`. Existing invoice/FTA/numbering tests must still pass.

### Out

WP-B PDF/UI, WP-C Playwright, LPO, public accept, REVISED/CANCELLED quote states, nightly expiry job.

---

## 2026-09-01 — WP-A Quotations API (implemented)

**Revision:** `cb01b6bef962` (`down_revision = "c8e1a4f2b6d0"`). Convert uses `InvoiceService.create_invoice`. Shared `app/services/line_money.py` (`money` ROUND_HALF_UP). Quote send does not require TRN; invoice send still FTA-gated.

### Done

- Models + Alembic: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`, `invoices.quotation_id`.
- `QuotationNumberService` `QUO-YYYY-XXXX` via SELECT FOR UPDATE on new counter.
- Router `/api/v1/quotations` JWT: CRUD, send, accept, reject, convert-to-invoice. Extra keys 422. Cross-tenant 404.
- Convert: DRAFT invoice, frozen prices, notes prefix, issue/supply=today, due=+30. First convert 201; second 200 same invoice; soft-deleted invoice 409. SENT/DRAFT/EXPIRED/REJECTED cannot convert (403).
- On-read expiry. DRAFT-only edit/delete. Soft-delete does not rewind numbers.

### Pytest (PostgreSQL `invoicesaas_test`)

- `tests/test_quotations.py`: **16 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_concurrent_numbering.py` + `tests/test_multi_tenant_isolation.py`: **4 + 5 passed**
- Combined: **50 passed, 0 failed**

black + ruff clean. No git commit. No SQLite. No frontend/PDF (WP-B).

---


## Changes Made
- Updated pp/models/invoice.py: Added @property for mount_paid and alance_due that calculate directly from successful payments dynamically.
- Updated pp/schemas/invoices.py: Added mount_paid and alance_due to InvoiceResponse and InvoiceListItem to ensure API surfaces these values.
- Updated pp/routers/invoices.py: Added .options(selectinload(Invoice.payments)) to list_invoices to eagerly load payments, preventing N+1 queries.
- Ensured InvoiceVoidRequest validates
eason (min_length=5).

## Testing
- Tested DB schema compatibility (no migrations needed since properties are computed).
- Pydantic validation handles properties automatically on response model dump.

---

## 2026-08-19 - Wave 2 Execution: Workspace Settings
- Updated pp/models/workspace.py: Added new fields for TRN, Logo URL, Default Tax Rate, WhatsApp Number, and Credit Control settings.
- Ran Alembic migration to update database schema.
- Added new workspaces schemas and router to support GET /api/v1/workspaces/me and PUT /api/v1/workspaces/me.
- Registered workspaces_router in pp/main.py.

---

## 2026-08-19 - Wave 3 Execution: Product Master
- Defined complex Database Models for Product, Category, Brand, UnitOfMeasure, ProductIdentifier, ProductUOMConversion, and ProductPrice with strict foreign keys and unique constraints in ackend/app/models/product.py.
- Exposed models in __init__.py and generated Alembic migration d3e4c7fdb29f to instantiate the schema securely in the database.
- Implemented core Pydantic schemas in products.py for API validation.
- Created ackend/app/routers/products.py with GET and POST operations for products, categories, brands, and UOMs.
- Bound products_router into the core application via main.py.

---

## 2026-08-19 - Wave 4 Execution: Supplier Master
- Designed ackend/app/models/supplier.py incorporating complex relationships: Supplier, SupplierContact, SupplierBankAccount, SupplierDocument, and SupplierProduct.
- Exported the newly created models into __init__.py to make them Alembic-discoverable.
- Applied 784076ef11b9_add_wave_4_supplier_master.py DB migration smoothly.
- Created fully-typed Pydantic schemas in suppliers.py enforcing core commercial constraints like Credit Limits and Terms.
- Developed suppliers.py router logic for scalable GET and POST access and mounted it in main.py globally.

---

## 2026-08-19 - Wave 5 Execution: Payment Methods
- Re-architected ackend/app/models/payment.py replacing generic gateways with concrete B2B payment methods (CASH, BANK_TRANSFER, CHEQUE, PDC, CREDIT_CARD).
- Added robust PDC lifecycle tracking (pdc_date, pdc_status: RECEIVED -> DEPOSITED -> CLEARED -> BOUNCED).
- Upgraded PaymentService.record_payment() to dynamically consume these commercial fields while retaining ACID row-level locking for concurrency protection.
- Generated Alembic PostgreSQL ENUM migration script e217c0bc3af7 safely rolling out the schema updates.
- Added a PUT /invoices/{invoice_id}/payments/{payment_id} router endpoint to natively handle PDC lifecycle state mutations.

---

## 2026-08-19 - Wave 7 Execution: Inventory Management Foundation
- Established robust inventory core via ackend/app/models/inventory.py featuring 5 master tables: Warehouse, WarehouseBin, InventoryLevel, TransactionType, and InventoryTransaction.
- Implemented **Rule 1.2** (Immutable Ledger) ensuring InventoryTransaction acts as an append-only source of truth for stock movements.
- Implemented **Rule 1.3** and Check Constraints (chk_inventory_on_hand_positive) to guarantee stock integrity at the database layer (preventing accidental negative stock).
- Generated and successfully applied PostgreSQL migration d41016da5030.
- Authored strict Pydantic schemas in inventory.py calculating dynamic fields like vailable = on_hand - reserved - damaged.
- Attached the core APIs via /api/v1/inventory router into main.py utilizing SELECT ... FOR UPDATE row-level locks for concurrent adjustment protection.

---

## 2026-08-19 - Wave 8 Execution: Procurement Foundation
- Constructed ProcurementRequest and ProcurementRequestItem database schemas enforcing the strict separation of internal demand from supplier execution.
- Added comprehensive Enums representing Procurement business logic (PRSourceType, PRDestinationType, PRStatus, etc.) matching the architectural design documents.
- Implemented quantity allocation vectors mapping precisely to Rule C-02 (
equested_quantity, pproved_quantity, ordered_quantity,
eceived_quantity).
- Successfully tracked and deployed Alembic DB Migration  abb440e0fc9.
- Bootstrapped fully-typed Pydantic schemas handling bidirectional relationships (Header 1:N Items) in schemas/procurement.py.
- Wired backend CRUD router mapping to /api/v1/procurement/requests integrating native sequence generators (PR-YYYY-00000X).

---

## 2026-08-19 - Wave 9 Execution: Request for Quotation (RFQ)
- Built the complex multi-stage RFQ and Sourcing models in ackend/app/models/rfq.py.
- Enforced Architectural Principle INV-3.1 ensuring RFQ, Quote, and Award entities strictly isolate themselves from the Inventory Ledger.
- Modeled SupplierRFQResponse and SupplierQuoteItem to act as immutable financial snapshots (handling exchange rates and quote currencies independent of the live master data).
- Engineered the core logic for the Evaluation Engine via Enums like RFQEvalCriteria.LOWEST_LANDED_COST.
- Generated and correctly applied PostgreSQL migration 64d6ac9e5b49 to safely register these 7 new relational tables.
- Deployed /api/v1/rfq router and strict Pydantic schemas enforcing zero-drift validation between PR items and RFQ sourcing.

---

## 2026-08-19 - Wave 10 Execution: Purchase Orders (SPO)
- Developed robust formal SupplierPurchaseOrder and SupplierPurchaseOrderItem tables in ackend/app/models/spo.py.
- Formatted linkage capabilities directly to RFQAward allowing 1:1 tracebacks from Market Sourcing to actual Purchasing commitments.
- Implemented financial snapshots including exchange_rate, subtotal, 	ax_amount, and 	otal_amount ensuring absolute static historical accuracy against fluctuating supplier pricing.
- Captured Fulfillment tracking vectors (
eceived_quantity) mirroring exactly into later GRN architecture.
- Added API endpoints with standard sequential generation (SPO-YYYY-00000X).
- Pushed and validated PostgreSQL Alembic migration 345906985988.

---

## 2026-08-19 - Wave 11 Execution: Goods Receipt Notes (GRN)
- Engineered physical fulfillment architecture via GoodsReceiptNote and GRNItem schemas natively within ackend/app/models/grn.py.
- Formally executed Rule 2.1 via three tracking vectors: quantity_received, quantity_accepted, and quantity_rejected ensuring precise tracking of damaged bounds before injection into live inventory.
- Created GRNStatus ENUM (DRAFT, RECEIVED, INSPECTED, POSTED) mapping exactly to physical warehouse operational flows.
- Bound items explicitly to warehouse_bins and supplier_purchase_order_items guaranteeing exact traceback to the legal PO execution limits.
- Generated and validated 2a98d90a2f79 Alembic PostgreSQL migration.
- Secured the /api/v1/grn Router to automatically validate that ccepted + rejected == received natively inside the POST controller.

---

## 2026-08-19 - Wave 12 Execution: General Navigation & Dashboard Polish
- Engineered cross-modular data aggregation endpoint /api/v1/dashboard/stats.
- Queried active states across Invoice, ProcurementRequest, RFQ, and GoodsReceiptNote simultaneously utilizing high-efficiency unc.count and unc.sum groupings natively in SQLAlchemy.
- Exposed holistic business health metrics: Total Receivables (AED), Pending Internal Demand, Active Market Sourcing volume, and Pending Inbound QA constraints.

## E2E Testing Bug Fixes (Wave 12)

- **Fixed InvoiceStatus ENUM mismatch**: The backend dashboard endpoint was incorrectly filtering InvoiceStatus.VOID (which didn't exist) instead of InvoiceStatus.CANCELLED.
- **Fixed property conversion to DB schema issue**: Fixed unc.sum(Invoice.balance_due) crashing asyncpg because alance_due and mount_paid are python properties and cannot be implicitly translated directly into SQL aggregate functions. Handled this using python-side evaluation over a query loaded with selectinload.

### Task 4E-4K: SPO Implementation
- Implemented `backend/app/schemas/spo.py` for pydantic models based on latest architecture.
- Created `backend/app/services/spo_service.py` to handle state machine transitions and core logic.
- Implemented `backend/app/routers/spo.py` for API endpoints.
- Added basic test scaffold in `backend/tests/test_spo.py`.
- Tested the code. All implementations comply with the new SPO requirements.

### Task 4M-4N: SPO E2E Testing (Wave 13)
- Fixed critical MissingGreenlet serialization errors in spo_service.py caused by lazy-loaded relationships inside async session commits by refactoring the methods to eagerly fetch items before returning to FastAPI.
- Authored ackend/tests/test_e2e_spo.py simulating the exact flow: Award -> SPO -> partial ack -> price amendment -> multi-GRN -> short-close remainder -> invoice match -> closed.
- Built robust test database initialization fixtures that cleanly create Suppliers, Warehouses, Products, and UOMs directly via the test client to fulfill PostgreSQL strict foreign key constraints.
- Validated E2E test passes cleanly using the invoicesaas_test PostgreSQL sandbox.
- **Wave 13 (Step 4) is fully completed.**

## 2026-08-20 - Wave 14/15 Execution: GRN Module
- Created/updated GRN schemas in app/schemas/grn.py to match the architecture specs for DTOs.
- Authored the core GRN Service layer in app/services/grn_service.py to execute disposition logic and stock posting.
- Validated atomic stock posting using SELECT FOR UPDATE on InventoryLevel (Task 5I).
- Configured tolerance bounds calculation and hook placeholder for Auto-PurchaseReturn drafting.
- Added API routes to app/routers/grn.py that consume the service layer.
- Authored a comprehensive E2E GRN testing suite in backend/tests/test_grn.py that validates the GRN state lifecycle.


### Task 5M-5N: GRN E2E Testing (Wave 15)
- Fixed MissingGreenlet serialization errors across the GRN router (create_grn, update_grn, start_receiving, cancel_grn, and ecord_disposition) and SPO router (get_spo) by replacing session.refresh() with explicit selectinload queries.
- Fixed IntegrityError caused by a PostgreSQL CHECK constraint (quantity_received = quantity_accepted + quantity_damaged + quantity_rejected) on GRNItem during insertion by temporarily setting quantity_accepted = quantity_received when items are added during receiving.
- Created `backend/tests/test_e2e_grn.py` to simulate the exact physical flow: SPO ACKNOWLEDGED → GRN (2 tranches, mixed disposition) → damaged reclass → rejected auto-return → SPO reconciliation reflects all.
- The test validates that the final SPO tracking variables (quantity_received, quantity_accepted, quantity_damaged_rejected) mathematically reflect both GRN tranches perfectly.
- Verified all E2E tests pass locally.
- **Wave 14/15 (Step 5) is fully completed.**

---

## 2026-08-24 — Application Stabilisation Fix Session (Groups 1–7)

### Group 1: main.py Cleanup ✅
- Rewrote `backend/app/main.py` completely
- All imports moved to top (resolved E402 violations per CLAUDE.md)
- Removed duplicate `dashboard_router` registration (was at lines 155 AND 165)
- Removed mid-file duplicate router block (`clients_router`, `health_router`, `invoices_router`, `payments_router`)
- All 15 routers now registered cleanly under `# Routers` section

### Group 2: Test DB Setup Fix ✅
- Fixed `backend/tests/test_auth.py`: Changed `async def setup_database()` to sync using `asyncio.run()` — tables were never created before
- Fixed `backend/tests/test_e2e_spo.py`: Same async→sync fixture fix (line 40)
- Added `from app.models import *` wildcard import so SQLModel.metadata is populated before `create_all`

### Group 3: GRN Test Failures ✅
- Fixed `backend/tests/test_grn.py`:
  - Corrected SPO route from `/api/v1/spo` to `/api/v1/spos/` (missing trailing slash + wrong prefix)
  - Added workspace_id query param to SPO create call
  - Added SPO state machine transitions (submit-approval → approve → send) before GRN creation
  - Added warehouse bin creation step (required for GRN stock posting)
  - Introduced module-level `_MODULE_TOKEN` / `_MODULE_WS_ID` cache to avoid hitting rate limiter (5/min) on `/auth/register` across two test functions
- Fixed `backend/tests/test_e2e_grn.py`: Replaced asyncio.run bin-creation DB hack with proper API call to new `/inventory/warehouses/{id}/bins` endpoint

### Group 4: SupplierInvoice float→Decimal Migration ✅
- Rewrote `backend/app/models/supplier_invoice.py`: All monetary fields now use `Decimal` with `Numeric(12,2)` SA columns; quantity fields use `Numeric(12,4)`
- Rewrote `backend/app/schemas/supplier_invoices.py`: All float types replaced with Decimal; migrated to ConfigDict
- Rewrote `backend/app/services/supplier_invoice_service.py`: Removed all `float()` cast workarounds; pure Decimal arithmetic; removed debug print statements
- Generated and applied Alembic migration `12bdad2ae924_fix_supplier_invoice_decimal_types.py` (16 column type changes: DOUBLE_PRECISION → Numeric)
- Fixed test assertion: `float(matched_inv["items"][0]["variance_quantity"]) == 20.0` since DB returns Decimal as string

### Group 5: Frontend Routes ✅
- `frontend/src/App.tsx`: Added missing routes:
  - `<Route path="supplier-invoices" element={<SupplierInvoices />} />`
  - `<Route path="supplier-invoices/:id" element={<SupplierInvoiceDetail />} />`
- `frontend/src/components/Layout.tsx`: Added AP Payables link (`/supplier-invoices`) and GRN link to Purchasing & Suppliers nav group; cleaned up Inventory Management group

### Group 6: Missing Architecture Docs ✅
- Created `architecture/entity-relationship.md`: Full Mermaid ERD for all 30+ entities
- Created `architecture/api-contracts.md`: Complete endpoint reference for all 15 routers
- Created `architecture/edge-cases.md`: 28 edge cases across procurement, inventory, products, finance, security — each with implementation status
- Created `architecture/procurement-rules.md`: PR/RFQ/SPO/GRN/3-Way Match business rules; document number formats; conflict register

### Group 7: Pydantic V2 ConfigDict Migration ✅
- Migrated all 12 schema files from deprecated `class Config: from_attributes = True` to `model_config = ConfigDict(from_attributes=True)`:
  - `clients.py`, `invoices.py`, `payments.py`, `workspaces.py`, `products.py`, `suppliers.py`, `inventory.py`, `procurement.py`, `rfq.py`, `spo.py`, `grn.py`, `supplier_invoices.py`
- Fixed `spo.py` which had both `class Config` AND `model_config` simultaneously (PydanticUserError crash)

### New Feature: Warehouse Bin Endpoint ✅
- Added `POST /api/v1/inventory/warehouses/{warehouse_id}/bins` — required for GRN stock posting
- Added `GET /api/v1/inventory/warehouses/{warehouse_id}/bins` — list bins in a warehouse
- Made `WarehouseBinCreate.warehouse_id` Optional (derived from URL path param)

### Final Test Results ✅
```
9 passed, 0 failed
- tests/test_auth.py::test_health_check         PASSED
- tests/test_auth.py::test_root                 PASSED
- tests/test_auth.py::test_register_and_login   PASSED
- tests/test_e2e_3way_match.py::test_3way_match_engine PASSED
- tests/test_e2e_grn.py::test_e2e_grn_complex_flow PASSED
- tests/test_e2e_spo.py::test_e2e_spo_flow     PASSED
- tests/test_grn.py::test_grn_lifecycle         PASSED
- tests/test_grn.py::test_grn_cancellation      PASSED
- tests/test_spo.py::test_create_spo            PASSED
```

---

## 2026-08-31 — WP-1 Product Master API (planned BEFORE product code)

**Spec:** `architecture/wave-3-product-master-addendum.md` (full) + mvp-sequence §5 WP-1 AC.
**Locked:** no Alembic (HEAD stays `06c9b4b1dcda`); no `models/product.py` edits; no payment/PDC PUT; no frontend; no git commit.

### Files to change

| File | Action |
|---|---|
| `backend/app/services/product_service.py` | **Create.** All uniqueness, 404 isolation, conversion/VAT/price/UOM rules. No commit. HTTPException 400/404/409. |
| `backend/app/schemas/products.py` | **Expand.** Category/Brand/UOM/Product Create+Update+Response; ProductDetailResponse; Identifier/Conversion/Price Create+Response. Decimal never float. Enum allow-lists. `extra="forbid"` on write bodies (rejects `from_uom_id`, `hs_code`, electrical keys → 422). |
| `backend/app/routers/products.py` | **Rewrite.** HTTP only; prefix `/products`. Static `/categories`, `/brands`, `/uom` before `/{product_id}`. POST 201. DELETE 200 `{success:true, data:null}`. Lists = `PaginatedResponse`. Nested child GET lists = unpaginated `SuccessResponse[list]`. Router commits after service. |
| `backend/app/services/__init__.py` | Export `ProductService` (project pattern). |
| `backend/tests/test_products.py` | **Create.** PostgreSQL `invoicesaas_test` harness matching isolation tests. Cases per addendum §13. |
| `backend/tests/test_multi_tenant_isolation.py` | Extend product section: B cannot GET/PUT/DELETE A's product **or children** (404). |

### Business rules to encode in service (not router)

- JWT `workspace_id` only; query `workspace_id` ignored.
- Cross-tenant / missing / soft-deleted parent → **404**, never 403.
- Category/Brand duplicate `name` among non-deleted → 409 (no new unique constraint).
- Category circular / self parent → 400.
- UOM/SKU uniqueness: live unique constraints include deleted rows → 409; **do not reuse SKU** after soft-delete.
- Soft-delete UOM blocked (400) if referenced by non-deleted `Product.base_uom_id` or any `ProductUOMConversion.to_uom_id`.
- PUT product `base_uom_id` while conversions exist → 400.
- Conversion: implied from = `Product.base_uom_id`; persist `to_uom_id` + `conversion_factor` Numeric(14,6); `to_uom_id == base` → 400; factor `> 0`; no `from_uom_id`.
- Identifier types allow-list: MPN, BARCODE, SUPPLIER_CODE, EAN, UPC, CUSTOMER_CODE.
- Prices: DEFAULT_SALES (one per product, no client/min_qty), TIER_1 (min_quantity > 0), CUSTOMER_SPECIFIC (client_id required, same workspace). Currency AED only. Decimal(12,2).
- Product `tax_rate` optional; if set 0–100; null = inherit workspace later (do not copy 5.00).
- Category/Brand/UOM/Product: soft `deleted_at`. Identifier/conversion/price: hard DELETE.
- Lists exclude `deleted_at IS NOT NULL`. Product list: no default `is_active` filter; optional `search` / `category_id` / `brand_id` / `is_active`.
- GET product by id: `ProductDetailResponse` with identifiers/conversions/prices; **no** stock embed. Children loaded by query (models have no Relationship — will not edit `product.py` to add `selectinload`).

### Out of scope (will not touch)

Alembic, `models/product.py`, payments/PDC PUT, frontend, WP-2/WP-3, quotations, FTA PDF, invoice `product_id`.

### Verification after implement

`pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` from `backend/` against PostgreSQL. black + ruff. No `Float` in new schema fields. No `print()`.

---

## 2026-08-31 — WP-1 Product Master API (implemented)

### Done

- `backend/app/services/product_service.py` — all WP-1 rules; no commit; conversion semantic in module docstring.
- `backend/app/schemas/products.py` — Create/Update/Response + detail/children; Decimal; Enum allow-lists; `extra="forbid"`.
- `backend/app/routers/products.py` — HTTP only; static routes first; POST 201; DELETE `{success:true, data:null}`; `PaginatedResponse` lists; unpaginated child GETs.
- `backend/app/services/__init__.py` — exports `ProductService`.
- `backend/tests/test_products.py` — PostgreSQL `_test` harness; addendum §13 cases.
- `backend/tests/test_multi_tenant_isolation.py` — B cannot GET/PUT/DELETE A's product or identifier/conversion/price (404).
- `backend/tests/test_e2e_spo.py`, `test_e2e_grn.py`, `test_e2e_3way_match.py` — accept 201; drop extra keys (`type`, `base_currency`) that are now 422.

Untouched: Alembic, `models/product.py`, payments/PDC PUT, frontend.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_products.py` + `tests/test_multi_tenant_isolation.py`: **20 + 5 = 25 passed, 0 failed.**

Related existing suite after e2e payload alignment: **32 passed** (includes spo/grn/e2e).

black + ruff clean on WP-1 files.

### Deviation (with evidence)

Addendum asked for `selectinload` on GET product. `Product` in `models/product.py` has **no SQLAlchemy `Relationship`** to identifiers/conversions/prices, and WP-1 forbids editing that model. Children are loaded with three scoped `select` queries instead. Response shape is unchanged (`identifiers` / `conversions` / `prices`, no stock).

---

## 2026-08-31 — WP-1 review nits W1–W6 (planned BEFORE code)

**Spec:** `.agents/reports/wp1-product-api-review.md` (APPROVE_WITH_NITS).
**Locked:** backend only; no frontend; no Alembic; no `models/product.py`; no payment/PDC; no git commit.

### Files to change

| File | Action |
|---|---|
| `backend/app/services/product_service.py` | W1: on product soft-delete, hard-delete identifier/conversion/price rows in the same call. Nested child DELETE still 404 via `_require_live_product`. W2: `_assert_acyclic_parent` 404 only on **immediate** parent (`_get_live`); further ancestors load without 404, deleted/missing = end-of-chain, still detect cycles among live nodes. W4: keep live-product conversion block (no code change). |
| `backend/tests/test_products.py` | W1 MPN reuse after soft-delete; nested child DELETE 404 after parent delete. W2 A←B←C, delete B, POST `parent_id=C` → 201. W4 DELETE BOX used as conversion `to_uom` → 400. W5: circular/self parent 400; brand duplicate 409; list without `is_active` includes inactive; duplicate TIER_1 same min_qty 409; same MPN on two live products 409; INTERNAL_SKU 422; PUT extra key 422; omit tax_rate → GET null. |
| `backend/tests/test_multi_tenant_isolation.py` | W3: token B + `?workspace_id=<A's uuid>` on GET/PUT/DELETE product **and one child** still 404. Category/brand/UOM cross-tenant 404. POST identifier/conversion/price as B on A's product_id → 404. |

### W6 (document-only, no code)

WP-1 `DEFAULT_SALES` / price uniqueness is service-only (pre-check then insert). Concurrent POSTs can both pass the SELECT until a later unique index. Accept this race for WP-1; catch-IntegrityError is a no-op until Alembic adds a unique. Not P0.

### Verification

`pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` from `backend/` against PostgreSQL `_test`. black + ruff. No Alembic. No `models/product.py` edit.

---

## 2026-08-31 — WP-1 review nits W1–W6 (implemented)

### Done

- W1: `delete_product` hard-deletes identifier, conversion, and price rows via `_hard_delete_children` before setting `deleted_at`. Nested child DELETE still 404s (`_require_live_product`). Test: MPN reused on a new product after soft-delete.
- W2: `_assert_acyclic_parent` 404s only on the immediate parent (`_get_live`). Further ancestors use `_load_category_maybe`; deleted/missing ends the walk; live-node cycles still 400. Test: A←B←C, delete B, POST `parent_id=C` → 201.
- W3: isolation uses token B + `?workspace_id=<A's uuid>` on product GET/PUT/DELETE and one child; category/brand/UOM cross-tenant 404; POST identifier/conversion/price as B on A's product_id → 404.
- W4: live-product conversion block unchanged. Test: conversion `to_uom=BOX` (not base) → DELETE BOX → 400.
- W5: circular/self parent 400; brand duplicate 409; list without `is_active` includes inactive SKUs; duplicate TIER_1 same min_quantity 409; same MPN on two live products 409; INTERNAL_SKU 422; PUT extra `hs_code` 422; omit tax_rate → GET null.

Untouched: Alembic, `models/product.py`, payments/PDC PUT, frontend.

### W6 (accepted, no code)

WP-1 price uniqueness (`DEFAULT_SALES` / TIER_1 / customer) is service-only until a later unique index. Concurrent POSTs can both pass the SELECT; catch-IntegrityError is a no-op without a DB unique. Accept this race for WP-1; not P0.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_products.py` + `tests/test_multi_tenant_isolation.py`: **29 + 5 = 34 passed, 0 failed.** black + ruff clean.

---

## 2026-08-31 — WP-A FTA Tax Invoice API (planned BEFORE code)

**Spec:** `architecture/wave-fta-tax-invoice-addendum.md` + `.agents/reports/architect-fta-tax-invoice-note.md`.
**Locked:** API + Alembic + pytest only. No frontend/PDF/Playwright/Arabic/IBAN/Net terms/quotes/LPO. No rewrite of `d3e4c7fdb29f` or ancestors. `down_revision = "06c9b4b1dcda"`.

### Files to change

| File | Action |
|---|---|
| `backend/app/models/workspace.py` | Add nullable `address` Text. No IBAN. |
| `backend/app/models/invoice.py` | Add `supply_date`, `invoice_kind`, seller/buyer name-address-TRN snapshots. |
| `backend/app/models/invoice_item.py` | Add optional `product_id`/`uom_id`/`sku_snapshot`, discounts, `line_net`, line `tax_amount`. Keep `total_price` as gross. |
| `backend/alembic/versions/<rev>_fta_tax_invoice_fields.py` | New revision from HEAD `06c9b4b1dcda`. Backfill `supply_date=issue_date`; backfill line net/VAT/gross. No `clients.trn`. |
| `backend/app/schemas/invoices.py` | FTA fields; `extra="forbid"`; AED-only write; optional `product_id`/`tax_rate`/`supply_date`; XOR line discounts; response snapshots + `amount_paid`/`balance_due`. |
| `backend/app/schemas/workspaces.py` | `address` on GET/PUT `/workspaces/me`. |
| `backend/app/schemas/clients.py` | Optional `trn` validation_alias writing `tax_id`. No new column. |
| `backend/app/schemas/common.py` | `ErrorCode.FTA_SEND_BLOCKED`, `NO_LIST_PRICE`. |
| `backend/app/services/invoice_service.py` | `money()` ROUND_HALF_UP per line; tax inherit product then workspace 5%; catalog copy; `assert_fta_sendable`; freeze snapshots; PUT item-replace math; HTTPException not ValueError 500. |
| `backend/app/routers/invoices.py` | HTTP only; `selectinload` items+payments; call service send/update. |
| `backend/app/main.py` | Unwrap `ErrorDetail` dict so `error.code`/`error.field` surface. |
| `backend/tests/test_invoices.py` | New PostgreSQL `_test` suite covering addendum §11. |
| `backend/tests/test_multi_tenant_isolation.py` | FTA workspace/client fields before send in `test_payment_is_workspace_isolated`; PUT isolation 404. |

### Math (service-owned)

`line_net = money(qty×price − discount)`; `line_vat = money(line_net × tax_rate/100)`; `total_price = line_net + line_vat` (gross). Header `subtotal = Σ line_net`. Omitted `tax_rate` → product.tax_rate else workspace `default_tax_rate` (5.00). Explicit `0` stays 0. Header discount deferred (extra key 422).

### Send hard-fails (400 `FTA_SEND_BLOCKED`)

AED; workspace TRN `^100[0-9]{12}$`; workspace address non-empty. STANDARD if client TRN valid or total > 10000 → also client `tax_id` + address. SIMPLIFIED otherwise. Snapshots frozen on send. Drafts save without TRN. 403 remains INVALID_STATE for non-DRAFT.

### Verification

`pytest tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py` from `backend/` against PostgreSQL `_test` (never SQLite). `alembic upgrade head` then `alembic check`. black + ruff.

---

## 2026-08-31 — WP-A FTA Tax Invoice API (implemented)

**Alembic revision:** `c8e1a4f2b6d0` (`down_revision = "06c9b4b1dcda"`). `alembic upgrade head` + `alembic check` clean on `invoicesaas` and `invoicesaas_test` (host 5434). Never rewrote `d3e4c7fdb29f`.

### Done

- Models: `workspaces.address`; invoice `supply_date` / `invoice_kind` / seller+buyer snapshots; line `product_id` / `uom_id` / `sku_snapshot` / discounts / `line_net` / `tax_amount`. No `clients.trn`. No IBAN.
- `InvoiceService`: `money()` ROUND_HALF_UP per line; omitted tax_rate → product then workspace 5.00; optional `product_id` catalog copy; FTA send hard-fails `FTA_SEND_BLOCKED` + snapshots; PUT item-replace math in service.
- Router HTTP-only; GET `selectinload` items+payments; `amount_paid`/`balance_due` on response.
- Workspace GET/PUT `/workspaces/me` includes `address`. Client `trn` alias writes `tax_id`.
- Exception handler unwraps `ErrorDetail` so `error.code` / `error.field` surface.
- Tests: `tests/test_invoices.py` (addendum §11) + isolation send FTA fixture + PUT 404 + overpay 400.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_invoices.py` + `tests/test_multi_tenant_isolation.py` + `tests/test_concurrent_numbering.py`: **22 + 5 + 4 = 31 passed, 0 failed.**

black + ruff clean on WP-A files.

### Out of WP-A (deferred, as locked)

Frontend, PDF “Tax Invoice”, Playwright, Arabic, Net 30/45/60, quotes/LPO, IBAN, header discount column, payment PUT.

---

## 2026-08-31 — WP-A FTA review warnings (planned BEFORE code)

**Spec:** `.agents/reports/wp-a-fta-tax-invoice-review.md` (W1, W3, W5) + `architecture/wave-fta-tax-invoice-addendum.md` §3/§6/§10.
**Locked:** backend only. No frontend. No Alembic rewrite of `c8e1a4f2b6d0`. No historical SENT PDF backfill (W2 = WP-B). No payment PUT. No SQLite. No new product features.

### Must fix

| # | Review | Action |
|---|---|---|
| W5 | `mark_as_sent` skips FTA | Call `assert_fta_sendable` + freeze snapshots inside `mark_as_sent`. `send_invoice` delegates so a future caller cannot skip FTA. |
| W1 | SIMPLIFIED may snapshot invalid / >15-char `client.tax_id` | Snapshot `buyer_trn_snapshot` only if `_is_valid_trn` (`^100[0-9]{12}$`); else `None`. Same shape as seller TRN. |
| W3 | STANDARD send + snapshot immutability untested | Add pytest: STANDARD 200 + snapshots; after send PUT invoice blocked and live workspace/client PUT does not change GET snapshots; SIMPLIFIED does not persist garbage `tax_id`. |

### Files to change

| File | Action |
|---|---|
| `backend/app/services/invoice_service.py` | W5: FTA + freeze in `mark_as_sent`. W1: buyer TRN snapshot only if valid FTA TRN. |
| `backend/tests/test_invoices.py` | STANDARD send success; snapshot immutability; SIMPLIFIED garbage `tax_id` → null snapshot. |

### Out of this follow-up

W2 migration header-total backfill, W4 catalog tax inherit / `NO_LIST_PRICE` tests, W6 `void_invoice` ValueError, W7 response currency enum, Alembic rewrite, payment PUT, frontend.

### Verification

`pytest tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` from `backend/` against PostgreSQL `_test`. black + ruff. No git commit.

---

## 2026-08-31 — WP-A FTA review warnings (implemented)

**Spec:** W1 / W3 / W5 from `.agents/reports/wp-a-fta-tax-invoice-review.md`. Alembic `c8e1a4f2b6d0` not rewritten. Payment PUT untouched.

### Done

- W5: `InvoiceService.mark_as_sent` now calls `assert_fta_sendable` then `_apply_send_snapshots` (kind + freeze) before DRAFT→SENT. `send_invoice` delegates to `mark_as_sent` so a future caller cannot skip FTA.
- W1: `_snapshot_trn` writes `buyer_trn_snapshot` / `seller_trn_snapshot` only when the value matches `^100[0-9]{12}$` (spaces stripped); otherwise `None`. Invalid / >15-char `client.tax_id` is not persisted on SIMPLIFIED send.
- W3: STANDARD send 200 with snapshots; after send invoice PUT is blocked (`INVALID_STATE`) and live workspace/client PUT does not change GET snapshots; SIMPLIFIED send with garbage `tax_id` leaves `buyer_trn_snapshot` null.

### Files changed

- `backend/app/services/invoice_service.py`
- `backend/tests/test_invoices.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_invoices.py` + `tests/test_multi_tenant_isolation.py` + `tests/test_concurrent_numbering.py`: **25 + 5 + 4 = 34 passed, 0 failed.**

black + ruff clean on changed Python files.

### Untouched (as locked)

Alembic `c8e1a4f2b6d0`, historical SENT PDF/header backfill (W2/WP-B), payment PUT, W4/W6/W7, frontend, SQLite.
