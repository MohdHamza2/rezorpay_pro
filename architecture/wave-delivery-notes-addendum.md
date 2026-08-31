# Delivery Note + stock ISSUE — Architecture Addendum (Gap 7)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `InventoryLevel` / `InventoryTransaction` / `TransactionType.ISSUE` (unused) / GRN `RECEIPT` posting / `CreditControlService.assert_not_hold` / LPO remaining / invoice items. Do **not** invent a second stock ledger, a `DeliveryOrder` module, or warehouse tables.
**Depends on:** Credit HOLD A–C (`e8e00f5`), Customer LPO (`8cf2480`), quotes, FTA invoices, Product Master.
**After this WP A–C:** tax credit notes (gap 10). Volume pricing (gap 8) can wait. Not this slice: transfers, cycle counts, sales returns, WhatsApp, OCR, Peppol, Arabic PDF.

Copy the LPO split: **WP-A API+Alembic+tests → WP-B UI+PDF → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

UAE name: **Delivery Note**. Code: `DeliveryNote`. Routes: `/delivery-notes`. Number: `DN-YYYY-XXXX`. UI: **Delivery Notes**. This is **not** a tax invoice and **not** a supplier GRN.

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| Sales | Quotes, LPO, invoices, credit HOLD live. **No** delivery-note model/router. Sales never decrements `on_hand`. |
| `TransactionType` | `INITIAL`, `RECEIPT`, `ISSUE`, `TRANSFER`, `ADJUSTMENT`. GRN posts **`RECEIPT`**. **`ISSUE` is unused.** |
| `InventoryLevel` | Bin-level `on_hand` / `reserved` / `damaged` Numeric(12,2), `on_hand >= 0`. `available` computed. Unique `(product_id, bin_id)`. |
| GRN post | `SELECT FOR UPDATE` on `InventoryLevel`; first bin if missing level; fail if warehouse has no bin. Does **not** always filter `workspace_id` on the lock query — **DN must filter `workspace_id`.** |
| `POST /inventory/adjust` | Any authenticated user. `on_hand += quantity`. Ledger `ADJUSTMENT`. No role, no reason enum, no product/warehouse workspace check. Negative result → 400. |
| LPO | `quantity` ordered, `quantity_invoiced` cache. **No** `quantity_delivered`. Invoice and LPO are independent children (partial invoices). |
| Invoice items | Optional `product_id`, optional `customer_purchase_order_item_id`. Ad-hoc lines exist. |
| Product | No `track_inventory` flag. Catalog vs ad-hoc = `product_id` present vs null. |
| `Workspace.block_do_on_hold` | Default True. Credit WP left it **unused**. `CREDIT_HOLD` is **400**. |
| `CreditEventReason` | `EVALUATE`, `PAYMENT`, `SEND_CHECK`, `RECEIVE_CHECK`. Add `DN_CONFIRM` this WP. |
| Settings UI | Has `block_po_on_hold`. Does **not** edit `block_do_on_hold`. |
| Layout | Sales: Clients, Quotations, LPO, Invoices. No Delivery Notes. |
| Alembic HEAD | `9f3a7c2e1d04` (`9f3a7c2e1d04_add_client_credit_control.py`). New revision **must** `down_revision = "9f3a7c2e1d04"`. Never rewrite credit/LPO/quotes/FTA history. |

---

## 1. ASCII — XOR parent → confirm ISSUE

```
  Source of truth (exactly one parent per DN):

    LPO (RECEIVED|PARTIAL|INVOICED)          Invoice (not CANCELLED)
         │                                        │
         │  remaining = ordered − Σ CONFIRMED     │  remaining = invoice qty − Σ CONFIRMED
         │  DN qty on that cpo_item_id            │  DN qty on that invoice_item_id
         │  (independent of quantity_invoiced)    │
         ▼                                        ▼
                    DeliveryNote  DN-YYYY-XXXX
                    DRAFT  (PUT / DELETE)
                       │
                       │  POST /{id}/confirm
                       │  HOLD + block_do_on_hold → 400 CREDIT_HOLD
                       │  catalog lines: ISSUE (−qty) on InventoryLevel
                       │  ad-hoc lines: no stock movement
                       ▼
                    CONFIRMED
                       │
                       │  POST /{id}/cancel
                       │  reverse: ISSUE (+qty) reference_type=DN_CANCEL
                       ▼
                    CANCELLED
```

PDF title **Delivery Note**. Invoice PDF stays **Tax Invoice**.

---

## 2. Number format — lock

