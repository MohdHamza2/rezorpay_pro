# AP Payment Reversal (cheque bounce / transfer reversal) — Architecture Addendum (Wave 25 / Phase 4 leftover)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `SupplierPayment` (immutable SUCCESS-only settlement) / `SupplierPaymentService._settle_invoice` / `supplier_payments.py` router / AP statement `PAYMENT_STATUSES=(SUCCESS, PENDING)` omit behavior / the Wave 24 PDC machine (`supplier_pdc_service.py`). Do **not** invent a second AP ledger, negative payments, refunds, or a new ledger doc-type.
**Depends on:** Wave 22 AP payments, Wave 23 SDNs (AP credit route), Wave 24 PDC-to-supplier (`234d5639ef8c`, HEAD).
**After this wave:** Phase 5 comms (ask before starting). Not this slice: reversal of a **CLEARED PDC** (terminal, mirror AR), AR-side changes, refunds as negative payments, statement reversal lines, maker-checker, daily presentment, frontend.

Why this is the remaining Phase 4 leftover: a CHEQUE / CASH / BANK_TRANSFER payment is recorded SUCCESS-on-receipt (MVP "cleared-on-receipt" shortcut) and settles the invoice. If the bank later bounces the cheque or reverses the transfer, the payment must **not** stay SUCCESS forever — the AP was never really reduced. The AR machine declines this (CLEARED is terminal; reopen AR with a credit note). On AP, Wave 23 already gave SDNs as the credit route, but for a bounced *payment* the correct recovery is an explicit **reversal**: restore the invoice AP that was consumed. This wave closes that gap for non-PDC instruments; a **CLEARED PDC** stays terminal exactly like AR.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `record_payment` | Non-PDC (CASH / BANK_TRANSFER / CHEQUE) → always `SUCCESS` + `_settle_invoice` (`amount_paid += amount; balance_due = max(0, balance_due − amount)`; APPROVED→PARTIALLY_PAID, PAID at 0 + `paid_at`). |
| PENDING → statement | `PAYMENT_STATUSES=(SUCCESS, PENDING)` loaded; PENDING renders `SUPPLIER_PAYMENT_PENDING` (not in paid); **FAILED/CANCELLED/REFUNDED omitted**. |
| PDC machine (Wave 24) | CLEARED → SUCCESS terminal; BOUNCED → FAILED; RETURNED → CANCELLED. `_require_pdc` blocks non-PDC. |
| Roles | Payment create/list/get any member; PDC four POSTs OWNER/ADMIN (MEMBER 403). |
| Immutability | Amount/method/`payment_date`/`pdc_date`/reference/bank **never** UPDATE. Only `status`/`pdc_status`/`updated_at` move. |
| Isolation | `SupplierInvoice` id+workspace → 404; `SupplierPayment` id+invoice_id → 404. Never 403. |
| Alembic HEAD | **`234d5639ef8c`**. No new columns/enums/statuses → **NO new revision** this wave; `alembic check` stays clean; guard pins (`test_pdc.py`, `test_pricing.py`) unchanged. |

---

## 1. Design

### 1.1 Endpoint

```
POST /api/v1/supplier-invoices/{invoice_id}/payments/{payment_id}/reverse
```

Empty body `{}` (`extra="forbid"` — 422 on stray keys, same as PDC POSTs). No `Idempotency-Key` (FOR UPDATE both rows; already-reversed → **200** same response). Rate limit **10/minute**. **OWNER / ADMIN** only; MEMBER → **403** `INSUFFICIENT_PERMISSIONS` (not 404).

### 1.2 Eligibility

Reversal applies to a payment that is **SUCCESS today**:

- `payment.status == PaymentStatus.SUCCESS` — else:
  - `pdc_status == FAILED` (already reversed) → **200** no-op (idempotent target state).
  - anything else (PENDING PDC, BOUNCED, RETURNED, CANCELLED) → **403** `INVALID_STATE`.
- `payment.payment_method != PaymentMethod.PDC` — a PDC uses its own machine; **CLEARED PDC is terminal** (mirror AR). Reversing a CLEARED PDC → **403** `INVALID_STATE` (it is SUCCESS, so the method guard catches it first: non-PDC guard → 403 with message "PDC payments use the PDC lifecycle; CLEARED is terminal").
- `invoice.status in (APPROVED, PARTIALLY_PAID, PAID)` — open AP. CANCELLED → **403** `INVALID_STATE`.
- Defensive: `amount <= invoice.amount_paid` else **400** `PAYMENT_EXCEEDS_BALANCE` (unreachable via the API — `amount_paid` is exactly Σ SUCCESS payment amounts; kept as a guard, mirroring the forward overpay lock).

### 1.3 Effect — `SupplierPaymentService.reverse_payment`

Lock invoice then payment, `FOR UPDATE`. Set `payment.status = FAILED`, `payment.updated_at = now`. Running the inverse of `_settle_invoice` **inside the lock**:

```
invoice.amount_paid  = money(invoice.amount_paid - amount)
invoice.balance_due  = money(invoice.balance_due + amount)
invoice.updated_at   = now
if invoice.balance_due > 0:
    invoice.paid_at  = None
    if invoice.status == PAID: invoice.status = PARTIALLY_PAID
    if invoice.status == PARTIALLY_PAID and invoice.amount_paid == 0: invoice.status = APPROVED
```

Amount/method/dates **never** rewritten. No credit re-evaluation on AP (none exists).

### 1.4 Statement / aging / balance — no fork, no change

