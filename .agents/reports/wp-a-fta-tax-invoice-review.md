# WP-A FTA Tax Invoice — Code Review

**Date:** 2026-08-31
**Scope:** API + Alembic + pytest only (`architecture/wave-fta-tax-invoice-addendum.md`). No implementation.
**Reviewer:** Ruflo reviewer subagent.
**Shipped:** Alembic `c8e1a4f2b6d0` (`down_revision = "06c9b4b1dcda"`), `InvoiceService`, invoice router/schemas/models, workspace `address`, `main.py` ErrorDetail unwrap, `tests/test_invoices.py` (22) + isolation + concurrent numbering.

**Verdict: `APPROVE_WITH_NITS`**

WP-B (Settings address, invoice form, PDF title **Tax Invoice**) may start. Fix the warnings below in WP-A follow-up or in WP-B; none are P0 tenant-leak or float-money.

No git commit. No production patches (no P0).

---

## Verdict rationale

Isolation, Decimal line math, omitted-`tax_rate` inherit, explicit `0`, FTA send hard-fails, DRAFT-only PUT, optional `product_id` with cross-workspace 404, linear Alembic, overpay 400, extra-key 422, AED write lock, and gapless `INV-YYYY-XXXX` locking are implemented and aligned with the addendum. Gaps are test coverage, snapshot hygiene on SIMPLIFIED, migration backfill of header totals, and a few spec nits — not security or money-float defects.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Tenant isolation 404 on invoices/items | **PASS.** GET/PUT/SEND/VOID filter `workspace_id` + `deleted_at`; cross-workspace is 404 not 403. No item sub-resource; items only via parent invoice. Cross-workspace `product_id` 404 (`_load_invoice_product`). Isolation tests cover invoice + payment send fixture. |
| 2 | Decimal / `ROUND_HALF_UP`; no float money | **PASS.** `money()` uses `Decimal.quantize(0.01, ROUND_HALF_UP)` per line then sum. Storage `Numeric(12,2)` / `(10,2)` / `(5,2)`. `_dec()` via `Decimal(str(...))`. No `float` in invoice service/models/schemas. JSON test payloads with `5.0` are coerced by Pydantic. |
| 3 | `tax_rate` omit → product then 5.00; explicit 0 stays 0 | **PASS.** `_line_tax_rate`: body if not `None` → `product.tax_rate` if not `None` → workspace `default_tax_rate`. Tests cover omit→5.00 and explicit 0. Product-vs-workspace distinction is not uniquely asserted (see W4). |
| 4 | Send hard-fails TRN regex + address; STANDARD vs SIMPLIFIED | **PASS.** 400 `FTA_SEND_BLOCKED` + `error.field`. Regex `^100[0-9]{12}$` after strip/spaces. STANDARD if valid buyer TRN **or** `total_amount > 10000`; else SIMPLIFIED. 403 remains `INVALID_STATE` for non-DRAFT. Cross-workspace send 404 before service. |
| 5 | Snapshots frozen on send; DRAFT-only PUT | **PASS.** `_freeze_snapshots` then `mark_as_sent`. Update/delete schemas omit snapshot fields (`extra="forbid"`). PUT non-DRAFT 403. Snapshots are not client-writable. Freeze-vs-live-mutation not tested (W3). |
| 6 | `product_id` optional; cross-workspace product 404 | **PASS.** Ad-hoc line 201. Catalog copies name/SKU/UOM/list price/tax. Description override works. Inactive → 400. Missing/other workspace → 404. |
| 7 | Alembic linear from HEAD; no history rewrite; ENUMs safe | **PASS.** `c8e1a4f2b6d0` revises `06c9b4b1dcda` only; ancestors untouched. `invoice_kind` is `String(20)`, not a PostgreSQL ENUM. No `ALTER TYPE`. No `clients.trn`. No IBAN. Check constraints `>= 0` on discounts/`line_net`/line `tax_amount`. |
| 8 | Overpayment still 400 | **PASS.** `test_overpayment_still_400` expects 400 `PAYMENT_EXCEEDS_BALANCE` (requires ErrorDetail unwrap). Payment service unchanged. |
| 9 | Extra keys 422; AED-only | **PASS.** `extra="forbid"` on invoice/item create+update. `hs_code` and header `discount_amount` 422. `Currency` enum AED-only; `USD` 422 on create. Service `_assert_aed` on create/update. |
| 10 | Gapless numbering still locked | **PASS.** `InvoiceNumberService` still `SELECT … FOR UPDATE`. Concurrent numbering tests unchanged (create-time, not send). Format `INV-YYYY-XXXX`. |
| 11 | `main.py` error unwrap: other routers? | **PASS with note.** Dict `detail` with `code` now surfaces `error.code` / `error.message` / optional `error.field`. String `detail` still `HTTP_ERROR`. Net fix for invoices, payments (`PAYMENT_EXCEEDS_BALANCE`), clients (`CLIENT_HAS_INVOICES`). No test asserts `HTTP_ERROR`. Handler still omits `exc.headers` (pre-existing 401 `WWW-Authenticate` drop — I8). |