**Format:** `DN-YYYY-XXXX` (e.g. `DN-2026-0001`).

**Mechanism:** `dn_counters` composite PK `(workspace_id, year)` + `DnNumberService` `SELECT FOR UPDATE`. Clone LPO/quote counters. Do **not** reuse `invoice_counters` / `quotation_counters` / `lpo_counters` / `spo_counters`. Soft-delete does **not** rewind. Failed create rolls back.

**Operational sequence**, not FTA-gapless. Delivery notes are not tax invoices.

---

## 3. Source of truth — XOR parent (lock)

User choice: invoice vs LPO vs either. **Lock: either, XOR — exactly one parent per DN.**

UAE electrical often **ships before or with** the tax invoice. LPO-only remaining would block walk-in sales. Invoice-only remaining would block ship-before-invoice. So:

| Parent | When | Remaining (cannot over-deliver) |
|---|---|---|
| `customer_purchase_order_id` | Contractor / LPO path | LPO line `quantity − Σ CONFIRMED DN qty` for that `cpo_item_id`. **Not** capped by `quantity_invoiced`. |
| `invoice_id` | Walk-in / quote→invoice, no LPO | Invoice line `quantity − Σ CONFIRMED DN qty` for that `invoice_item_id`. |

**Rules:**

- Exactly one of `customer_purchase_order_id` / `invoice_id` is set. Both or neither → **422**.
- If the invoice has `customer_purchase_order_id`, traders still create the DN against the **LPO** (physical remaining). Do not set both FKs.
- Client on the DN **must** equal the parent’s `client_id`.
- LPO parent status ∈ {RECEIVED, PARTIAL, INVOICED}. DRAFT/CANCELLED LPO → 403 `INVALID_STATE`.
- Invoice parent: not deleted, not `CANCELLED`. DRAFT invoice **allowed** (ship with unsigned tax invoice).
- Each DN line **must** reference a parent line (`customer_purchase_order_item_id` XOR `invoice_item_id` matching the header). Unknown / other-parent line → **404**.
- Cannot invent SKUs not on the parent.
- Over-deliver → **400** `VALIDATION_ERROR` `field=quantity`. DRAFT DNs do **not** consume remaining; CONFIRMED do. Concurrent confirm: `SELECT FOR UPDATE` the DN **and** parent header.

Add `quantity_delivered` Numeric(10,2) default 0 on **LPO items** (cache, like invoiced). Recalc on DN confirm/cancel. Invoice items: **no** delivered column (compute on GET if needed).

Multiple DNs per parent (partial deliveries). Same pattern as many invoices per LPO.

---

## 4. State machine — lock

Enum `DeliveryNoteStatus`: `DRAFT | CONFIRMED | CANCELLED`

**Not in this WP:** DISPATCHED, PARTIAL, DELIVERED, RETURNED, reserve/RELEASE. One confirm ships **all lines on that DN** (partial *order* = another DRAFT DN).

```
              ┌────────────┐
              │   DRAFT    │  PUT / DELETE
              └──────┬─────┘
           /confirm  │
                     ▼
              ┌────────────┐
              │ CONFIRMED  │  stock ISSUE posted (catalog lines)
              └──────┬─────┘
            /cancel  │
                     ▼
              ┌────────────┐
              │ CANCELLED  │  stock reversed (ISSUE +qty)
              └────────────┘
```

| From | To | How |
|---|---|---|
| (create) | DRAFT | `POST /delivery-notes` |
| DRAFT | CONFIRMED | `POST /{id}/confirm` — ISSUE stock |
| DRAFT | (gone) | `DELETE` soft-delete (`deleted_at`) |
| CONFIRMED | CANCELLED | `POST /{id}/cancel` `{reason?}` — reverse stock |

**Confirm once (idempotent):** already CONFIRMED → **200** same payload, **no** second ISSUE. Lock DN row `FOR UPDATE`.

**Cancel DRAFT:** use DELETE, not `/cancel`. `/cancel` is CONFIRMED only.

No un-confirm except cancel. CANCELLED is terminal.

---

## 5. Lines — stock vs ad-hoc

DN lines are **qty + identity**, not money (no tax/price). Description + SKU snapshot for the PDF.

| Column | Lock |
|---|---|
| `product_id` | **Required to move stock.** Copied from parent if parent has one. Other-workspace product → 404. Inactive product → **400** on create/confirm. |
| Ad-hoc parent line (`product_id` null) | Allowed. **No** `InventoryTransaction`. Confirm still succeeds. |
| `quantity` | Numeric(10,2) `> 0`. ≤ remaining. |
| `uom_id` / `sku_snapshot` / `description` | Copy from parent; description required. |
| `bin_id` | Optional per line; default header bin. |

