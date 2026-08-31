# WP-A Customer LPO — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0 tenant-leak or float-money).
**Spec:** `architecture/wave-customer-lpo-addendum.md`, `.agents/reports/architect-customer-lpo-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B (Sales nav **LPO** at SPA `/lpos`, PDF title **LPO**) may start.

No P0 tenant leak. No float money columns or `float()` on the LPO / line-money / invoice-slice path. Partial invoices go through `InvoiceService.create_invoice` with `quotation_id=None`. FTA send gates are unchanged (`mark_as_sent` always `assert_fta_sendable`). Alembic is a linear new revision on `cb01b6bef962`. Reviewer re-ran the claimed suite: **70 passed** (69.96s) on PostgreSQL `_test`. `alembic heads` is `59084165d346` only. `alembic check`: no new upgrade operations.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 | **PASS.** `get_visible` filters `workspace_id` + `deleted_at`. GET/PUT/receive/invoices/cancel → 404 for workspace B (`test_isolation_workspace_b_404`). Convert-to-lpo other-workspace quote → 404 (`test_quotations.test_isolation_workspace_b_404`). JWT workspace never from body (`extra="forbid"`). Client create 404s other-workspace `client_id`. |
| 2 | Decimal; over-invoice 400; remaining math (DRAFT counts) | **PASS with nit W1.** Shared `line_money.money()` ROUND_HALF_UP. Columns `Numeric(12,2)` / qty `Numeric(10,2)`. Over-qty 101/100 → 400 `VALIDATION_ERROR` `field=quantity`, LPO unchanged. Countable invoices: `deleted_at IS NULL` and `status != CANCELLED` (DRAFT counts). LPO row `SELECT FOR UPDATE` before slice. Concurrent full remaining: 201+400, `quantity_invoiced` never exceeds ordered. See W1 for duplicate line ids in one body. |
| 3 | States; `/receive`; CANCELLED rules | **PASS.** `DRAFT → RECEIVED → PARTIAL → INVOICED`. PUT/DELETE/receive non-DRAFT → 403 `INVALID_STATE`. DRAFT `DELETE` soft-deletes (no CANCELLED row). `/cancel` RECEIVED only; with countable invoice → 403; without → CANCELLED; `/invoices` after cancel → 403. No `/confirm`, no CONFIRMED/CLOSED. |
| 4 | Quote convert mutex 409; idempotent 200 | **PASS.** ACCEPTED → DRAFT LPO, quote CONVERTED, lines frozen, notes prefix. Second convert-to-lpo → 200 same id. Convert-to-invoice after LPO → 409 `CONFLICT` `field=quotation_id`. Convert-to-lpo after quote→invoice → 409. SENT/DRAFT → 403. Quote `SELECT FOR UPDATE` on convert. Unique `customer_purchase_orders.quotation_id`. Soft-deleted invoice still blocks convert-to-lpo (existing quotes rule). |
| 5 | Partial invoices via InvoiceService; many per LPO; `quotation_id` null | **PASS.** `CustomerPurchaseOrderService.create_invoices` → `InvoiceService.create_invoice(..., quotation_id=None, customer_purchase_order_id=lpo.id)`. Omit items = all remaining. 40 then 60 → PARTIAL then INVOICED; third `/invoices` → 400. Invoice items persist `customer_purchase_order_item_id`. Frozen `unit_price`/`tax_rate` passed explicitly so `_line_unit_price` does not hit DEFAULT_SALES. Header LPO totals stay ordered qty (`recalculate` not re-run on invoice). |
| 6 | Recalc on void / DRAFT delete | **PASS.** Invoice router `DELETE` calls `InvoiceService.soft_delete_draft` which sets `deleted_at` then `recalc_invoiced`. `void_invoice` sets CANCELLED then recalc. Delete DRAFT invoice → remaining restored, LPO RECEIVED. Void SENT (after FTA-valid send) → remaining restored. |
| 7 | PUT blocked on LPO-linked invoices | **PASS.** `InvoiceService.update_draft` 403 `INVALID_STATE` when `customer_purchase_order_id` is set. Tested. Walk-in `POST /invoices` cannot attach an LPO (`InvoiceCreate` `extra="forbid"`, no CPO field). |
| 8 | `LPO-YYYY-XXXX` not INV/QUO/SPO counters | **PASS.** New `lpo_counters` + `LpoNumberService` `SELECT FOR UPDATE`. Prefix `LPO-`. Soft-delete does not rewind (`0002` deleted → next `0003`). Concurrent 10 creates unique sequential `0001`–`0010`. `invoice_counters` / `quotation_counters` / `spo_counters` untouched. |
| 9 | FTA send still gated | **PASS.** LPO `/invoices` creates DRAFT; `invoice_kind` and seller snapshots null. Send without TRN → `FTA_SEND_BLOCKED` 400. `mark_as_sent` still always `assert_fta_sendable`. No send-on-create. |
| 10 | Alembic linear; unique `invoices.quotation_id` kept | **PASS.** `59084165d346` `down_revision = "cb01b6bef962"`. Single head. Quotes/FTA/product revisions not rewritten. Adds `invoices.customer_purchase_order_id` indexed **not** unique; `invoice_items.customer_purchase_order_item_id` indexed FK. Does not drop `ix_invoices_quotation_id` unique. Partial unique `uq_cpo_workspace_client_po_number` WHERE `customer_po_number IS NOT NULL`. `alembic check` clean. |

---

## Findings

### Critical (P0)

None. No tenant leak on LPO GET/mutate/receive/invoice/cancel or quote convert-to-lpo. No `Float` / `float()` on money. Public invoice create cannot set `customer_purchase_order_id` or `quotation_id`.

### Warning

**W1 — Duplicate `customer_purchase_order_item_id` in one `/invoices` body can over-invoice**
`_resolve_slices` compares each requested qty to the line’s remaining **before this request**, and does not accumulate qty already sliced in the same payload. Two rows `{line_id, 60}` + `{line_id, 60}` against remaining 100 both pass; `InvoiceService` writes two items (qty 120). `recalc_invoiced` then **clamps** `quantity_invoiced` to `quantity`, so GET LPO looks clean while the tax invoice over-states qty. Concurrent two POSTs are serialized by LPO `FOR UPDATE` and are fine. Single-line `quantity > remaining` is 400. Fix: per-line running remaining in `_resolve_slices` (or 400 on duplicate ids). Not a tenant leak / not float money — do not block WP-B.

**W2 — `converted_lpo_id` hydration includes soft-deleted LPOs**
`map_converted_lpo_ids` filters `workspace_id` but not `deleted_at`. After a converted LPO is DRAFT-deleted, GET quote can still show `converted_lpo_id` pointing at a 404 LPO (convert-to-lpo correctly 409s and does not recreate). WP-B should treat that id as possibly gone. Same class of nit as quotations W3 (invoice hydration), now fixed there for invoices.

**W3 — `create()` maps every `IntegrityError` to customer PO 409**
Flush failure (unique `lpo_number`, unique `quotation_id`, or unique customer PO) all become HTTP 409 `field=customer_po_number` after `session.rollback()`. Duplicate customer PO is also pre-checked. Concurrent first-counter insert is handled in `LpoNumberService` (same rollback-retry as QUO/INV). Wrong field on a rare unique-number collision only.

### Info

**I1 — VARCHAR lengths vs spec `String(50)` / `String(100)`**
Migration uses unbounded `AutoString()` for `lpo_number`, `customer_po_number`, `sku_snapshot`, `description`. Models’ `max_length` is Pydantic-side. `alembic check` is clean. Same autogenerate style as quotations.

**I2 — Soft-deleted DRAFT still occupies `customer_po_number` uniqueness**
Partial unique index and `assert_unique_customer_po` do **not** exclude `deleted_at`. Matches spec’s index definition. After deleting a draft, the same client cannot reuse `PO-001` (409). Internal `lpo_number` correctly does not rewind. WP-B should surface the 409 clearly.

**I3 — Spec §11 gaps in pytest (behavior present)**
Covered: numbering, customer PO unique-per-client, tax/XOR/extra/USD, isolation GET/PUT/receive/invoices/cancel, non-DRAFT 403, quote convert + mutex, receive→invoice all remaining + FTA block, partial then full, over-invoice, concurrent `/invoices`, DRAFT invoice delete, void restore, PUT LPO-linked 403, cancel rules, concurrent LPO numbers.
Not automated: DELETE isolation 404 (same `_load_or_404`), unknown line id 404, W1 duplicate line ids, discount-amount pro-rate leftover, convert-to-lpo after LPO soft-delete 409 (quote-side 409 after invoice delete is tested), whitespace `customer_po_number` → NULL, list pagination wrapper, `alembic upgrade head` in pytest. Reviewer ran `alembic check` and 70 tests.

**I4 — Combined pytest on a dirty `_test` DB can ERROR**
Each file’s module-scoped fixture `drop_all` / `create_all` on shared `invoicesaas_test`. A first combined run in this review hit IntegrityError (45 errors); a retry of the same 70 was green. Run files alone or ensure the test DB is idle. Not a product defect.

**I5 — `/invoices` when remaining is 0 returns 400 not 403**
Forbidden table says 403 unless RECEIVED/PARTIAL. Spec §11.10 and the test expect **400** `VALIDATION_ERROR` for a third full invoice. Implementation matches the test lock. Empty `items: []` is treated as omit-all (falsy list), not “nothing selected”.

**I6 — Convert OpenAPI default is 200**
Runtime sets 201 vs 200 on `Response.status_code` (same as quote convert-to-invoice). Fine for WP-B if the client uses the HTTP status.

**I7 — Style / split**
`customer_po_service.py` is 551 lines (spec asked &lt; 500; support module already exists). Function-level schema imports in `serialize*` clone quotations/invoices. `recalc_invoiced` / `invoiced_qty_map` / `has_countable_invoice` key by LPO id without `Invoice.workspace_id` (defense in depth; API cannot plant a cross-tenant CPO FK). Number year uses `datetime.now().year` (naive local), cloned from QUO/INV.

**I8 — No confirm / SPO / email**
No `/confirm`, no convert-to-cpo alias, no 501 stubs, no SPO/GRN edits. Routes JWT via `get_current_user` / `get_current_workspace_id` (list/GET/DELETE use workspace dep, which requires an active user). Test file is `test_customer_lpos.py` not spec’s `test_customer_purchase_orders.py`.

---

## Isolation (checklist 1)

Every LPO load used by HTTP:

```python
.where(CustomerPurchaseOrder.id == lpo_id)
.where(CustomerPurchaseOrder.workspace_id == workspace_id)
.where(CustomerPurchaseOrder.deleted_at.is_(None))
```

Quote convert-to-lpo uses the same quote `get_visible` workspace filter. `existing_converted_lpo` / `map_converted_lpo_ids` also filter `CustomerPurchaseOrder.workspace_id`. Invoice list `customer_purchase_order_id` is applied **after** `Invoice.workspace_id` (empty list, not a leak).

---

## Remaining math (checklist 2)

Source of truth: `SUM(invoice_items.quantity)` joined to countable parent invoices, written back to `quantity_invoiced` in `recalc_invoiced` after create/void/DRAFT delete. Router `/invoices` locks the LPO row first. Discount-amount slices pro-rate `money(discount_amount * invoice_qty / quantity)` and cap with leftover across invoices. Percent discounts copy through. Inactive catalog products on invoice-from-LPO become ad-hoc (omit `product_id`) so send/create does not 400.

---

## Alembic (checklist 10)

```
cb01b6bef962 (quotations) → 59084165d346 (customer LPOs)  [HEAD]
```

Downgrade drops FKs/indexes/tables then `DROP TYPE IF EXISTS` for `customerpurchaseordereventtype` and `customerpurchaseorderstatus`. ENUMs match models: `DRAFT|RECEIVED|PARTIAL|INVOICED|CANCELLED` and event types `CPO_CREATED|CPO_UPDATED|CPO_RECEIVED|CPO_INVOICE_CREATED|CPO_CANCELLED|CPO_RECALC`. Check constraints: totals ≥ 0, `quantity > 0`, `quantity_invoiced >= 0`, `quantity_invoiced <= quantity`.

---

## WP-B gate

**APPROVE_WITH_NITS** — WP-B UI `/lpos` + `LpoPDF` (title **LPO**) may start.

Please fold **W1** (accumulate remaining per line in one `/invoices` body) into WP-A follow-up or early WP-B backend patch so traders cannot over-invoice by repeating a line id. **W2** is UI-safe if converted LPO links tolerate 404. Do not start OCR, credit HOLD, or delivery notes.
