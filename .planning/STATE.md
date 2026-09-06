# Project State

**Current Phase:** Phase 3: Advanced Inventory (Waves 18-19b)
**Status:** Completed Phase 2

## Recent Actions
- Executed Phase 2 (Wave 7 Enquiry Management).
- Verified Enquiry Management in backend (SQLModel, schemas, endpoints).
- Verified Enquiry Management via UI in browser subagent (Kanban rendering, Detail View, Client linking).
- Ran automated Playwright E2E tests, which successfully pass.
- Full audit 2026-09-06: fixed frontend production build (debit-note PDF/AR panel/enquiry TS errors), fixed backend test suite (228 passing), added frontend lint+build job to CI.
- Audit remediation (M-series): gapless PR/RFQ/GRN numbering (counters + FOR UPDATE, alembic `9f3a2c1e5d84`), SECRET_KEY production guard, configurable CORS_ORIGINS, health E402, deleted leftover root test scripts. Backend suite 228 passed incl. new concurrent PR/RFQ/GRN numbering tests; ruff + black clean.
- Wave 18 (Stock Reservations from Customer POs): implemented end-to-end — models (`StockReservation`, `StockReservationItem`, `ReservationStatus`), alembic `b2a4d6f8e1c0` (locked invariant: `InventoryLevel.reserved == SUM(quantity - quantity_consumed)` over ACTIVE lines), schemas, service (`create/cancel/expire/release_for_dispatch`, 7-day TTL, FIFO release), router endpoints (create 201, list with status/cpo/warehouse filters, get, cancel, owner/admin expire), DN confirm integration (release before `post_issue`). Backend suite 238 passed incl. 7 new reservation tests; ruff + black clean; `alembic check` clean.
- Wave 19 (Multi-warehouse Stock Transfers): implemented end-to-end — models (`StockTransfer`/`StockTransferItem`/`StockTransferCounter` + `TransferStatus`), alembic `c6b3e7a9d2f0` (adds `inventory_levels.in_transit` swing column + check `>= 0`, gapless `ST-YYYY-0001` counter), schemas (incl. partial-receive discrepancy via `received_quantity`), service (`create/approve/dispatch/receive/cancel`, state machine DRAFT→APPROVED→IN_TRANSIT→RECEIVED, `in_transit` swing accounting mirrored as TRANSFER ledger txns, cancel IN_TRANSIT returns to source), router endpoints (create 201, paginated list with status/source/dest filters, get, approve/dispatch/receive/cancel). Backend suite 246 passed incl. 8 new transfer tests; ruff + black clean; `alembic check` clean.
- Wave 19b (Stock Counting / Reconciliation): implemented end-to-end — models (`StockCount`/`StockCountItem`/`StockCountCounter` + `StockCountStatus` SCHEDULED→IN_PROGRESS→COMPLETED→RECONCILED, CANCELLED; unique (count_id, product_id, bin_id) line; tz-aware lifecycle timestamps), alembic `e1f5b8a2c3d4` (tables `stock_counts`/`stock_count_items`/`stock_count_counters`, gapless `SC-YYYY-0001` counter), schemas (`CountRecordRequest` extra=forbid + non-negative, `StockCountResponse` with variance), service (`create_count` snapshots `on_hand` per bin at schedule, `record/complete/approve/reconcile/cancel`; `COUNT_TOLERANCE_PERCENT=2.00` multiplication compare flags `requires_approval`; reconcile applies `on_hand += variance` via `lock_or_create_level` + writes ADJUSTMENT ledger rows `reason=COUNT_CORRECTION`; `in_transit`/`reserved`/`damaged` never touched), router endpoints (create 201, paginated list with status/warehouse filters, get, record/complete/approve/reconcile/cancel; OWNER/ADMIN-only mutations, GET open to members). Backend suite 255 passed incl. 9 new stock-count tests; ruff + black clean; `alembic check` clean; migration downgrade/upgrade round-trip verified. Restored three guard test modules after a PowerShell `python -c` truncation incident and re-pinned alembic head assertions to `e1f5b8a2c3d4` (`test_pdc`, `test_pricing`); `test_product_electrical_specs` rewritten to walk the head→root lineage dynamically so future waves never break it.

## Pending Works
- [x] Research Advanced Inventory domain (stock reservations from Customer POs, multi-warehouse transfers, stock counting/reconciliation).
- [x] Create implementation plan for Phase 3 (Wave 18 reservations addendum written; research complete).
- [x] Wave 18: Stock Reservations from Customer POs (models, migration, service, API, DN dispatch integration, tests).
- [x] Wave 19: Multi-warehouse Stock Transfers.
- [x] Wave 19b: Stock Counting / Reconciliation.
