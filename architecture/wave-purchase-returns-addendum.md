# Purchase Returns + Supplier Debit Notes — Wave 23 Addendum (Phase 4)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** GRN disposition (GRN-004 auto-return hook is an empty `pass`), `SupplierInvoice` `balance_due` write path (today only `create` and `_settle_invoice` write it), AP statement + aging (balance-due driven, statement doc-type is a Pydantic-only enum), gapless counter pattern (`GRNNumberService`), inventory `lock_or_create_level` + `InventoryTransaction` ledger (reason/reference_type are plain `varchar`, no ENUM change needed).
**Depends on:** Wave 22 supplier AP (HEAD `a3f4c7d9e1b2`), Wave 21 3-way match, GRN disposition posting, inventory ledger.
**After this slice:** PDC-to-supplier, supplier-invoice event/history table, Phase 5 comms.

Copy the Wave 22 slice: **API + pytest in one WP** (no frontend). Alembic: **one new revision** for five new tables + three new enums. Do not start anything else until pytest green.

Wave 25 of `MASTER_PLAN_V3` = "Returns + Credit/Debit Notes". This addendum implements the **purchase (AP) half**: goods sent back to a supplier for money back, and the supplier **debit note** (`SDN-`) that offsets what we owe on approved supplier invoices. The sales-return/credit-note half is **out of scope** (existing AR credit notes already handle the sales side).

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `GRNStatus` enum | `DRAFT, RECEIVING, PENDING_INSPECTION, PARTIALLY_ACCEPTED, ACCEPTED, PARTIALLY_REJECTED, REJECTED, CANCELLED` (Postgres `grnstatus`). |
| `GRNItem` | No per-item status. Disposition is numeric snapshots: `quantity_received = quantity_accepted + quantity_damaged + quantity_rejected` (CheckConstraint `chk_grnitem_quantity_received_match`). Requires `spo_item_id` (FK `supplier_purchase_order_items.id`), `product_id`, `uom_id`. **Damaged/rejected quantities never post to inventory** — only `quantity_accepted` is receipt-posted (`TransactionType.RECEIPT`, `reference_type="grn"`). |
| GRN disposition hook | `grn_service.py` lines ~288-291: `if item.quantity_rejected > 0: pass` — **the designed trigger (GRN-004) is an empty `pass` today. This wave fills it.** |
| `SupplierInvoice` money | `total_amount`, `amount_paid`, `balance_due`. Only two writers today: `create_supplier_invoice` (sets `balance_due = total_amount`) and `supplier_payment_service._settle_invoice` (payments). A supplier debit note is a **third, deliberate write path** (same `FOR UPDATE` + `money()` discipline). |
| `SupplierInvoiceStatus` | `RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID, CANCELLED`. `PAID` means **cash-settled via payments only** — a debit note offset NEVER flips an invoice to `PAID` and never touches `amount_paid`/`paid_at`. |
| `InventoryLevel` | `on_hand / reserved / damaged / in_transit` `Numeric(12,2)`, non-negative. Available = `on_hand − reserved − damaged`. |
| `InventoryTransaction` | `transaction_type` is Postgres ENUM `transactiontype` (`INITIAL, RECEIPT, ISSUE, TRANSFER, ADJUSTMENT`); `reference_type` varchar(50) + `reason` varchar(30) are **plain strings** → `reference_type="PRN"`, `reason="PURCHASE_RETURN"` need **no migration**. `ISSUE` semantics here = goods dispatched out (delivery notes already use it). |
| `lock_or_create_level` | `app/services/inventory_ledger.py` — `(workspace_id, product_id, warehouse_id, bin_id)` `FOR UPDATE`, creates zeros row; used by stock-count (`reason="COUNT_CORRECTION"`). Mirror for return stock-out. |
| Gapless counters | `GRNCounter`/`GRNNumberService` (`grn_number.py`): PK `(workspace_id, year)`, `last_number`, `FOR UPDATE` + IntegrityError retry, `f"GRN-{year}-{last_number:06d}"`. Mirror for `PRN-YYYY-XXXX` and `SDN-YYYY-XXXX`. |
| AR debit notes (tax) | Table `tax_debit_notes`, router `/debit-notes`, prefix `TDN-`. `DN-` prefix belongs to **delivery notes**. → supplier note uses table `supplier_debit_notes`, router `/supplier-debit-notes`, prefix **`SDN-`** (no collision). |
| Statement | `schemas/supplier_statements.py` doc-type is a **Pydantic-only enum** → adding `SUPPLIER_DEBIT_NOTE` touches no DB. Insertion points: `ACTIVITY_ORDER`, `collect_activity`, `reconstruct_opening`, `period_totals`, `SupplierStatementTotals` (add `credited`). |
| Aging / footer | `open_ap_invoices` (`status IN (APPROVED, PARTIALLY_PAID) AND balance_due > 0`) feeds both AP aging and the statement `amount_due_now`. **Reduce `balance_due` on apply → aging + footer pick it up with zero query changes.** |
| Auth | No shared `require_owner_or_admin` helper; gating is inline `user.role not in (UserRole.OWNER, UserRole.ADMIN) → 403 INSUFFICIENT_PERMISSIONS`. GET open to members; **all return/note mutations + note apply are OWNER/ADMIN**. |
| `raise_error` | `app/services/customer_po_support.py`; `ErrorCode` in `app/schemas/common.py`. New codes: `RETURN_QTY_EXCEEDS_RECEIVED`, `DEBIT_NOTE_EXCEEDS_BALANCE`. |
| Alembic HEAD | **`a3f4c7d9e1b2`**. New revision `down_revision = "a3f4c7d9e1b2"`. Never rewrite history. |