**Confirm stock rule:** for each line with `product_id`:

```
available = on_hand - reserved - damaged
if available < qty → 400 VALIDATION_ERROR field=quantity
```

No `allow_negative_stock` flag. CheckConstraint `on_hand >= 0` stays. `reserved` is **not** used this WP (no reservation table). Do **not** add `RESERVE`/`RELEASE` to `TransactionType`.

At least one line required. All-ad-hoc DN: CONFIRMED with zero ledger rows (commercial delivery of non-stock items).

---

## 6. HOLD

Reuse `CreditControlService.assert_not_hold`.

- On **confirm only**, and **only if** `workspace.block_do_on_hold` is True (live default True).
- HTTP **400** `CREDIT_HOLD`, `field=client.credit_status`. Same as send/receive.
- WARNING does not block.
- DRAFT create/PUT never blocked.
- Add `CreditEventReason.DN_CONFIRM` (Alembic `ALTER TYPE crediteventreason ADD VALUE 'DN_CONFIRM'`).
- Payments / invoice void / LPO receive rules unchanged.

WP-B Settings: expose `block_do_on_hold` (credit WP deferred this checkbox).

---

## 7. Inventory posting — reuse GRN pattern

New helper `app/services/inventory_ledger.py` (keep GRN as-is unless a one-line workspace filter is trivial). DN **must not** increment `on_hand` without a ledger row.

**Confirm** (catalog line), same transaction as status flip:

1. `SELECT InventoryLevel … workspace_id, product_id, warehouse_id, bin_id FOR UPDATE`.
2. If missing: create level at 0 (bin must exist and belong to that warehouse + workspace).
3. If `available < qty` → 400.
4. `on_hand -= qty`.
5. `InventoryTransaction`: `type=ISSUE`, `quantity= −qty` (live comment: negative = out), `source_bin_id=bin`, `destination_bin_id=null`, `reference_type="DN"`, `reference_id=delivery_note_item.id`, `user_id`.

**Cancel CONFIRMED:**

1. Same row lock.
2. `on_hand += qty`.
3. `InventoryTransaction`: `type=ISSUE`, `quantity= +qty`, `destination_bin_id=bin`, `reference_type="DN_CANCEL"`, `reference_id=same item id`.

Ledger is **immutable** (no PUT/DELETE on transactions). Decimal Numeric(12,2), never float.

**Warehouse / bin:** header `warehouse_id` required, same workspace, `is_active`. Optional header `bin_id`; default **first active bin** of that warehouse (GRN). No bin → **400**. Other-workspace warehouse → **404**.

Do not post GRN `RECEIPT` from DN. Do not change SPO/GRN services except optional shared ledger helper.

---

## 8. `POST /inventory/adjust` — admin back door (lock)

**Keep the endpoint.** Sales stock exit is DN confirm, not adjust. Adjust stays the opening-balance / damage / count door.

Tighten in this WP (same Alembic/service PR is fine; no new table):

| Rule | Lock |
|---|---|
| Role | **OWNER or ADMIN** only. MEMBER → **403** `INSUFFICIENT_PERMISSIONS`. |
| Reason | Required allow-list: `DAMAGE` \| `COUNT_CORRECTION` \| `LOSS` \| `OPENING` \| `OTHER`. Extra/missing → 422. |
| Notes | Required, min 3 chars (was free `reference`). Store on txn: `reference_type="ADJUSTMENT"`, `reference_id` null; put reason+notes in a new optional `InventoryTransaction.notes` Text **or** prefix `reference_type` as `ADJUSTMENT:{reason}` if adding a column is heavier — **lock: add nullable `notes` Text + `reason` String(30) on `inventory_transactions`**. |
| Isolation | Product, warehouse, bin must belong to JWT workspace → else **404**. |
| Qty | Decimal ≠ 0. `on_hand + qty >= 0` else 400. Always write `ADJUSTMENT` ledger (already). `FOR UPDATE` (already). |
| UI | Inventory page may keep adjust for ADMIN only. MEMBER sees levels read-only. |

Do not remove adjust. Do not let DN confirm call adjust.

---

## 9. PDF (WP-B)

New `frontend/src/components/pdf/DeliveryNotePDF.tsx` (clone LPO layout).

