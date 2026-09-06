# Supplier AP + Payments — Wave 22 Addendum (Phase 4)

**Date:** 2026-09-06
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `SupplierInvoice` (already has `amount_paid`, `balance_due`, `paid_at`, `PARTIALLY_PAID`/`PAID` statuses **that nothing ever writes**), the 3-way match engine (`submit-matching` → `MATCHED`/`DISCREPANCY`, `resolve-discrepancy`/`approve` → `APPROVED`), the AR `Payment`/`PaymentMethod`/`PaymentStatus` enums, `PaymentService.record_payment` idempotency + immutability pattern, `PaymentService` status enum reuse, `CreditControlService.aging_buckets` (reuse, do not fork), `ar_statement_service` generated-statement pattern.
**Depends on:** Wave 21 3-way match (merged, HEAD `e1f5b8a2c3d4`), Wave 19b counting, AR PDC/statements.
**After this slice:** Phase 5 comms, purchase returns + debit notes, SPO amendments, RFQ award, supplier child-table APIs.

Copy the AR payment slice: **API + pytest in one WP** (no frontend). Alembic: **one new revision** for two new tables. Do not start anything else until pytest green.

UAE electrical AP: suppliers bill Net 30/45/60; buyer needs to record supplier payments (CASH / bank / cheque), see an AP ledger + statement per supplier, and track how long approved invoices have been owing. Wave 21 already builds the matching gate; this wave adds the money side.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `SupplierInvoice.status` | `RECEIVED → PENDING_MATCHING → (MATCHED | DISCREPANCY) → APPROVED → (PARTIALLY_PAID | PAID)`, `CANCELLED`. **`APPROVED`/`PARTIALLY_PAID`/`PAID` are the only payable states.** `MATCHED` must be approved first (INV-6.1). |
| `SupplierInvoice` money | `total_amount`, `amount_paid` (default 0), `balance_due` (set to `total_amount` at create). Decimals `Numeric(12,2)`. |
| `PaymentMethod` enum | `CASH | BANK_TRANSFER | CHEQUE | PDC | CREDIT_CARD` (AR shared). **AP posts only `CASH / BANK_TRANSFER / CHEQUE` in this wave** (see §2.4). |
| `PaymentStatus` enum | `PENDING | SUCCESS | FAILED | CANCELLED | REFUNDED` (AR shared). **AP writes only `SUCCESS`.** Only SUCCESS counts toward `amount_paid`. |
| `PaymentService.record_payment` | The concurrency template to mirror: `FOR UPDATE` lock on the invoice row inside the txn, idempotency check inside the txn (workspace-scoped, 48 h TTL, expired key deleted+reinserted), balance-cap before insert, then status recompute. |
| `payments.py` router | `POST` requires `Idempotency-Key` header (≤255 chars) → else 400; `@limiter.limit("10/minute")`; PUT → 405 immutable. Mirror all of it for AP. |
| `CreditControlService.aging_buckets` | Buckets `current, days_1_30, days_31_60, days_61_90, days_90_plus` from `(as_of − due_date).days`; sums live `balance_due`. **Reuse for AP** by passing `SupplierInvoice` rows (duck-typed on `balance_due`/`due_date`). |
| `ar_statement_service` | Generated statement: query-only, opening reconstructed, running balances, `money()` rounding, 366-day range, `as_of` ≤ today, 2000-line cap. Mirror for supplier statement. |
| `raise_error` helper | `app/services/customer_po_support.py`; `ErrorCode` in `app/schemas/common.py`. |
| Alembic HEAD | **`e1f5b8a2c3d4`**. New revision `down_revision = "e1f5b8a2c3d4"`. Never rewrite history. |

CLAUDE.md: Decimal `Numeric(12,2)` + `money()` rounding; payments immutable; wrapper `{success, data, error}`; isolation **404 not 403**; never SQLite; workspace-scoped everywhere; no comments unless asked.

---

## 1. What Wave 21 already gives us (do not rebuild)