CLAUDE.md: Decimal `Numeric(12,2)` + `money()`; no float money; wrapper `{success, data, error}`; workspace isolation **404 not 403**; never SQLite; no comments unless asked; commit is the final lifecycle step.

---

## 1. What exists today (do not rebuild)

- `purchase_returns` / supplier debit notes: **greenfield** — no model, router, schema, migration, or test anywhere. Only the GRN-004 `pass` placeholder.
- Supplier-invoice `balance_due`: only two writers (`create`, `_settle_invoice`). Aging + statement read it live.
- **Spec reconciliation** (three sources conflicted — resolved as follows, reason on each):
  1. **Return states**: `procurement-rules.md` (`DRAFT → PENDING_SUPPLIER → APPROVED → DISPATCHED → COMPLETED`, with `REJECTED`, `CANCELLED`) wins over `MASTER_PLAN_V3` (`DRAFT, REQUESTED, SENT, PARTIALLY_RETURNED, FULLY_RETURNED, CLOSED`) because it matches `api-contracts.md`'s actions 1:1 AND enforces the documented "supplier approval before dispatch" gate. **7 states, mapped to explicit endpoints (§4).**
  2. **Note entity**: `api-contracts.md` `POST /debit-notes` (supplier-side, `supplier_id` + optional `supplier_invoice_id` + optional `purchase_return_id`) + V3 `DebitNote` statuses `DRAFT/ISSUED/APPLIED/CANCELLED` win. `procurement-rules.md`'s "SupplierCreditNote on COMPLETED" is **superseded**: a credit-from-supplier that offsets AP is a debit note in this domain; note is created at **dispatch** (goods shipped back), not COMPLETED (per `api-contracts`).
  3. **Trigger**: `procurement-rules.md` ("return created from GRN for rejected/damaged items") + the GRN-004 hook both indicate **auto-return on disposition**. Implemented now (§5).

---

## 2. PurchaseReturn model (`purchase_returns`)

| Column | Type / rule |
|---|---|
| `id` | UUID PK |
| `workspace_id` | FK `workspaces.id`, indexed |
| `supplier_id` | FK `suppliers.id`, indexed |
| `grn_id` | FK `goods_receipt_notes.id`, indexed. **Required** — every return traces to a receipt. |
| `prn_number` | `str(50)`, gapless `PRN-YYYY-XXXX`, indexed |
| `return_date` | `date` |
| `status` | `PurchaseReturnStatus` enum (new DB enum `purchasereturnstatus`): `DRAFT, PENDING_SUPPLIER, APPROVED, DISPATCHED, COMPLETED, REJECTED, CANCELLED`. Default `DRAFT`. |
| `reason` | `Text`, required |
| `created_by` | FK `users.id` |
| `created_at` / `updated_at` | tz-aware |

