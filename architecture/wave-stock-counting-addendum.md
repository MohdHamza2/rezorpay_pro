# Wave 19b — Stock Counting / Reconciliation

**Project:** InvoiceSaaS (rezorpay_pro)
**Phase:** Phase 3 Advanced Inventory — sub-feature 3 of 3
**Date:** 2026-09-06
**Status:** Planned BEFORE code

---

## Problem

The only way to correct physical stock today is the `/inventory/adjust` back
door (immediate OWNER/ADMIN `ADJUSTMENT` ledger write, one level per call).
There is no workflow to compare **system (expected) vs physical (counted)**
stock per bin, track a variance, flag big variances for manager review, and
apply corrections in one reconciled pass. `inventory-rules.md` defines the
Stock Count lifecycle (`SCHEDULED → IN_PROGRESS → COMPLETED → RECONCILED`),
variance = `counted − expected`, and tolerance-based auto-approval — none of
which is implemented.

## Scope

1. **StockCount** header + **StockCountItem** lines at bin level, gapless
   `SC-YYYY-0001` numbers, over a single warehouse.
2. `expected_quantity` **snapshotted at schedule time** from the bin's
   `InventoryLevel.on_hand` (physical count counts ALL stock — reserved and
   damaged included; `in_transit` is a swing column and is NOT part of the
   snapshot). Variance computed at completion: `variance = counted − expected`.
3. Tolerance flagging: lines whose variance exceeds
   `COUNT_TOLERANCE_PERCENT = 2.00%` of expected are marked
   `requires_approval = True` and need a manager `approve` before they can be
   applied. Zero-expected with non-zero-counted is always flagged.
4. Reconciliation applies corrections as `ADJUSTMENT` ledger rows
   (`reference_type = "COUNT"`, `reference_id = count.id`, line
   `notes` prefixes the count number) and moves the level's `on_hand` by the
   variance delta. Reserved / damaged / in_transit columns are untouched.
5. `COMPLETED` closes out counting; `RECONCILED` means adjustments applied;
   `CANCELLED` voids a count with no stock movement.

Out of scope: cost/UOM conversions, book stock during an open count (the
physical-counting window is assumed mutation-free; delta is applied to the
current `on_hand` at reconcile time), per-item approval, inter-branch
counting, sampling / cycle counting.

## Design

### Models (`app/models/stock_count.py`)