- Endpoints: `POST /supplier-invoices`, `GET /supplier-invoices`, `GET /supplier-invoices/{id}`, `POST /{id}/submit-matching`, `POST /{id}/resolve-discrepancy`, `POST /{id}/approve`.
- `SupplierInvoiceStatus.PARTIALLY_PAID` / `PAID` and columns `amount_paid`, `balance_due`, `paid_at` **already exist but nothing ever sets them**. This wave is the missing writer.
- There is **no** supplier-invoice event/history table and **no** audit hook in `supplier_invoice_service`. Do **not** add one this wave; the immutable `supplier_payments` rows are the AP audit trail.

**Wave 22 therefore = new `supplier_payments` + idempotency tables, a recording service (mirror AR), AP aging, supplier statement (= the AP ledger), wired into the existing status machine.**

---

## 2. Payment recording

### 2.1 Model — `SupplierPayment` (`supplier_payments`)

| Column | Type / rule |
|---|---|
| `id` | UUID PK |
| `workspace_id` | FK `workspaces.id`, indexed |
| `supplier_id` | FK `suppliers.id`, indexed |
| `supplier_invoice_id` | FK `supplier_invoices.id`, indexed |
| `amount` | `Numeric(12,2)`, `CheckConstraint(amount > 0)` |
| `payment_date` | `DateTime(timezone=True)` — UTC date as `datetime.combine(date, min).replace(tzinfo=utc)` like AR |
| `payment_method` | `PaymentMethod` enum (shared) |
| `status` | `PaymentStatus` enum (shared). Created `SUCCESS`. |
| `reference_number` | `str(100)` nullable |
| `bank_name` | `str(255)` nullable |
| `created_by` | FK `users.id` |
| `created_at` / `updated_at` | tz-aware, server/client default |

### 2.2 Model — `SupplierPaymentIdempotencyKey` (`supplier_payment_idempotency_keys`)

Mirror `IdempotencyKey` exactly (workspace-scoped compound PK, 48 h TTL, `is_expired()`), **but** FK `supplier_payment_id` → `supplier_payments.id`. Do **not** reuse the AR `idempotency_keys.payment_id` column (it FK-targets `payments.id`; sharing it would be a lie).

### 2.3 Recording flow — `SupplierPaymentService.record_payment` (mirror AR step-for-step)

1. `SELECT ... FOR UPDATE` the supplier invoice (workspace-scoped). Missing → **404 `NOT_FOUND`**.
2. Idempotency check **inside the transaction**: same workspace+key found and unexpired → return the existing payment (no new row, no double count). Expired → delete row, continue.
3. **Eligibility gate (integrates the 3-way match engine):** `invoice.status` must be `APPROVED` or `PARTIALLY_PAID`, else **400 `INVALID_STATE`** (`"Supplier invoice is not APPROVED; it cannot be paid"`). `CANCELLED`, `MATCHED`, `DISCREPANCY`, `RECEIVED`, `PENDING_MATCHING` all rejected — nothing bypasses approval, so the match engine is never bypassed.
4. `balance_due = money(total_amount − amount_paid)`; amount `> balance_due` → **400 `PAYMENT_EXCEEDS_BALANCE`** (same message shape as AR). No overpayment.
5. Insert `SupplierPayment` (`status=SUCCESS`), flush for id.
6. Insert idempotency-key row (workspace-scoped, 48 h TTL).
7. Recompute invoice: `amount_paid += amount`; `balance_due = money(max(0, total − amount_paid))`; if `balance_due == 0` → `status = PAID`, `paid_at = now(utc)`; elif previous `APPROVED` → `status = PARTIALLY_PAID`. **Never** downgrade `PAID`. Empty-amount updates are idempotent (0 reduces nothing).
8. Commit. Return the payment. **No** `InvoiceEvent`/audit row (none exists for supplier invoices — §1); the payment row is the record. **No** credit-control evaluation (credit control is AR-side only).

### 2.4 Payment methods — MVP gate

AP posts `CASH`, `BANK_TRANSFER`, `CHEQUE` only. `PDC` to a supplier (post-dated cheque issued) is **deferred** — it needs the AR PDC lifecycle generalized (deposit/clear/bounce) and would otherwise create un-billable `PENDING` rows. `CREDIT_CARD` is a sales-acceptance method, not AP. The schema validator rejects non-{CASH, BANK_TRANSFER, CHEQUE} with **422 `VALIDATION_ERROR`** `field=payment_method`. `pdc_date`/`pdc_status`/gateway fields are **not** in the AP payload.