`return_status`-driven money value (sidebar on the return): `total_value = Σ items (quantity × unit_price)` — **computed in the service at dispatch time**, no stored duplicative header total (single source of truth = item rows, like GRN).

---

## 3. PurchaseReturnItem model (`purchase_return_items`)

| Column | Type / rule |
|---|---|
| `id` | UUID PK |
| `purchase_return_id` | FK `purchase_returns.id`, indexed |
| `grn_item_id` | FK `grn_items.id`, indexed — **real connectivity: return line ↔ GRN line ↔ SPO item ↔ product** |
| `product_id` | FK `products.id` (snapshot from grn_item) |
| `internal_sku` / `description` | snapshot strings from grn_item |
| `uom_id` | FK `units_of_measure.id` (snapshot) |
| `quantity` | `Numeric(12,4)`, `> 0` (CheckConstraint per row) |
| `unit_price` | `Numeric(12,2)`, `> 0` — **agreed return price snapshot** (from payload; GRN-004 auto-items take `grn_item.spo_item.unit_price`) |
| `stock_out_qty` | `Numeric(12,4)`, default 0 — the portion drawn from on-hand inventory (accepted goods) at dispatch |
| `return_type` | `ReturnType` enum (new DB enum `purchasereturntype`): `QUALITY_ISSUE, DAMAGE, WRONG_ITEM, EXCESS` (procurement-rules) |
| `notes` | `Text` nullable |

**Caps (invariant, enforced at create and re-checked at `submit-for-supplier-approval`) — prevents over-returning:**
1. Per `grn_item`: cumulative return `quantity` across **all non-CANCELLED** purchase returns ≤ `grn_item.quantity_received` → else `400 RETURN_QTY_EXCEEDS_RECEIVED`.
2. `stock_out_qty` (assigned at dispatch) ≤ `quantity_remaining_accepted`, where `quantity_remaining_accepted = grn_item.quantity_accepted − Σ dispatched/stocked returns already at dispatch for that grn_item`, and ≤ current available `on_hand`. Stock-out uses `TransactionType.ISSUE, quantity=-stock_out_qty, reference_type="PRN", reason="PURCHASE_RETURN"`.

---

## 4. Purchase-return state machine

```
DRAFT ──submit-for-supplier-approval──▶ PENDING_SUPPLIER ──approve──▶ APPROVED ──dispatch──▶ DISPATCHED ──complete──▶ COMPLETED
 │                                         │                                                          (supplier confirmed receipt)
 ├──cancel──▶ CANCELLED                    ├──reject──▶ REJECTED
 │        (DRAFT / PENDING_SUPPLIER only)  └──cancel──▶ CANCELLED (PENDING_SUPPLIER only)
```

| Transition | Endpoint | Allowed from | Side effects |
|---|---|---|---|
| create | `POST /purchase-returns` | — | Sets `DRAFT`; gapless `PRN`; caps checked (200/201) |
| submit | `POST /{id}/submit-for-supplier-approval` | `DRAFT` | Re-checks caps; → `PENDING_SUPPLIER` |
| approve | `POST /{id}/approve` | `PENDING_SUPPLIER` | → `APPROVED` (supplier accepted the return) |
| **dispatch** | `POST /{id}/dispatch` | `APPROVED` | → `DISPATCHED`; **stock-out** (ISSUE ledger rows); **auto-creates ISSUED debit note (SDN)** for `Σ items (qty × unit_price)` |
| complete | `POST /{id}/complete` | `DISPATCHED` | → `COMPLETED` (supplier received the goods; no money side effect — note already ISSUED) |
| reject | `POST /{id}/reject` | `PENDING_SUPPLIER` | → `REJECTED` |
| cancel | `POST /{id}/cancel` | `DRAFT`, `PENDING_SUPPLIER` | → `CANCELLED`; **only before dispatch** (after dispatch a note exists) |

