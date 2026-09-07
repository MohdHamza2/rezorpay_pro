# Wave 28: UAE VAT Compliance Pack Export — Architecture Addendum (Phase 5)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file** (report-first).
**Review verdict (2026-09-07):** all three interpretation points confirmed as recommended — supplier invoices included = all except CANCELLED (§2.3); CN/TDN net item-level into output buckets (§4); `format=json` uses the `SuccessResponse` wrapper while CSV stays a raw binary `StreamingResponse` (§5).
**Extends:** `architecture/phase-5-comms-integrations-planning.md` §5 (VAT pack locks), live `invoice`/`credit_note`/`tax_debit_note`/`supplier_invoice` models, `ar_statement_service` period guards, `line_money.money`, `_require_owner_admin` RBAC precedent, `slowapi` limiter.
**Alembic:** **NO** — pure read-only queries. HEAD stays `c5b7a3e9f21d`; guardian pins (`test_pdc.py`/`test_pricing.py`) **unchanged**.
**Depends on:** nothing new from 26/27 (independent; runs on the same codebase).
**Review decision points (all confirmed locked by review, 2026-09-07):** §2.3 supplier statuses, §4 CN/TDN netting, §5 JSON wrapper.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `Invoice` | `issue_date`/`supply_date`/`due_date` Date; `invoice_kind` STANDARD/SIMPLIFIED; FTA snapshots (`seller_*`, `buyer_*`); `subtotal`/`tax_amount`/`total_amount` Numeric(12,2); `status` DRAFT/SENT/PARTIALLY_PAID/PAID/OVERDUE/CANCELLED; `deleted_at` column exists. |
| `InvoiceItem` | `tax_rate` Numeric(5,2); `line_net`/`tax_amount` line VAT; `total_price` = gross; `sku_snapshot`; `description`. |
| `CreditNote` | `issue_date` Date; status DRAFT/ISSUED (no CANCELLED); `invoice_kind` + snapshots; `tax_amount`/`total_amount`; `original_invoice_number`; `deleted_at` exists. `CreditNoteItem` has `tax_rate`/`line_net`/`tax_amount`. |
| `TaxDebitNote` | `issue_date` Date; status DRAFT/ISSUED; snapshots; header `tax_amount`/`total_amount`; `original_invoice_number`; `deleted_at` exists. `TaxDebitNoteItem` has `tax_rate`/`tax_amount`/`total_price` (gross; **no `line_net`** → net = `total_price − tax_amount`). |
| `SupplierInvoice` | `invoice_date` **DateTime(timezone=True)** (coerce to UTC date, `ar_statement_service.payment_on` pattern); `vat_amount`/`subtotal`/`total_amount`; status RECEIVED/PENDING_MATCHING/MATCHED/DISCREPANCY/APPROVED/PARTIALLY_PAID/PAID/CANCELLED; **no `deleted_at`**; `supplier_id` FK → `Supplier.name`/`trn`. `SupplierInvoiceItem` has `vat_rate`/`vat_amount`/`total_price` (gross; no net → net = `total_price − vat_amount`). |
| `Client` | `name`, `tax_id` (TRN), `address`. |
| `Workspace` | `name`, `trn`, `address`, `default_tax_rate`. |
| Period guards | `ar_statement_service.assert_from_not_after_to` (422 VALIDATION_ERROR) + `assert_range_not_too_long` (MAX_RANGE_DAYS 366, 422 DATE_RANGE_TOO_LONG). Reuse both. |
| Money | `line_money.money` — `Decimal`→`ROUND_HALF_UP` 2dp. Sums must use it; never float; no quantize to 0 (some lines are 0.00). |
| RBAC | `_require_owner_admin(user)` precedent (`pdc_service`, `email_service`); MEMBER → 403 `INSUFFICIENT_PERMISSIONS`. Test member token = direct `User(role=MEMBER)` insert + login (pattern `tests/test_email_comms.py:_member_token`). |
| Rate limit | `@limiter.limit("10/minute")` with `request: Request` first param (`comms_emails.py` pattern). |
| Wrapper | `SuccessResponse[T]` JSON; zip is **raw** `StreamingResponse`, `response_model=None`, never wrapped. |
| Config | pydantic-settings `case_sensitive=True`, `extra="ignore"`. `VAT_ORG_TRN` does **not** exist yet — add it (config only, no migration). |
| Tests | PostgreSQL `+_test`, `drop_all/create_all` module scope, `TestClient`, `hash_password` from `app.auth.utils`; direct SQLModel inserts for status variety (no API path exists for OVERDUE). |