### 2.5 Immutability

Payments are **never** updated or deleted. `PUT /supplier-payments/{id}` → **405 `METHOD_NOT_ALLOWED`** (mirror AR). No cancel/void/reversal endpoints this wave (cheque bounce/refund handling is a later wave — record a correcting payment or debit-note settlement then).

---

## 3. Query surface

| Endpoint | Purpose |
|---|---|
| `POST /supplier-payments` | Record a payment (idempotency-key required, 10/min). |
| `GET /supplier-payments` | Paginated list; filters `supplier_id`, `status`, `from`/`to` (payment_date). |
| `GET /supplier-payments/{id}` | One payment (workspace-scoped, 404 isolation). |
| `PUT /supplier-payments/{id}` | **405** immutable. |
| `GET /supplier-invoices/{id}/ap-balance` | `{total_amount, amount_paid, balance_due, currency}` — mirrors AR `/balance`. |
| `GET /supplier-invoices/{id}/payments` | Paginated payments for one invoice (mirror AR). |
| `GET /ap-aging` | AP aging report (§4). |
| `GET /suppliers/{id}/statement` | Supplier statement / **AP ledger** (§5). |

Roles: any JWT workspace member may read and record (same as AR payments). Cross-workspace id → **404**, never 403.

---

## 4. AP aging

Open AP = `SupplierInvoice` where `status ∈ {APPROVED, PARTIALLY_PAID}` and `balance_due > 0` (no deleted-flag columns exist on supplier invoices). `PAID` (balance 0) and `CANCELLED` are excluded by construction.

`GET /ap-aging?as_of=&supplier_id=&view=`:

| Query | Lock |
|---|---|
| `as_of` | Optional `date`, default UTC today, **not after today** → 422 `VALIDATION_ERROR` `field=as_of`. |
| `supplier_id` | Optional filter. Given → 404 if not in workspace. |
| `view` | `summary` (default) | `detail` | `by_supplier`. |

- **Buckets:** reuse live `CreditControlService.aging_buckets(invoices, as_of)` (duck-typed on `balance_due`/`due_date`), zero-duplication.
- `summary`: `as_of`, `supplier_count`, `invoice_count`, `total_outstanding`, `buckets` (the 5 live keys, `CreditBuckets` shape).
- `detail`: every open invoice with supplier, supplier invoice number, `invoice_date`, `due_date`, `days_overdue`, `balance_due`, and its bucket key.
- `by_supplier`: per-supplier `{supplier: {id, name}, total_outstanding, buckets}` + workspace grand totals (`total_outstanding`, `buckets`).
- Invariant: `sum(buckets) == total_outstanding`. Past `as_of` allowed (days computed vs `as_of`); amounts always **live** `balance_due`.

---

## 5. Supplier statement = AP ledger

**Decision: generated, query-only — no ledger table** (same reasoning as `wave-ar-statement-addendum`: a persisted AP ledger is a second book that drifts from `supplier_invoices` + `supplier_payments`). The statement *is* the AP ledger view.

`GET /suppliers/{id}/statement?from=&to=&as_of=`:

| Query | Lock |
|---|---|
| `from` | Required `date` |
| `to` | Required `date` |
| `as_of` | Optional `date`, default today, not after today |

Validation identical to AR: `from > to` → 422 `field=from`; `(to−from).days > 366` → 422 `DATE_RANGE_TOO_LONG` `field=to`; activity lines > 2000 → 400 `STATEMENT_TOO_LARGE`; no pagination.

Include-set S: this supplier's invoices, `status ∈ {APPROVED, PARTIALLY_PAID, PAID}`.
Payments: `status=SUCCESS`, parent invoice ∈ S.
**Excluded:** `CANCELLED` invoices and their payments (void + money gone together), `RECEIVED`/`PENDING_MATCHING`/`MATCHED`/`DISCREPANCY` (not approved, not billable yet).

Doc-type enum (new, AP-scoped): `OPENING | SUPPLIER_INVOICE | SUPPLIER_PAYMENT | SUPPLIER_PAYMENT_PENDING`.

| Line | Debit | Credit |
|---|---|---|
| Opening | (reconstructed) | |
| SUPPLIER_INVOICE (`invoice_date` in range) | `total_amount` | 0 |
| SUPPLIER_PAYMENT (SUCCESS in range) | 0 | `amount` |
| SUPPLIER_PAYMENT_PENDING | 0 | 0 (memo-only) |

