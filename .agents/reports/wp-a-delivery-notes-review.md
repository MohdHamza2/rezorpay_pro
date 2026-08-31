# WP-A Delivery Notes + stock ISSUE — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0 tenant-leak, float stock, or stock double-issue).
**Spec:** `architecture/wave-delivery-notes-addendum.md`, `.agents/reports/architect-delivery-notes-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B UI `/delivery-notes` (Sales nav, XOR create, confirm/cancel, Delivery Note PDF, Settings `block_do_on_hold`, ADMIN-only adjust) **may start**.

No P0 tenant leak on DN GET/list/confirm/cancel or adjust product/warehouse/bin. Qty and `on_hand` are `Numeric` + `Decimal` — no `float()` / SQL `Float` on the ISSUE path. Concurrent confirm of the last units is serialized by `DeliveryNote` `FOR UPDATE` + parent header `FOR UPDATE` + `InventoryLevel` `FOR UPDATE`; confirm is idempotent (no second `ISSUE`); cancel is CONFIRMED-only (one reverse). Alembic is a linear new revision on credit HEAD `9f3a7c2e1d04`. Pytest was **not re-run** in this review pass; `test_delivery_notes.py` has **14** functions covering spec §13. Combined **75 passed** is taken from `.agents/reports/backend-execution-report.md` (DN 14 + GRN 2 + credit 17 + LPO 17 + invoices 25).

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 | **PASS.** `get_visible` filters `id` + `workspace_id` + `deleted_at IS NULL`. Cross-workspace GET/confirm → 404 (tested). Create from other-workspace LPO/invoice/warehouse → 404 (tested). Adjust other-workspace product → 404 (tested). Parent load (`load_lpo` / `load_invoice`), warehouse/bin (`load_warehouse` / `load_bin` join), and catalog product all filter JWT workspace. List filters `workspace_id`. JWT workspace from auth deps, never from body. |
| 2 | Decimal qty; never float stock | **PASS.** DN line `Numeric(10, 2)`; levels/txns `Numeric(12, 2)`. Schemas use `Decimal`. Ledger `qty_dec` is `Decimal(str(value))` — no `float()`. `post_issue` / `adjust` mutate `on_hand` with Decimal arithmetic. CheckConstraint `on_hand >= 0`. DN has no money columns. |
| 3 | XOR parent; over-deliver 400 | **PASS.** Schema `extra="forbid"` + XOR validator (both/neither 422, extra key 422). DB check `check_dn_parent_xor` / `check_dn_item_parent_xor`. Unknown / other-parent line → 404. Over-deliver → 400 `VALIDATION_ERROR` `field=quantity`. Cannot invent SKUs: line `product_id` copied from parent only. |
| 4 | LPO remaining vs invoiced (ship-before-invoice) | **PASS.** Remaining = ordered − Σ CONFIRMED DN qty for that `cpo_item_id` (`confirmed_cpo_qty_map`). Does **not** read `quantity_invoiced`. Test: confirm 40 with invoiced 0; 70 → 400; 60 → CONFIRMED 100. LPO-linked invoice still uses LPO parent when creating from LPO (`invoice_id` null). Invoice-backed remaining = invoice qty − CONFIRMED DN qty; 11 vs 10 → 400. |
| 5 | Confirm idempotent 200; cancel reverses once | **PASS.** Already `CONFIRMED` → return same payload, skip `_issue_stock`. Router loads DN `FOR UPDATE` first so a second in-flight confirm sees the flipped row. `/cancel` requires `CONFIRMED`; DRAFT must DELETE (403). Cancel posts `ISSUE` `+qty` `reference_type=DN_CANCEL`, sets `CANCELLED` (terminal), recals `quantity_delivered`. Second cancel cannot re-enter (status gate). |
| 6 | `CREDIT_HOLD` only on confirm when `block_do_on_hold` | **PASS.** `_assert_hold` only from `confirm`. Flag false → return. Flag true → `CreditControlService.assert_not_hold(..., CreditEventReason.DN_CONFIRM)` → 400 `CREDIT_HOLD` `field=client.credit_status`. WARNING does not raise. Create/PUT have no hold gate. Test: HOLD + flag true → 400 DRAFT; flag false → 200 (create during HOLD already succeeded). |
| 7 | Insufficient stock 400; `FOR UPDATE` | **PASS.** `lock_or_create_level` `SELECT InventoryLevel … workspace_id, product_id, warehouse_id, bin_id FOR UPDATE`. `available = on_hand - reserved - damaged`; `available < qty` → 400 `field=quantity` **before** decrement. Status still DRAFT; `on_hand` unchanged (exception before commit; session `close()` rolls back). Spec `available` formula matches. |
| 8 | DN does not call adjust | **PASS.** `_issue_stock` → `post_issue` only (`TransactionType.ISSUE`). No `adjust(` in delivery-note service/support. Adjust stays OWNER/ADMIN back door with reason allow-list + notes. MEMBER 403 `INSUFFICIENT_PERMISSIONS`. |
| 9 | Alembic linear | **PASS.** `a7c4e9d2b105` `down_revision = "9f3a7c2e1d04"` only. No other revision parented on credit HEAD. Chain is single-file linear through LPO → credit → DN. Tables `dn_counters`, `delivery_notes`, `delivery_note_items`, `delivery_note_events`; `quantity_delivered` + checks; `inventory_transactions.reason`/`notes`; `ALTER TYPE crediteventreason ADD VALUE IF NOT EXISTS 'DN_CONFIRM'`. No `stock_reservations`. Credit/LPO/quotes/FTA history not rewritten. |
| 10 | Concurrent confirm doesn't double-issue | **PASS (HTTP path).** Same DN: row lock then idempotent status check. Two DRAFTs of last 10 units: parent `FOR UPDATE` then remaining SUM, then level `FOR UPDATE` + available check + `on_hand >= 0`. Catalog lines sorted by `(product_id, bin_id)` to avoid deadlocks. Test `test_concurrent_confirm_last_ten_units` expects one 200, one 400, `on_hand == 0`. Idempotent test: second confirm 200, **one** `ISSUE` row. |

---

## Findings

### Critical (P0)

None. Cross-tenant DN id is 404 with no payload leak. Cross-tenant parent/warehouse/product is 404. Stock ISSUE is Decimal/`Numeric`, not float. Double-issue of the same DN is blocked by `FOR UPDATE` + CONFIRMED short-circuit. Two DNs over the last units cannot drive `on_hand < 0` on the HTTP confirm path.

### Warning

**W1 — Isolation 404 wrapper code is `HTTP_ERROR`**
`_load_or_404` raises `HTTPException(404, "Delivery note not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no DN JSON leaked. Parent/warehouse 404s via `raise_error` correctly use `NOT_FOUND`. WP-B must treat **HTTP 404**, not only `error.code === "NOT_FOUND"`.

**W2 — `lock_or_create_level` does not retry unique insert**
Empty `(product_id, bin_id)`: two concurrent first ISSUEs can both miss the `SELECT FOR UPDATE` (no row to lock), both `INSERT`. Unique `uq_inventory_product_bin` fails one with `IntegrityError` → 500, not a second decrement. Counter insert in `DnNumberService` already uses a savepoint + re-lock. Same pattern belongs here. Spec test 8 seeds stock via adjust first, so it does not catch this. Not double-issue; worst case a 500 on first receipt-less confirm into a new bin.

**W3 — Service `confirm`/`cancel` trust the router lock**
`DeliveryNoteService.confirm` does not re-`SELECT FOR UPDATE` the DN. The router does (`for_update=True`). Today the only caller is the router. A future internal caller that passes an unlocked DRAFT identity-map object could double-ISSUE. Defense in depth: lock inside the service (same as parent header).

**W4 — HOLD path loads client/workspace by PK**
`_assert_hold` uses `session.get(Workspace, dn.workspace_id)` and `session.get(Client, dn.client_id)` then `assert_not_hold` (which **does** lock the client by id+workspace). DN row is already workspace-scoped, so this is not an API IDOR. Corrupt `client_id` FK would evaluate another tenant’s cache. Same class as credit WP W5.

**W5 — `DeliveryNoteUpdate` does not schema-check line parent vs header**
Create validator requires item XOR to match header. PUT items with the wrong parent key hit `resolve_slices` → 422 `"Item parent must match the delivery-note header"`. Blocked, but 422 at service not schema. Header parent FKs are not in the update schema (cannot switch LPO↔invoice on PUT) — good.

**W6 — Alembic pytest uses env `DATABASE_URL`, not `_test`**
`test_alembic_upgrade_head_and_check` runs `alembic upgrade head` / `check` with `cwd=backend`. That is the app database from `.env` (execution report: `invoicesaas`), while the rest of the module uses `{DATABASE_URL}_test` + `create_all`. Harmless if already at head; not isolated.

### Info

**I1 — Pytest not re-run here**
14 functions in `test_delivery_notes.py` map to spec §13 (numbers + concurrent unique split into two tests). 75 combined claimed in `backend-execution-report.md`. This pass is static.

**I2 — Test file length**
`backend/tests/test_delivery_notes.py` is ~807 lines. Spec §12 “files < 500” is aimed at app modules (service 456, support 392, ledger 309 — under). Tests are over.

**I3 — Unused `FILS`**
`inventory_ledger.FILS` is defined, never used.

**I4 — DN year is `datetime.now().year`, not UTC**
`utc_today()` is used for `delivery_date`. Number uses local year. Fine except around New Year vs UTC.

**I5 — Pre-existing: `GET /inventory/warehouses/{id}/bins` does not check warehouse workspace**
WP-A tightened **adjust** isolation (spec §8) and left list-bins as-is. Not introduced by DN. Do not treat WP-A as having closed that older hole.

**I6 — Coverage gaps (logic present)**
Second `/cancel` 403; concurrent confirm of the **same** DN; inactive product 400 on create/confirm; DRAFT/CANCELLED LPO 403; CANCELLED invoice 403; extra key on confirm body 422; ADMIN role (OWNER is tested via register). Code paths exist.

**I7 — Mid-file schema imports**
`serialize` / `serialize_list_item` import schemas inside the functions (`E402` vs CLAUDE.md). Cycle avoidance; not a runtime bug.

**I8 — `get_session` has no explicit rollback**
`finally: session.close()` — SQLAlchemy `close()` rolls back uncommitted work. Insufficient-stock and HOLD failures therefore do not persist ISSUE. Prefer explicit `rollback()` on error (project-wide, not DN-only).

**I9 — Blocked confirm still runs credit `evaluate`**
`assert_not_hold` evaluates (reason `DN_CONFIRM`) then raises. Same as send. Can write `credit_status_events` on a failed confirm. Spec said reuse that helper.

---

## Spec lock vs shipped

| Lock | Shipped |
|---|---|
| `DN-YYYY-XXXX` via `dn_counters` + `FOR UPDATE` | `DnNumberService`; savepoint on first-year insert |
| XOR one parent; LPO remaining independent of invoiced | Schema + DB check + `confirmed_cpo_qty_map` |
| DRAFT → CONFIRMED (`ISSUE` −qty `DN`) → CANCELLED (`ISSUE` +qty `DN_CANCEL`) | Service + ledger |
| Confirm idempotent 200 | Status short-circuit after DN lock |
| HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` | `_assert_hold` |
| Ledger helper filters `workspace_id` (GRN lock does not) | `lock_or_create_level` includes `workspace_id` |
| Adjust OWNER/ADMIN + reason + notes; DN must not call it | `adjust()` role/reason; DN calls `post_issue` |
| `quantity_delivered` cache on LPO items | Recalc on confirm/cancel; LPO GET exposes delivered/undelivered |
| Alembic from `9f3a7c2e1d04` | `a7c4e9d2b105` |

Router prefix `/delivery-notes` under `/api/v1`. Pagination on list. Extra keys 422 on create/update/confirm/cancel/adjust.

---

## WP-B notes (not blockers)

- Isolation toasts: use HTTP status 404 (W1 `HTTP_ERROR` vs `NOT_FOUND`).
- Settings: expose `block_do_on_hold` (credit WP deferred the checkbox).
- Inventory: MEMBER read-only; ADMIN adjust with reason allow-list + notes ≥ 3.
- PDF title **Delivery Note**, not Tax Invoice; English; CANCELLED watermark.
- Create: XOR LPO remaining **or** invoice remaining; omit items copies remaining parent lines (catalog + ad-hoc).
- Do not start WP-C Playwright until WP-B build + confirm reduces levels.

---

## Out of scope (correctly omitted)

Transfers, cycle counts, reservations, sales-return receiving, tax credit notes, WhatsApp, Arabic PDF, Peppol, OCR, negative stock, volume pricing, FTA invoice field changes, SPO/GRN formula changes (shared ledger helper is new; GRN posting left as-is).