- `StockCountStatus(Enum)`: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`,
  `RECONCILED`, `CANCELLED` (DB enum `stockcountstatus`).
- `StockCount`: workspace, `count_number` (index per workspace),
  `warehouse_id`, `status`, `started_at`, `completed_at`, `reconciled_at`,
  `cancelled_at`, `approved_by`, `approved_at`, `notes`, `created_by`,
  timestamps, `items` relationship.
- `StockCountItem`: `count_id`, `product_id`, `bin_id`,
  `expected_quantity` (snapshot), `counted_quantity`
  (`Optional[Decimal]`, `None` = not yet counted, check `>= 0`),
  `requires_approval` (default False), `approved` (default False), `notes`.
  Unique `(count_id, product_id, bin_id)`.
- `StockCountCounter` (`stock_count_counters`, composite PK workspace+year)
  cloned from `TransferCounter`; `StockCountNumberService` clone of
  `TransferNumberService` (`SC-2026-0001`). Register all models in
  `models/__init__.py`.

### Percent helpers (`app/services/stock_count_service.py`)

- `COUNT_TOLERANCE_PERCENT = Decimal("2.00")`.
- `needs_approval(expected, counted)`: if `variance == 0` → False; if
  `expected == 0` → True (cannot divide); else
  `abs(variance) * 100 > expected * tolerance` (multiplication compare, no
  division, no floats).

### Service (`app/services/stock_count_service.py`)

- `create_count(...)` → SCHEDULED, assigns number, validates the warehouse,
  snapshots every `InventoryLevel` for the warehouse into one
  `StockCountItem` per `(product_id, bin_id)` with `expected_quantity = on_hand`.
- `record_count(...)`: SCHEDULED → IN_PROGRESS (first record). Sets one line's
  `counted_quantity` (rejects `< 0`, unknown/foreign line 404). Later records
  are cumulative line updates until COMPLETED.
- `complete_count(...)`: rejects if any line has `counted_quantity is None`
  (all lines must be counted; a missing line → 400 naming the line). Computes
  `requires_approval` per line, sets `COMPLETED` + `completed_at`.
- `approve_count(...)`: OWNER/ADMIN manager review. Sets `approved = True` on
  every `requires_approval` line, records `approved_by`/`approved_at`.
- `reconcile_count(...)`: rejects unless COMPLETED and no `requires_approval`
  line remains unapproved (`400`). Per line with non-zero variance: `FOR
  UPDATE` lock the level, `level.on_hand += variance`, write an `ADJUSTMENT`
  ledger row (`reference_type="COUNT"`, `reference_id=count.id`,
  `reason="COUNT_CORRECTION"`, `notes=f"{count_number} variance"`,
  source_bin for negative / destination_bin for positive). Sets
  `RECONCILED` + `reconciled_at`. Never produces negative on_hand (delta
  applied to current on_hand; the `on_hand >= 0` DB check is the backstop).
- `cancel_count(...)`: SCHEDULED/IN_PROGRESS → CANCELLED (no stock movement).
  COMPLETED/RECONCILED cannot be cancelled.
- `get_visible`, `serialize`, `serialize_list_item` (mirror transfers).

### API (`/api/v1/inventory/counts`, router `inventory.py`)

- `POST /counts` (201) create scheduled count (snapshots expected).
- `GET /counts` paginated (filters: status, warehouse_id).
- `GET /counts/{count_id}`.
- `POST /counts/{count_id}/record` — `CountRecordRequest { item_id,
  counted_quantity, notes? }`, `extra=forbid`.
- `POST /counts/{count_id}/complete`.
- `POST /counts/{count_id}/approve` — manager review of flagged lines.
- `POST /counts/{count_id}/reconcile`.
- `POST /counts/{count_id}/cancel`.

Role gates: mutating count endpoints are OWNER/ADMIN only (they culminate in
adjustments — same policy as `/adjust`); GET is open to any workspace member.
`/counts` routes cannot collide with `/levels` or `/warehouses`.

### Alembic

New head `e1f5b8a2c3d4_add_stock_counts.py` (down_revision `c6b3e7a9d2f0`):
`stock_counts`, `stock_count_items`, `stock_count_counters`, `stockcountstatus`
enum. Applied with `alembic upgrade head`; `alembic check` clean. Bump the 3
alembic-head guard tests to `e1f5b8a2c3d4`.

### Ledger semantics (trace, single line)

| Step | on_hand (bin) | Count item |
| --- | --- | --- |
| Schedule (expected) | 100 | expected=100 |
| Hard count | 100 | counted=82, variance=18 |
| Reconcile (delta −18) | 82 | RECONCILED |

Reserved/damaged/in_transit are never adjusted by a count: `available()`
recomputes naturally from the corrected `on_hand`.

## Test Plan (`backend/tests/test_stock_counts.py`)

1. Create: SCHEDULED, `SC-` gapless number, warehouse validation, full level
   snapshot (`expected = on_hand` incl. reserved), all-zero bin still captured.
2. Record: SCHEDULED → IN_PROGRESS, sets `counted_quantity`, rejects negative
   and unknown line, rejects foreign-workspace line (404).
3. Complete: rejects when a line is uncounted (400 names line); after all
   counted computes `variance` and flags tolerance lines.
4. Tolerance: small variance (≤2%) not flagged; large variance flagged;
   zero-expected with counted > 0 flagged; exact-zero variance unflagged.
5. Reconcile without approve → 400 when a flagged line exists; approve then
   reconcile applies deltas, writes `ADJUSTMENT`/`COUNT` ledger rows, moves
   `on_hand` to counted, status RECONCILED.
6. Cancel: SCHEDULED/IN_PROGRESS → CANCELLED with no stock movement; cancel
   RECONCILED → 400.
7. Permissions: MEMBER 403 on create/complete/approve/reconcile/cancel,
   200 on GET.
8. Multi-tenant isolation: workspace B cannot read or mutate A's count.
9. Pagination/filters; reconcile non-COMPLETED → 400; record after
   RECONCILED → 400.

---

**State flow:**

```
SCHEDULED ──record─▶ IN_PROGRESS ──complete─▶ COMPLETED ──approve▶ (reviewed)
   │                                              │
   └─────────────cancel──▶ CANCELLED              └──reconcile──▶ RECONCILED
```
