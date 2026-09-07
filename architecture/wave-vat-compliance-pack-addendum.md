# Wave 28: UAE VAT Compliance Pack Export — Architecture Addendum (Phase 5)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file** (report-first).
**Review verdict (2026-09-07):**
- **rev 1:** all three interpretation points confirmed as recommended — supplier invoices included = all except CANCELLED (§2.3); CN/TDN net item-level into output buckets (§4); `format=json` uses the `SuccessResponse` wrapper while CSV stays a raw binary `StreamingResponse` (§5).
- **rev 2 (these changes applied):** currency semantics (§2.4), supplier `invoice_date` business-date semantics (§2.1), and Alembic HEAD verification (checked live → `c5b7a3e9f21d`) all resolved against live code. Supplier inclusion wording hardened (§2.3); no-netting-engine boundary made explicit (§4.4); non-AED supplier invoices are listed but **never silently aggregated** (manifest `warnings`).
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
| `SupplierInvoice` | `invoice_date` **DateTime(timezone=True)** — driver renders UTC; Wave 28 buckets by **GST business date** (§2.1), NOT `.date()` on the UTC value; `vat_amount`/`subtotal`/`total_amount`; status RECEIVED/PENDING_MATCHING/MATCHED/DISCREPANCY/APPROVED/PARTIALLY_PAID/PAID/CANCELLED; **no `deleted_at`**; **currency unrestricted** (any 3-letter value, items too — multi-currency input is a designed feature via the match engine's `FAILED_CURRENCY`); `supplier_id` FK → `Supplier.name`/`trn`. `SupplierInvoiceItem` has `vat_rate`/`vat_amount`/`total_price` (gross; no net → net = `total_price − vat_amount`). |
| Currency (verified) | Sales invoices: **AED enforced** at create / PUT / send (`invoice_service._assert_aed` → 422; send → 400 `FTA_SEND_BLOCKED`; schema `Currency` has only `AED`). Credit notes: `currency = invoice.currency` (AED). Tax debit notes: `currency = invoice.currency` (AED). Supplier invoices: **unrestricted** (`str(max_length=3)`, stored as entered; match engine compares vs SPO currency → `FAILED_CURRENCY`). |
| FX mechanism (verified) | **None.** `RFQ.exchange_rate` exists (default 1.0, Numeric(12,6)) but is **never read** anywhere; no conversion/`forex`/`fx_rate` field on supplier invoices; nothing converts stored amounts to AED. **Wave 28 must NOT invent one.** |
| `Client` | `name`, `tax_id` (TRN), `address`. |
| `Workspace` | `name`, `trn`, `address`, `default_tax_rate`. |
| Period guards | `ar_statement_service.assert_from_not_after_to` (422 VALIDATION_ERROR) + `assert_range_not_too_long` (MAX_RANGE_DAYS 366, 422 DATE_RANGE_TOO_LONG). Reuse both. |
| Money | `line_money.money` — `Decimal`→`ROUND_HALF_UP` 2dp. Sums must use it; never float; no quantize to 0 (some lines are 0.00). |
| RBAC | `_require_owner_admin(user)` precedent (`pdc_service`, `email_service`); MEMBER → 403 `INSUFFICIENT_PERMISSIONS`. Test member token = direct `User(role=MEMBER)` insert + login (pattern `tests/test_email_comms.py:_member_token`). |
| Rate limit | `@limiter.limit("10/minute")` with `request: Request` first param (`comms_emails.py` pattern). |
| Wrapper | `SuccessResponse[T]` JSON; zip is **raw** `StreamingResponse`, `response_model=None`, never wrapped. |
| Config | pydantic-settings `case_sensitive=True`, `extra="ignore"`. `VAT_ORG_TRN` does **not** exist yet — add it (config only, no migration). |
| Tests | PostgreSQL `+_test`, `drop_all/create_all` module scope, `TestClient`, `hash_password` from `app.auth.utils`; direct SQLModel inserts for status variety (no API path exists for OVERDUE). |

**Drift vs §5.2 of the parent plan:** parent says "`invoice.invoice_date`"; the live column is **`issue_date`** (the FTA issue date). The business-date filter below uses `issue_date` for sales invoices/CN/TDN and the **GST calendar date** of `invoice_date` for supplier invoices (§2.1). `created_at` is **never** a filter or a date shown.

---

## 1. Locked character and payload

### 1.1 In
- Strictly **read-only accounting/compliance export**. NOT an FTA submission, NOT certification, NOT e-invoicing, NOT XML/EDI filing. ZIP CSV + JSON mirror (LOCK #9/#10 of the parent plan).
- **No Alembic, no tables, no columns**, no model changes. Only addition is `config.py` → `VAT_ORG_TRN` (+ `.env.example`).
- `GET /api/v1/reports/vat-compliance?from&to&format=csv|json` — OWNER/ADMIN only, `10/minute`, `to−from > 366 days` → 422.
- ZIP (7 entries): `sales_invoices.csv`, `invoice_lines.csv`, `credit_notes.csv`, `tax_debit_notes.csv`, `purchase_invoices.csv`, `vat_summary.csv`, `manifest.json`.
- `format=json` returns the **same aggregates** as a JSON body (not a zip).

### 1.2 Out (deferred)
FTA submission/certification; XML/EDI/PINT-AE; per-invoice `invoice_kind` override; VAT return *filing* (boxes/„filing" logic); frontend; historic backfill; AR aging coupling; multi-workspace org packs.

**No transactional netting/currency-credit engine is implemented.** The VAT summary performs **read-only aggregation of already-issued documents**: credit notes reduce and tax debit notes increase the *output summary* only; invoice/CN/TDN source rows are never modified, netted, or co-settled. There is no dashboard/credit-balance mutation, no invoice re-dating, no FX conversion, and no recovered-input-VAT claiming logic (§4.4).

---

## 2. Data rules

### 2.1 Business dates (inclusive `[from, to]` per document)
| Document | Date used |
|---|---|
| Sales invoice | `issue_date` |
| Credit note | `issue_date` |
| Tax debit note | `issue_date` |
| Supplier invoice (input) | **GST business date** of `invoice_date` (see below) |

`from`/`to` are Calendar-Date query params (`Query(..., alias="from"/"to")`; Python `period_from`/`period_to`).

**Supplier `invoice_date` → GST business date (locked, rev 2):** `invoice_date` is `DateTime(timezone=True)` (a `timestamptz`); the asyncpg driver renders it as UTC (no explicit session TZ in `app/database.py`), so `.date()` on the returned value yields the **UTC calendar date** — which arbitrarily shifts an off-hour Gulf timestamp by −1 day (e.g. `2026-09-01 00:30 +04:00` → UTC `2026-08-31 20:30` → `.date()` = **08-31**). That is wrong for a compliance period. Wave 28 therefore defines the explicit business-date rule:

- `business_date(invoice_date) = invoice_date.astimezone(GST).date()` where `GST = timezone(timedelta(hours=4))` (Gulf Standard Time, **fixed UTC+4, no DST**; a stdlib fixed offset — no new dependency, and `zoneinfo`/`tzdata` are NOT required).
- The whole pack is consistent in calendar dates on the **Gulf business calendar** (`from`/`to` inclusive, supplier invoices rendered in GST), matching UAE accounting reality.
- **Divergence note:** the live supplier statement / AP-aging stack buckets `invoice_date` by the driver-UTC `.date()` (`supplier_statement_service.py`). Wave 28 deliberately uses the GST rule for compliance-period correctness and does **not** change statements/aging (out of scope); the divergence is documented here and in §9 so the VAT pack and statements may disagree on an off-hour supplier invoice date.

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
Parent §5.2 “supplier invoices received”. Locked meaning: **supplier-invoice inclusion means the invoice exists in the accounting system and has not been cancelled** — i.e. any lifecycle status other than CANCELLED (RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID). CANCELLED is the invalid-node terminal. Test coverage asserts CANCELLED absent and RECEIVED + APPROVED present.

**This export does NOT determine input-tax recoverability or eligibility for VAT-return deduction.** The FTA attaches additional conditions to recovering input tax (retaining the relevant tax invoice/documentation, payment conditions, etc.). Including a supplier invoice here means only *“recorded in the accounting system, not cancelled”* — never an implicit claim that its VAT is deductible.

### 2.4 Locked: currency (verified against live code — rev 2)
Findings (from `app/services/invoice_service.py`, `app/schemas/invoices.py`, `app/services/credit_note_service.py`, `app/services/tax_debit_note_service.py`, `app/schemas/supplier_invoices.py`, `app/models/rfq.py`):

| Document | Currency at creation | Aggregatable in the pack? |
|---|---|---|
| Sales invoice | **AED forced** (`_assert_aed` at create 422 / PUT 422 / send 400 `FTA_SEND_BLOCKED`; schema enum only `AED`) | Yes — stored amounts are AED |
| Credit note | `= invoice.currency` → AED | Yes |
| Tax debit note | `= invoice.currency` → AED | Yes |
| Supplier invoice (input) | **Unrestricted** `str(max_length=3)`, items carry the same currency | **Only if AED** (§4.2). Non-AED listed but never aggregated |

- **No FX mechanism exists in the codebase.** `RFQ.exchange_rate` (Numeric(12,6), default 1.0) is never read by any other module; there is no conversion/converted-amount field on supplier invoices and nothing converts stored values to AED. `line_net`/`tax_amount`/`vat_amount` are plain `Numeric` columns denominated in each document's own header currency.
- **Wave 28 does NOT invent an exchange-rate mechanism** (reviewer mandate). Because not even the output side has any stored AED-converted amount for foreign supplier invoices, the pack's aggregation currency is **AED**, and the rule is:
  - **Output summary (invoices + CN + TDN): fully AED by construction** (input documents are AED-enforced).
  - **Input summary (supplier invoices): only AED supplier invoices are aggregated** into `vat_summary` input buckets.
  - **Non-AED supplier invoices are still included in `purchase_invoices.csv`** (with their `currency` column preserved) and are **explicitly enumerated** in `manifest.warnings.non_aed_supplier_invoices` — the exclusion from the summary is never silent.
- `manifest.currency = "AED"` means *the aggregation/reporting currency of `vat_summary` and the net tax figures* — never a claim that `purchase_invoices.csv` rows are AED.

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
- `invoice_date` rendered as the **GST business date** (§2.1).
- Includes **all non-CANCELLED** supplier invoices in the period, **regardless of currency**; the `currency` column preserves each row's own denomination. Non-AED rows are excluded from the summary (§2.4/§4.2) and enumerated in `manifest.warnings`.

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
  "currency": "AED",            // aggregation/reporting currency of vat_summary + net tax
  "warnings": { "non_aed_supplier_invoices": ["SI-…", "…"] },   // [] when none; non-AED input never aggregated
  "summary": { "output_tax": "…", "input_tax": "…", "net_tax": "…" },
  "files": [ "sales_invoices.csv", "invoice_lines.csv", "credit_notes.csv", "tax_debit_notes.csv", "purchase_invoices.csv", "vat_summary.csv" ],
  "excluded": { "statuses": "DRAFT invoices / DRAFT credit notes / DRAFT TDN / CANCELLED invoices / CANCELLED supplier invoices" }
}
```
`org.trn` = `VAT_ORG_TRN` if non-empty else `workspace.trn` (may be empty/`""`). **Report generation is never blocked by an absent TRN** (LOCK #10). `net_tax = output_tax − input_tax` (money()). The `currency` field is the **aggregation** currency — it does NOT state that `purchase_invoices.csv` rows are AED (§2.4); non-AED rows stay listed there and surface in `warnings`.

---

## 4. `vat_summary` computation (locked)

Built at **line level** (buckets keyed by `tax_rate`; one row per rate present, outputs and inputs):

### 4.1 output buckets
- Sales: for each included `InvoiceItem`: `taxable += line_net`, `vat += tax_amount`, `count += 1`, keyed by `tax_rate`.
- Credit notes **reduce output** at their own rate: for each included `CreditNoteItem`: `taxable −= line_net`, `vat −= tax_amount`, `count += 1`.
- Tax debit notes **raise output** at their own rate: for each included `TaxDebitNoteItem`: `taxable += (total_price − tax_amount)`, `vat += tax_amount`, `count += 1`.

### 4.2 input buckets
- For each included `SupplierInvoiceItem` of an **AED** supplier invoice: `taxable += (total_price − vat_amount)`, `vat += vat_amount`, `count += 1`, keyed by `vat_rate`.
- **Non-AED supplier invoices are excluded from the summary** (§2.4): their rows stay in `purchase_invoices.csv` and their numbers are collected into `manifest.warnings.non_aed_supplier_invoices`. They are never added to `input_tax` — no currency mixing, ever.

### 4.3 rounding
Bucket sums accumulate in `Decimal`, then each final bucket cell is emitted via `money()` (§0). `output_tax = Σ(vat of output rows)`, `input_tax = Σ(vat of input rows)`.

Rationale: `credit_notes.csv`/`tax_debit_notes.csv` are separate files but the summary must present net output VAT (a FTA VAT-return-shaped view), so adjustments net into their own rate buckets.

### 4.4 Boundary: this is aggregation, not an engine (locked, rev 2)
CN/TDN netting happens **only inside the read-only summary output** — no transactional netting, no credit-balance mutation, no invoice state change, no co-settlement, no FX conversion. Credit notes reduce output; tax debit notes increase it; source documents remain independent and unchanged. The pack performs **zero writes** (read-only service boundary) and asserts nothing about input-tax deductibility (§2.3).

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
12. **Non-AED supplier invoices (currency, rev 2):** seed an AED supplier invoice and a non-AED one (e.g. USD `1000.00`). Assert: both appear in `purchase_invoices.csv` with their own `currency`; the USD row's number appears in `manifest.warnings.non_aed_supplier_invoices`; USD `vat_amount` is **absent** from `vat_summary` input buckets and from `input_tax` (no mixing); AED input still aggregates; `net_tax` uses only AED input.
13. **GST business date (rev 2):** seed a supplier invoice with `invoice_date = 2026-09-01T00:30:00+04:00` (instant `2026-08-31T20:30Z`). Query window `[2026-09-01, 2026-09-30]` → the invoice is **included** and `purchase_invoices.csv`/`manifest` show `2026-09-01` (GST rule), NOT 08-31. Also confirm with a naive `2026-09-01T23:00:00` value bucketed to `2026-09-02` (GST render) for awareness of the rule.

Verify: full suite green + ruff + black on touched files + `alembic check` clean (no head change; guardian pins untouched). Then `STATE.md` + commit.

---

## 8. NOT in this slice

FTA submission/certification; XML/EDI/PINT-AE; VAT-return box filing logic; frontend UI; `invoice_kind` override; header-level summary only (summary is line-level); AR-aging coupling; backfill; scheduled/cached exports; multi-workspace org packs.

---

## 9. Drift

| Paper | This wave |
|---|---|
| Parent §5.2 “`invoice.invoice_date`” | Live column `issue_date` (FTA issue date) — sales invoices, CN, TDN use it; supplier invoices use the **GST business date** of `invoice_date` (§2.1). |
| Parent §5.4 “6 entries + headers” | 6 data CSVs + `manifest.json` = 7 zip entries; empty sets emit header-only files. |
| `created_at` as tax filter | **Never** — business dates only (§2.1). |
| FTA snapshots | Prefer `buyer/seller_*_snapshot` over live client/workspace columns for issued docs (§3.1). |
| Summary | Line-level, CN/TDN net into output buckets (§4). |
| Supplier `invoice_date` rendering | Live statement/AP-aging use driver-UTC `.date()`; the VAT pack uses the **GST (UTC+4) business date** — deliberate, documented divergence (§2.1). |
| Currency | Sales/CN/TDN amounts AED by construction; supplier invoices may be any currency — **non-AED supplier invoices are listed but never aggregated**, surfaced via manifest `warnings` (§2.4/§4.2). No FX conversion invented. |
| `RFQ.exchange_rate` | Unused across the system; NOT used or extended by Wave 28. |

---

## 10. Coder checklist

1. Report-first: prepend the Wave 28 section to `.agents/reports/backend-execution-report.md` **before any code**.
2. Config only: `VAT_ORG_TRN` in `app/config.py` + `backend/.env.example`. **No Alembic; no model edits.** **HEAD verified live = `c5b7a3e9f21d`** (`alembic heads`, 2026-09-07, after Wave 27); guardian pins unchanged; `alembic check` clean. Do NOT hardcode — re-verify `alembic heads` before implementing.
3. Implement service → schemas → router (`reports.py`) → wire `main.py`. Service includes the GST business-date helper (stdlib `timezone(timedelta(hours=4))`, no `zoneinfo`/`tzdata`) and the AED-only input summary rule. **Do NOT add any exchange-rate/conversion logic — none exists in the system and none may be invented.**
4. Tests §7 green; full suite green; ruff + black clean on touched files.
5. Update `STATE.md`; then commit the wave.
6. Each wave commits separately; never leave verified work uncommitted.