- Statement `_load_payments` already omits FAILED → a reversed payment disappears from activity; `totals.paid` recomputes from surviving SUCCESS rows; opening reconstruction = billed − SUCCESS paid − credited stays exact; closing_running recomputes to the restored `balance_due` → identity `closing_running == amount_due_now` holds. **No new doc-type, no statement code change.**
- `GET .../ap-balance`, `ap-aging`, `open_ap_invoices`: all read live `amount_paid`/`balance_due` → the invoice re-enters open AP / aging the moment it is reversed. No change.
- Reversed payment history stays visible via `GET /supplier-payments?status=FAILED` and `GET /supplier-payments/{id}` (audit trail; row is never DELETE).

### 1.5 Module boundaries

| Layer | Owns |
|---|---|
| `routers/supplier_payments.py` | `POST .../reverse` endpoint, HTTP 403/404, rate limit |
| `SupplierPaymentReversalService.reverse_payment` | FOR UPDATE pair, eligibility guards, `FAILED` + `_reverse_settlement` in lock |
| `SupplierPaymentService._settle_invoice` | **Reuse** forward side (untouched) |
| `SupplierStatementService` / `ap_aging` | **No code change** |

Reversal lives in a **dedicated `supplier_payment_reversal_service.py`**, not
in `supplier_payment_service.py` (would push it past the 500-line cap — the
documented release valve from Wave 24) and not in `supplier_pdc_service.py`
(it is PDC-specific; the machine forbids non-PDC).

### 1.6 API summary

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/supplier-payments` | any member | Unchanged (Idempotency-Key) |
| GET | `/supplier-payments`, `GET /{id}`, PUT 405, `ap-balance`, invoice payments, `ap-aging*`, statement | any member / JWT | Unchanged |
| POST | `/supplier-invoices/{id}/payments/{id}/pdc/*` | OWNER / ADMIN | Unchanged (Wave 24) |
| POST | `/supplier-invoices/{id}/payments/{id}/reverse` | **OWNER / ADMIN** | §1.2-1.3 this wave |

---

## 2. Tests — `backend/tests/test_supplier_payment_reversal.py`

PostgreSQL only. Decimals. Password 8+. Seed/invoice via the Wave 22 helpers (`seed_invoice`, `post_payment`, `ap_balance`).

1. **Full reversal, PARTIALLY_PAID invoice:** CHEQUE 4000/10000 → reverse → `status=FAILED`; `ap-balance` amount_paid 0.00, balance_due 10000.00; invoice back to APPROVED (paid 0). Second reverse → **200** no-op, balances unchanged.
2. **Full reversal of a settled (PAID) invoice:** CASH 10000/10000 (PAID, paid_at set) → reverse → amount_paid 0, balance_due 10000, status **APPROVED**, `paid_at` cleared.
3. **Partial reversal:** pay 800 (PARTIALLY_PAID), reverse 300 → amount_paid 500, balance_due 500, still PARTIALLY_PAID. Amount/method/date unchanged in response.
4. **Statement mapping:** invoice 1000, CASH 400 SUCCESS → statement `totals.paid=400`, SUCCESS line present; reverse → statement has no payment line, `totals.paid=0`, `amount_due_now=1000`, identity `closing_running == amount_due_now`.
5. **ap-aging re-entry:** after reversal the invoice appears in `ap-aging` detail and `sum(buckets) == balance_due`.
6. **Illegal:** reverse CLEARED PDC → **403** `INVALID_STATE`; reverse PENDING PDC → **403** (`_require_pdc` style); reverse RETURNED/BOUNCED payment → **403**; reverse on CANCELLED invoice → **403**.
7. **Isolation:** workspace B reverse on A's invoice/payment → **404** not 403.
8. **RBAC:** MEMBER POST payment OK; MEMBER `/reverse` → **403** `INSUFFICIENT_PERMISSIONS`.
9. **Defensive 400 not reachable:** skip (amount ≤ amount_paid invariant guaranteed by `_settle_invoice`).
10. Regression: full suite green; `alembic check` clean; guard pins stay on `234d5639ef8c`.

---

## 3. NOT in this wave

CLEARED-PDC reversal (terminal, mirror AR — reopen AP with an SDN); AR-side payment reversal; refunds / negative payments; statement `PAYMENT_REVERSED` doc-type; maker-checker/payment approvals; daily presentment; `pdc_outstanding`; frontend; new enums/columns.

---

## 4. Drift vs Wave 24 addendum / STATE

| Source | This wave |
|---|---|
| Wave 24 §13 / STATE "reversal of SUCCESS payment deferred to the SDN route" | **Now implemented** as an explicit `/reverse` (status→FAILED + `_reverse_settlement`). The SDN route remains the fix for a *CLEARED PDC* and for supplier-credit adjustments (unchanged). |
| AR "CLEARED is terminal, reopen with credit note" | Mirrored: CLEARED PDC terminal; SUCCESS non-PDC has a proper reversal. |

---

## 5. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` one section (Wave 25).
2. **No Alembic.** HEAD stays `234d5639ef8c`; `alembic check` clean; guard pins unchanged.
3. Schema: `SupplierPaymentReversalRequest` (empty, `extra="forbid"`) in `supplier_payments.py`.
4. Service: `SupplierPaymentReversalService.reverse_payment` in `supplier_payment_reversal_service.py` (FOR UPDATE pair; SUCCESS-only; non-PDC; open-invoice guard; FAILED + `_reverse_settlement`; idempotent 200 on FAILED). Keep `_settle_invoice` untouched.
5. Router: `POST /supplier-invoices/{invoice_id}/payments/{payment_id}/reverse` (OWNER/ADMIN, 10/min, empty-forbid body).
6. Tests §2 green; full suite green; ruff + black clean; commit the wave.
7. Next: ask before Phase 5 (comms).