`SUPPLIER_PAYMENT_PENDING` exists for parity with AR and future PDC-to-supplier, but this wave's schema cannot create PENDING payments; still handle the row type in the assembler.

Math (identical formulas to AR statement, mirrored): opening = Σ invoice totals before `from` − Σ SUCCESS payments before `from`; running begins at opening, `money(running + debit − credit)`; `totals = {billed, paid, pending, closing_running}`; footer `{amount_due_now, aging}` where `amount_due_now = Σ live balance_due` of open AP. `as_of` affects aging day-count only; amounts stay live.

`currency = "AED"` (single-currency workspace; matches AR statement shape).

---

## 6. Schemas

- `backend/app/schemas/supplier_payments.py`: `SupplierPaymentCreate` (amount `gt=0`; `payment_method` enum restricted; `payment_date` ≤ today validator mirroring AR; `reference_number` ≤ 100; `bank_name` ≤ 255), `SupplierPaymentResponse`, `SupplierApBalanceResponse`, `SupplierPaymentFilters` (optional).
- `backend/app/schemas/ap_aging.py`: `ApAgingSummaryResponse`, `ApAgingDetailResponse`, `ApAgingBySupplierResponse` (each holds the `CreditBuckets` shape — import from `app.schemas.clients`).
- `backend/app/schemas/supplier_statements.py`: `StatementDocType` (`OPENING | SUPPLIER_INVOICE | SUPPLIER_PAYMENT | SUPPLIER_PAYMENT_PENDING`) + `DOC_TYPE_LABELS`, `SupplierStatementLine`, `SupplierStatementTotals`, `SupplierStatementResponse` — mirror `ar_statements.py`.
- Reuse `SuccessResponse`, `PaginatedResponse`, `PaginationMeta`, `ErrorCode` from `app.schemas.common`.
- Add `AP_PAYMENT_NOT_APPROVED` and `AP_AGING_VIEW` errors if desired; core codes already exist (`PAYMENT_EXCEEDS_BALANCE`, `INVALID_STATE`, `NOT_FOUND`, `VALIDATION_ERROR`, `DATE_RANGE_TOO_LONG`, `STATEMENT_TOO_LARGE`). String codes `IDEMPOTENCY_KEY_REQUIRED` / `IDEMPOTENCY_KEY_TOO_LONG` (exact AR strings in `payments.py`) used as-is.

---

## 7. Migration

One revision `e1f5b8a2c3d4 → new` (`add_supplier_payments`): create `supplier_payments` (with `CheckConstraint("supplier_payments", "amount > 0")`) and `supplier_payment_idempotency_keys`; index `supplier_id`, `supplier_invoice_id`, `created_by`, `payment_date`. Downgrade drops both. No column changes to existing tables. `models/__init__.py` registers both models in `__all__`.

Settings/workspace: **no** new workspace settings (`ap_approval_threshold` D-27 stays informational; approvals are the existing `approve_invoice`).

---

## 8. Modules

| Layer | Owns |
|---|---|
| `models/supplier_payment.py` | `SupplierPayment`, `SupplierPaymentIdempotencyKey` |
| `services/supplier_payment_service.py` | `record_payment` (mirror AR), balance calc, list/get, open-AP set, aging assembly, statement assembly |
| `routers/supplier_payments.py` | HTTP, 404, idempotency-key header, rate limit, query validation, PUT 405 |
| `schemas/supplier_payments.py`, `schemas/ap_aging.py`, `schemas/supplier_statements.py` | Payloads |
| `CreditControlService.aging_buckets` | Buckets — **reuse** |

File-size rule: services < 500 lines; split `ap_aging_service.py` / `supplier_statement_service.py` out of `supplier_payment_service.py` if it would exceed. Keep statement + aging in their own service modules mirroring AR separation.

`main.py`: import router, `app.include_router(supplier_payments_router, prefix="/api/v1")`.

---

## 9. Tests

`backend/tests/`, PostgreSQL only, Decimal fils, 404 isolation.

