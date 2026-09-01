# Architect note — AR aging + Account Statement (Gap 12 / Phase 8)

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-ar-statement-addendum.md`

## Alembic

**NO.** Generated GET over live invoices / SUCCESS payments / ISSUED CNs / `credit_balance`. No `ar_statements` table (would be a second ledger). HEAD remains **`b8d5f0c3a216`**. Later WPs `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA history.

## PDF title

**`Account Statement`** — not Tax Invoice, not Tax Credit Note. Client-side `@react-pdf/renderer` from JSON. **No** `/ar-statement.pdf` route (invoices/CNs have no server PDF).

## Aging

Reuse `CreditControlService.aging_buckets`: **current / 1–30 / 31–60 / 61–90 / 90+**. Outstanding = live `balance_due` (`max(0, total − SUCCESS paid − ISSUED credited)`). Exclude CANCELLED, DRAFT, PAID-at-zero. `credit_balance` parked, not a bucket. `as_of=today` must match `GET /clients/{id}/credit`.

## Activity

Include SENT / PARTIALLY_PAID / PAID / OVERDUE invoices in `[from,to]`. Exclude DRAFT, CANCELLED (+ their payments/CNs), quotes/LPO/DN, DRAFT CNs. Opening reconstructed from the same rules with date `< from`. Date range **required**, max **366** days, hard cap **2000** lines. No pagination. Isolation **404**. MEMBER+ (same as GET client).

## PDC

Live `record_payment` always **SUCCESS** (PDC reduces AR today). **Do not fix** (Phase 9). SUCCESS PDC → Payment line, method PDC, **in** `totals.paid`. PENDING → **Payment (pending)**, not cleared cash, **not** in paid. No bounce endpoints.

## WP

- **A** API + pytest (`test_ar_statement.py`). No frontend. No Alembic.
- **B** `/clients/:id/statement` + `StatementPDF.tsx` after A is green.
- **C** Playwright: SENT + SUCCESS pay + ISSUED CN → three types, credited ≠ paid, aging = JSON; workspace B GET 404. Docker 8000 / Postgres 5434. Never SQLite.

Out: bilingual, debit notes, WhatsApp, Peppol, refunds, payment PUT, invoice-list `amount_credited`, dashboard overdue pack.
