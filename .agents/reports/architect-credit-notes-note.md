# Architect note — Tax credit notes addendum (Gap 10)

**Date:** 2026-09-01
**Code:** none. No Alembic files written this turn.

**Addendum:** `architecture/wave-credit-notes-addendum.md`

## Alembic

**YES.** New revision, `down_revision = "a7c4e9d2b105"` (DN HEAD). Never rewrite history.

Tables: `credit_note_counters`, `credit_notes`, `credit_note_items`, `credit_note_events`.

Columns: `invoices.amount_credited` default 0; `clients.credit_balance` default 0. Enum `CREDIT_NOTE_ISSUED` on invoice events.

## Number

`CN-YYYY-XXXX` via `credit_note_counters` + `SELECT FOR UPDATE`, allocated **at create**. **Gapless** (FTA tax document, same contract as INV). Do not reuse `invoice_counters`. Soft-delete does not rewind.

## States

`DRAFT → ISSUED` (issue **posts** AR). No `/apply`. No PUT/DELETE after ISSUED. Soft-delete DRAFT only. Issue idempotent 200.

## Parent / remaining

Invoice SENT/PARTIALLY_PAID/PAID/OVERDUE only. Lines ≥ 1, each `invoice_item_id`; qty ≤ line remaining; header total ≤ `invoice.total − Σ ISSUED CNs`. Same `money()`. Frozen invoice line prices.

## Invoice effect

`balance_due = max(0, total − paid − credited)`. Never mutate payment rows or invoice line money.

- Unpaid/partial: shrink due; may become PAID if CN covers remainder (recalc SENT/PARTIAL/OVERDUE).
- **PAID + CN: stay PAID.** Do **not** reopen PARTIALLY_PAID. Increment `clients.credit_balance` by over-credit (`paid − net_billed`). No auto-apply this WP.

## HOLD / PDF

Issue **never** `CREDIT_HOLD`. PDF title **Tax Credit Note**, EN, snapshots + original INV number/date.

## WP / out

A API+Alembic+tests → B UI+PDF → C Playwright.

Out: debit notes, WhatsApp, Arabic, Peppol, refunds as negative payments.
