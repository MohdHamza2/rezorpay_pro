# WP-A–C Customer LPO — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full slice — WP-A API+Alembic, W1 over-invoice nit, WP-B UI/PDF, WP-C Playwright. Review only. No git commit. No code changes (no P0 tenant-leak or float-money).
**Spec:** `architecture/wave-customer-lpo-addendum.md`, `.agents/reports/wp-a-customer-lpo-review.md` (W1 claimed fixed), `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

The A–C slice may be committed when asked. No P0 tenant leak. No `Float` / `float()` on LPO, line-money, or invoice-slice paths. Money columns stay `Numeric(12,2)` / qty `Numeric(10,2)` with shared `line_money.money()` ROUND_HALF_UP.

W1 is **fixed**: `_resolve_slices` accumulates leftover remaining per line in one `/invoices` body; `test_duplicate_line_ids_over_invoice_400_cache_unchanged` asserts 400 and unchanged cache. Partial invoices go through `InvoiceService.create_invoice` with `quotation_id=None`. FTA send still only runs in `mark_as_sent` → `assert_fta_sendable`. Alembic remains a linear head on quotes.

Leftover nits (W2 hydration, invoice Edit affordance, Playwright story vs addendum §12) are not ship-blockers.

**Next gap (do not implement here):** **credit HOLD / overdue (gap 6)** — UAE Phase 5 (`credit_control_service`, nightly overdue+HOLD, block confirm/dispatch). Then delivery notes (gap 7 / Phase 6). Not WhatsApp, OCR, Peppol, or credit notes.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 API + e2e | **PASS.** `get_visible` filters `workspace_id` + `deleted_at`. GET/PUT/receive/invoices/cancel → 404 for workspace B (`test_isolation_workspace_b_404`). Convert-to-lpo uses quote `get_visible` (other-workspace quote → 404). Playwright `lpo-isolation.spec.ts` GET 404 (not 403). Invoice list `customer_purchase_order_id` is applied **after** `Invoice.workspace_id`. JWT workspace never from body (`extra="forbid"`). |
| 2 | Over-invoice 400 including duplicate line ids in one POST | **PASS (W1 fixed).** Qty 101/100 → 400 `VALIDATION_ERROR` `field=quantity`, LPO unchanged. Duplicate `{line,60}` + `{line,60}` against remaining 100 → 400; `quantity_invoiced` stays 0; no invoice rows. Per-line `leftover` map in `_resolve_slices`. Concurrent two POSTs: 201+400 via LPO `SELECT FOR UPDATE`. Countable invoices: `deleted_at IS NULL` and `status != CANCELLED` (DRAFT counts). |
| 3 | Partial invoice via InvoiceService; DRAFT counts remaining | **PASS.** `create_invoices` → `InvoiceService.create_invoice(..., quotation_id=None, customer_purchase_order_id=lpo.id)`. 40 then 60 → PARTIAL then INVOICED; third → 400. Delete DRAFT invoice restores remaining and status RECEIVED. Frozen `unit_price`/`tax_rate` passed so `_line_unit_price` does not hit DEFAULT_SALES. Header LPO totals stay ordered qty. |
| 4 | PUT blocked on LPO-linked invoices | **PASS (API).** `InvoiceService.update_draft` 403 `INVALID_STATE` when `customer_purchase_order_id` is set. Tested. Walk-in `POST /invoices` cannot attach an LPO (`InvoiceCreate` `extra="forbid"`). See W4: Invoices UI still shows Edit on every DRAFT. |
| 5 | Quote convert mutex | **PASS.** ACCEPTED → DRAFT LPO, quote CONVERTED, lines frozen. Second convert-to-lpo → 200 same id. Convert-to-invoice after LPO → 409 `CONFLICT` `field=quotation_id`. Convert-to-lpo after quote→invoice → 409. SENT/DRAFT → 403. Quote row locked (`_load_and_expire` `FOR UPDATE`). Unique `customer_purchase_orders.quotation_id`. UI disables Convert to invoice when `converted_lpo_id` is set (list + detail). |
| 6 | PDF LPO not Tax Invoice; SPO nav unchanged | **PASS.** `LpoPDF` title **LPO**; footer “This is not a tax invoice.” Preview `data-testid="lpo-pdf-title"` is `LPO`. `InvoicePDF` still **Tax Invoice**; `QuotationPDF` still **Quotation**. Sales nav: Clients → Quotations → **LPO** (`/lpos`) → Invoices. Purchasing still **Purchase Orders** → `/spo`. No shared SPO models/PDF. |
| 7 | FTA send still gated | **PASS.** LPO `/invoices` creates DRAFT; `invoice_kind` and seller snapshots null. Send without TRN → `FTA_SEND_BLOCKED` 400. `mark_as_sent` always `assert_fta_sendable`. Playwright: receive → invoice 50% → send shows `fta-send-blocked`, status stays DRAFT. No send-on-create. |
| 8 | Numbering `LPO-YYYY-XXXX` | **PASS.** `lpo_counters` + `LpoNumberService` `SELECT FOR UPDATE`. Prefix `LPO-`. Soft-delete does not rewind (`0002` deleted → next `0003`). Concurrent 10 creates unique `0001`–`0010`. INV/QUO/SPO counters untouched. |
| 9 | Playwright receive + remaining qty + 404 | **PASS.** `lpos.spec.ts`: manual LPO, number regex, PDF title LPO not Tax Invoice, Receive, remaining `2`, invoice qty `1`, DRAFT invoice, FTA block, quote convert-to-LPO, convert-to-invoice 409. `lpo-isolation.spec.ts`: cross-tenant GET 404. Nine e2e files including these two. |
| 10 | No OCR / WhatsApp scope creep | **PASS.** No `/confirm`, no convert-to-cpo alias, no 501 stubs, no DN routes, no OCR/WhatsApp in LPO modules. Settings WhatsApp + SPO GRN `quantity_confirmed` are pre-existing, not this slice. |

---

## Findings

### Critical (P0)

None. No tenant leak on LPO GET/mutate/receive/invoice/cancel, quote convert-to-lpo, or invoice list filtered by LPO id. No float money on the persist path.

### Warning

**W2 — `converted_lpo_id` hydration still includes soft-deleted LPOs** *(carried from WP-A)*
`map_converted_lpo_ids` filters `workspace_id` but not `deleted_at`. After a converted LPO is DRAFT-deleted, GET quote can still show `converted_lpo_id` pointing at a 404 LPO. Convert-to-lpo correctly 409s and does not recreate. UI “Open LPO” will land on “LPO not found.” Same class as invoice hydration (also unfiltered). Not a leak.

**W3 — `create()` maps every `IntegrityError` to `customer_po_number` 409** *(carried)*
Flush failure (unique `lpo_number`, unique `quotation_id`, or unique customer PO) all become HTTP 409 `field=customer_po_number` after `session.rollback()`. Duplicate customer PO is also pre-checked. Concurrent first-counter insert is handled in `LpoNumberService`. Wrong field on a rare unique-number collision only.

**W4 — Invoices UI still offers Edit on LPO-linked DRAFTs**
`InvoiceListItem` has no `customer_purchase_order_id`. `Invoices.tsx` shows Edit for every `DRAFT`. Submit hits PUT → service 403 (tested). Change qty by deleting the DRAFT and posting `/invoices` again, as spec’d — the pencil control does not say that. `InvoiceService.can_edit` is still status-only; the LPO block lives only in `update_draft`. Today the router calls both, so PUT cannot slip through.

### Info

**I1 — Playwright vs addendum §12 WP-C story**
Shipped e2e covers receive, remaining qty, FTA gate, quote→LPO mutex, API isolation 404. It does **not** invoice the rest, assert over-invoice in the browser, or open `/lpos/{id}` as workspace B (SPA shows “LPO not found” on API 404). Isolation e2e is API GET, which matches checklist 1. Happy path is manual LPO then a separate quote convert, not quote→LPO→50%→rest in one flow.

**I2 — LPO PDF preview is HTML, not `@react-pdf`**
`LpoPdfPreview` is a title/meta stub (same pattern as quotation preview). Download uses real `LpoPDF` with title **LPO**. E2E asserts the stub test id, and that invoice `pdf-title` is absent.

**I3 — VARCHAR / file length / year clock**
Migration `AutoString()` for `lpo_number` / `customer_po_number` (Pydantic `max_length` only). `customer_po_service.py` is 554 lines (spec asked &lt; 500; support module exists). Number year uses `datetime.now().year` (naive local), cloned from QUO/INV. Soft-deleted DRAFT still occupies `customer_po_number` uniqueness (matches spec index). Test file is `test_customer_lpos.py` not spec’s `test_customer_purchase_orders.py`.

**I4 — `/invoices` when remaining is 0 returns 400 not 403**
Forbidden table says 403 unless RECEIVED/PARTIAL. Spec §11.10 and tests expect **400** `VALIDATION_ERROR` for a third full invoice. Implementation matches the test lock. Empty `items: []` is treated as omit-all (falsy list). UI always sends explicit qty rows.

**I5 — Linked invoices on LPO detail are not links**
GET embeds `{ id, invoice_number, status, total_amount }`. Detail table is display-only; create-invoice navigates to `/invoices` (there is no `/invoices/:id` route). Acceptable for this SPA.

**I6 — `recalc_invoiced` still clamps `quantity_invoiced` to `quantity`**
Defense in depth after W1. Source of truth remains `SUM(invoice_items.quantity)` on countable parents. Discount-amount slices pro-rate and cap leftover across invoices. Percent discounts copy through. Inactive catalog products on invoice-from-LPO become ad-hoc.

---

## Isolation (checklist 1)

Every LPO load used by HTTP:

```python
.where(CustomerPurchaseOrder.id == lpo_id)
.where(CustomerPurchaseOrder.workspace_id == workspace_id)
.where(CustomerPurchaseOrder.deleted_at.is_(None))
```

Quote convert-to-lpo uses the same quote `get_visible` workspace filter. `existing_converted_lpo` / `map_converted_lpo_ids` also filter `CustomerPurchaseOrder.workspace_id`. Client create 404s other-workspace `client_id`. Playwright isolation is API GET 404, not a second-browser SPA session.

---

## Remaining math + W1 (checklist 2)

Before resolve, `create_invoices` refreshes `quantity_invoiced` from `invoiced_qty_map` (countable invoices including DRAFT). `_resolve_slices`:

- Omit items → all remaining `> 0`.
- Explicit items: unknown / other-LPO line id → 404; running `leftover[line_id]`; qty `>` leftover → 400 unless leftover is 0 and the id was not yet seen (skip remaining-0 lines).
- Duplicate ids that together exceed remaining → 400 before `InvoiceService` writes.

Lock: LPO row `SELECT FOR UPDATE` on the invoices route.

---

## Quote mutex (checklist 5)

| Already | convert-to-invoice | convert-to-lpo |
|---|---|---|
| ACCEPTED, nothing | 201 DRAFT invoice | 201 DRAFT LPO |
| CONVERTED + live invoice | 200 same invoice | 409 |
| CONVERTED + live LPO | 409 | 200 same LPO |
| CONVERTED + invoice or LPO soft-deleted | 409 | 409 |

`invoices.quotation_id` unique **stays**. LPO invoices do not set it. Event metadata `{ "lpo_id": ... }` on `QUOTATION_CONVERTED`.

---

## Alembic

```
cb01b6bef962 (quotations) → 59084165d346 (customer LPOs)  [HEAD]
```

Adds `lpo_counters`, CPO tables, `invoices.customer_purchase_order_id` indexed **not** unique, `invoice_items.customer_purchase_order_item_id` indexed FK. Does not drop unique `invoices.quotation_id`. Partial unique `uq_cpo_workspace_client_po_number` WHERE `customer_po_number IS NOT NULL`. ENUMs: `DRAFT|RECEIVED|PARTIAL|INVOICED|CANCELLED`. No `/confirm`, no `CONFIRMED`/`CLOSED`.

---

## WP-B / WP-C surfaces

- SPA path **`/lpos`**; API **`/customer-purchase-orders`**.
- Manual form + quote Convert to LPO; Receive; Cancel (RECEIVED only in UI); invoice remaining qty inputs; ordered/invoiced/remaining columns; customer PO number.
- Convert to invoice disabled when `converted_lpo_id` is set.
- No new OCR, WhatsApp, DN, or supplier SPO/GRN behavior.

---

## Commit gate

**APPROVE_WITH_NITS** — may commit when asked.

Please fold **W2** (exclude `deleted_at` in `map_converted_lpo_ids`) and **W4** (hide Edit when the invoice is LPO-linked, after list payload or a GET) into a follow-up. Do **not** start OCR, WhatsApp, or delivery notes.

**Next after LPO A–C:** **credit HOLD / overdue (gap 6)**, then delivery notes (gap 7).
