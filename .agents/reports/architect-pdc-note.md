# Architect note — Payment / PDC truth + bounce (Gap 11 / Phase 9)

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-pdc-addendum.md`

## Alembic

**NO.** `paymentmethod` / `pdcstatus` / `pdc_date` already in `e217c0bc3af7`; `paymentstatus` in `13b9c7b44074`. No new tables or columns. Reuse `CreditEventReason.PAYMENT` and existing invoice events. HEAD stays **`b8d5f0c3a216`**. Later WPs `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR history.

## `record_payment` PDC

**All `method=PDC` inserts:** `status=PENDING`, `pdc_status=RECEIVED`, `pdc_date` required. Includes today/past cheques. Does **not** reduce `balance_due`. CASH / BANK / CARD / **CHEQUE** stay immediate SUCCESS (CHEQUE = cleared-on-receipt). Ignore body `pdc_status`. Compare dates to **`utc_today()`**.

Reason: T9 (not SUCCESS until CLEARED) + machine starts at RECEIVED. Paper’s “future only PENDING” is the minimum; CHEQUE is the one-step cash path.

## PUT

**405** `METHOD_NOT_ALLOWED` on `PUT /invoices/{id}/payments/{id}` (404 first if invoice not in workspace). Not 410. Amount/method/dates never updated. No DELETE.

## Four POSTs

```
POST /invoices/{invoice_id}/payments/{payment_id}/pdc/deposit|clear|bounce|return
```

RECEIVED→DEPOSITED (on/after `pdc_date`); DEPOSITED→CLEARED = SUCCESS + invoice FOR UPDATE; DEPOSITED→BOUNCED = **FAILED** (not PENDING); RECEIVED→RETURNED = **CANCELLED**. Illegal → **403** `INVALID_STATE`. Idempotent **200** if already in target (clear also 200 if historical SUCCESS PDC). OWNER/ADMIN; MEMBER **403** `INSUFFICIENT_PERMISSIONS`. No Idempotency-Key on these four.

**CLEARED→BOUNCED out** (use CN). Historical SUCCESS rows left as cash.

## Bounce HOLD

Recording PDC **never** blocked. Bounce **does** `CreditControlService.evaluate(..., PAYMENT)`. CN issue still not blocked. Do not force HOLD; use existing exposure rules.

## Over-clear

PENDING PDC does not consume `balance_due`, so CASH can still fill the invoice. `/pdc/clear` when `amount > balance_due` → **400** `PAYMENT_EXCEEDS_BALANCE`. **Do not** park `credit_balance` (that is CN unapplied credit). Never negative payment.

## AR statement

Do not fork math. New uncleared PDC = Payment (pending). After clear = Payment in `totals.paid`. Patch `test_success_pdc_in_paid`. Playwright statement already uses CASH.

## WP

- **A** API + `test_pdc.py`. No frontend. No Alembic.
- **B** invoice payment modal: pending until clear; deposit/clear/bounce/return for OWNER/ADMIN.
- **C** Playwright: future PDC stays SENT; deposit+clear pays; bounce leaves AR; isolation 404. Docker 8000 / Postgres 5434. Never SQLite.

Out: volume pricing, bilingual, debit notes, Peppol, WhatsApp, refunds, PUT amount, deleting payments.