Coder claim **31 passed** (`22 + 5 + 4`) was not re-executed in this review. Logic and tests match the addendum; treat that count as coder-reported.

---

## Findings

### Critical

None. No cross-workspace invoice/item/product leak. No float money path in WP-A invoice math.

---

### Warning

#### W1 — SIMPLIFIED send may snapshot invalid / oversized buyer `tax_id`

`_freeze_snapshots` writes `buyer_trn_snapshot = normalize(client.tax_id)` whenever the string is non-empty, including invalid IDs on SIMPLIFIED invoices.

- `buyer_trn_snapshot` is `String(15)`. `clients.tax_id` is `max_length=50`. A 16–50 character non-TRN value can **fail the send flush** (varchar overflow) or freeze garbage into the snapshot.
- WP-B PDF that prints `buyer_trn_snapshot` when present would show a non-FTA TRN on a simplified invoice.

**Fix (follow-up):** snapshot buyer TRN only if `_is_valid_trn(...)`; otherwise `None`.

#### W2 — Migration backfills line money but not header totals or snapshots

`c8e1a4f2b6d0` updates `invoice_items.line_net` / `tax_amount` / `total_price` and `invoices.supply_date`. It does **not** recompute `invoices.subtotal` / `tax_amount` / `total_amount`, and leaves snapshots null on existing SENT rows (addendum allowed best-effort).

After upgrade, live SENT invoices can have `Σ line_net ≠ header.subtotal`. WP-B must **fall back to live workspace/client when snapshots are null**, even if `status !== DRAFT`. New sends are fine.

#### W3 — STANDARD send success and snapshot immutability untested

`test_standard_send_requires_buyer_trn_and_address` only covers 400s. There is no test that:

- B2B client with valid TRN + address (or total > 10000 with both) sends 200 with `invoice_kind=STANDARD` and snapshots set;
- After send, PUT workspace/client TRN or address does not change GET snapshots.

Implementation looks correct; WP-B should not assume STANDARD was E2E-proven.

#### W4 — Catalog tax inherit and `NO_LIST_PRICE` untested

`test_product_id_copies_catalog` uses product `tax_rate=5.00`, same as workspace default — does not prove `_line_tax_rate` prefers product over workspace. Missing product with no `DEFAULT_SALES` price → 422 `NO_LIST_PRICE` is implemented, not tested.

#### W5 — `mark_as_sent` still skips FTA checks

Addendum: call `assert_fta_sendable` inside `mark_as_sent`. Router uses `send_invoice` (assert → freeze → `mark_as_sent`). Direct `mark_as_sent` remains a bypass. Only caller today is `send_invoice`. Defense-in-depth gap, not an HTTP hole.

#### W6 — `void_invoice` still raises `ValueError` → 500

Addendum asked to replace ValueError 500 risk with HTTPException. Send path is converted; double-void still `ValueError` uncaught in the router → global 500. Pre-existing; not FTA-specific.

#### W7 — `InvoiceResponse.currency` is AED-only enum

Write path correctly 422s USD. GET/create response validates `Currency.AED`. Any historic USD row will **500 on GET** `/invoices/{id}`. List items omit currency so list still works. Low likelihood (default AED); worth `str` on the response schema.

---

### Info

#### I1 — `InvoiceUpdate` supply/issue cross-field only when both present in the body

Create: pydantic 422 if `supply_date > issue_date`. Update: schema skips if only one date is patched; **service** `_assert_supply_date` still 422s against stored dates. Error envelope differs (pydantic `details` vs `VALIDATION_ERROR` + `field`). Behavior is correct.

#### I2 — `InvoiceItemUpdate` unused; no XOR

PUT replaces via `InvoiceItemCreate` (XOR present). Dead schema is harmless.

#### I3 — Payment PUT still exists

