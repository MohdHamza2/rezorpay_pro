# WP-A–C Quotations — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full quotations slice — Alembic `cb01b6bef962`, WP-A API + nits, WP-B UI/PDF, WP-C Playwright. Review only. No git commit. No feature work (no P0 tenant-leak or float-money found).
**Specs:** `architecture/wave-quotations-addendum.md`, `.agents/reports/wp-a-quotations-review.md` (nits claimed fixed), `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

LPO (gap 5) may start. Do not open another quotations WP for these nits. Commit when asked.

No P0 tenant leak. No `float()` / `Float` on quote or shared line-money paths. Convert goes through `InvoiceService.create_invoice` with explicit frozen `unit_price`. FTA send gates remain on `POST /invoices/{id}/send` only. WP-A nits **W1–W3 are fixed** in code and pytest. No LPO/CPO stub routes.

This reviewer did not re-run pytest or Playwright; claims (18 quote tests / 52 combined pytest; 7 Playwright files green) were checked against the tree, not re-executed.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 API + e2e | **PASS.** Every HTTP load uses `workspace_id` + `deleted_at IS NULL`. Cross-tenant GET/PUT/send/accept/convert → 404 in pytest. Playwright `quotation-isolation.spec.ts` GET 404 (not 403). JWT workspace never from body (`extra="forbid"`). DELETE/reject use the same `_load_or_404` (untested in pytest; e2e does not hit the UI URL as workspace B). |
| 2 | Decimal; convert no re-price | **PASS.** Columns `Numeric(12,2)` / `(10,2)` / `(5,2)`. Shared `line_money.money()` `ROUND_HALF_UP` fils. Convert passes explicit `unit_price` + stored `tax_rate`. `_line_unit_price` short-circuits when `unit_price` is set. Pytest: quote `20.00` vs list `12.50` stays `20.00`. Inactive/foreign catalog line becomes ad-hoc (SKU may prefix description). |
| 3 | States + DRAFT-only edit; expiry persist then 403 | **PASS.** PUT/DELETE/send non-DRAFT → 403 `INVALID_STATE`. Convert only ACCEPTED. SENT + `valid_until < UTC today` expires on GET/list/accept/reject/convert. **W1 fixed:** `_load_and_expire` commits SENT→EXPIRED **before** the action 403s. `test_accept_reject_convert_persist_expiry_without_prior_get` reads PostgreSQL status (not GET). UI: edit/send/delete on DRAFT only; Accept on SENT; Convert on ACCEPTED; `/edit` on non-DRAFT redirects to detail. |
| 4 | Convert workspace-scoped; idempotent 200; deleted invoice 409 | **PASS.** Unique `invoices.quotation_id`. First convert 201 DRAFT invoice; second 200 same id. Soft-deleted invoice 409 `CONFLICT` `field=quotation_id`. `map_converted_ids` / `existing_converted_invoice` filter `Invoice.workspace_id` (**W3 fixed**). Convert locks the quote `SELECT FOR UPDATE`. Invoice create API cannot set `quotation_id` (`InvoiceCreate` `extra="forbid"`). |
| 5 | QUO numbering not invoice counters | **PASS.** `quotation_counters` + `QuotationNumberService.with_for_update()`. Format `QUO-YYYY-XXXX`. Soft-delete does not rewind (`0001` deleted → `0002`). Concurrent 10 creates unique sequential. Invoice `INV-` path untouched. |
| 6 | PDF title Quotation not Tax Invoice | **PASS.** `QuotationPDF.tsx` title **Quotation**; filename `Quotation_{QUO-…}.pdf`; valid until; Helvetica; EXPIRED/REJECTED watermark. `InvoicePDF.tsx` still **Tax Invoice**. Preview: `quotation-pdf-title` vs invoice `pdf-title`. Playwright asserts Quotation and `pdf-title` count 0. |
| 7 | Invoice FTA send still gated | **PASS.** Quote send: DRAFT + AED + ≥1 line, no TRN. `InvoiceService.mark_as_sent` still always `assert_fta_sendable`. Converted DRAFT send without TRN → `FTA_SEND_BLOCKED`; quote stays `CONVERTED`. Playwright: convert lands on invoices list, Send shows `fta-send-blocked`. |
| 8 | Extra keys 422; wrapper pagination | **PASS.** Create/update/send/reject `extra="forbid"`; `hs_code` 422; `USD` 422. List: `page` default 1, `per_page` 20 max 100, `PaginatedResponse` (`data` + `pagination` sibling). UI unwraps that wrapper. Pagination not asserted in `test_quotations.py` (I2 leftover). |
| 9 | Playwright create-send-accept-convert | **PASS with nit I7.** Happy path: register → client → ad-hoc quote → PDF title → send → PUT 403 → `/edit` bounce → accept → convert → `/invoices` DRAFT → FTA send blocked. Does **not** create a catalog product + `DEFAULT_SALES` in e2e (spec WP-C listed that). Catalog + frozen price is covered in pytest. Spec negatives (second convert, expired cannot convert) are pytest-only. |
| 10 | LPO not stubbed | **PASS.** No `convert-to-cpo`, no enquiry_id, no public accept. All quote routes require Bearer (`get_current_user` / `get_current_workspace_id`). |

---

## WP-A nits (claimed fixed) — re-check

| Nit | Status |
|---|---|
| **W1** Expiry persist rolls back on 403 | **Fixed.** Router `_load_and_expire` commits EXPIRED, then accept/reject/convert 403 `INVALID_STATE`. Session `expire_on_commit=False`, so the in-memory row stays EXPIRED. Pytest reads DB status without GET. |
| **W2** Inactive product copy said “invoice” | **Fixed.** `_resolve_line(..., line_owner="quotation")` → “Cannot add an inactive product to a quotation line”. Invoice path unchanged. Pytest asserts `"quotation" in msg` and `"invoice" not in msg`. |
| **W3** Converted-invoice lookup unscoped | **Fixed for isolation.** Both helpers filter `Invoice.workspace_id`. Pytest `test_converted_invoice_hydration_is_workspace_scoped`. Residual: `map_converted_ids` still does **not** exclude `deleted_at`, so `converted_invoice_id` can point at a 404 invoice after convert-once 409 (I6). |

---

## Findings

### Critical (P0)

None. No cross-tenant quote GET/mutate/convert leak. No float money columns or `float()` in quote/line-money/invoice convert path. `InvoiceCreate` cannot attach `quotation_id`.

### Warning

None that block LPO.

**W-C1 — WP-C negatives not in Playwright (coverage only)**
Spec WP-C asked: second convert same invoice; expired quote cannot convert; other-workspace **quotation URL** 404. Shipped e2e: API GET isolation only, plus the happy path. Second convert, 409-after-delete, and on-read expiry are covered in pytest, not Playwright. Isolation e2e does not open `/quotations/{id}` as workspace B (API 404 is equivalent for leak risk).

### Info

**I1 — VARCHAR lengths vs spec `String(50)` / `String(100)` / `String(500)`**
Migration uses unbounded `AutoString()` for `quotation_number`, `sku_snapshot`, `description`. Models’ `max_length` is Pydantic-side. Same autogenerate style as other SQLModel tables. `alembic check` was reported clean.

**I2 — Pytest still omits a few spec §12 paths**
Missing automated coverage: list pagination wrapper, reject/DELETE cross-tenant 404, reject on EXPIRED, list bulk-expiry, `alembic upgrade head` / `alembic check` as a test. Implementation is present. Isolation DELETE/reject share `_load_or_404`.

**I3 — Convert OpenAPI default is 200**
Runtime sets 201 vs 200 on `Response.status_code`. Client uses HTTP status. Fine.

**I4 — Number year vs quote date timezone**
`QuotationNumberService` uses `datetime.now().year` (naive local), cloned from invoices. Quote dates use UTC. New-year edge only. `IntegrityError` → `session.rollback()` still clones invoices (safe because generate runs before other writes).

**I5 — Style / split**
Files under 500 lines (`quotation_service` ~359, `quotation_support` ~263, router ~303, `QuotationForm` ~321). Function-level schema imports in `serialize*` clone invoices.

**I6 — `converted_invoice_id` after invoice soft-delete**
`map_converted_ids` returns the deleted invoice id. Detail shows “Open draft invoice” → `/invoices` list (empty). Convert-again correctly 409. UI does not special-case 409.

**I7 — Playwright happy path is ad-hoc, not catalog**
Spec WP-C: product with `DEFAULT_SALES` then quotation. UI has a product picker; e2e uses ad-hoc lines. Frozen catalog price is pytest `test_accept_convert_draft_invoice_frozen_prices`.

**I8 — PDF preview is HTML, not the `@react-pdf` blob**
Same pattern as `InvoicePdfPreview`. Download uses `QuotationPDF`. Playwright checks the HTML title. Real PDF title is still **Quotation**.

**I9 — Convert navigates to invoice list**
There is no `/invoices/:id` route. `/invoices` is the live invoice surface (row status + Send). Matches existing invoice UX and the Playwright assertion.

**I10 — Frontend money types are `number`**
Display/PDF use `Number(...).toFixed(2)`. Writes go through JSON → Pydantic `Decimal`. Storage remains `Numeric`. Not a float-money P0.

---

## Isolation (checklist 1)

Every quote load used by HTTP:

```python
.where(Quotation.id == quotation_id)
.where(Quotation.workspace_id == workspace_id)
.where(Quotation.deleted_at.is_(None))
```

Cross-workspace client/product on create → 404. Convert uses the JWT workspace (same as the locked quote) for `InvoiceService.create_invoice`. Idempotent 200 reloads the invoice with that workspace; mismatch 404 rather than leak.

`test_isolation_workspace_b_404`: GET/PUT/send/accept/convert.
Playwright: workspace B GET → 404, not 403.

---

## Money and convert (checklist 2, 4, 7)

- `money()` / `apply_line_money` extracted; invoices import the same helpers. `_dec` uses `Decimal(str(value))`.
- Header: Σ `line_net`, Σ line VAT, `money(subtotal + tax)`.
- Convert payload: explicit `quantity`, `unit_price`, `tax_rate`, XOR discounts; `product_id` omitted if inactive/deleted/other-workspace.
- Invoice totals recomputed by `InvoiceService`; `invoice_kind` and snapshots stay null until invoice `/send`.
- Notes: `Converted from {quotation_number}.` plus original notes.
- Issue/supply = UTC today; due = +30.

---

## Numbering and Alembic (checklist 5)

```
… → 06c9b4b1dcda → c8e1a4f2b6d0 (FTA) → cb01b6bef962 (quotations, HEAD)
```

`down_revision = "c8e1a4f2b6d0"`. Tables: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`. Column: `invoices.quotation_id` UUID nullable unique indexed FK. ENUMs `quotationstatus`, `quotationeventtype`. No `enquiry_id` / `revision_number` / LPO tables. FTA and Product Master revisions not rewritten.

