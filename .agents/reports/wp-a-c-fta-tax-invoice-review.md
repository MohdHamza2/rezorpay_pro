# WP-A–C FTA Tax Invoice — Code Review

**Date:** 2026-09-01
**Scope:** Full slice vs `architecture/wave-fta-tax-invoice-addendum.md` — WP-A API+Alembic, claimed WP-A nit fixes (W1/W3/W5), WP-B UI/PDF, WP-C Playwright.
**Reviewer:** Ruflo reviewer subagent.
**Mode:** Review only. No implementation. No git commit.

**Shipped (reviewed on disk):**

- Alembic `c8e1a4f2b6d0` (`down_revision = "06c9b4b1dcda"`)
- `InvoiceService` FTA send + `mark_as_sent`, snapshots, line VAT math, `tests/test_invoices.py` + isolation
- Settings address, invoice form, Tax Invoice PDF + preview, `FTA_SEND_BLOCKED` banner
- Playwright: `fta-send-blocked`, `fta-tax-invoice` (SIMPLIFIED), `fta-isolation` 404; product specs still in the same run

**Prior WP-A verdict:** `APPROVE_WITH_NITS` (`.agents/reports/wp-a-fta-tax-invoice-review.md`). W1 / W3 / W5 claimed fixed — **verified**.

**Verdict: `APPROVE_WITH_NITS`**

This slice may be committed when the user asks. Next product work is quotations → LPO (gaps 4–5), not another FTA pass.

No P0 tenant-leak. No backend float-money path. Remaining items are coverage, PDF live-fallback hygiene on SIMPLIFIED buyer TRN, and pre-existing gaps (password 6 vs 8, void `ValueError`, response `Currency` enum).

---

## Verdict rationale

Isolation 404, Decimal `ROUND_HALF_UP` line math, FTA send hard-fails, `mark_as_sent` no longer skipping FTA, SIMPLIFIED refusing garbage `buyer_trn_snapshot`, DRAFT-only PUT, extra-key 422, AED write lock, gapless `INV-YYYY-XXXX`, PDF title **Tax Invoice**, and snapshot-or-live fallback are in place and match the addendum.

WP-C proves the SIMPLIFIED happy path, send-blocked, and cross-tenant GET 404. It does **not** exercise the addendum’s catalog `product_id` + inherited VAT browser path, nor STANDARD buyer-TRN in the browser (API tests do). That is a nit, not a BLOCK — checklist item 11 is explicit.