Pre-existing PDC lifecycle `PUT /invoices/{id}/payments/{payment_id}` (Wave 5). WP-A did not add or remove it. Matches “PDC PUT untouched”, not “no payment PUT in the codebase.”

#### I4 — Tests use `SQLModel.metadata.create_all`, not Alembic

Same harness as isolation/numbering. Migration correctness is a separate `alembic upgrade` / `alembic check` claim (coder: clean on `invoicesaas` and `_test`).

#### I5 — Isolation/numbering JSON still sends `tax_rate: 5.0`

Pydantic stores Decimal. Not a production float column.

#### I6 — `invoice_service.py` ~683 lines; mid-file schema imports in serializers

Style (file length, E402 on serialize helpers). `Invoice.amount_paid` still lazy-imports `PaymentStatus`.

#### I7 — `WorkspaceUpdate` does not `extra="forbid"`

Unknown keys (e.g. `iban`) are ignored, not 422. Addendum extra-forbid lock is on invoice/item bodies. Address GET/PUT round-trip is tested.

#### I8 — HTTPException handler does not copy `exc.headers`

401s from auth still lose `WWW-Authenticate`. Pre-existing; unwrap branch did not add header forwarding. String-detail routers unchanged (`HTTP_ERROR`).

#### I9 — Service does not re-check client `workspace_id` on create

Router 404s foreign `client_id`. `_load_send_context` uses `session.get(Client)` without workspace filter. Safe on the public API; not defense-in-depth.

#### I10 — Header `subtotal` / `tax_amount` are sums of already-quantized lines (not re-quantized)

Matches addendum. `total_amount = money(subtotal + tax_amount)`.

#### I11 — Client `trn` is validation_alias only

`tax_id` column unchanged. No `clients.trn`. Correct.

---

## Spec coverage vs `test_invoices.py`

| Addendum §11 | Coverage |
|---|---|
| 1 Omit tax_rate → 5% | `test_omit_tax_rate_inherits_workspace_default_5_percent` |
| 2 Explicit 0 | `test_explicit_tax_rate_zero_stays_zero` |
| 3 ROUND_HALF_UP identity | `test_line_money_round_half_up_and_header_identity` |
| 4 Line discount % VAT on net | `test_line_discount_percent_vat_on_net` |
| 5 Both discounts 422 | `test_both_discount_fields_422` |
| 6 product_id copy / override / 404 / inactive 400 | `test_product_id_*` (tax inherit vs workspace not isolated) |
| 7 Ad-hoc 201 | `test_adhoc_line_without_product_id_201` |
| 8–10 Send TRN/address | three send-blocked tests |
| 11 STANDARD missing buyer fields | `test_standard_send_requires_buyer_trn_and_address` (failure only) |
| 12 SIMPLIFIED success + snapshots | `test_simplified_send_succeeds_and_freezes_snapshots` |
| 13 PUT non-DRAFT 403 | `test_put_non_draft_403_invalid_state` |
| 14 Isolation 404 | `test_multi_tenant_isolation.py` (invoice GET/PUT/SEND/VOID) |
| 15 Overpay 400 | `test_overpayment_still_400` |
| 16 Extra `hs_code` 422 | `test_item_extra_key_hs_code_422` (+ header discount) |
| 17 supply_date > issue_date 422 | `test_supply_date_after_issue_date_422` |
| 18 Gapless | `test_concurrent_numbering.py` |
| 19 Isolation send FTA fixture | `test_payment_is_workspace_isolated` PUTs workspace TRN+address |

Extra (good): workspace address round-trip, supply default, draft PUT math, USD 422.

---

## WP-B notes (do not block start)

1. Prefer invoice snapshots when `status !== DRAFT` **and snapshots are non-null**; else live `/workspaces/me` + client (W2).
2. Title **Tax Invoice**; print supply date; line net / VAT% / VAT AED / gross.
3. Settings: `address` + TRN already on GET/PUT `/workspaces/me`.
4. Client TRN: send `tax_id` or alias `trn`; STANDARD send needs address + valid TRN.
5. Do not treat `buyer_trn_snapshot` as always FTA-valid until W1 is fixed.
6. Payment PUT is unchanged PDC; not part of this invoice form slice.

---

## Out of scope (confirmed absent)

- `clients.trn` column
- Workspace IBAN
- Header discount column
- New payment PUT
- Frontend / PDF / Playwright
- PostgreSQL ENUM changes / history rewrite
