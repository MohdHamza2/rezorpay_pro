# Wave 18 — Stock Reservations from Customer POs

**Project:** InvoiceSaaS (rezorpay_pro)
**Phase:** Phase 3 Advanced Inventory — sub-feature 1 of 3
**Date:** 2026-09-06
**Status:** Planned BEFORE code

---

## Problem

A Customer PO (LPO) commits stock to a customer before a Delivery Note is
dispatched. Without a reservation step the same physical stock can be promised
to two customers: the delivery pipeline only checks `on_hand` at DN confirm,
and nothing ever writes the `reserved` column that already exists on
`inventory_levels` (available = `on_hand - reserved - damaged`).

## Scope

1. **StockReservation** header + **StockReservationItem** lines
   (bin-level, mirrors `InventoryLevel(product, warehouse, bin)`).
2. Reservation creation against a received LPO → increments
   `InventoryLevel.reserved` per (product, warehouse, bin).
3. Reservation release on DN confirm → decrements `reserved` **before**
   the ISSUE posting, making the two-phase commit real.
4. Reservation cancellation and expiry → release `reserved` back to available.

Out of scope for this wave: transfers, stock counting, reorder automation
(follows in Waves 19-20/architecture left-overs).

## Design

### Models (`app/models/stock_reservation.py`)

- `ReservationStatus(Enum)`: `ACTIVE`, `DISPATCHED`, `CANCELLED`, `EXPIRED`.
- `StockReservation`: workspace, LPO, status, `expires_at`
  (default `now + 7 days`), `cancelled_at`, `cancellation_reason`, timestamps.
- `StockReservationItem`:
  - FK `customer_purchase_order_item_id`, `product_id`, `warehouse_id`, `bin_id`.
  - `quantity`, `quantity_consumed`, `status`, `dispatched_at`.
  - Check constraints: `quantity > 0`, `0 <= quantity_consumed <= quantity`.

### Invariant

```
InventoryLevel.reserved == SUM(quantity - quantity_consumed)
over ACTIVE items of that (product, warehouse, bin)
```

Maintained inside the service only (single writer). Never written via the
adjust back-door or GRN.

### Service (`app/services/stock_reservation_service.py`)

- `create_reservation(...)`:
  - LPO must be shippable (`RECEIVED`/`PARTIAL`/`INVOICED`).
  - Line qty must not exceed undelivered minus already ACTIVE-reserved.
  - For each line: resolve bin, `FOR UPDATE` lock the `InventoryLevel`,
    reject if `available < qty`, then `reserved += qty`.
- `cancel_reservation(...)`: ACTIVE only → release remaining per item.
- `expire_due(...)`: ACTIVE headers past `expires_at` → release as EXPIRED.
- `release_for_dispatch(session, cpo_item_id, product_id, qty)`:
  - FIFO over ACTIVE items (`created_at, id`); decrement `reserved`,
    advance `quantity_consumed`; a fully-consumed item → `DISPATCHED`.
  - Called from DN confirm BEFORE `post_issue` so `available` already
    includes the qty being shipped. Returns the reserved qty consumed;
    anything beyond reserved ships from unreserved stock as today.

### API (`/api/v1/inventory/reservations`)

- `POST /reservations` (201) create from LPO lines.
- `GET /reservations` paginated (filters: status, cpo_id, warehouse_id).
- `GET /reservations/{reservation_id}`.
- `POST /reservations/{reservation_id}/cancel`.
- `POST /reservations/expire` (OWNER/ADMIN only; releases due ACTIVE).

### DN integration (`app/services/delivery_note_service.py`)

`_issue_stock` for `from_lpo` catalog lines releases reservations first,
then posts the ISSUE transaction (unchanged semantics for invoice-backed DNs;
cancel remains unchanged — reservations stay DISPATCHED).

## Test Plan (`backend/tests/test_stock_reservations.py`)

1. Create reserves qty and drops available; insufficient stock → 400.
2. Cancel releases reserved back to available (reservation listed CANCELLED).
3. DRAFT LPO cannot be reserved; over-reservation beyond undelivered → 400.
4. Partial DN dispatch consumes reserved FIFO; item stays ACTIVE, reserved drops.
5. Full dispatch marks item DISPATCHED and header DISPATCHED.
6. Expiry endpoint releases due ACTIVE reservations.
7. Multi-tenant isolation: workspace B cannot read/cancel workspace A's reservation.
8. List pagination + filters.
