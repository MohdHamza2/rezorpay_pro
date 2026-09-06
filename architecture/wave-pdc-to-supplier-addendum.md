# PDC-to-supplier (AP post-dated cheque issued) + cheque bounce/reversal split — Architecture Addendum (Phase 4 leftover)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `SupplierPayment` / `SupplierPaymentService.record_payment` / `supplier_payments.py` router/schema / `SUPPLIER_PAYMENT_PENDING` statement line / the AR PDC machine (`pdc_service.py`, `wave-pdc-addendum.md`). Do **not** invent a second AP ledger, negative payments, refunds, or un-SUCCESS a cleared payment.
**Depends on:** Wave 22 AP payments (`a3f4c7d9e1b2`), Wave 23 purchase returns + supplier debit notes (`b4a2c6e8f10d`, HEAD), AR PDC lifecycle (`e217c0bc3af7` + `wave-pdc-addendum.md`).
**After this wave:** Phase 5 comms (ask before starting). Not this slice: recovering a SUCCESS CASH/BANK/CHEQUE after bounce; daily presentment / SAAS; `pdc_outstanding`; maker-checker; `CLEARED → BOUNCED` (late bank failure after clear).

Why deferred (Wave 22 addendum §2.4 / §10 "Out"): AP posted only CASH / BANK_TRANSFER / CHEQUE. Recording a post-dated cheque ISSUED to a supplier would have created un-billable PENDING rows. This wave generalizes the AR PDC machine — the same RECEIVED → DEPOSITED → CLEARED | BOUNCED, RECEIVED → RETURNED model, proven in `test_pdc.py`/`pdc_service.py` — to the payable side. **"Cheque bounce/reversal"** splits into two instruments: the **PDC** machine (this wave) and **reversal of an already-SUCCESS CHEQUE/CASH/BANK** (OUT, mirroring AR's "CLEARED is terminal, reopen with a credit note" — here a **supplier debit note**, Wave 23).

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `SupplierPaymentService.record_payment` | **Always inserts `PaymentStatus.SUCCESS`** and calls `_settle_invoice` (amount_paid += amount; `balance_due = max(0, balance_due − amount)`; PAID at 0). PDC is rejected up front by schema `AP_PAYMENT_METHODS` (CASH/BANK_TRANSFER/CHEQUE only). |
| `supplier_payments.status` / `payment_method` columns | PG enums `paymentstatus` + `paymentmethod` (`a3f4c7d9e1b2`, `create_type=False`). **PDC and PENDING already exist as DB enum values.** No `CREATE TYPE` needed. |
| `SupplierPayment` model | Has **no** `pdc_date` / `pdc_status` columns. New alembic revision required. |
| `SupplierInvoice.amount_paid` / `balance_due` | SUCCESS payments only (`_settle_invoice`). PENDING never nets. |
| AP statement | `payment_activity`: `status=PENDING` → doc `SUPPLIER_PAYMENT_PENDING`, credit 0, `pending_amount=amount`, `cleared_cash=False`; SUCCESS → `SUPPLIER_PAYMENT`, credit, in `totals.paid`; FAILED/CANCELLED omitted (`PAYMENT_STATUSES = (SUCCESS, PENDING)`). **Already PDC-ready. No math change.** |
| AP aging / `ap-balance` | `open_ap_invoices` uses `balance_due > 0`; aging buckets past-due on `balance_due`. PENDING PDC never nets. No change. |
| Roles | Payment create/list/get: any JWT member. No PDC-action RBAC today → add OWNER/ADMIN only on the four POSTs. |
| Isolation | Cross-workspace invoice/payment → **404** `NOT_FOUND`, never 403. |
| PUT | `/supplier-payments/{id}` already **405** `METHOD_NOT_ALLOWED` (with 404 isolation). No change. |
| Idempotency | `POST /supplier-payments` requires `Idempotency-Key` (48h, workspace-scoped). Four PDC POSTs take **no** key (AR `/pdc/*` pattern). |
| Overpay | `amount > balance_due` → **400** `PAYMENT_EXCEEDS_BALANCE` at insert and at clear. |
| Decimal | `money()` / Numeric(12,2) everywhere for `balance_due` math. Never float. |
| UTC date gate | Use `utc_today()` (from `credit_control_service`), **not** naive `date.today()`. |

---

## 1. ASCII — issue → deposit → clear | bounce | return

```
  POST /supplier-payments                Idempotency-Key required
  method=CASH|BANK_TRANSFER|CHEQUE
         → status=SUCCESS immediately (CHEQUE dated today/past = cleared-on-receipt MVP)
         → _settle_invoice reduces balance_due

  method=PDC  (pdc_date required)
         → status=PENDING, pdc_status=RECEIVED
         → does NOT reduce balance_due
         → invoice stays APPROVED / PARTIALLY_PAID (never PAID)
         → overpay cap still applies (amount <= balance_due)

           RECEIVED
              │
              │  POST .../payments/{id}/pdc/deposit   on/after pdc_date (UTC today)
              ▼
           DEPOSITED ─────────────────────┐
              │                           │
              │  POST .../pdc/clear       │  POST .../pdc/bounce
              ▼                           ▼
           CLEARED                     BOUNCED
           status=SUCCESS              status=FAILED
           FOR UPDATE invoice          amount/method/dates UNCHANGED
           _settle_invoice             no SUCCESS, balance unchanged
           may APPROVED→PARTIAL/PAID   no credit evaluate (AP has none)
                                      AR/AP unchanged (never was SUCCESS)

           RECEIVED ──POST .../pdc/return──► RETURNED
                                             status=CANCELLED
                                             no SUCCESS
```

---

## 2. `record_payment` — PDC rule (lock)

Compare `pdc_date` to **`utc_today()`** (`CreditControlService.utc_today`, same helper the statement/aging use). Do **not** use naive `date.today()`.

### 2.1 `payment_method=PDC`

| Rule | Lock |
|---|---|
| `pdc_date` | **Required.** Missing/null → **422** `VALIDATION_ERROR` `field=pdc_date` (schema validator, like AR). |
| Insert status | **Always `PENDING`**, including `pdc_date <= utc_today`. |
| Insert `pdc_status` | **Always `RECEIVED`.** Ignore any body `pdc_status` (AP schema never accepted it; do not add it to Create). |
| `balance_due` / `amount_paid` | **Unchanged.** PENDING is not in `amount_paid`. **Skip `_settle_invoice`.** |
| Invoice status | **Unchanged.** Must not flip to PAID. |
| Overpay at insert | `amount > balance_due` still **400** `PAYMENT_EXCEEDS_BALANCE`. PENDING does **not** consume the cap, so a second CASH (or another PDC) up to live `balance_due` is allowed. |
| `payment_date` | Receive/issue date (default UTC today, existing not-in-future validator). **Not** rewritten to `pdc_date`. |
| Idempotency | Same `Idempotency-Key` duplicate returns the **same** payment row (whatever its current status), still one row, `balance_due` untouched. |

**Why PENDING even when `pdc_date` is today/past (mirror AR §2.1):** the machine starts at RECEIVED; immediate SUCCESS on an issued cheque is the silent-paid-then-bounce bug; operators wanting one-step cash use **CHEQUE**.

### 2.2 Non-PDC methods (unchanged)

| Method | Status | `pdc_status` | Notes |
|---|---|---|---|
| CASH | SUCCESS | null | Immediate cash |
| BANK_TRANSFER | SUCCESS | null | |
| CHEQUE | SUCCESS | null | Dated today/past via `payment_date`. **Not** on the PDC machine. Bounce/clear/deposit/return → **403** `INVALID_STATE`. |

Do not invent CHEQUE-pending. Do not require `pdc_date` on CHEQUE.

---

## 3. Four POSTs (exact paths)

Base `/api/v1`. JWT. Wrapper. Empty body `{}` (`PdcActionRequest`, `extra="forbid"` — AR schema, reuse).

```
POST /supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/deposit
POST /supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/clear
POST /supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/bounce
POST /supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/return
```

**No** `Idempotency-Key`: `SELECT FOR UPDATE` payment **and** invoice; already-in-target-state → **200** same `SupplierPaymentResponse`; never double-post AP.

Rate-limit: **10/minute** (`@limiter.limit("10/minute")`, same as payment create). **OWNER / ADMIN only** (`UserRole.OWNER, UserRole.ADMIN`); **MEMBER** → **403** `INSUFFICIENT_PERMISSIONS` (inventory-adjust pattern). **Not** 404.

### 3.1 State machine

Only `payment_method=PDC` enters the machine. Any other method → **403** `INVALID_STATE`.

| From | To | Endpoint | Payment.status | Invoice AP |
|---|---|---|---|---|
| RECEIVED | DEPOSITED | `/pdc/deposit` | stays PENDING | none |
| DEPOSITED | CLEARED | `/pdc/clear` | **SUCCESS** | `_settle_invoice` (FOR UPDATE) |
| DEPOSITED | BOUNCED | `/pdc/bounce` | **FAILED** | none (never SUCCESS) |
| RECEIVED | RETURNED | `/pdc/return` | **CANCELLED** | none |

**Deposit date gate:** `pdc_date <= utc_today()`. Before that → **400** `VALIDATION_ERROR` `field=pdc_date`. Message: cannot deposit before cheque date.

**Illegal transitions** (RECEIVED→clear, RECEIVED→bounce, DEPOSITED→return, CLEARED→bounce, RETURNED→deposit, CHEQUE→any, SUCCESS/CLEARED→bounce/return): **403** `INVALID_STATE`, `error.field` may be `pdc_status` (same as AR / live CN-DN forbidden ops).

**Idempotent 200** when already in the **target** state: deposit `DEPOSITED`; clear `CLEARED` **or** (`status=SUCCESS` and method PDC); bounce `BOUNCED`; return `RETURNED`.

**CLEARED is terminal.** No `CLEARED → BOUNCED` (late bank failure after presentment). That would un-SUCCESS a payment. Reopen AP with a **supplier debit note** (Wave 23) if a cleared cheque later fails. Edge-cases C2 out — mirrors AR §3.1.

**Bounce = FAILED**, **return = CANCELLED.** Statement already omits both (FAILED/CANCELLED are not in `PAYMENT_STATUSES`). Row **stays** (never DELETE). Amount/method/`payment_date`/`pdc_date`/reference/bank **never** rewritten.

### 3.2 Clear — overpay lock

On `/pdc/clear`, after locking invoice + payment:

```
if payment.amount > invoice.balance_due:
    400 PAYMENT_EXCEEDS_BALANCE   # same code as POST payment
```

Then `SupplierPaymentService._settle_invoice(invoice, payment.amount)` under the lock (sets SUCCESS, `amount_paid += amount`, `balance_due = max(0, balance_due − amount)`, PAID at 0). **No** AR `update_status_from_payments` — AP owns `_settle_invoice` (already nets DN credits via `balance_due`; do not re-derive).

Typical case: PENDING PDC AED 100 + later CASH AED 100 on an AED 100 invoice → clear → **400**. Operator boosts/returns the cheque (if RECEIVED) or leaves it deposited/bounces. Multiple PENDING PDCs on one invoice allowed; first clear that fits succeeds.

### 3.3 Concurrency

`SELECT FOR UPDATE` the **supplier invoice** (id + workspace_id → 404 isolation) **and** the **payment** (id + invoice_id → 404). Recompute `balance_due` inside the lock before SUCCESS. Decimal / `money()` / Numeric(12,2). Never float.

---

## 4. Immutability

| Action | Lock |
|---|---|
| Amount / method / `payment_date` / `pdc_date` / reference / bank | **Never UPDATE** |
| DELETE payment | **No route.** |
| `status` / `pdc_status` | **Only** the four POSTs (+ insert rules in §2) |
| `PUT /supplier-payments/{id}` | Already **405** `METHOD_NOT_ALLOWED` (404 cross-workspace). Keep. |

CLAUDE.md "never update or delete payment records" means **money identity**. PDC lifecycle writes `status` / `pdc_status` / `updated_at` only.

---

## 5. Roles

| Action | Role |
|---|---|
| `POST /supplier-payments` (incl. PDC) | any member (unchanged) |
| Four `/pdc/*` POSTs | **OWNER / ADMIN** → 403 `INSUFFICIENT_PERMISSIONS` for MEMBER |

AP has **no** credit control / HOLD — bounce does **not** evaluate anything (unlike AR §5). Do not add `CreditControlService.evaluate` calls on the AP machine.

---

## 6. Existing rows & "cheque bounce/reversal" split

| Row | After this wave |
|---|---|
| New PDC insert | PENDING + RECEIVED |
| Old non-PDC SUCCESS rows | Unchanged (they were never on the machine) |
| `POST .../pdc/clear` on SUCCESS PDC (historic) | **200** no-op (guard §3.1), no amount rewrite |
| SUCCESS CASH/BANK/CHEQUE that later bounces | **OUT this wave.** No un-SUCCESS path. Mirror AR: reopen with a **supplier debit note** (§9 out-list). |

---

## 7. Statement / aging — do not fork math

`SupplierStatementService` already renders PENDING as **Payment (pending)** (`SUPPLIER_PAYMENT_PENDING`, credit 0, `pending_amount`, not in `totals.paid`), SUCCESS as **Payment** (in `totals.paid`), and omits FAILED/CANCELLED. **No code change.**

| After this wave | Statement |
|---|---|
| Uncleared PDC | **Payment (pending)**; not in `totals.paid`; aging uses live `balance_due` |
| PDC after `/pdc/clear` | **Payment** + method PDC, **in** `totals.paid` |
| BOUNCED / RETURNED | Omitted (FAILED / CANCELLED) |

AP aging (`open_ap_invoices`, buckets, `by_supplier`) and `GET .../ap-balance`: **no change** — PENDING never nets.

---

## 8. Isolation

Cross-workspace invoice id or payment id → **404** `NOT_FOUND`, **never 403**.

Load: `SupplierInvoice` where `id` + `workspace_id`; then `SupplierPayment` where `id` + `invoice_id`. Missing either → 404. Do not leak existence across workspaces.

---

## 9. Alembic — **YES** (unlike AR)

New revision, `down_revision = "b4a2c6e8f10d"`. Add to `supplier_payments`:

```
pdc_date   sa.Date (nullable)
pdc_status postgresql.ENUM('RECEIVED','DEPOSITED','CLEARED','BOUNCED','RETURNED',
                           name='pdcstatus', create_type=False), nullable
```

`schema.py` has PENDING/SDNs added by `b4a2c6e8f10d`; do **not** re-touch those. Both PG enum types (`paymentmethod`, `paymentstatus`, `pdcstatus`) already exist. Downgrade drops both columns.

**New HEAD replaces the two guard pins:** `test_pdc.py:751` and `test_pricing.py:497` assert `"b4a2c6e8f10d" in alembic-heads` and `alembic check` clean — re-point the revision string to the new head. `test_alembic_new_revision_parent_and_check` auto-adapts.

---

## 10. API summary

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/supplier-payments` | any member | Idempotency-Key. PDC→PENDING. |
| GET | `/supplier-payments` | any member | Unchanged (list now shows PENDING rows + pdc fields) |
| GET | `/supplier-payments/{id}` | any member | Unchanged |
| PUT | `/supplier-payments/{id}` | JWT | **405** (unchanged) |
| GET | `/supplier-invoices/{id}/ap-balance` | any member | Unchanged SUCCESS-only paid |
| GET | `/supplier-invoices/{id}/payments` | any member | Unchanged |
| GET | `/ap-aging*` | any member | Unchanged |
| GET | `/suppliers/{id}/statement` | any member | Unchanged math |
| POST | `/supplier-invoices/{id}/payments/{id}/pdc/deposit` | **OWNER / ADMIN** | §3 |
| POST | `/supplier-invoices/{id}/payments/{id}/pdc/clear` | **OWNER / ADMIN** | §3 |
| POST | `/supplier-invoices/{id}/payments/{id}/pdc/bounce` | **OWNER / ADMIN** | §3 |
| POST | `/supplier-invoices/{id}/payments/{id}/pdc/return` | **OWNER / ADMIN** | §3 |

Response model: `SupplierPaymentResponse` gains `pdc_date` + `pdc_status` (Optional). Create gains `pdc_date: Optional[date]`, validator `pdc_date_required_if_pdc`.

---

## 11. Module boundaries

| Layer | Owns |
|---|---|
| `routers/supplier_payments.py` | HTTP, 404/403, rate limit; four POSTs |
| `SupplierPaymentService.record_payment` | Insert SUCCESS vs PENDING+RECEIVED; overpay; skip settle for PDC |
| `SupplierPdcService` (new `supplier_pdc_service.py`) | Four transitions, `_settle_invoice` on clear (mirror `PdcService`) |
| `SupplierPaymentService._settle_invoice` | **Reuse** on clear — no second formula |
| `SupplierStatementService` / `ap_aging` | **No code change** |

`supplier_payment_service.py` is already ~407 lines; putting the machine there would exceed 500 → **new file**, mirroring `pdc_service.py` + `_require_owner_admin` (reuse helpers, do not import the AR service's private fns).

---

## 12. Tests — `backend/tests/test_supplier_pdc.py`

PostgreSQL only (never SQLite). Decimal. Isolation 404. Password 8+ (`securepassword123`). Seed rows directly (Wave 22 pattern — do not run the 3-way-match chain).

1. **Future PDC:** APPROVED invoice; POST PDC `pdc_date = utc_today + 7` → **200**; `status=PENDING`, `pdc_status=RECEIVED`, `pdc_date` echoed; invoice still **APPROVED**, `balance_due` unchanged; `ap-balance.amount_paid` and `totals.paid` exclude it.
2. **PDC `pdc_date` missing** → 422 `field=pdc_date`; still no payment row.
3. **PDC dated today** → still PENDING+RECEIVED (stricter-than-paper rule); deposit allowed.
4. **CASH / BANK_TRANSFER / CHEQUE** still SUCCESS immediately; invoice may go PAID/PARTIAL.
5. **Deposit before `pdc_date`** → 400 `field=pdc_date`; stays RECEIVED.
6. **Deposit on/after date** → DEPOSITED; still PENDING; balance unchanged; second deposit → **200** same row.
7. **Clear** after deposit: `status=SUCCESS`, `pdc_status=CLEARED`; `amount_paid` up, `balance_due` down; full amount → **PAID**; partial → PARTIALLY_PAID. Amount/method/dates unchanged.
8. **Bounce** after deposit: `status=FAILED`, `pdc_status=BOUNCED`; amount unchanged; invoice **not** PAID; `balance_due` unchanged; second bounce → **200**. Bounce from RECEIVED → **403** `INVALID_STATE`.
9. **Return** from RECEIVED → `CANCELLED` + RETURNED, not SUCCESS; return from DEPOSITED → **403**.
10. **Illegal:** RECEIVED→clear, CHEQUE→bounce, CLEARED→bounce, SUCCESS CASH→bounce → **403** `INVALID_STATE`.
11. **Over-clear:** PENDING PDC = full balance + CASH = full balance (both 200); `/pdc/clear` → **400** `PAYMENT_EXCEEDS_BALANCE`; PDC still PENDING/DEPOSITED; CASH SUCCESS; amount not rewritten.
12. **Statement:** uncleared PDC → **Payment (pending)** line, `pending_amount`, not in `totals.paid`, opening excludes; cleared PDC → Payment, in `totals.paid`; bounced/returned rows omitted.
13. **Isolation:** workspace B POST any `.../pdc/*` on A's invoice/payment → **404** not 403.
14. **MEMBER** token: POST payment (PDC) **200**; `/pdc/clear` **403** `INSUFFICIENT_PERMISSIONS` (OWNER seeded as `register_and_token`; MEMBER added via workspace invite — `test_ar_statement.py` pattern).
15. **Idempotency-Key** still required on POST; duplicate PDC key returns same row once; four PDC POSTs work **without** the header.
16. Do not break: purchase returns, SDN settle, ap_aging, statement DN tests, full suite green, `alembic check`, guard pins re-pointed.

---

## 13. NOT in this wave

Reversal of an already-SUCCESS payment after bank bounce (CHEQUE/CASH/BANK) — defer, use supplier debit notes; `CLEARED → BOUNCED`; daily/SAAS presentment; maker-checker / payment approvals; `pdc_outstanding` dashboards; multi-currency; AP event/history table; AR-side changes; frontend (no frontend this wave); new enum values.

---

## 14. Drift vs paper / old architecture docs

| Source | This wave |
|---|---|
| Wave 22 "Out": PDC-to-supplier + cheque bounce/reversal | **PDC machine in**; SUCCESS-payment reversal **out** (SDN route) |
| Paper: PDC pending only if future-dated | **All PDC PENDING until CLEARED**; CHEQUE remains immediate SUCCESS (mirror AR §2/§14) |
| V3 state machines `PDC_PENDING` / `PRESENTED` | Live enums **RECEIVED / DEPOSITED / CLEARED / BOUNCED / RETURNED** |
| Illegal transition 409 | **403** `INVALID_STATE` (live CN/DN / AR PDC) |
| Alembic likely no (AR did none) | **Yes** — AP genuinely lacks the two columns |

---

## 15. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` one section for this wave (Wave 24).
2. Migration `down_revision = "b4a2c6e8f10d"`; `alembic upgrade head` round-trip downgrade/upgrade; **re-point** `test_pdc.py:751` + `test_pricing.py:497` to the new head; `alembic check` clean.
3. `record_payment`: PDC → PENDING+RECEIVED, **skip `_settle_invoice`**; CHEQUE/CASH/BANK unchanged SUCCESS.
4. New `supplier_pdc_service.py` mirrors `pdc_service.py` (FOR UPDATE both rows; 404 isolation; 403 on illegal transitions; OWNER/ADMIN; no credit evaluate on AP; `_settle_invoice` on clear under overpay lock).
5. Reuse `utc_today()`. Decimal `money()`. Do not fork statement aging math.
6. Tests: `test_supplier_pdc.py` §12 green; full suite green; ruff + black clean via pre-commit.
7. Update `.planning/STATE.md` + `backend-execution-report.md`, then **commit** the wave.
8. Next: ask before Phase 5 (comms).
