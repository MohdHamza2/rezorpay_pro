# WP-A Quotations — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0 tenant-leak or float-money).
**Spec:** `architecture/wave-quotations-addendum.md`, `.agents/reports/architect-quotations-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B (Quotation UI + PDF title **Quotation**) may start.

No P0 tenant leak. No float money columns or `float()` in the quote/line-money path. Convert goes through `InvoiceService.create_invoice`. FTA send gates are unchanged. Alembic is a linear new revision on `c8e1a4f2b6d0`. Reviewer re-ran the claimed suite: **50 passed**. `alembic heads` is `cb01b6bef962` only. `alembic check`: no new upgrade operations.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Workspace 404 isolation on quotes and convert | **PASS.** `get_visible` filters `workspace_id` + `deleted_at`. GET/PUT/DELETE/send/accept/reject/convert all 404 via `_load_or_404` / `get_for_response`. Tested GET/PUT/send/accept/convert. JWT `workspace_id` never from body (`extra="forbid"`). |
| 2 | Decimal `money()`; convert does not re-price | **PASS.** Shared `app/services/line_money.py` (`ROUND_HALF_UP` fils). Columns `Numeric(12,2)`. Convert passes explicit `unit_price` / stored `tax_rate`. `_line_unit_price` short-circuits when `unit_price` is set. Test: quote `20.00` vs list `12.50` stays `20.00`. |
| 3 | DRAFT-only edit; convert only ACCEPTED; on-read expiry | **PASS.** PUT/DELETE/send non-DRAFT → 403 `INVALID_STATE`. Convert SENT/DRAFT/EXPIRED/REJECTED → 403. SENT + `valid_until < UTC today` expires on GET/list/accept/reject/convert. See nit W1 on persist-on-403. |
| 4 | Second convert 200 same invoice; soft-deleted invoice 409 | **PASS.** Unique `invoices.quotation_id`. First convert 201; second 200 same id; soft-deleted invoice 409 `CONFLICT` `field=quotation_id`. Convert locks the quote `SELECT FOR UPDATE`. |
| 5 | `QUO-YYYY-XXXX` FOR UPDATE; not `invoice_counters` | **PASS.** `quotation_counters` + `QuotationNumberService.with_for_update()`. Soft-delete does not rewind (`0001` deleted → next `0002`). Concurrent 10 creates unique sequential. |
| 6 | Extra 422; AED; pagination wrapper | **PASS.** Create/update/send/reject `extra="forbid"`; `hs_code` 422; `USD` 422. List: `page` default 1, `per_page` 20 max 100, `PaginatedResponse` (`data` + `pagination` sibling). Pagination untested in pytest (I2). |
| 7 | FTA invoice send still gated; quotes send without TRN OK | **PASS.** Quote send: DRAFT + AED + ≥1 line only. `InvoiceService.mark_as_sent` still always `assert_fta_sendable`. Converted DRAFT send without TRN → `FTA_SEND_BLOCKED`; quote stays `CONVERTED`. |
| 8 | Alembic linear; no history rewrite | **PASS.** `cb01b6bef962` `down_revision = "c8e1a4f2b6d0"`. Single head. FTA `c8e1a4f2b6d0` and Product Master `d3e4c7fdb29f` not rewritten (`git diff` empty). Downgrade drops ENUM types. |
| 9 | Router HTTP-only | **PASS with nit I3.** State machine, expiry, money, convert, isolation live in `QuotationService` / `quotation_support`. Router: auth, wrappers, 404, status codes. List SQL filters sit in the router (same pattern as invoices). |
| 10 | Convert creates DRAFT invoice via `InvoiceService` | **PASS.** `QuotationService.convert_to_invoice` → `InvoiceService.create_invoice(...)` with frozen lines, notes prefix, issue/supply = UTC today, due = +30, `quotation_id=quote.id`. Status DRAFT; `invoice_kind` and snapshots null. No hand-inserted `Invoice` / `InvoiceItem`. |

---

## Findings

### Critical (P0)

None. No tenant leak on quote GET/mutate/convert. No `Float` / `float()` on money. Invoice create API cannot set `quotation_id` (`InvoiceCreate` `extra="forbid"`).

### Warning

**W1 — Expiry persist rolls back when accept/reject/convert 403s**
On-read expiry mutates the row in the same transaction as the action. Router commits only after a successful service call. `HTTPException` 403 → session close rolls back, so a SENT quote past `valid_until` can remain SENT in the DB until GET or list. In-request convert/accept still 403 (`expire_locked` then `INVALID_STATE`). Spec asked persist on those paths. Tests GET first, so they do not catch this. Not a convert bypass.

**W2 — Shared product helper says “invoice” on quote lines**
Quote create/update calls `_resolve_line` → `_load_invoice_product`. Inactive product 400 message is “Cannot add an inactive product to an invoice”. Behavior/status codes are correct.

**W3 — Converted-invoice lookup is not workspace-scoped (defense in depth)**
`map_converted_ids` and `existing_converted_invoice` query `Invoice.quotation_id` without `workspace_id`. Not a leak today: `get_visible` scopes the quote; `quotation_id` is globally unique; convert writes `quotation.workspace_id`; idempotent convert reloads via `InvoiceService.get_for_response(..., workspace_id)`. `map_converted_ids` also returns soft-deleted invoices, so `converted_invoice_id` can point at a 404 invoice after convert-once 409. WP-B should treat that id as possibly gone.

### Info

**I1 — VARCHAR lengths vs spec `String(50)` / `String(100)` / `String(500)`**
Migration uses unbounded `AutoString()` for `quotation_number`, `sku_snapshot`, `description`. Models’ `max_length` is Pydantic-side. `alembic check` is clean (metadata matches DB). Same autogenerate style as other SQLModel tables.

**I2 — Spec §12.15 and a few isolation/expiry paths are not in pytest**
Missing automated coverage: list pagination wrapper, reject/DELETE cross-tenant 404, reject on EXPIRED, list bulk-expiry, `alembic upgrade head` / `alembic check`. Implementation is present. Reviewer ran `alembic check` and the 50-test set.

**I3 — Convert OpenAPI default is 200**
Runtime sets 201 vs 200 on `Response.status_code`. Fine for WP-B if the client uses the HTTP status, not the schema default.

**I4 — Number year vs quote date timezone**
`QuotationNumberService` uses `datetime.now().year` (naive local), cloned from invoices. Quote dates use UTC. New-year edge only. Soft-delete / FOR UPDATE / rollback-on-fail match the invoice counter, including `IntegrityError` → `session.rollback()` (safe here because generate runs before other writes).

**I5 — Style / split**
Files under 500 lines (`quotation_service` 349, `quotation_support` 253, router 289). Function-level schema imports in `serialize*` clone invoices. Several service methods >20 lines.

**I6 — No LPO / public accept / enquiry**
No `convert-to-cpo`, no unauthenticated accept, no `enquiry_id`. All quote routes take Bearer via `get_current_user` / `get_current_workspace_id` (DELETE uses workspace dep, which requires an active user).

---

## Isolation (checklist 1)

Every quote load used by HTTP:

```python
.where(Quotation.id == quotation_id)
.where(Quotation.workspace_id == workspace_id)
.where(Quotation.deleted_at.is_(None))
```

Cross-workspace client/product on create → 404. Convert uses the locked quote’s `workspace_id` for `InvoiceService.create_invoice`. Idempotent 200 reloads the invoice with the JWT workspace; mismatch would 404 rather than leak.

`test_isolation_workspace_b_404` covers GET/PUT/send/accept/convert. DELETE and reject use the same `_load_or_404` (untested).

---

## Money and convert (checklist 2, 10)

- `money()` / `apply_line_money` extracted; invoices import the same helpers.
- Header: Σ `line_net`, Σ line VAT, `money(subtotal + tax)`.
- Convert payload: explicit `quantity`, `unit_price`, `tax_rate`, XOR discounts, `product_id` omitted if inactive/deleted/other-workspace (SKU may prefix description).
- Invoice totals recomputed by `InvoiceService`; snapshots / `invoice_kind` stay null until invoice `/send`.

---

## Numbering and Alembic (checklist 5, 8)

```
… → 06c9b4b1dcda → c8e1a4f2b6d0 (FTA) → cb01b6bef962 (quotations, HEAD)
```

Tables: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`. Column: `invoices.quotation_id` UUID nullable unique indexed FK. PostgreSQL ENUMs `quotationstatus`, `quotationeventtype`. No `enquiry_id` / `revision_number` / LPO tables.

---

## Tests (reviewer re-run)

PostgreSQL `invoicesaas_test` via existing TestClient + `create_all` (project pattern; not SQLite).

| File | Result |
|---|---|
| `tests/test_quotations.py` | 16 passed (incl. concurrent QUO numbers, convert-once, 409, FTA contrast, expiry, isolation) |
| `tests/test_invoices.py` | 25 passed |
| `tests/test_concurrent_numbering.py` | 4 passed |
| `tests/test_multi_tenant_isolation.py` | 5 passed |
| **Total** | **50 passed, 0 failed** (46.6s) |

`alembic heads` → `cb01b6bef962 (head)`
`alembic check` → `No new upgrade operations detected`

---

## WP-B gate

**Clear to start WP-B.** Do not retitle `InvoicePDF` (Tax Invoice). New `QuotationPDF` title **Quotation**. Convert navigation should tolerate a missing invoice when `converted_invoice_id` is set but GET invoice 404s (W3). Prefer Accept then Convert on SENT; Convert enabled on ACCEPTED only.