---

## UI / PDF (WP-B)

- Layout Sales: Clients → **Quotations** → Invoices (`nav-quotations`).
- List: status / client / search / pagination 20.
- Form: client, dates, validity default +14, product picker, ad-hoc, inherit tax, XOR discount (zod), AED only. Extra keys not sent (`buildLinePayload` allowlist).
- Actions: Send / Accept / Reject (optional reason) / Convert on ACCEPTED only; SENT copy “Accept first”.
- Convert → `/invoices` DRAFT row. Tax Invoice PDF unchanged.

---

## Tests

| Layer | Tree |
|---|---|
| `tests/test_quotations.py` | **18** `test_*` (incl. concurrent QUO numbers, convert-once, 409, FTA contrast, W1 persist expiry, W3 hydration scope, isolation) |
| Claimed combined pytest | 18 + 25 invoices + 5 tenant isolation + 4 concurrent INV = **52** |
| Playwright | **7** files / **7** tests: quotations happy path, quotation isolation GET 404, plus existing FTA/product specs |

PostgreSQL `_test` via TestClient + `create_all` (project pattern; not SQLite).

---

## Gate

**Clear to commit when asked. Next: LPO (gap 5), not more quotes.**

Do not retitle `InvoicePDF`. Do not add `convert-to-cpo` in this tree. Fold I2/I6/W-C1 only if they ride along with LPO or a later hygiene pass.
