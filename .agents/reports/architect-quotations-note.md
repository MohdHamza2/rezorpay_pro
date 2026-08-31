# Architect note — Quotations addendum (Gap 4)

**Date:** 2026-09-01
**Code:** none. No Alembic files written this turn.

**Addendum:** `architecture/wave-quotations-addendum.md`

## Alembic

**YES.** New revision, `down_revision = "c8e1a4f2b6d0"` (FTA HEAD). Never rewrite history.

Tables: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`. Column: `invoices.quotation_id` UUID nullable unique FK.

No `enquiry_id`, `revision_number`, `revised_from_id`, LPO tables, `clients`/`products` column changes.

## Number format

`QUO-YYYY-XXXX` via `quotation_counters` + `SELECT FOR UPDATE` (clone invoice counter, **do not** reuse `invoice_counters`).

Quotes are **not** FTA tax invoices — sequence is operational uniqueness, not legal gapless. Soft-delete does not rewind. Failed create rolls back.

## States

`DRAFT → SENT → ACCEPTED | REJECTED | EXPIRED`. Convert **only from ACCEPTED** → `CONVERTED`.

No `REVISED` / `CANCELLED` this WP. Expiry is **on-read** (`valid_until` default quotation_date + 14 days), not a nightly job.

## Convert rules

- Call `InvoiceService.create_invoice` → **DRAFT** invoice. Copy client, AED, frozen line qty/price/discount/tax/`product_id` (omit product_id if inactive). Notes prefix `Converted from QUO-…`.
- Dates: issue/supply = today; due = today+30 (UX only).
- **Do not** run FTA send gates (TRN/address). Those wait for `POST /invoices/{id}/send`.
- Convert once: unique `invoices.quotation_id`. Second convert **200** same invoice; if that invoice is soft-deleted → **409**, do not recreate.
- SENT cannot convert (accept first). EXPIRED/REJECTED/DRAFT cannot convert (**403** `INVALID_STATE`).
- LPO convert: **skip** (no stub routes). Next after quotes A–C.

## WP split

A API+Alembic+tests → B UI+PDF title **Quotation** (EN) → C Playwright.

## Out

Customer PO OCR, WhatsApp, Arabic, credit HOLD, delivery notes, public accept, revise.