- Illegal transition → `400 INVALID_STATE` with the expected-from message (mirror supplier-invoice style).
- Mutations (create/submit/approve/dispatch/complete/reject/cancel) → OWNER/ADMIN gate (`403 INSUFFICIENT_PERMISSIONS`); GET list/get → any member.
- `dispatch` is the money+stock boundary — it runs in one transaction: status flip, stock-out (with `on_hand` guard `400 VALIDATION_ERROR "Insufficient on-hand stock for return"` if a stock-out line would go negative), SDN creation (gapless).

**Stock-out rule at dispatch (deterministic, no double-dip):** for each item,
`stock_out_qty = min(quantity, grn_item.quantity_accepted − already_stocked_returns, level.on_hand)`.
`already_stocked_returns` = Σ `stock_out_qty` on other non-CANCELLED return rows for that `grn_item`. A return item whose quantity exceeds accepted stock (e.g. entirely rejected/damaged) simply gets `stock_out_qty = 0` — it never entered inventory, nothing to decrement. Zero-stock-out returns are legal (returns of never-stocked goods). Ledger rows are written **only** for items with `stock_out_qty > 0`.

---

## 5. GRN-004 auto-return (fills the `pass`)

On `record_disposition` in `grn_service`, when `item.quantity_rejected > 0 or item.quantity_damaged > 0`:
1. Locate an existing `DRAFT` `PurchaseReturn` for `(grn_id, supplier_id = grn.supplier_id)` in this workspace; else create one (`PRN` gapless, `reason = "Auto-created from GRN disposition"`, `created_by` = disposition user).
2. Upsert a `PurchaseReturnItem` for that `grn_item`:
   - SAME quantity components from the disposition: rejected qty row `return_type=QUALITY_ISSUE`, damaged qty row `return_type=DAMAGE` (only the non-zero halves are created).
   - `unit_price = grn_item.spo_item.unit_price` (SPO snapshot), `quantity = this disposition's rejected/damaged qty`, `product_id/internal_sku/description/uom_id` snapshots copied from `grn_item`.
   - If a row already exists for `(purchase_return_id, grn_item_id, return_type)`, **accumulate** `quantity` (add). Caps still enforced (`RETURN_QTY_EXCEEDS_RECEIVED`) keeping Σ ≤ `quantity_received`.
3. All inside the same transaction as the disposition (so auto-return can never be orphaned). Guarded by `FOR UPDATE` on `grn_item`.

This is the designed trigger and closes the loop: **disposition → auto DRAFT return → submit/approve/dispatch → SDN → AP offset**. A user may edit nothing on an auto-return except via new manual returns (auto-return items are append-only; editing is future scope). Manual `POST /purchase-returns` remains for accepted-then-defective stock (creates its own return + item with the stock-out path).

**Why this is safe:** rejected/damaged never posted to inventory, so an auto-return's `stock_out_qty` computes to 0 (accepted contribution 0) → no stock movement, no negative stock. The exception ("accepted, later found defective") is covered by **manual** returns whose items start from accepted stock → stock-out happens at dispatch.

---

## 6. SupplierDebitNote model (`supplier_debit_notes`)

| Column | Type / rule |
|---|---|
| `id` | UUID PK |
| `workspace_id` | FK `workspaces.id`, indexed |
| `supplier_id` | FK `suppliers.id`, indexed |
| `purchase_return_id` | FK `purchase_returns.id` **nullable** — set when auto-created at dispatch |
| `dn_number` | `str(50)`, gapless **`SDN-YYYY-XXXX`**, indexed |
| `amount` | `Numeric(12,2)`, `CheckConstraint(amount > 0)` — always = return `total_value` for auto notes; manual amount from payload |
| `status` | `SupplierDebitNoteStatus` (new DB enum `supplierdebitnotestatus`): `DRAFT, ISSUED, APPLIED, CANCELLED` |
| `source_type` | `str(20)`: `"PURCHASE_RETURN"` | `"MANUAL"` |
| `issue_date` | `date` |
| `applied_invoice_id` | FK `supplier_invoices.id` nullable, indexed |
| `reason` | `Text` nullable |
| `created_by` | FK `users.id` |
| `applied_at` / `cancelled_at` | tz-aware, nullable |
| `created_at` / `updated_at` | tz-aware |

A debit note = money the **supplier owes us** (credit against payable). It never reduces `amount_paid`, never sets `paid_at`, never flips `PAID`.

---

