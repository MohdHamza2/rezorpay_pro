# WP-A–C PDC truth — code review

**Date:** 2026-09-01
**Scope:** Full slice vs `architecture/wave-pdc-addendum.md`, `.agents/reports/wp-a-pdc-review.md`, `.claude/CLAUDE.md`.
**Review only.** No features. No git commit.

## Verdict

**APPROVE_WITH_NITS**

No remaining P0s from the lock list (SUCCESS-on-insert, PUT money mutate, bounce/return un-SUCCESS of historical cash, over-clear parking `credit_balance`, tenant 403 leak, Python float money, new Alembic). WP-A historical-SUCCESS patch is still in API and UI. Slice **may be committed when asked**.

This review did not re-run pytest or Playwright. File counts match the claim (`test_pdc.py` 17, `test_ar_statement.py` 13, Playwright `test(` = 22). `alembic heads` = **`b8d5f0c3a216`**. `alembic check` = no new upgrade operations.

## P0s

### Remaining

None.

### Preserved from WP-A (must stay)

Historical `SUCCESS` + `pdc_status=RECEIVED` (pre-WP live shape):

| Path | Lock |
|---|---|
| `/pdc/clear` | 200 no-op; amount unchanged; no `pdc_status` backfill |
| `/pdc/deposit`, `/bounce`, `/return` | **403 `INVALID_STATE`** (`_cleared_already` + PENDING required on deposit/return) |
| UI | `isPdcCash` treats `status=SUCCESS` or `CLEARED` as cash; **no** Deposit / Bounce / Return / Clear |

Happy-path bounce of **PENDING** deposited PDC still sets `FAILED` (never was SUCCESS). PUT still 405. Insert still PENDING+RECEIVED.

## Checklist

| # | Lock | Result |
|---|---|---|
| 1 | Isolation **404** not 403 (API + Playwright); own PUT **405** | **Pass** with nit. Invoice `id`+`workspace_id` then payment `id`+`invoice_id`. MEMBER 403 only after lock. Playwright B on A’s ids → 404, not 403. Own PUT pytest = 405 wrapper. Playwright own PUT allows **422** as well as 405 (body parsed first). |
| 2 | Decimal; amount never rewritten; no DELETE | **Pass.** `Numeric(12,2)`; `balance_due` quantize; no `float(` in payment/PDC services; no `.amount =`; PUT does not apply `PaymentUpdate`; no payment DELETE route. |
| 3 | Future PDC does not PAID; CHEQUE/CASH still SUCCESS | **Pass.** Insert always PENDING+RECEIVED (body `pdc_status` ignored). CHEQUE/CASH/BANK/CARD SUCCESS. E2E future stays SENT, amount_paid AED 0. |
| 4 | Clear SUCCESS + balance; bounce FAILED; return CANCELLED from RECEIVED+PENDING only | **Pass.** Clear: FOR UPDATE, `update_status_from_payments`. Bounce: FAILED + `evaluate(..., PAYMENT)`. Return: RECEIVED **and** PENDING; DEPOSITED → 403. |
| 5 | Historical SUCCESS: no deposit/bounce/return (UI + API 403) | **Pass.** API regression in `test_illegal_transitions_403`. UI `legalPdcActions` empty when `isPdcCash`. |
| 6 | Over-clear 400; `credit_balance` untouched | **Pass.** `/pdc/clear` uses `InvoiceService.calculate_balance_due`. No `credit_balance` writes in PDC/payment services. Pytest asserts parked credit unchanged and amount not rewritten. |
| 7 | MEMBER UI hides actions; API 403 | **Pass** (API tested; UI hide not in Playwright). `canManagePdc` OWNER/ADMIN only; `_require_owner_admin` → `INSUFFICIENT_PERMISSIONS`. MEMBER POST payment still 200. |
| 8 | Statement note §7; AR math not forked; statement E2E still CASH | **Pass.** `ArStatementService` still SUCCESS vs PENDING vs omit. `test_success_pdc_in_paid` is deposit+clear. `PDC_SUCCESS_NOTE` exact copy on ArStatement + PDF + preview. `ar-statement.spec.ts` still records **CASH**. |
| 9 | No Alembic; Idempotency-Key on create only | **Pass.** HEAD `b8d5f0c3a216`. `recordPayment` sends key; four PDC POSTs `{}` without it. Pytest: create requires key; deposit works without. |
| 10 | Playwright 22 including prior suites | **Pass on count / claimed run.** 22 `test(` across e2e (3 PDC happy + 1 isolation + 18 prior). WP-C report: 22 passed. Not re-executed here. |
| 11 | Wrapper errors; extra keys not POSTed on PDC actions | **Pass.** `raise_error` → `{success:false, error:{code,message}}`. `PdcActionRequest` `extra=forbid`. UI `postPdcAction(..., {})`; `paymentCreateBody` never sends `pdc_status`. |

## Nits

Carry-forward (WP-A) plus WP-B/C:

1. **PUT parses `PaymentUpdate` before 405.** Invalid enum/body can 422 instead of 405. Handler still `del`s the body. Playwright isolation **accepts 422** (`not 200`) for own PUT; pytest with `{status: FAILED}` is the real 405 lock.
2. **`record_payment(..., pdc_status=)` unused.** Router forwards it; `_insert_status` ignores it (correct).
3. **`create_payment` leftover `except ValueError`.** Overpay/404 already `raise_error`.
4. **`PaymentCreate.payment_date` uses `date.today()`;** deposit gate is `utc_today()`. Near-midnight UTC vs local can disagree. Playwright `isoDate()` is local `Date` — same latent flake for same-day deposit+clear.
5. **Return idempotent 200** (already `RETURNED`) not asserted. Spec §3.1.
6. **MEMBER 403** pytest only on `/pdc/clear`. Deposit/bounce/return share `_ready`. Playwright does not cover MEMBER hide.
7. **Bounce `evaluate` has no `flush`.** PENDING vs FAILED are both non-SUCCESS, so exposure is unchanged; still sloppy.
8. **Tests `SQLModel.metadata.create_all`** on Postgres `_test` (repo convention). Production HEAD asserted via `alembic heads` / `alembic check`.
9. **`list_payments` mid-file `from sqlalchemy import func`** (pre-existing E402).
10. **Statement E2E does not assert `statement-pdc-note`.** Copy is on the page; AR spec still CASH as required.
11. **UI `parseFloat(paymentAmount)`** on submit. Backend still Decimal. Not a Python-float money P0.
12. **Future RECEIVED shows Deposit** (API 400 date gate). WP-B plan allowed this; axios interceptor toasts the wrapper error.

Not P0: no tenant 403 leak, no float money in services, no new Alembic, PUT does not mutate, over-clear does not park `credit_balance`, new PDC insert is not SUCCESS, historical SUCCESS cannot be un-SUCCESS’d via deposit→bounce or return.

## Commit

**Yes — may be committed when asked.** Do not commit `.env`, caches, `frontend/dist`, or `.claude-flow` policy tmp files.

## Next UAE gap (do not implement)

1. **Volume pricing** (gap 8)
2. Then **bilingual PDF**
3. **Debit notes** stay later (not this next slice)