Do not treat `APPROVE_WITH_NITS` as “WP-C fully matches addendum §12 WP-C paragraph.” Treat it as: ship-safe; leftovers are documented; quotes/LPO next.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 API + e2e | **PASS.** Router GET/PUT/SEND/VOID filter `workspace_id` + `deleted_at`; cross-workspace is 404 not 403. Cross-workspace `product_id` 404. `test_invoice_is_workspace_isolated` + `test_payment_is_workspace_isolated` (FTA fixture on send). Playwright `fta-isolation.spec.ts` GET 404 (not 403). No `/invoices/:id` SPA route — API GET is the isolation surface. |
| 2 | Decimal line math; UI `?? 0` before `toFixed` | **PASS.** `money()` = `quantize(0.01, ROUND_HALF_UP)` per line then sum. `_dec(str(...))`. No `float` in invoice service/models/schemas. FTA UI: `formatAed` / PDF `money()` use `Number(value ?? 0).toFixed(2)`. |
| 3 | Send hard-fails; `mark_as_sent` cannot skip FTA | **PASS.** W5 fixed. `mark_as_sent` calls `assert_fta_sendable` then `_apply_send_snapshots`. `send_invoice` only delegates to `mark_as_sent`. 400 `FTA_SEND_BLOCKED` + `error.field`. 403 remains `INVALID_STATE` for non-DRAFT. |
| 4 | SIMPLIFIED does not snapshot garbage TRN | **PASS.** W1 fixed. `_snapshot_trn` persists only `^100[0-9]{12}$`. `test_simplified_send_does_not_snapshot_invalid_tax_id` (`GARBAGE_TAX_ID` → `buyer_trn_snapshot is None`, still 200 SIMPLIFIED). |
| 5 | PDF title Tax Invoice; snapshot-or-live fallback | **PASS with nit.** Title is `Tax Invoice` (PDF + HTML preview). `snapOrLive`: non-DRAFT uses non-empty snapshot, else live (W2 migrated SENT). See W-B1: SIMPLIFIED `buyer_trn_snapshot` is intentionally null, so live `client.tax_id` can print after send. |
| 6 | Extra keys not sent from UI | **PASS.** `buildLinePayload` / create+update payloads are allow-lists (`InvoiceItemWrite`). No `hs_code`, `from_uom_id`, `line_net`, `id`, header `discount_amount`. API `extra="forbid"` on invoice/item create+update. |
| 7 | DRAFT-only edit | **PASS.** UI hides Edit/Send except `DRAFT`; `openModal` refuses non-DRAFT. Router `can_edit` + service `update_draft` both 403 `INVALID_STATE`. Snapshots not on update schema. |
| 8 | Payments PUT untouched; gapless numbering | **PASS.** `PUT /invoices/{id}/payments/{payment_id}` still PDC lifecycle; not in this slice’s dirty set. `InvoiceNumberService` still `SELECT … FOR UPDATE`, format `INV-YYYY-XXXX`. Numbering tests unchanged (create-time). |
| 9 | Playwright vs addendum WP-C; flaky 429 | **PASS with nits.** Covered: register → (optional) Settings TRN+address → client → ad-hoc invoice → send / block → preview **Tax Invoice**; second workspace GET 404. **Not** covered: catalog `product_id` + inherited VAT in this E2E (addendum WP-C listed it; WP-C brief used ad-hoc). Workers=1; register retries 429 (5×, 16s). Product-isolation can sit ~1m when the 5/minute auth window is full. Coder-reported 5 passed — not re-executed here. |
| 10 | Password 6 vs 8 still a gap | **CONFIRMED (pre-existing).** `Register.tsx` / `Login.tsx` zod `.min(6)`; `UserRegister` requires `len >= 8`. E2E uses `Passw0rd1` (8+). Not FTA-specific. |
| 11 | STANDARD buyer-TRN path untested in browser | **CONFIRMED (not BLOCK).** API: `test_standard_send_succeeds_and_freezes_snapshots` + `test_snapshots_immutable_after_send`. Playwright happy path is SIMPLIFIED, no `taxId`. |

WP-A nits **W1 / W3 / W5: fixed.** W3 now has STANDARD success + snapshot immutability tests.

Coder pytest/e2e counts were not re-run in this review.

---

## Findings

### Critical

None. No cross-workspace invoice/item/product leak. No float stored or computed in WP-A invoice math. `mark_as_sent` cannot bypass FTA.

---

### Warning

#### W-B1 — SIMPLIFIED SENT PDF can print live buyer `tax_id` (null snapshot → live)

`snapOrLive` uses live when snapshot is null/blank. That is correct for **legacy SENT** rows (W2) and for seller fields on new sends (always snapshotted).

For **new SIMPLIFIED** sends, `buyer_trn_snapshot` is **intentionally** `None` (W1). BuyerBlock then prints `client.tax_id` if the live client has one:

- Garbage TRN on a cash buyer (the W1 case) can still appear on the PDF even though the snapshot is clean.
- After send, editing the client TRN **drifts** the SENT PDF (kind stays `SIMPLIFIED`).

Addendum: omit buyer TRN row if null. HTML preview does not print buyer TRN (so E2E cannot catch this). Binary `InvoicePDF` does.

**Fix (follow-up, not this slice):** if `invoice_kind === 'SIMPLIFIED'`, do not live-fallback buyer TRN (print snapshot only). Keep live fallback when `invoice_kind` is null (migrated SENT).

#### W4 — Catalog tax inherit vs workspace, and `NO_LIST_PRICE`, still untested (carried)

`_create_catalog_product` defaults `tax_rate="5.00"` (same as workspace). `_line_tax_rate` product-over-workspace is implemented, not uniquely asserted. Missing `DEFAULT_SALES` → 422 `NO_LIST_PRICE` implemented, not tested.