**Drift vs §5.2 of the parent plan:** parent says "`invoice.invoice_date`"; the live column is **`issue_date`** (the FTA issue date). The business-date filter below uses `issue_date` for sales invoices/CN/TDN and the UTC-date part of `invoice_date` for supplier invoices. `created_at` is **never** a filter or a date shown.

---

## 1. Locked character and payload

### 1.1 In
- Strictly **read-only accounting/compliance export**. NOT an FTA submission, NOT certification, NOT e-invoicing, NOT XML/EDI filing. ZIP CSV + JSON mirror (LOCK #9/#10 of the parent plan).
- **No Alembic, no tables, no columns**, no model changes. Only addition is `config.py` → `VAT_ORG_TRN` (+ `.env.example`).
- `GET /api/v1/reports/vat-compliance?from&to&format=csv|json` — OWNER/ADMIN only, `10/minute`, `to−from > 366 days` → 422.
- ZIP (7 entries): `sales_invoices.csv`, `invoice_lines.csv`, `credit_notes.csv`, `tax_debit_notes.csv`, `purchase_invoices.csv`, `vat_summary.csv`, `manifest.json`.
- `format=json` returns the **same aggregates** as a JSON body (not a zip).

### 1.2 Out (deferred)
FTA submission/certification; XML/EDI/PINT-AE; per-invoice `invoice_kind` override; VAT return *filing* (boxes/„filing" logic); frontend; netting/credit engine; historic backfill; AR aging coupling.

---

## 2. Data rules

### 2.1 Business dates (inclusive `[from, to]` per document)
| Document | Date used |
|---|---|
| Sales invoice | `issue_date` |
| Credit note | `issue_date` |
| Tax debit note | `issue_date` |
| Supplier invoice (input) | UTC date of `invoice_date` (convert via `payment_on`-style datetime→date) |

`from`/`to` are Calendar-Date query params (`Query(..., alias="from"/"to")`; Python `period_from`/`period_to`).

### 2.2 Lifecycle-based inclusion — no invented VAT states
| Document | Included statuses | Excluded |
|---|---|---|
| Sales invoice | **SENT, PARTIALLY_PAID, PAID, OVERDUE** | DRAFT, CANCELLED |
| Credit note | **ISSUED** | DRAFT |
| Tax debit note | **ISSUED** | DRAFT |
| Supplier invoice (input) | **all except CANCELLED** (§2.3) | CANCELLED |

- **OVERDUE is never excluded** — payment status and tax-document status are separate. Outstanding amount is irrelevant to the pack (§5.2 parent).
- Every query scoped `workspace_id == workspace.id`; where a `deleted_at` column exists, add `deleted_at IS NULL`. (`supplier_invoices` has no `deleted_at`.)
- Inclusion uses **stored** tax fields verbatim (written at save/issue time). The pack does not recompute VAT.

### 2.3 Locked: supplier invoice statuses
Parent §5.2 “supplier invoices received”. Locked meaning: **a supplier invoice with any lifecycle status other than CANCELLED** (RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID). CANCELLED is the invalid-node terminal. Test coverage asserts CANCELLED absent and RECEIVED + APPROVED present.

---

## 3. ZIP content — exact files and columns

All amounts emitted as `f"{decimal:.2f}"` (never float/scientific); dates `YYYY-MM-DD`. Empty entity set → file still present with header row only (deterministic 7 entries).

### 3.1 `sales_invoices.csv`
`invoice_number, issue_date, supply_date, due_date, invoice_kind, status, currency, client_name, client_trn, subtotal, tax_amount, total_amount, seller_trn`

- `client_name`/`client_trn` = `COALESCE(buyer_name_snapshot, client.name)` / `COALESCE(buyer_trn_snapshot, client.tax_id)` (snapshots are the FTA truth for issued docs).
- `seller_trn` = `COALESCE(seller_trn_snapshot, workspace.trn)`.

### 3.2 `invoice_lines.csv`
`invoice_number, description, sku_snapshot, quantity, unit_price, tax_rate, discount_amount, line_net, tax_amount, total_price`

One row per `InvoiceItem` of an included invoice (exact stored line values; `quantity` as stored, e.g. `2.00`).

### 3.3 `credit_notes.csv`
`credit_note_number, issue_date, original_invoice_number, reason, status, client_name, client_trn, subtotal, tax_amount, total_amount`

### 3.4 `tax_debit_notes.csv`
`debit_note_number, issue_date, original_invoice_number, reason, status, client_name, client_trn, subtotal, tax_amount, total_amount`

### 3.5 `purchase_invoices.csv` (input VAT)
`supplier_invoice_number, invoice_date, supplier_name, supplier_trn, currency, subtotal, vat_amount, total_amount, status`

- `supplier_name`/`supplier_trn` from the `Supplier` join (workspace-scoped supplier).

### 3.6 `vat_summary.csv`
`direction, tax_rate, count, taxable_amount, vat_amount`

Per-rate bucket rows for **output** and **input** (§4). `tax_rate` printed as fixed 2dp (e.g. `5.00`, `0.00`).

### 3.7 `manifest.json`
```json
{
  "generator": "InvoiceSaaS VAT Compliance Pack",
  "version": "1",
  "generated_at": "…",            // UTC ISO 8601
  "period": { "from": "…", "to": "…" },
  "org": { "name": "…", "trn": "<VAT_ORG_TRN or workspace.trn, may be empty>", "address": "…" },
  "currency": "AED",
  "summary": { "output_tax": "…", "input_tax": "…", "net_tax": "…" },
  "files": [ "sales_invoices.csv", "invoice_lines.csv", "credit_notes.csv", "tax_debit_notes.csv", "purchase_invoices.csv", "vat_summary.csv" ],
  "excluded": { "statuses": "DRAFT invoices / DRAFT credit notes / DRAFT TDN / CANCELLED invoices / CANCELLED supplier invoices" }
}
```
`org.trn` = `VAT_ORG_TRN` if non-empty else `workspace.trn` (may be empty/`""`). **Report generation is never blocked by an absent TRN** (LOCK #10). `net_tax = output_tax − input_tax` (money()).

---

## 4. `vat_summary` computation (locked)

Built at **line level** (buckets keyed by `tax_rate`; one row per rate present, outputs and inputs):

### 4.1 output buckets
- Sales: for each included `InvoiceItem`: `taxable += line_net`, `vat += tax_amount`, `count += 1`, keyed by `tax_rate`.
- Credit notes **reduce output** at their own rate: for each included `CreditNoteItem`: `taxable −= line_net`, `vat −= tax_amount`, `count += 1`.
- Tax debit notes **raise output** at their own rate: for each included `TaxDebitNoteItem`: `taxable += (total_price − tax_amount)`, `vat += tax_amount`, `count += 1`.

### 4.2 input buckets
- For each included `SupplierInvoiceItem`: `taxable += (total_price − vat_amount)`, `vat += vat_amount`, `count += 1`, keyed by `vat_rate`.

### 4.3 rounding
Bucket sums accumulate in `Decimal`, then each final bucket cell is emitted via `money()` (§0). `output_tax = Σ(vat of output rows)`, `input_tax = Σ(vat of input rows)`.

Rationale: `credit_notes.csv`/`tax_debit_notes.csv` are separate files but the summary must present net output VAT (a FTA VAT-return-shaped view), so adjustments net into their own rate buckets. Flagged for review.

---

## 5. Endpoint (locked)

`GET /api/v1/reports/vat-compliance`

| Param | Type | Notes |
|---|---|---|
| `from` | `date` required | `period_from: date = Query(..., alias="from")` |
| `to` | `date` required | `period_to: date = Query(..., alias="to")` |
| `format` | `Literal["csv","json"]` default `"csv"` | |

- RBAC: OWNER/ADMIN only (`_require_owner_admin`); MEMBER → 403 `INSUFFICIENT_PERMISSIONS`.
- `@limiter.limit("10/minute")` — both formats.
- Guards: reuse `assert_from_not_after_to` (422 `VALIDATION_ERROR`, field `from`) and `assert_range_not_too_long` (422 `DATE_RANGE_TOO_LONG`, field `to`).
- `format=csv`: `StreamingResponse(zip_bytes, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="vat-compliance-{from}_to_{to}.zip"'})`, **`response_model=None`** — the shared `{success,data,error}` wrapper is NOT used for binary (parent §5.4). Zip built in-memory (`io.BytesIO` + `zipfile.ZipFile`, `ZIP_DEFLATED`).
- `format=json`: `SuccessResponse[VatComplianceJsonResponse]` with the same aggregates (manifest + summary + the six tabular datasets) — the standard wrapper **is** used for JSON (locked; the parent §5.4 mandate only forbids wrapping the binary zip).
- New router `app/routers/reports.py`, wired `app.include_router(reports_router, prefix="/api/v1")` in `main.py`.

Cross-workspace: all rows filtered to the JWT workspace; workspace B documents never appear in workspace A’s pack (404-style isolation is implicit — nothing is ever fetched outside the workspace).

---

## 6. Module boundaries

| Layer | Owns |
|---|---|
| `routers/reports.py` | `GET /api/v1/reports/vat-compliance`, RBAC, `10/minute`, query params, format dispatch, `StreamingResponse` |
| `services/vat_compliance_service.py` | query assembly (§2), datasets (§3), `vat_summary` (§4), `build_zip()`, JSON payload — all reads, no writes |
| `schemas/vat_compliance.py` | `VatComplianceJsonResponse` (+ row models for each dataset) |
| `app/config.py` + `.env.example` | `VAT_ORG_TRN: str = ""` — **optional**, never blocks generation (LOCK #10) |

---

## 7. Tests — `tests/test_vat_compliance.py`

PostgreSQL only; direct SQLModel seeding for status variety (no API sets OVERDUE). One workspace with TRN set; invoices across SENT/PARTIALLY_PAID/PAID/OVERDUE/DRAFT/CANCELLED; CN ISSUED + DRAFT; TDN ISSUED + DRAFT; supplier invoices RECEIVED/APPROVED/CANCELLED; VAT rates 5.00 and 0.00.

1. **CSV zip integrity:** `format=csv` → 200 `application/zip`; bad `Content-Disposition` filename `vat-compliance-*-to-*.zip`; unzip → exactly the 7 entries; every CSV has header row; `manifest.json` parses; org present with TRN when set.
2. **Per-line VAT math:** `invoice_lines.csv` matches stored `line_net`/`tax_amount`/`tax_rate`/`total_price` (2-line invoice, mixed 5% / 0%).
3. **Summary output+input:** per-rate buckets; 5% output = Σ invoice line_net → tax 5%; CN 5% reduces output bucket; TDN raises it (net = total−tax); 0% bucket carries VAT 0.00; input bucket from `vat_amount`; `output_tax − input_tax = net_tax`.
4. **Excluded statuses absent:** DRAFT invoice, CANCELLED invoice, DRAFT CN, DRAFT TDN, CANCELLED supplier invoice all absent from their CSVs; RECEIVED + APPROVED supplier invoices present.
5. **OVERDUE-but-SENT included:** an OVERDUE invoice (issue in range) appears in `sales_invoices.csv` and its lines in `invoice_lines.csv`.
6. **Period bounds:** `to−from = 367 days` → 422 `DATE_RANGE_TOO_LONG`; `from > to` → 422 `VALIDATION_ERROR`.
7. **RBAC:** MEMBER → 403 `INSUFFICIENT_PERMISSIONS` (both formats).
8. **JSON mirror:** `format=json` → `success:true`, `.data` aggregates equal the CSV-derived values (same sums/datasets), manifest keyed the same.
9. **Business-date, not created_at:** rows inserted with `issue_date` in range but backdated `created_at` outside → included; `issue_date` outside range (recent created_at) → excluded.
10. **No-TRN tolerance:** `VAT_ORG_TRN` unset and workspace TRN null → 200, manifest `org.trn == ""` (never blocked).
11. **Workspace isolation:** workspace B documents absent from workspace A’s pack (format=csv and format=json).

Verify: full suite green + ruff + black on touched files + `alembic check` clean (no head change; guardian pins untouched). Then `STATE.md` + commit.

---

## 8. NOT in this slice

FTA submission/certification; XML/EDI/PINT-AE; VAT-return box filing logic; frontend UI; `invoice_kind` override; header-level summary only (summary is line-level); AR-aging coupling; backfill; scheduled/cached exports; multi-workspace org packs.

---

## 9. Drift

| Paper | This wave |
|---|---|
| Parent §5.2 “`invoice.invoice_date`” | Live column `issue_date` (FTA issue date) — sales invoices, CN, TDN use it; supplier invoices use UTC date of `invoice_date`. |
| Parent §5.4 “6 entries + headers” | 6 data CSVs + `manifest.json` = 7 zip entries; empty sets emit header-only files. |
| `created_at` as tax filter | **Never** — business dates only (§2.1). |
| FTA snapshots | Prefer `buyer/seller_*_snapshot` over live client/workspace columns for issued docs (§3.1). |
| Summary | Line-level, CN/TDN net into output buckets (§4). |

---

## 10. Coder checklist

1. Report-first: prepend the Wave 28 section to `.agents/reports/backend-execution-report.md` **before any code**.
2. Config only: `VAT_ORG_TRN` in `app/config.py` + `backend/.env.example`. **No Alembic; no model edits; head stays `c5b7a3e9f21d`** (guardian pins unchanged, `alembic check` clean).
3. Implement service → schemas → router (`reports.py`) → wire `main.py`.
4. Tests §7 green; full suite green; ruff + black clean on touched files.
5. Update `STATE.md`; then commit the wave.
6. Each wave commits separately; never leave verified work uncommitted.