## 7. Supplier debit note state machine + AP apply

```
DRAFT ──issue──▶ ISSUED ──apply──▶ APPLIED        (applied_invoice_id set, balance_due reduced)
 │                │
 └──cancel──▶ CANCELLED  └──cancel──▶ CANCELLED   (only if not yet APPLIED)
```

| Transition | Endpoint | Allowed from | Side effects |
|---|---|---|---|
| create (manual) | `POST /supplier-debit-notes` | — | `DRAFT`, gapless `SDN`, `source_type=MANUAL` (201) |
| issue | `POST /{id}/issue` | `DRAFT` | → `ISSUED` |
| **apply** | `POST /{id}/apply` | `ISSUED` | Reduce `supplier_invoice.balance_due` (see guards) → `APPLIED`, set `applied_invoice_id`, `applied_at` |
| cancel | `POST /{id}/cancel` | `DRAFT`, `ISSUED` | → `CANCELLED`, set `cancelled_at`. `APPLIED` notes are permanent. |

**Apply guards (all in one txn, `FOR UPDATE` on invoice):**
1. Payload `{ supplier_invoice_id }` → invoice must exist **in the same workspace** → else `404 NOT_FOUND`.
2. `invoice.supplier_id == note.supplier_id` → else `400 INVALID_STATE` ("Debit note supplier must match invoice supplier").
3. `invoice.status in (APPROVED, PARTIALLY_PAID)` → else `400 INVALID_STATE` (a `PAID`/pre-approved/`CANCELLED` invoice has no payable to offset; paid invoices would create an unmodeled supplier credit — out of scope, rejected loudly).
4. `note.amount ≤ invoice.balance_due` → else `400 DEBIT_NOTE_EXCEEDS_BALANCE` (no negative balances; partial-invoice offset is a later allocation feature).
5. Apply reduces `invoice.balance_due = money(balance_due − amount)`, `invoice.updated_at = now`. **Does NOT change status/amount_paid/paid_at.** If balance hits 0, the invoice drops out of `open_ap_invoices`/aging/`amount_due_now` automatically (they filter `balance_due > 0`).
6. Idempotency: a second `apply` on an `APPLIED` note → `409 CONFLICT` ("Debit note already applied") — loud, no double-reduction.

**Auto note at dispatch:** created with `status=ISSUED` (supplier-approved return ⇒ credit agreed), `dn_number` gapless, `amount = return total_value (money())`.

---

## 8. Statement + aging integration (no query rewrites for aging)

- **AP aging**: no changes. The apply path reduces `balance_due`; `open_ap_invoices`, `ap_aging`, and the statement footer read it live.
- **Statement** (the AP ledger) — new doc type so applied notes appear as credits:
  1. `schemas/supplier_statements.py`: add `SUPPLIER_DEBIT_NOTE = "SUPPLIER_DEBIT_NOTE"` + label `"Supplier debit note"`; add `credited: Decimal` to `SupplierStatementTotals`.
  2. `ACTIVITY_ORDER`: `SUPPLIER_INVOICE: 0, SUPPLIER_DEBIT_NOTE: 1, SUPPLIER_PAYMENT: 2, SUPPLIER_PAYMENT_PENDING: 3`.
  3. New `debit_note_activity(note)` builder: `date = applied_at date`, `doc_type SUPPLIER_DEBIT_NOTE`, `number = dn_number`, `reference = reason`, `debit=ZERO`, `credit=amount`, `cleared_cash=True`, `payment_method=None`, `payment_status=None`. **Only `APPLIED` notes are shown** (the economic effect date is the apply date — keeps statement vs live `balance_due` consistent).
  4. `_load_adjustments` (new): batch-load `APPLIED` notes for include-set supplier invoices (or supplier-scoped); wire into `collect_activity` + `reconstruct_opening` (subtract applied-before-window) + `period_totals` (`credited` = applied-in-window), and add `"credited": money(...)` to totals dict.
- Doc-type enum is **Pydantic-only** — no migration.

---

## 9. Schemas

