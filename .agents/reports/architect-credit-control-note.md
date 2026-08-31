# Architect note — Credit HOLD / overdue addendum (Gap 6)

**Date:** 2026-09-01
**Code:** none. No Alembic files written this turn.

**Addendum:** `architecture/wave-credit-control-addendum.md`

## Alembic

**YES.** New revision, `down_revision = "59084165d346"` (LPO HEAD). Never rewrite history.

`clients`: `credit_limit` nullable Decimal(12,2), `payment_terms_days` int default 0 (allow 0/30/45/60), `credit_status` ACTIVE|WARNING|HOLD, changed_at/by. Table `credit_status_events`. No new Workspace columns (reuse flags). No invoice columns. No `SUSPENDED`, no `credit_unlimited`.

## Client credit / exposure

- Limit: **NULL = inherit** `workspace.credit_limit_default`; **0 = COD**; >0 = cap.
- Terms: `payment_terms_days` default **0**. Convert/LPO invoice due_date = issue + terms (replace +30).
- Exposure: Σ `balance_due` of **SENT + PARTIALLY_PAID + OVERDUE** (not DRAFT/PAID/CANCELLED). SUCCESS payments only. Decimal.

## WARNING vs HOLD

Reuse `credit_warning_days` / `credit_hold_days` / `block_po_on_hold`. HOLD if `exposure > effective_limit` OR oldest overdue days > hold_days. Else WARNING if > warning_days. WARNING does not block. Auto both directions. No ADMIN override this WP.

## Blocks (400 `CREDIT_HOLD`)

- **Always** block invoice **SEND** on HOLD (after FTA checks).
- Block LPO **`/receive`** iff `block_po_on_hold`.
- Do **not** block DRAFT create, quote convert, payments, void.
- `block_do_on_hold` unused until DN.

## OVERDUE

On-read (and payment recalc): SENT/PARTIALLY_PAID + `due_date < today` + `balance_due > 0`. Never mutate PAID/CANCELLED. Partial pay while past due stays OVERDUE. No Celery. Payments stay immutable.

## WP

A API+Alembic+tests → B clients/settings/send toast → C Playwright HOLD blocks send.

## Out

AR statement PDF, PDC bounce, FTA changes, delivery notes, WhatsApp.
