# WP-A–C Delivery Notes + stock ISSUE — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full slice — WP-A API+Alembic+pytest, WP-B UI/PDF, WP-C Playwright. Review only. No git commit. No feature work (no P0 tenant leak, float stock, or double-issue found).
**Spec:** `architecture/wave-delivery-notes-addendum.md`, `.agents/reports/wp-a-delivery-notes-review.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-A–C may be committed when asked. Next gap is **tax credit notes (gap 10)**. Do not implement that here.

No P0 tenant leak on DN GET/list/confirm/cancel or adjust product/warehouse/bin. Qty and `on_hand` on the ISSUE path are `Numeric` + `Decimal` (`qty_dec` = `Decimal(str(value))`) — no `float()` in ledger/service. Confirm is idempotent (no second `ISSUE`); cancel is CONFIRMED-only (one reverse); concurrent last-units confirm is serialized by DN `FOR UPDATE` + parent header `FOR UPDATE` + `InventoryLevel` `FOR UPDATE`. Alembic is a linear new revision on credit HEAD `9f3a7c2e1d04`. Playwright suite claimed **14 passed** (stock 10→8, HOLD confirm 400, isolation 404) in `.agents/reports/frontend-execution-report.md`. This pass is static; pytest/Playwright were **not re-run**.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 API + e2e | **PASS.** `get_visible` filters `id` + `workspace_id` + `deleted_at IS NULL`. Cross-workspace GET/confirm → 404 (pytest + Playwright `delivery-note-isolation.spec.ts`). Create from other-workspace LPO/invoice/warehouse → 404 (pytest). Adjust other-workspace product → 404 (pytest). Parent/warehouse/bin/catalog product load JWT workspace. List filters `workspace_id`; workspace B list is `[]`. JWT workspace from auth deps, never from body. UI detail keys off **HTTP 404** (`isHttpNotFound`), not `error.code === "NOT_FOUND"` (WP-A W1). |
| 2 | Decimal stock; `FOR UPDATE` | **PASS.** DN line `Numeric(10,2)`; levels/txns `Numeric(12,2)`. Schemas `Decimal`. Ledger `qty_dec` never `float()`. Confirm: DN row `FOR UPDATE` (router) + parent header `FOR UPDATE` + `lock_or_create_level` `SELECT InventoryLevel … workspace_id, product_id, warehouse_id, bin_id FOR UPDATE`. `available = on_hand - reserved - damaged`; insufficient → 400 `field=quantity` before decrement. CheckConstraint `on_hand >= 0`. DN has no money columns. |
| 3 | Over-deliver 400; remaining vs invoiced | **PASS.** XOR schema + DB `check_dn_parent_xor` / `check_dn_item_parent_xor`. Both/neither/extra key → 422. Unknown / other-parent line → 404. Over-deliver → 400 `VALIDATION_ERROR` `field=quantity`. LPO remaining = ordered − Σ CONFIRMED DN qty for that `cpo_item_id` — **does not read `quantity_invoiced`**. Pytest: confirm 40 with invoiced 0; 70 → 400; 60 → CONFIRMED 100. Invoice-backed remaining = invoice qty − CONFIRMED DN qty; 11 vs 10 → 400. LPO-linked invoice still uses LPO parent when creating from LPO (`invoice_id` null). |
| 4 | Confirm idempotent; cancel reverse once | **PASS.** Already `CONFIRMED` → 200 same payload, skip `_issue_stock`. Router locks DN `FOR UPDATE` first. `/cancel` requires `CONFIRMED`; DRAFT must DELETE (403). Cancel posts `ISSUE` `+qty` `reference_type=DN_CANCEL`, sets `CANCELLED` (terminal), recals `quantity_delivered`. Second cancel cannot re-enter (status gate + row lock). Pytest: second confirm 200, **one** `ISSUE` row; cancel restores `on_hand` and delivered cache to 0. |
| 5 | `CREDIT_HOLD` only on confirm when flag on | **PASS.** `_assert_hold` only from `confirm`. Flag false → return. Flag true → `CreditControlService.assert_not_hold(..., DN_CONFIRM)` → 400 `CREDIT_HOLD` `field=client.credit_status`. WARNING does not raise. Create/PUT have no hold gate. Settings exposes `block_do_on_hold` (`settings-block-do-on-hold`). Pytest + Playwright HOLD request-only: flag on → 400 DRAFT; flag off → 200. UI confirm toasts `CREDIT_HOLD` without interceptor duplicate (`HANDLED_TOAST_CODES`). |
| 6 | Adjust not used by DN | **PASS.** `_issue_stock` → `post_issue` only (`TransactionType.ISSUE`). No `adjust(` in delivery-note service/support. Adjust stays OWNER/ADMIN back door with reason allow-list + notes ≥ 3; MEMBER 403 `INSUFFICIENT_PERMISSIONS`. Playwright opening stock uses ADMIN `OPENING` adjust, not DN. Inventory **page** still has no adjust form (warehouse stub) — see I3. |
| 7 | PDF title Delivery Note | **PASS.** `DeliveryNotePDF` title **Delivery Note**; HTML preview `dn-pdf-title` **Delivery Note**. No VAT/price columns. CANCELLED watermark. English Helvetica. Footer “not a tax invoice.” Playwright asserts title and `pdf-title` count 0. Unchanged: Invoice **Tax Invoice**, Quotation **Quotation**, LPO **LPO**. |
| 8 | Playwright stock drop + 404 | **PASS (claimed).** Suite **14 passed** (frontend-execution-report): catalog LPO confirm opening 10 → ship 2 → `on_hand` 8; HOLD confirm 400 `CREDIT_HOLD`; workspace B GET DN 404 not 403. Product/FTA/quote/LPO/credit specs still in that run. This review did not re-run Playwright. |
| 9 | Invoice-parent DN only API? | **NIT (not a miss of XOR).** API + WP-B form both support invoice remaining (radio `dn-parent-type-invoice`). Pytest covers invoice over-deliver. Playwright happy path is **LPO remaining only** (addendum WP-C). Detail “delivered vs ordered” table is LPO-only. Invoice remaining is computed in the browser (`confirmedInvoiceQtyMap`, `Number()`, `per_page: 100`) because invoice items have no `quantity_delivered` column (spec lock). |
| 10 | Alembic linear | **PASS.** `a7c4e9d2b105` `down_revision = "9f3a7c2e1d04"` only. No other revision parented on credit HEAD. Tables `dn_counters`, `delivery_notes`, `delivery_note_items`, `delivery_note_events`; `quantity_delivered` + checks; `inventory_transactions.reason`/`notes`; `ALTER TYPE crediteventreason ADD VALUE IF NOT EXISTS 'DN_CONFIRM'`. No `stock_reservations`. Credit/LPO/quotes/FTA history not rewritten. |

---

## Findings

### Critical (P0)

None. Cross-tenant DN id is 404 with no DN JSON leak. Cross-tenant parent/warehouse/product is 404. Stock ISSUE is Decimal/`Numeric`, not float. Double-issue of the same DN is blocked by `FOR UPDATE` + CONFIRMED short-circuit. Two DNs over the last units cannot drive `on_hand < 0` on the HTTP confirm path. Cancel reverse cannot run twice.

### Warning

**W1 — Isolation 404 wrapper code is `HTTP_ERROR` (carried from WP-A)**
`_load_or_404` raises `HTTPException(404, "Delivery note not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no DN JSON leaked. WP-B correctly uses HTTP status (`isHttpNotFound`). Parent/warehouse 404s via `raise_error` use `NOT_FOUND`.

**W2 — `lock_or_create_level` does not retry unique insert (carried from WP-A)**
Empty `(product_id, bin_id)`: two concurrent first ISSUEs can both miss `SELECT FOR UPDATE` (no row), both `INSERT`. Unique `uq_inventory_product_bin` fails one with `IntegrityError` → 500, not a second decrement. Counter insert already uses a savepoint + re-lock. Spec test 8 / Playwright seed stock via adjust first, so they do not catch this. Not double-issue.

**W3 — Service `confirm`/`cancel` trust the router lock (carried from WP-A)**
`DeliveryNoteService.confirm` does not re-`SELECT FOR UPDATE` the DN. The router does (`for_update=True`). Today the only caller is the router. A future internal caller that passes an unlocked DRAFT identity-map object could double-ISSUE. Defense in depth: lock inside the service.

**W4 — HOLD path loads client/workspace by PK (carried from WP-A)**
`_assert_hold` uses `session.get(Workspace, dn.workspace_id)` and `session.get(Client, dn.client_id)` then `assert_not_hold` (which **does** lock the client by id+workspace). DN row is already workspace-scoped, so this is not an API IDOR.

**W5 — Invoice remaining in the UI uses JS `Number` and page 100**
`confirmedInvoiceQtyMap` sums CONFIRMED DN lines with `Number(item.quantity)` and lists `per_page: 100`. API remaining on create/confirm is still Decimal. Over-deliver is still 400 server-side. A workspace with >100 CONFIRMED DNs on one invoice could **under-count** delivered in the form (UI remaining too high); submit then 400. Display/`parseAmount` float is preview only — not stock mutation.

**W6 — Pre-existing: `GET /inventory/warehouses/{id}/bins` does not check warehouse workspace**
DN form lists bins after a warehouse pick from the workspace-filtered warehouse list. Direct API with a foreign warehouse UUID can still list bins. WP-A I5; not introduced by DN; adjust/ISSUE still 404 the foreign product/warehouse on write.

### Info

**I1 — Tests not re-run here**
Pytest `test_delivery_notes.py` **14** functions (backend-execution-report: 14 passed; combined 75 with GRN/credit/LPO/invoices). Playwright **14 passed** claimed in frontend-execution-report (3 DN specs + 11 prior). Static review.

**I2 — Invoice-parent DN in the browser is untested**
Form XOR is shipped (`dn-parent-type-invoice`, `loadInvoiceRemainingLines`). Playwright leftover: LPO remaining only. Cancel CONFIRMED / reverse not in the browser (API pytest covers). Over-deliver toast not in the browser.

**I3 — WP-B inventory adjust UI deferred**
`Inventory.tsx` is still a warehouse list stub (“Add Warehouse coming soon”). No MEMBER/ADMIN adjust form, no levels table. Spec §8 UI “may keep adjust for ADMIN only.” API is locked (OWNER/ADMIN + reason). Playwright seeds via `POST /inventory/adjust` `OPENING`. Acceptable leftover; not a DN stock hole.

**I4 — File length**
App modules under 500 lines (service ~456, support ~392, ledger ~309). `backend/tests/test_delivery_notes.py` ~807 (spec §12 aimed at app modules).

**I5 — Unused `FILS`; DN year is local `datetime.now().year`**
`inventory_ledger.FILS` unused. `utc_today()` for `delivery_date`; number year is local. Fine except New Year vs UTC.

**I6 — Mid-file schema imports (`E402`)**
`serialize` / `serialize_list_item` import schemas inside the functions (cycle avoidance).

**I7 — Blocked confirm still runs credit `evaluate`**
`assert_not_hold` evaluates (reason `DN_CONFIRM`) then raises. Same as send. Can write `credit_status_events` on a failed confirm. Spec said reuse that helper.

**I8 — Alembic pytest uses env `DATABASE_URL`, not `_test`**
`test_alembic_upgrade_head_and_check` runs against the app database from `.env`. Harmless if already at head; not isolated.

**I9 — Isolation e2e is API GET, not a logged-in browser URL**
Addendum WP-C wording “other workspace DN URL 404.” Shipped test is `GET /api/v1/delivery-notes/{id}` 404. UI route would show `dn-not-found` via the same 404. Not re-proven in Chromium as workspace B.

**I10 — `get_session` has no explicit rollback**
`finally: session.close()` — SQLAlchemy `close()` rolls back uncommitted work. Insufficient-stock and HOLD failures do not persist ISSUE.

---

## Spec lock vs shipped

| Lock | Shipped |
|---|---|
| `DN-YYYY-XXXX` via `dn_counters` + `FOR UPDATE` | `DnNumberService`; savepoint on first-year insert |
| XOR one parent; LPO remaining independent of invoiced | Schema + DB check + `confirmed_cpo_qty_map`; UI radio XOR |
| DRAFT → CONFIRMED (`ISSUE` −qty `DN`) → CANCELLED (`ISSUE` +qty `DN_CANCEL`) | Service + ledger; UI Confirm / Cancel delivery |
| Confirm idempotent 200 | Status short-circuit after DN lock |
| HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` | `_assert_hold` + Settings checkbox |
| Ledger helper filters `workspace_id` (GRN lock does not) | `lock_or_create_level` includes `workspace_id` |
| Adjust OWNER/ADMIN + reason + notes; DN must not call it | `adjust()` role/reason; DN calls `post_issue`; Playwright `OPENING` seed |
| `quantity_delivered` cache on LPO items | Recalc on confirm/cancel; LPO GET + detail table |
| PDF title **Delivery Note** | `@react-pdf/renderer` + HTML preview |
| Sales nav `/delivery-notes` after LPO | Layout + AuthGuard routes |
| Alembic from `9f3a7c2e1d04` | `a7c4e9d2b105` |
| WP-C Playwright stock drop + isolation 404 | Claimed 14 passed; 10→8, HOLD 400, GET 404 |

Router prefix `/delivery-notes` under `/api/v1`. Pagination on list. Extra keys 422 on create/update/confirm/cancel/adjust.

---

## WP split coverage

### WP-A — API + Alembic + tests
Models, migration, XOR, remaining, confirm ISSUE, cancel reverse, HOLD gate, LPO `quantity_delivered`, tighten adjust, pytest §13. Unchanged from WP-A **APPROVE_WITH_NITS**.

### WP-B — UI + PDF
Sales nav **Delivery Notes** after LPO. Create XOR LPO remaining or invoice remaining. Warehouse/bin picker. Confirm / cancel / DRAFT edit-delete. `DeliveryNotePDF` title **Delivery Note**. Settings `block_do_on_hold`. Isolation toasts HTTP 404. CREDIT_HOLD banner without interceptor duplicate. Inventory adjust UI **not** built (stub page).

### WP-C — Playwright
Register → Settings flag checked → client → API warehouse+bin+catalog+OPENING 10 → UI LPO receive → DN remaining 2 → preview **Delivery Note** → confirm → levels 8. HOLD request-only 400 then 200 with flag off. Workspace B GET 404. Did not break product/FTA/quote/LPO/credit specs (claimed).

---

## Out of scope (correctly omitted)

Transfers, cycle counts, reservations, sales-return receiving, **tax credit notes (gap 10)**, WhatsApp, Arabic PDF, Peppol, OCR, negative stock, volume pricing, FTA invoice field changes, SPO/GRN formula changes (shared ledger helper is new; GRN posting left as-is).

---

## Commit / next

- Verdict is **APPROVE\*** → may commit when the user asks. Do not commit from this review.
- Next gap: **tax credit notes** (addendum §14 / §17). Do not implement in this slice.
