# WP-A PDC truth — code review

**Date:** 2026-09-01
**Scope:** API + pytest only (`architecture/wave-pdc-addendum.md`, `.agents/reports/architect-pdc-note.md`)
**No UI. No git commit. WP-B not started.**

## Verdict

**APPROVE_WITH_NITS** on the current tree.

Originally shipped code was **BLOCK** on P0: historical `SUCCESS` + `pdc_status=RECEIVED` rows (the live pre-WP shape) could be **un-SUCCESS’d** via `POST .../pdc/return` (single call) or `deposit` then `bounce`. That path is patched in this review. Remaining items are nits. **WP-B may start.**

## P0s

### Remaining

None.

### Found in shipped WP-A, patched during review

**Severity: critical (P0 — bounce/return un-SUCCESS)**

`PdcService.return_cheque` treated any `pdc_status=RECEIVED` as returnable and set `status=CANCELLED`. Addendum §0 and §6 say tests/DB already have PDC with `status=SUCCESS` while the frontend often stored `RECEIVED`. `/pdc/return` on that row dropped the payment out of `amount_paid` and could un-PAID the invoice. Amount was not rewritten, but money identity (SUCCESS cash) was reversed.

`deposit` also accepted `SUCCESS`+`RECEIVED` and moved `pdc_status` to `DEPOSITED` without touching `status`. A following `/pdc/bounce` then set `FAILED` — the CLEARED→bounce hole by another door.

Happy-path bounce of **PENDING** deposited PDC → `FAILED` was already correct (never SUCCESS). PUT 405, insert PENDING, over-clear 400, isolation 404, no Alembic, no float were already fine.

**Patch (in-review):** `_cleared_already` (`CLEARED` or `status=SUCCESS` + method PDC) now **403 `INVALID_STATE`** on deposit, bounce, and return. Deposit/return also require `PENDING`. Clear remains **200 no-op**. Regression assertions in `test_illegal_transitions_403`.

## Checklist

| # | Lock | Result |
|---|---|---|
| 1 | Isolation 404 never 403 (PDC POSTs + PUT, other-ws invoice) | **Pass.** Invoice `id`+`workspace_id` then payment `id`+`invoice_id`. MEMBER 403 only after lock. Tests: `test_isolation_pdc_actions_404`, `test_put_405_other_workspace_404`. |
| 2 | Decimal `money()`; never float; `FOR UPDATE` invoice+payment | **Pass** with nit. `Numeric(12,2)`; `balance_due` already `quantize(0.01)`; no `float`. `_lock_invoice` then `_lock_payment` both `with_for_update()`. PdcService does not call `money()` itself. |
| 3 | Amount/method/dates never UPDATE; no DELETE | **Pass.** Transitions write `status` / `pdc_status` / `updated_at` only. No payment DELETE route (`session.delete` is idempotency-key TTL only). |
| 4 | PDC insert PENDING; does not reduce `balance_due`; not PAID | **Pass.** `_insert_status`; body `pdc_status=CLEARED` ignored. CHEQUE/CASH/BANK/CARD still SUCCESS. |
| 5 | `pdc_date` required 422; ignore body `pdc_status`; `utc_today()` deposit gate | **Pass.** 422 `VALIDATION_ERROR` `field=pdc_date`. Deposit compares `pdc_date` to `CreditControlService.utc_today`. |
| 6 | Clear SUCCESS + `update_status_from_payments`; over-clear 400; `credit_balance` unchanged | **Pass.** No `credit_balance` writes in payment/PDC services. |
| 7 | Bounce FAILED not PENDING; evaluate; amount unchanged | **Pass.** `CreditEventReason.PAYMENT`. Historical SUCCESS bounce 403. |
| 8 | Return CANCELLED from RECEIVED only | **Pass** after patch (RECEIVED **and** PENDING; SUCCESS 403). DEPOSITED → 403. |
| 9 | Illegal 403 `INVALID_STATE`; MEMBER 403 `INSUFFICIENT_PERMISSIONS`; MEMBER POST payment | **Pass.** `_require_owner_admin` on all four POSTs; create payment is any JWT. |
| 10 | Idempotency-Key on create; four POSTs without; idempotent 200 on target | **Pass.** Deposit/clear/bounce second-call covered. Return second-call not asserted (nit). |
| 11 | Historical SUCCESS PDC left; clear 200 no-op | **Pass.** Amount unchanged. Deposit/return/bounce 403 after patch. |
| 12 | No Alembic; PUT 405 wrapper | **Pass.** `alembic heads` = `b8d5f0c3a216`. No new revision file. PUT: workspace invoice 404 then 405 `METHOD_NOT_ALLOWED` wrapper. |
| 13 | AR statement not forked; `test_success_pdc_in_paid` patched | **Pass.** `ArStatementService` has no PDC-specific math. Test is deposit+clear. |
| 14 | Tests hit PostgreSQL; assertions match | **Pass.** `postgresql+asyncpg` `…/invoicesaas` → `invoicesaas_test` (port 5434). `test_pdc.py` 17 + `test_ar_statement.py` 13 = **30 passed** after patch. |

## Nits

1. **PUT parses `PaymentUpdate` before 405.** Invalid enum/body can 422 instead of 405. Handler still does not apply the body (`del payment_data`).
2. **`record_payment(..., pdc_status=)` is unused.** Router still forwards it; `_insert_status` ignores it (correct). Dead parameter.
3. **`create_payment` still has a `except ValueError` branch.** Overpay/404 now raise `HTTPException` via `raise_error`; that branch is leftover.
4. **`PaymentCreate.payment_date` uses `date.today()`,** not `utc_today()`. Deposit gate is UTC; payment-date-not-future can disagree near midnight.
5. **Return idempotent 200** (already `RETURNED`) is unspecified in tests. Spec §3.1.
6. **MEMBER 403** is asserted on `/pdc/clear` only (matches §12.15). Deposit/bounce/return share `_ready` so they 403 too; not re-tested.
7. **Bounce `evaluate` has no `flush` before credit snapshot.** PENDING vs FAILED are both non-SUCCESS, so exposure is unchanged; still sloppy.
8. **Tests `SQLModel.metadata.create_all`** on Postgres `_test` (repo convention), not `alembic upgrade`. Production HEAD is still asserted via `alembic heads` / `alembic check` inside `test_fta_cn_hold_overpay_alembic`.
9. **`test_fta_cn_hold_overpay_alembic`** covers overpay + CN issue on HOLD + Alembic; FTA send is only via `_sent_invoice`, not a dedicated FTA assertion.
10. **`list_payments` mid-file `from sqlalchemy import func`** (pre-existing E402 vs CLAUDE.md). Not introduced as logic.

Not P0 / not blocking WP-B: no tenant 403 leak, no float money, no new Alembic, PUT does not mutate, over-clear does not park `credit_balance`, new PDC insert is not SUCCESS.

## WP-B

**Yes — WP-B may start** on this tree (P0 patch included, pytest 30 green).

UI must treat historical `SUCCESS` PDC as cash (clear no-op). Do not show Return/Deposit/Bounce on SUCCESS. MEMBER: hide actions; API 403 if called.