| | Delivery Note | Tax Invoice |
|---|---|---|
| Title | **Delivery Note** | Tax Invoice |
| Number | `DN-YYYY-XXXX` | `INV-YYYY-XXXX` |
| Refs | LPO number **or** invoice number | — |
| Lines | SKU, description, qty (no VAT/price required) | net / VAT / gross |
| Language | **English only** | English |
| Watermark | CANCELLED | CANCELLED |

Seller name/address/TRN print if present; **not** required to confirm. Client-side `@react-pdf/renderer`. Not stored at confirm.

---

## 10. Schema (Alembic **yes**)

`down_revision = "9f3a7c2e1d04"`. Never rewrite history.

### `dn_counters`

Same shape as `lpo_counters`.

### `delivery_notes`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID FK index | |
| `client_id` | UUID FK index | = parent client |
| `customer_purchase_order_id` | UUID FK nullable index | XOR with invoice_id |
| `invoice_id` | UUID FK nullable index | |
| `warehouse_id` | UUID FK | |
| `bin_id` | UUID FK nullable | default first active bin |
| `dn_number` | `String(50)` | Unique `(workspace_id, dn_number)` |
| `status` | ENUM above | default DRAFT |
| `delivery_date` | Date NOT NULL | default UTC today |
| `shipping_address` | Text nullable | default client.address |
| `vehicle_number` / `driver_name` | `String(100)` nullable | |
| `notes` / `cancellation_reason` | Text nullable | |
| `confirmed_by` / `confirmed_at` | UUID / timestamptz nullable | set on confirm |
| `created_at` / `updated_at` / `deleted_at` | timestamptz | DRAFT soft-delete |

Check: `(customer_purchase_order_id IS NULL) <> (invoice_id IS NULL)` (one parent).

### `delivery_note_items`

Parent line FK (one of the two, matching header), `product_id` nullable, `uom_id`, `sku_snapshot`, `description`, `quantity` Numeric(10,2) > 0, optional `bin_id`, timestamps.

### `delivery_note_events`

Clone LPO events: `DN_CREATED`, `DN_UPDATED`, `DN_CONFIRMED`, `DN_CANCELLED`.

### Other

- `customer_purchase_order_items.quantity_delivered` Numeric(10,2) NOT NULL default 0; check `>= 0` and `<= quantity`.
- `inventory_transactions.reason` String(30) nullable; `notes` Text nullable.
- PG enum value `DN_CONFIRM` on `crediteventreason`.
- No `stock_reservations` table.

---

## 11. API

Base `/api/v1`. Prefix `/delivery-notes`. JWT on all. `SuccessResponse` / `PaginatedResponse`. Extra keys **422**. Decimal qty. Cross-tenant **404**.

```
POST   /delivery-notes
GET    /delivery-notes?status&client_id&customer_purchase_order_id&invoice_id&search&page&per_page
GET    /delivery-notes/{id}
PUT    /delivery-notes/{id}                 DRAFT only
DELETE /delivery-notes/{id}                 DRAFT soft-delete
POST   /delivery-notes/{id}/confirm         DRAFT → CONFIRMED + ISSUE
POST   /delivery-notes/{id}/cancel          CONFIRMED → CANCELLED + reverse
```

Create body: exactly one parent id, `warehouse_id`, optional `bin_id` / dates / address / vehicle / items (or omit items to copy **all remaining** catalog+ad-hoc parent lines).

Confirm: empty body. Cancel: `{ reason?: str }`.

No `/reserve`, `/dispatch` alias, Idempotency-Key (row lock is enough), or DN money endpoints.

LPO GET may add `quantity_delivered` / `quantity_undelivered` (`quantity - quantity_delivered`).

Adjust: `POST /inventory/adjust` body `{ product_id, warehouse_id, bin_id, quantity, reason, notes }` — drop free-form `reference` or keep as alias of `notes` for one release then forbid extra.

---

## 12. Module boundaries

| Layer | Owns |
|---|---|
| `routers/delivery_notes.py` | HTTP, wrapper |
| `services/delivery_note_service.py` | XOR parent, remaining, state, HOLD gate |
| `services/dn_number.py` | FOR UPDATE `DN-YYYY-XXXX` |
| `services/inventory_ledger.py` | ISSUE ±qty, FOR UPDATE, workspace 404 |
| `CreditControlService.assert_not_hold` | confirm if `block_do_on_hold` |
| `routers/inventory.py` `adjust` | role + reason; move logic into ledger/service |

Files < 500 lines. Do not fork GRN posting formulas (same Decimal, same lock).

---