#### W2 — Migration backfills lines, not header totals (carried; WP-B mitigated)

`c8e1a4f2b6d0` updates item `line_net` / `tax_amount` / `total_price` and `supply_date`. Header `subtotal` / `tax_amount` / `total_amount` and snapshots on existing SENT rows are untouched (addendum allowed best-effort). WP-B `snapOrLive` covers null snapshots. Header vs Σ lines can still disagree on **old** SENT rows until re-saved (cannot; non-DRAFT).

#### W-C1 — WP-C browser path is SIMPLIFIED ad-hoc, not addendum catalog line

Addendum §12 WP-C: client with TRN+address → product + `DEFAULT_SALES` → invoice with `product_id` and inherited VAT → send → PDF. Shipped: client **without** TRN, **ad-hoc** line, HTML preview (not binary PDF parse). Product catalog remains a **separate** spec. API covers `product_id` copy/404/inactive.

Do not block commit. Do not pretend the addendum paragraph was fully E2E’d.

---

### Info

#### I-A1 — Password 6 vs 8 (checklist 10)

Unchanged. Register UI accepts 6–7 chars; API 422s. Login min-6 is fine (login has no server min).

#### I-A2 — `void_invoice` still `ValueError` → 500 (prior W6)

Send path uses `HTTPException`. Double-void still uncaught `ValueError`. Pre-existing; not FTA.

#### I-A3 — `InvoiceResponse.currency` still AED-only enum (prior W7)

Writes 422 USD. Historic USD row GET `/invoices/{id}` can 500. List items omit currency. Low likelihood.

#### I-A4 — `WorkspaceUpdate` still not `extra="forbid"` (prior I7)

Unknown keys (e.g. `iban`) ignored. Invoice/item bodies are forbidden-extra. Settings form does not send IBAN.

#### I-A5 — `_load_send_context` does not re-check client `workspace_id` (prior I9)

Router 404s foreign `client_id` on create; update cannot change `client_id`. Public API safe; not defense-in-depth.

#### I-A6 — File length / mid-file imports (prior I6)

`invoice_service.py` ~681 lines; serialize helpers import schemas mid-file. `Invoices.tsx` ~757 lines. Style only.

#### I-A7 — `InvoiceItemUpdate` unused; no XOR

PUT replace-all uses `InvoiceItemCreate` (XOR present). Dead schema is harmless.

#### I-A8 — Tests still `create_all`, not Alembic (prior I4)

Same harness as isolation/numbering. Migration correctness is the coder `alembic upgrade` / `alembic check` claim (linear head `c8e1a4f2b6d0`).

#### I-A9 — UI money on the wire is JSON numbers

`buildLinePayload` uses `Number(...)`. Backend still `Decimal`. Tests send strings. Typical fils amounts survive; not a storage-float bug.

#### I-A10 — PDF download uses list-cached client, not `GET /clients/{id}`

`getClients()` default page size is 20. SENT invoices use snapshots first. DRAFT preview can miss buyer fields if the client is not on page 1.

#### I-A11 — Product picker is first 100 active products

`PRODUCT_PAGE_SIZE = 100`, page 1. Catalog-heavy workspaces can omit SKUs from the dropdown (ad-hoc still works).

#### I-A12 — Auth register `5/minute`

Helpers retry; workers=1. FTA specs were fast in the coder run; `product-isolation` absorbed the wait.

#### I-A13 — STANDARD via `total > 10000` success untested

Failure path tested (`client.tax_id` 400). Success STANDARD is via valid buyer TRN (small invoice). Kind logic is the same once buyer TRN+address exist.

#### I-A14 — PDF optional UOM / WhatsApp / email

Lines print SKU if present, not UOM code (`uom_id` only on the item). WhatsApp and buyer email come from **live** workspace/client even after send. Not FTA-required particulars.

#### I-A15 — Alembic linear

`c8e1a4f2b6d0` revises `06c9b4b1dcda` only. `invoice_kind` is `String(20)`, not a PG ENUM. No `clients.trn`. No IBAN. Ancestors untouched.

---

## WP-A nit regression (claimed fixed)

