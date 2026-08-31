# Architect note — Delivery Note + stock ISSUE addendum (Gap 7)

**Date:** 2026-09-01
**Code:** none. No Alembic files written this turn.

**Addendum:** `architecture/wave-delivery-notes-addendum.md`

## Alembic

**YES.** New revision, `down_revision = "9f3a7c2e1d04"` (credit HEAD). Never rewrite history.

Tables: `dn_counters`, `delivery_notes`, `delivery_note_items`, `delivery_note_events`.

Also: `customer_purchase_order_items.quantity_delivered`; `inventory_transactions.reason` + `notes`; PG enum value `DN_CONFIRM` on `crediteventreason`.

No `stock_reservations`. No second DeliveryOrder module.

## Number

`DN-YYYY-XXXX` via `dn_counters` + `SELECT FOR UPDATE`. Operational, not FTA-gapless. Do not reuse INV/QUO/LPO/SPO counters.

## States

`DRAFT → CONFIRMED` (ISSUE −qty) → `CANCELLED` (ISSUE +qty reverse, `reference_type=DN_CANCEL`). DRAFT uses soft-delete. Confirm idempotent 200. No reserve / DISPATCHED / RETURNED.

## Source of truth (XOR)

Exactly one parent: **LPO** (remaining = ordered − CONFIRMED DN qty; ship-before-invoice OK) **or** **invoice** (remaining = invoice qty − CONFIRMED DN qty). Both/neither → 422. Cannot over-deliver (400). Catalog `product_id` required to move stock; ad-hoc lines confirm without ISSUE.

## HOLD

Confirm blocked **iff** `block_do_on_hold` → **400 `CREDIT_HOLD`**. WARNING does not block. Create/PUT never blocked.

## Inventory / adjust

Reuse GRN `FOR UPDATE` + bin; filter `workspace_id`. `ISSUE` was unused — this WP writes it. Never float.

`POST /inventory/adjust`: **keep** as OWNER/ADMIN back door; require reason allow-list + notes; workspace 404; always ledger. MEMBER 403. DN must not call adjust.

## PDF / WP

Title **Delivery Note**, English only. A API+Alembic+tests → B UI `/delivery-notes` → C Playwright confirm issues stock.

## Out

Transfers, counts, reservations, WhatsApp, credit notes, Arabic.