- `schemas/purchase_returns.py`: `PurchaseReturnItemCreate` (`grn_item_id`, `quantity` Decimal gt 0, `unit_price` Decimal gt 0, `return_type`, `notes`), `PurchaseReturnCreate` (`supplier_id`, `grn_id`, `return_date`, `reason`, `items` 1..N), `PurchaseReturnItemResponse` (incl. `stock_out_qty`, `total_price = money(qty × unit_price)`), `PurchaseReturnResponse` (header + `items`, `total_value` computed), pagination wrapper usage.
- `schemas/supplier_debit_notes.py`: `SupplierDebitNoteCreate` (manual; `supplier_id`, `issue_date`, `amount` gt 0, `reason`), `SupplierDebitNoteApplyRequest` (`supplier_invoice_id`), `SupplierDebitNoteResponse`, pagination wrapper usage.
- `schemas/supplier_statements.py`: add doc type + `credited` (see §8).
- Reuse `ErrorDetail`/`SuccessResponse`/`PaginatedResponse`/`PaginationMeta` from `schemas/common.py`.

---

## 10. Router surface (prefix `/api/v1`; wrapper responses; pagination on lists)

**`routers/purchase_returns.py`** (`tags=["Purchase Returns"]`):
`POST /purchase-returns` (201), `GET /purchase-returns` (filters: `supplier_id`, `grn_id`, `status`), `GET /purchase-returns/{id}`, `POST /purchase-returns/{id}/submit-for-supplier-approval`, `POST /purchase-returns/{id}/approve`, `POST /purchase-returns/{id}/dispatch`, `POST /purchase-returns/{id}/complete`, `POST /purchase-returns/{id}/reject`, `POST /purchase-returns/{id}/cancel`. All mutations deposit on `get_current_user` (role gate) + `get_current_workspace_id`.

**`routers/supplier_debit_notes.py`** (`tags=["Supplier Debit Notes"]`):
`POST /supplier-debit-notes` (201), `GET /supplier-debit-notes` (filters: `supplier_id`, `status`, `purchase_return_id`), `GET /supplier-debit-notes/{id}`, `POST /supplier-debit-notes/{id}/issue`, `POST /supplier-debit-notes/{id}/apply` (body `SupplierDebitNoteApplyRequest`), `POST /supplier-debit-notes/{id}/cancel`.

Wire both into `app/main.py` under `/api/v1`.

---

## 11. Services + number services (module layout)

- `services/purchase_return_number.py` — `PurchaseReturnNumberService.next_purchase_return_number(...)` → `PRN-YYYY-XXXX` (mirror `GRNNumberService`; model `PurchaseReturnCounter` PK `(workspace_id, year)`).
- `services/supplier_debit_note_number.py` — `SupplierDebitNoteNumberService.next_debit_note_number(...)` → `SDN-YYYY-XXXX` (model `SupplierDebitNoteCounter`).
- `services/purchase_return_service.py` — `create`, `get`, `list` (filters+pagination), `submit_for_supplier_approval`, `approve`, `dispatch` (stock-out + auto SDN), `complete`, `reject`, `cancel`; cap math `_remaining_accepted` / `_cumulative_returned`; `total_value`.
- `services/supplier_debit_note_service.py` — `create`, `get`, `list`, `issue`, `apply` (guards §7), `cancel`, `total` helpers.
- `services/grn_service.py` — fill GRN-004 hook (§5) calling `purchase_return_service.record_disposition_auto_items(...)`.

All money via `money()`/`qty_dec`; all mutations workspace-scoped; errors via `raise_error`.

---

## 12. Not in scope (explicit)

- Sales returns / AR credit-note auto-generation from sales returns (Pydantic `CreditNote` path already exists; sales-return is its own future wave).
- Allocating one debit note across multiple invoices (MVP = whole note → one invoice).
- Debit note "partial apply" and carry-forward supplier credit for over-applied/PAID-invoice cases (rejected loudly instead — §7 guard 3/4).
- `TransactionType` new enum value (`ISSUE` reused), per-quantity bin-level picking, return shipping/delivery documents, print/PDF, frontend, PDC-to-supplier, event/history table.
- **Tax/VAT**: return item `unit_price` is a snapshot; the SDN is a net amount with no VAT recomputation. VAT treatment of supplier returns is deferred to the supplier-credit tax wave (flag for finance/consult).

---