## 13. Tests — `backend/tests/test_delivery_notes.py`

PostgreSQL only.

1. Create from LPO → `DN-{year}-0001`; second `0002`. Concurrent unique.
2. Both parents or neither → 422. Cross-workspace LPO/invoice/warehouse → 404.
3. LPO remaining: ordered 100, confirm 40 → `quantity_delivered` 40; second DN 70 → 400; second 60 → CONFIRMED 100.
4. LPO delivered 40 with `quantity_invoiced` 0 still OK (ship before invoice).
5. Invoice-backed DN: cannot exceed invoice line qty. LPO-linked invoice still uses **LPO** parent when creating from LPO.
6. Catalog confirm: `on_hand` decreases; `ISSUE` qty negative; `reference_type=DN`. Ad-hoc line: no txn.
7. Insufficient available → 400; `on_hand` unchanged; DN stays DRAFT.
8. Concurrent confirm last 10 units: one 200 CONFIRMED, one 400; never `on_hand < 0`.
9. Second confirm → 200, one ISSUE row per catalog line.
10. Cancel CONFIRMED: `on_hand` restored; `DN_CANCEL` txn; status CANCELLED; LPO `quantity_delivered` 0.
11. HOLD + `block_do_on_hold=true` → confirm 400 `CREDIT_HOLD`; flag false → confirm 200.
12. PUT/DELETE non-DRAFT → 403. Isolation workspace B 404.
13. Adjust: MEMBER 403; ADMIN with reason `OPENING` 200 + ledger; other-workspace product 404; extra key 422.
14. `alembic upgrade head` + `alembic check` clean.

Do not break GRN receipt tests, LPO over-invoice, credit HOLD send/receive, FTA send, payment immutability.

---

## 14. WP split

### WP-A — API + Alembic + tests

Models, migration from `9f3a7c2e1d04`, DN service + ledger, confirm ISSUE, cancel reverse, HOLD gate, LPO `quantity_delivered`, tighten adjust, pytest §13. **No frontend.**

**Acceptance:** §13 green; `alembic check`; confirm issues stock; cancel reverses; cannot over-deliver vs chosen parent; HOLD 400 when `block_do_on_hold`; adjust ADMIN+reason; 404 isolation; Decimal.

### WP-B — UI + PDF

- Layout Sales: **Delivery Notes** (`/delivery-notes`) after LPO.
- Create from LPO remaining or from invoice remaining (XOR). Warehouse/bin picker.
- Confirm / Cancel. Show delivered vs ordered.
- `DeliveryNotePDF`: title **Delivery Note**, not Tax Invoice. English.
- Settings: `block_do_on_hold`.
- Inventory: MEMBER read-only; ADMIN adjust with reason.

**Acceptance:** `npm run build`; confirm reduces levels; Tax Invoice / Quotation / LPO PDFs unchanged.

### WP-C — Playwright

Register → warehouse+bin → product → GRN or ADMIN opening adjust → LPO receive → DN confirm → levels drop. HOLD + `block_do_on_hold` blocks confirm. Other workspace DN URL 404.

**Acceptance:** local API + Postgres. No transfers, counts, WhatsApp, credit notes.

---

## 15. Drift vs paper

| Paper | This WP |
|---|---|
| `DO-YYYY-XXXX` / DeliveryOrder | **`DN-YYYY-XXXX` / DeliveryNote** |
| DISPATCHED / reserve / Idempotency-Key | **CONFIRMED**; no reserve |
| Gapless legal DN | **Operational** sequence |
| HOLD 403 | **400 CREDIT_HOLD** |
| Remaining vs invoice **and** LPO blended | **XOR one parent** |
| RETURNS via CN | **Cancel reverse only**; CN is gap 10 |
| Kill `/inventory/adjust` | **Keep**, ADMIN + reason + ledger |

---

## 16. NOT in this WP

Transfers, cycle counts, reservations, sales-return receiving, tax credit notes, WhatsApp, Arabic, Peppol, OCR, negative stock, volume pricing, FTA invoice field changes, supplier SPO/GRN behavior changes (except optional shared ledger helper).

---

## 17. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic **yes**, `down_revision = "9f3a7c2e1d04"` only.
3. Confirm = `ISSUE` (−qty). Cancel CONFIRMED = `ISSUE` (+qty). Never adjust-from-DN.
4. XOR parent. Over-deliver 400. HOLD confirm uses `block_do_on_hold`.
5. WP-A tests green before WP-B.
6. Next after A–C: **tax credit notes (gap 10)**.