- **`test_supplier_payments.py`** — recording:
  1. Seed supplier invoice `status=APPROVED` (`total_amount=1000`, `balance_due=1000`). Record 400 → invoice `PARTIALLY_PAID`, `amount_paid=400`, `balance_due=600`, status SUCCESS, `payment_date` UTC.
  2. Record remaining 600 → invoice `PAID`, `paid_at` set, `balance_due=0`.
  3. Overpayment on open invoice → 400 `PAYMENT_EXCEEDS_BALANCE`.
  4. Eligibility gate: `RECEIVED`, `MATCHED`, `DISCREPANCY`, `CANCELLED` invoices → 400 `INVALID_STATE`; `MATCHED` blocked even though amount matches.
  5. Idempotency: same workspace+key replayed → same payment id returned, `amount_paid` unchanged, row count unchanged; different key on same invoice → second payment.
  6. Missing `Idempotency-Key` → 400; key > 255 chars → 400.
  7. Method gate: `PDC` → 422 `VALIDATION_ERROR`; `CASH`/`BANK_TRANSFER`/`CHEQUE` OK.
  8. `payment_date` in the future → 422.
  9. PUT → 405.
  10. Cross-workspace invoice id → 404; cross-workspace payment id GET → 404.
  11. `GET /supplier-invoices/{id}/ap-balance` matches `amount_paid`/`balance_due`.
  12. `GET /supplier-invoices/{id}/payments` paginated list lines up.
- **`test_ap_aging.py`**:
  1. Open invoices land in correct buckets per `(as_of − due_date).days`; `sum(buckets) == total_outstanding`.
  2. PAID (balance 0) and CANCELLED excluded.
  3. `as_of` future → 422; past as_of allowed and shifts days.
  4. `by_supplier` sums match workspace totals; `supplier_id` filter scopes it; unknown supplier → 404.
  5. **Invariant** (forge two invoices then aging): bucket sums == outstanding == live `balance_due` totals.
- **`test_supplier_statement.py`**:
  1. `from > to` → 422; range > 366 → 422 `DATE_RANGE_TOO_LONG`; `as_of` future → 422.
  2. APPROVED invoice in range → SUPPLIER_INVOICE debit; CANCELLED + its payments omitted; non-approved statuses omitted.
  3. SUCCESS payment in range → credit, `totals.paid`; opening reconstructed from rows before `from`.
  4. Running balances and `closing_running` match `money(opening + billed − paid)`.
  5. `amount_due_now` == Σ live open `balance_due`; wide-range identity `closing_running == amount_due_now` when all surviving activity covered.
  6. Cross-workspace supplier → 404.
- Regression: full suite stays green; `alembic check` clean; guard test `test_alembic_new_revision_parent_and_check` walks the new head (it auto-adapts).

**Integration with match engine:** the gate test in `test_supplier_payments.py` (RECEIVED/MATCHED/DISCREPANCY all rejected, only APPROVED/PARTIALLY_PAID payable) proves Wave 22 consumes Wave 21's state machine. The full GRN→match chain already lives in `test_e2e_3way_match.py`; do **not** duplicate the 30-call chain here — seed rows directly.

---

## 10. NOT in this wave

PDC-to-supplier + cheque bounce/reversal; purchase returns + debit-note AP settlement; supplier-invoice event/history table; maker-checker/payment approvals; multi-currency; bulk payments across invoices; partial-invoice multi-payment UX flows on the frontend (no frontend this wave); workspace settings `ap_approval_threshold` enforcement; an `ap_ledger` **table** (statement is the ledger); AR-side changes.

---

## 11. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` one section for Wave 22.
2. Migration `down_revision = "e1f5b8a2c3d4"`; `alembic upgrade head`, round-trip downgrade/upgrade, `alembic check`.
3. `record_payment` mirrors AR exactly (lock → idempotency → gate → cap → insert → key → status). Reuse `aging_buckets`. Reuse `money()`.
4. Only SUCCESS counts. No overpayment. Immutable. 404 isolation. `{success, data, error}`.
5. pytest green (new + full suite, 255 baseline), ruff + black clean, guard tests pass.
6. Update `.planning/STATE.md` (Wave 22 + Phase 4 progress) then **commit** the wave (lifecycle final step).
7. Next slot after this: Phase 5 comms, or the audit leftovers (purchase returns/debit notes) — ask before starting a new phase.
