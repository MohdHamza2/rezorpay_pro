# Wave 19 — Multi-warehouse Stock Transfers

**Project:** InvoiceSaaS (rezorpay_pro)
**Phase:** Phase 3 Advanced Inventory — sub-feature 2 of 3
**Date:** 2026-09-06
**Status:** Planned BEFORE code

---

## Problem

Stock can only be received at one warehouse and issued to customers; there is
no way to move goods between warehouses. `inventory-rules.md` defines the
Transfer lifecycle (`DRAFT → APPROVED → IN_TRANSIT → RECEIVED`, plus cancel)
and a `quantity_in_transit` swing account, but none of it is implemented:
`TransactionType.TRANSFER` exists in the enum yet nothing ever writes it.

## Scope

1. **StockTransfer** header + **StockTransferItem** lines, bin-level
   (`source_bin_id`/`destination_bin_id`), gapless `ST-YYYY-0001` numbers.
2. **`in_transit`** column on `inventory_levels` (from `inventory-rules.md`).
   Dispatch: source `on_hand -= qty`, source `in_transit += qty`.
   Receipt: source `in_transit -= qty`, destination `on_hand += received`.
   Cancel of an in-transit transfer returns stock to the source.
3. Ledger trail: `TRANSFER` rows with `reference_id = transfer.id`
   (negative at source, positive at destination).
4. Discrepancy on receipt (`received < dispatched`) recorded per line;
   lost quantity is implicit in the swing account (see Design).

Out of scope: stock counting/reconciliation (Wave 19b), transfers between
products, cost/UOM conversions, inter-warehouse reservations.

## Design

### Models (`app/models/stock_transfer.py`)

- `TransferStatus(Enum)`: `DRAFT`, `APPROVED`, `IN_TRANSIT`, `RECEIVED`, `CANCELLED`
  (DB enum `transferstatus`).
- `StockTransfer`: workspace, `transfer_number` (unique per workspace),
  `source_warehouse_id`, `destination_warehouse_id` (check `source != destination`),
  `status`, `notes`, `dispatched_at`, `received_at`, `cancelled_at`,
  `cancellation_reason`, `created_by`, timestamps, `items` relationship.
- `StockTransferItem`: `transfer_id`, `product_id`, `quantity`,
  `received_quantity` (default 0), `source_bin_id`, `destination_bin_id`.
  Checks: `quantity > 0`, `received_quantity >= 0`, `received_quantity <= quantity`.
- `TransferCounter` (`stock_transfer_counters`, composite PK workspace+year)
  cloned from `DnCounter`; `TransferNumberService` clone of `DnNumberService`
  (`ST-2026-0001`). Register all in `models/__init__.py`.
- `InventoryLevel.in_transit` column (Numeric(12,2), default 0, `>= 0` check).

### `available` and in_transit

`inventory_ledger.available()` is unchanged: `on_hand − reserved − damaged`.
`in_transit` is a swing account — stock physically absent from the source but
not yet at the destination. Invariant checks use `on_hand` at dispatch.

### Service (`app/services/stock_transfer_service.py`)

- `create_transfer(...)` → DRAFT, assigns number, resolves bins (explicit or
  first active of each warehouse), validates products + warehouses + bins.
- `approve_transfer(...)`: DRAFT → APPROVED.
- `dispatch_transfer(...)`: APPROVED → IN_TRANSIT. Per item, `FOR UPDATE` lock
  the source level; reject if `available < qty`; `on_hand −= qty`,
  `in_transit += qty`; ledger `TRANSFER` `−qty` (source_bin). Sets
  `dispatched_at`. Idempotent guard: only APPROVED.
- `receive_transfer(...)`: IN_TRANSIT → RECEIVED with per-line
  `received_quantity` (default `quantity`). Per item, lock destination level:
  `on_hand += received`; lock source level: `in_transit −= quantity`;
  ledger `TRANSFER` `+received` (destination_bin). `received_at` set when all
  lines closed. Rejects `received > quantity`. Lines may be partially received
  (discrepancy stored on the line).
- `cancel_transfer(...)`: DRAFT/APPROVED → CANCELLED (no stock movement);
  IN_TRANSIT → CANCELLED returns dispatched qty to source
  (`on_hand += quantity`, `in_transit −= quantity`) with `TRANSFER` ledger.
  RECEIVED cannot be cancelled.
- `get_visible`, `serialize`, `serialize_list_item` (mirror reservations).

### API (`/api/v1/inventory/transfers`, router `inventory.py`)

- `POST /transfers` (201) create drafts.
- `GET /transfers` paginated (filters: status, source_warehouse_id,
  destination_warehouse_id).
- `GET /transfers/{transfer_id}`.
- `POST /transfers/{transfer_id}/approve`.
- `POST /transfers/{transfer_id}/dispatch`.
- `POST /transfers/{transfer_id}/receive` (optional per-line quantities,
  `extra=forbid`).
- `POST /transfers/{transfer_id}/cancel`.

No role gates (any workspace member, matching DN/LPO flows); the OWNER/ADMIN
restriction stays with `adjust`.

### Alembic

New head `c6b3e7a9d2f0_add_stock_transfers.py` (down_revision `b2a4d6f8e1c0`):
`stock_transfers`, `stock_transfer_items`, `stock_transfer_counters`,
`inventory_levels.in_transit` (+ check), `transferstatus` enum. Applied with
`alembic upgrade head`; `alembic check` clean. Bump the 3 alembic-head guard
tests to `c6b3e7a9d2f0`.

### Ledger semantics (trace, single line)

| Step | Source.on_hand | Source.in_transit | Dest.on_hand |
| --- | --- | --- | --- |
| Starting | 100 | 0 | 0 |
| Dispatch 30 | 70 | 30 | 0 |
| Receive 20 of 30 | 70 | 0 | 20 |
| Cancel in-transit (before receive) | 100 | 0 | 0 |

`on_hand` total tracks physical reality (100 → 90 after partial receipt: 10
lost). Missing transit qty is the line discrepancy, never a negative balance.

## Test Plan (`backend/tests/test_stock_transfers.py`)

1. Create renders `ST-` number, DRAFT, resolves destination bin.
2. Dispatch decrements source `on_hand`, bumps `in_transit`, ledger `TRANSFER`,
   status IN_TRANSIT; insufficient available at source → 400.
3. Receive full: dest `on_hand` incremented, source `in_transit` cleared,
   status RECEIVED, transfer number on ledger rows.
4. Partial receive: `received_quantity` recorded on line, discrepancy kept.
5. Cancel APPROVED: no stock movement; cancel IN_TRANSIT: returns to source;
   cancel RECEIVED → 400.
6. State machine guard: dispatch DRAFT → 400, receive BEFORE dispatch → 400,
   double dispatch → 400.
7. Multi-tenant isolation: workspace B cannot read or advance A's transfer.
8. Pagination/filters; zero-qty line → 400.

---

**State flow:**

```
DRAFT ──approve──▶ APPROVED ──dispatch──▶ IN_TRANSIT ──receive──▶ RECEIVED
   │                  │                     │
   └──cancel──▶ CANCELLED ◀──cancel────────┘
```