## 13. Alembic migration (one revision, down_revision `a3f4c7d9e1b2`)

Create + enums:
- `purchasereturnstatus` (`DRAFT,PENDING_SUPPLIER,APPROVED,DISPATCHED,COMPLETED,REJECTED,CANCELLED`)
- `purchasereturntype` (`QUALITY_ISSUE,DAMAGE,WRONG_ITEM,EXCESS`)
- `supplierdebitnotestatus` (`DRAFT,ISSUED,APPLIED,CANCELLED`)

Table order: `purchase_return_counters`, `purchase_returns` → `purchase_return_items`; `supplier_debit_note_counters`, `supplier_debit_notes`. FK/check rules:
- `purchase_return_items.quantity > 0` (check `chk_preturn_item_quantity_positive`), `stock_out_qty ≥ 0` default 0
- `purchase_return_items.unit_price > 0` (check on column) — not the composite guard
- `supplier_debit_notes.amount > 0` (check `chk_sdn_amount_positive`)
- Indexes on every FK + `prn_number`/`dn_number`.
- Downgrade drops tables (reverse order) then enums.

Sanity: `alembic upgrade head`, downgrade→upgrade round-trip, `alembic check` clean; guardian head pins in `tests/test_pdc.py` + `tests/test_pricing.py` re-pinned to the new head.

---

## 14. Tests (three files, Postgres `invoicesaas_test`, established harness)

**`tests/test_purchase_returns.py`** (seed GRN/GRNItem + SPO rows directly — accepted convention, avoids the 30-call API chain):
- Cap invariant: create with `quantity` > available → `400 RETURN_QTY_EXCEEDS_RECEIVED`; cumulative across two returns also capped.
- State machine: submit→approve→dispatch→complete happy path; illegal transitions → `400 INVALID_STATE` (e.g. dispatch from DRAFT, complete from APPROVED, cancel after dispatch).
- GRN-004: seed SPO + GRN + GRNItem, run disposition with rejected/damaged qty via service → DRAFT auto-return + auto-items (accumulate on second disposition); cap respected.
- Inventory: accepted-then-returned (manual return) → dispatch decrements `on_hand`; account with 0 accepted → no ledger rows; negative-stock guard.
- Ledger: `InventoryTransaction` rows have `transaction_type=ISSUE`, `reference_type="PRN"`, `reason="PURCHASE_RETURN"`.
- Isolation: other-workspace id → 404; member role mutation → 403.

**`tests/test_supplier_debit_notes.py`**:
- Manual create DRAFT → issue → apply reduces `supplier_invoice.balance_due`; `amount_paid`/`paid_at`/status untouched; `applied_at` + `applied_invoice_id` set.
- Guards: apply to PAID / pre-approved invoice → `400 INVALID_STATE`; amount > `balance_due` → `400 DEBIT_NOTE_EXCEEDS_BALANCE`; wrong supplier → `400 INVALID_STATE`; second apply → `409 CONFLICT`; cancel applied → `400 INVALID_STATE`.
- Dispatch auto-SDN: dispatch a return → `SDN-` ISSUED note exists with `amount = total_value`.
- Isolation: foreign note → 404; member apply → 403.
- AP aging + `ap-balance` reflect the reduced `balance_due`.

**`tests/test_supplier_statement_dn.py`**:
- Applied note in-window → `SUPPLIER_DEBIT_NOTE` credit line with running balance; opening reconstruction subtracts applied-before-window notes; `totals.credited` correct; `amount_due_now` reflects applied balance; `aging.buckets` current reduced.
- ISSUED-but-not-APPLIED note → **absent** from the statement (date-consistency rule §8).
- Workspace isolation 404.

---

## 15. Checklist

- [ ] Models + `models/__init__.py` exports; migration `nv` created + applied; round-trip + `alembic check`
- [ ] Number services + counters
- [ ] Purchase-return service + GRN-004 hook + stock-out + auto SDN
- [ ] SDN service + apply guards
- [ ] Statement doc type + `credited` + adjust-loaders
- [ ] Two routers + main.py wiring
- [ ] Three test files green; full suite green; ruff+black clean
- [ ] Guardian head pins updated
- [ ] `STATE.md` + `backend-execution-report.md` + **commit**