| Prior | Status |
|---|---|
| W1 SIMPLIFIED garbage `buyer_trn_snapshot` / varchar overflow | **Fixed.** `_snapshot_trn` + test. |
| W3 STANDARD success + snapshot immutability untested | **Fixed.** Two tests. |
| W5 `mark_as_sent` skipped FTA | **Fixed.** Assert + freeze inside `mark_as_sent`. |
| W2 / W4 / W6 / W7 | Still present (warnings/info above). |

---

## Spec coverage

### Addendum §11 (`test_invoices.py`)

| # | Coverage |
|---|---|
| 1 Omit tax_rate → 5% | `test_omit_tax_rate_inherits_workspace_default_5_percent` |
| 2 Explicit 0 | `test_explicit_tax_rate_zero_stays_zero` |
| 3 ROUND_HALF_UP identity | `test_line_money_round_half_up_and_header_identity` |
| 4 Line discount % VAT on net | `test_line_discount_percent_vat_on_net` |
| 5 Both discounts 422 | `test_both_discount_fields_422` |
| 6 product_id copy / override / 404 / inactive 400 | `test_product_id_*` (tax inherit vs workspace not isolated) |
| 7 Ad-hoc 201 | `test_adhoc_line_without_product_id_201` |
| 8–10 Send TRN/address | three send-blocked tests |
| 11 STANDARD missing buyer fields | `test_standard_send_requires_buyer_trn_and_address` |
| 12 SIMPLIFIED success + snapshots | `test_simplified_send_succeeds_and_freezes_snapshots` + garbage-TRN test |
| 13 PUT non-DRAFT 403 | `test_put_non_draft_403_invalid_state` |
| 14 Isolation 404 | `test_multi_tenant_isolation.py` + Playwright GET |
| 15 Overpay 400 | `test_overpayment_still_400` |
| 16 Extra `hs_code` 422 | `test_item_extra_key_hs_code_422` (+ header discount) |
| 17 supply_date > issue_date 422 | `test_supply_date_after_issue_date_422` |
| 18 Gapless | `test_concurrent_numbering.py` |
| 19 Isolation send FTA fixture | `test_payment_is_workspace_isolated` PUTs workspace TRN+address |

Extra (good): STANDARD success, snapshot immutability, SIMPLIFIED junk TRN, workspace address round-trip, supply default, draft PUT math, USD 422.

### WP-B vs addendum §12

Settings address + TRN label; Clients TRN + B2B address hint; invoice product picker + ad-hoc + discount XOR + inherit VAT placeholder + supply_date + AED; PDF **Tax Invoice** + line net/VAT/gross + CANCELLED watermark; send banner. Matches WP-B acceptance except binary PDF “5% VAT” is inferred from line rate, not a hardcoded label.

### WP-C vs addendum §12

| Addendum | Shipped |
|---|---|
| Register → Settings TRN+address+tax 5% | Yes (`saveWorkspaceFta`; tax input asserted 5) |
| Client with TRN+address | Address yes; **no TRN** (SIMPLIFIED) |
| Product + DEFAULT_SALES | **No** (ad-hoc line). Catalog is a separate spec. |
| Invoice `product_id` + inherited VAT | **No** in FTA E2E; API yes |
| Send → PDF/download fields | Send + **HTML** preview title + seller TRN. Download exists; E2E does not parse the blob. |
| Negative: send before TRN | `fta-send-blocked.spec.ts` |
| Second workspace 404 | `fta-isolation.spec.ts` API GET |

---

## Out of scope (confirmed absent)

- `clients.trn` column (alias `trn` → `tax_id` only)
- Workspace IBAN
- Header discount column
- New payment PUT / PDC changes
- PostgreSQL ENUM changes / history rewrite
- Arabic PDF / Peppol / quotes / LPO / credit notes
- Invoice-kind client override
- USD tax invoices on write/send

---

## Commit when asked

Safe to commit this slice as FTA WP-A–C. Do **not** expand this review into quotes/LPO. Leftovers (W-B1, W-C1, password 6/8, W4 tests) are follow-ups, not a reason to reopen FTA as the next feature.
