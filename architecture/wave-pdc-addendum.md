# Payment / PDC truth + bounce — Architecture Addendum (Gap 11 / Phase 9)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Payment` / `PaymentService.record_payment` / `PUT /invoices/{id}/payments/{id}` / SUCCESS-only `Invoice.amount_paid` / `balance_due = max(0, total − SUCCESS paid − ISSUED credited)` / `CreditControlService.evaluate` / AR statement PENDING vs SUCCESS. Do **not** invent a second payment ledger, negative payments, refunds, or auto-apply `credit_balance`.
**Depends on:** AR Account Statement A–C (`eea1523d`), tax credit notes (`b5a755e`), credit HOLD (`e8e00f5`), FTA tax invoices, LPO, quotes, Product Master, delivery notes.
**After this WP A–C:** volume pricing (gap 8). Not this slice: bilingual PDF, debit notes, WhatsApp, Peppol, refunds as negative payments, auto-apply `credit_balance`, workspace-wide aging report.

Copy the CN/DN split: **WP-A API+Alembic(if needed)+pytest → WP-B UI → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

UAE electrical wholesale: customers pay with **post-dated cheques**. A future PDC is a promise, not cash. Recording it must **not** mark the tax invoice PAID. Bounce must leave AR open and re-run credit HOLD. CHEQUE dated today/past stays the MVP “cleared-on-receipt” shortcut.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `PaymentService.record_payment` | **Always inserts `PaymentStatus.SUCCESS`**, including `payment_method=PDC`. SUCCESS reduces `balance_due` immediately. Body `pdc_status` is stored as sent; frontend often sends `RECEIVED` while status is still SUCCESS. |
| `PUT /invoices/{invoice_id}/payments/{payment_id}` | Mutates `status` / `pdc_status`. Maps CLEARED→SUCCESS, BOUNCED/RETURNED→FAILED. **Violates CLAUDE.md payment immutability.** This WP **replaces** it. |
| `Invoice.amount_paid` / `balance_due` | SUCCESS payments only. `balance_due = max(0, total − amount_paid − amount_credited)`. PENDING does not consume AR. |
| AR statement GET | SUCCESS → **Payment** in `totals.paid`. PENDING → **Payment (pending)**, credit 0, not in paid. FAILED/CANCELLED/REFUNDED omitted. Do **not** fork this math. |
| Credit HOLD | Payments **never** blocked (`CREDIT_HOLD` is send/LPO-receive/DN). `evaluate` already runs after `record_payment` with `CreditEventReason.PAYMENT`. Bounce does **not** exist. |
| CN issue | Never blocked by HOLD. Payments never updated/deleted on issue. |
| Idempotency | `POST /invoices/{id}/payments` requires `Idempotency-Key` (48h, workspace-scoped). |
| Overpay | `amount > balance_due` → **400** `PAYMENT_EXCEEDS_BALANCE`. No negative payments. |
| Isolation | Cross-workspace invoice → **404** `NOT_FOUND`, never 403. |
| Roles | Payment POST/GET: any JWT (`get_current_user`). No PDC-action RBAC today. |
| Models | `PaymentMethod` includes PDC. `PDCStatus`: RECEIVED / DEPOSITED / CLEARED / BOUNCED / RETURNED. `PaymentStatus`: PENDING / SUCCESS / FAILED / CANCELLED / REFUNDED. Columns `pdc_date`, `pdc_status` exist (`e217c0bc3af7`). |
| Alembic HEAD | **`b8d5f0c3a216`** (`b8d5f0c3a216_add_credit_notes.py`). AR statement added **no** revision. If this WP adds a revision, `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR history. |
| Historical rows | Tests/DB may already have PDC with `status=SUCCESS`. Do not rewrite amounts. |
| Statement tests | `test_success_pdc_in_paid` POSTs PDC and expects `totals.paid`. **Must change** after this WP. Playwright statement already records **CASH**. |

CLAUDE.md: Decimal `Numeric(12,2)`; payments immutable (**never update/delete amount**); overpay 400; wrapper `{success, data, error}`; isolation **404 not 403**; never SQLite. Gaps paper: amount/method/date immutable; **PDC status is a lifecycle**, not a financial rewrite of amount.

---

## 1. ASCII — receive → deposit → clear | bounce | return

```
  POST /invoices/{id}/payments     Idempotency-Key required
  method=CASH|BANK_TRANSFER|CREDIT_CARD|CHEQUE
         → status=SUCCESS immediately (CHEQUE = cleared-on-receipt MVP)
         → reduces balance_due

  method=PDC  (pdc_date required)
         → status=PENDING, pdc_status=RECEIVED
         → does NOT reduce balance_due
         → invoice stays SENT / PARTIALLY_PAID / OVERDUE
         → CREDIT_HOLD never blocks this POST

           RECEIVED
              │
              │  POST .../pdc/deposit     on/after pdc_date (UTC today)
              ▼
           DEPOSITED ─────────────────────┐
              │                           │
              │  POST .../pdc/clear       │  POST .../pdc/bounce
              ▼                           ▼
           CLEARED                     BOUNCED
           status=SUCCESS              status=FAILED
           FOR UPDATE invoice          amount/method/dates UNCHANGED
           balance_due shrinks         no SUCCESS
           may SENT→PARTIAL/PAID       credit evaluate (may HOLD)
                                       AR unchanged (never was SUCCESS)

           RECEIVED ──POST .../pdc/return──► RETURNED
                                            status=CANCELLED
                                            no SUCCESS

  PUT /invoices/{id}/payments/{id}  →  405 METHOD_NOT_ALLOWED
  DELETE payment                    →  no route (405 if hit)
```

---

## 2. `record_payment` — PDC rule (lock)

Compare `pdc_date` to **`utc_today()`** (`CreditControlService.utc_today` / same helper as statements). Do **not** use naive `date.today()` for this gate.

### 2.1 `payment_method=PDC`

| Rule | Lock |
|---|---|
| `pdc_date` | **Required.** Missing/null → **422** `VALIDATION_ERROR` `field=pdc_date`. |
| Insert status | **Always `PENDING`**, including `pdc_date <= utc_today`. |
| Insert `pdc_status` | **Always `RECEIVED`.** Ignore body `pdc_status` (frontend today sends RECEIVED; do not trust it). |
| `balance_due` | **Unchanged.** PENDING is not in `amount_paid`. |
| Invoice status | `update_status_from_payments` still runs (no-op if no SUCCESS). Must **not** flip PAID. |
| HOLD | **Never** blocks. Keep existing `evaluate(..., PAYMENT)` after insert (exposure unchanged unless other on-read OVERDUE flips). |
| Overpay at insert | `amount > balance_due` still **400** `PAYMENT_EXCEEDS_BALANCE`. PENDING does **not** consume the cap, so a second **CASH** (or another PDC) up to live `balance_due` is allowed. |
| `payment_date` | Receive date (default UTC today). **Not** rewritten to `pdc_date`. `payment_date` still cannot be in the future (existing validator). |

**Why PENDING even when `pdc_date` is today or past (stricter than paper’s “future only”):**

1. **T9:** “PDC not SUCCESS until CLEARED.” Immediate SUCCESS on a same-day PDC is the silent-PAID-then-bounce bug.
2. The dedicated machine **starts at RECEIVED**. Inserting SUCCESS skips deposit/clear and makes bounce an un-SUCCESS rewrite.
3. Paper already gives **CHEQUE today/past → SUCCESS** as the cleared-on-receipt shortcut. Operators who want one-step cash use **CHEQUE**. **PDC** is the bounceable instrument.

Paper §2.6 “PDC (`pdc_date > today`) → PENDING” is the **minimum**. This WP applies PENDING to **all** PDC inserts. Compatible and stricter.

### 2.2 Non-PDC methods

| Method | Status | `pdc_status` | Notes |
|---|---|---|---|
| CASH | SUCCESS | null | Immediate cash |
| BANK_TRANSFER | SUCCESS | null | |
| CREDIT_CARD | SUCCESS | null | |
| CHEQUE | SUCCESS | null | Dated today/past via `payment_date` (cannot be future). Ignore `pdc_date` if sent. **Not** on the PDC machine. Bounce/clear → **403** `INVALID_STATE`. |

Do not invent CHEQUE-pending. Do not require `pdc_date` on CHEQUE.

---

## 3. Replace PUT — four POSTs (exact paths)

Base `/api/v1`. JWT. Wrapper. Empty body `{}` (`extra="forbid"` if the project uses a body model; otherwise no JSON required).

```
POST /invoices/{invoice_id}/payments/{payment_id}/pdc/deposit
POST /invoices/{invoice_id}/payments/{payment_id}/pdc/clear
POST /invoices/{invoice_id}/payments/{payment_id}/pdc/bounce
POST /invoices/{invoice_id}/payments/{payment_id}/pdc/return
```

**No** `Idempotency-Key` on these four (CN `/issue` pattern): `SELECT FOR UPDATE` payment **and** invoice; already-in-target-state → **200** same `PaymentResponse`; do not double-post AR.

Rate-limit: same **10/minute** as payment create (optional but recommended).

### 3.1 State machine

Only `payment_method=PDC`. Other methods → **403** `INVALID_STATE`.

| From | To | Endpoint | Payment.status | Invoice AR |
|---|---|---|---|---|
| RECEIVED | DEPOSITED | `/pdc/deposit` | stays PENDING | none |
| DEPOSITED | CLEARED | `/pdc/clear` | **SUCCESS** | `update_status_from_payments` (FOR UPDATE) |
| DEPOSITED | BOUNCED | `/pdc/bounce` | **FAILED** | none (never SUCCESS); **evaluate** |
| RECEIVED | RETURNED | `/pdc/return` | **CANCELLED** | none |

**Deposit date gate:** `pdc_date <= utc_today()`. Before that → **400** `VALIDATION_ERROR` `field=pdc_date`. Message: cannot deposit before cheque date.

**Illegal transitions** (examples: RECEIVED→clear, RECEIVED→bounce, DEPOSITED→return, CLEARED→bounce, RETURNED→deposit, CHEQUE→any): **403** `INVALID_STATE` (same HTTP as CN/DN/LPO forbidden ops; not 409). `error.field` may be `pdc_status`.

**Idempotent 200** when already in the **target** state:

| POST | Already |
|---|---|
| deposit | `pdc_status=DEPOSITED` (and not terminal bounce/return/cleared) |
| clear | `pdc_status=CLEARED` **or** (`status=SUCCESS` and method=PDC) — historical SUCCESS PDC, **no amount rewrite**, do not require backfilling `pdc_status` |
| bounce | `pdc_status=BOUNCED` |
| return | `pdc_status=RETURNED` |

**CLEARED is terminal this WP.** No `CLEARED → BOUNCED` (late bank return). That would un-SUCCESS a payment. Reopen AR with a **tax credit note** if a cleared cheque later bounces. Edge-cases.md C2 is **out**.

**Bounce = FAILED not PENDING:** PENDING would still render as **Payment (pending)** on the statement (misleading). FAILED is omitted by existing statement rules (do not fork). The row **stays** (never DELETE). Amount/method/`payment_date`/`pdc_date` **never** rewritten.

**Return = CANCELLED:** paper “cancelled before deposit”. Distinct from bank bounce.

### 3.2 Clear — overpay lock

On `/pdc/clear`, after locking invoice+payments:

```
if payment.amount > InvoiceService.calculate_balance_due(invoice):
    400 PAYMENT_EXCEEDS_BALANCE   # same code as POST payment
```

**Do not** park `clients.credit_balance`. That field is **unapplied tax-credit-note credit** (CN addendum). Auto-apply is **out**. Never insert a negative payment.

Typical case: PENDING PDC AED 100 + later CASH AED 100 on a AED 100 invoice (PENDING did not consume the cap). Clear then **400**. Operator **RETURNS** the cheque (if still RECEIVED) or leaves it uncleared / bounces if already deposited.

Multiple PENDING PDCs on one invoice are allowed. First clear that fits succeeds; a second that would overpay → 400.

### 3.3 Concurrency

`SELECT FOR UPDATE` the **invoice** (same as `record_payment`) and the **payment** row. Recalc `balance_due` inside the lock before SUCCESS. Decimal `money()` / Numeric(12,2). Never float.

---

## 4. Immutability

| Action | Lock |
|---|---|
| Amount / method / `payment_date` / `pdc_date` / reference / bank | **Never UPDATE** |
| DELETE payment | **No route.** Do not add. |
| `status` / `pdc_status` | **Only** the four POSTs (+ insert rules in §2) |
| `PUT /invoices/{invoice_id}/payments/{payment_id}` | Keep the path. Handler returns **405** `ErrorCode.METHOD_NOT_ALLOWED` (add the code in `common.py`). Wrapper `{success:false, error:{code, message}}`. Resolve invoice in JWT workspace first: missing → **404** (isolation). Then 405 even if the payment exists. **Not 410.** Paper T9 / `test_payment_immutability` intent / `api-contracts.md` 405. |
| `PaymentUpdate` schema | Unused; may remain or be deleted. Must not be applied. |

CLAUDE.md “never update or delete payment records” means **money identity**. PDC lifecycle writes `status`/`pdc_status`/`updated_at` only.

---

## 5. HOLD / credit

| Action | HOLD |
|---|---|
| `POST .../payments` (any method, incl. PDC) | **Allow** (collections) |
| Four PDC POSTs | **Allow** (collections / bank ops) |
| `POST /credit-notes/{id}/issue` | **Allow** (unchanged) |
| Invoice send / LPO receive / DN confirm | Unchanged blocks |

**Bounce must call** `CreditControlService.evaluate(..., CreditEventReason.PAYMENT)` after setting BOUNCED/FAILED. Reuse **PAYMENT** (no new `CreditEventReason` value). Result is ACTIVE / WARNING / **HOLD** from **existing** rules (exposure vs limit, overdue days). Do **not** force HOLD on every bounce.

Recording PDC does **not** reduce exposure (PENDING). Bounce of DEPOSITED does not restore a SUCCESS that never happened; invoice stays open → evaluate may HOLD. That is the Phase 9 exit (“bounce puts client WARNING/HOLD”) when the client is already over limit or overdue.

Paper Q5: HOLD outstanding = invoiced AR minus SUCCESS only. PENDING PDC does **not** increase available credit. **Keep that.** Do not add PENDING face value into exposure.

---

## 6. Existing SUCCESS PDC rows

**No data migration. No amount rewrite.**

| Row | After this WP |
|---|---|
| New PDC insert | PENDING + RECEIVED |
| Old PDC `status=SUCCESS` | Stays SUCCESS; still in `amount_paid` / statement `totals.paid` |
| `POST .../pdc/clear` on those | **200** no-op (§3.1) |
| `POST .../pdc/bounce` on SUCCESS/CLEARED | **403** `INVALID_STATE` (terminal). Fix AR with CN if needed. |

Tests that POST PDC and expect immediate SUCCESS / PAID / `totals.paid` **must** change (CASH/CHEQUE, or explicit deposit+clear).

---

## 7. AR statement — do not fork math

`ArStatementService` stays SUCCESS vs PENDING vs omit FAILED/CANCELLED.

| After this WP | Statement |
|---|---|
| New uncleared PDC | **Payment (pending)**; not in `totals.paid`; aging uses live `balance_due` (PDC not netted) |
| PDC after `/pdc/clear` | **Payment** + method PDC; **in** `totals.paid` (SUCCESS is cleared cash) |
| Historical SUCCESS PDC | Still **Payment** in paid (leave rows) |
| BOUNCED / RETURNED | Omitted (FAILED / CANCELLED) — same as today’s omit list |

**Do not** add `PAYMENT_BOUNCED` doc types this WP.

WP-B: replace statement footer `PDC_SUCCESS_NOTE` (live: *“PDC recorded as SUCCESS reduces outstanding until bounce/clear (later wave).”*) with:

> Uncleared PDC is Payment (pending) and is not cash. Cleared PDC is Payment.

GET `/clients/{id}/ar-statement` must keep working. Patch `test_success_pdc_in_paid`: use CASH, **or** PDC + deposit + clear, **or** keep a session-inserted SUCCESS PDC only to prove historical SUCCESS still lists as Payment.

Playwright statement already uses CASH — no change required for WP-C statement specs unless they start recording PDC.

---

## 8. Isolation

Cross-tenant invoice id or payment id → **404** `NOT_FOUND`, **never 403**.

Load: `Invoice` where `id` + `workspace_id`; then `Payment` where `id` + `invoice_id`. Missing either → 404. Do not leak that the payment exists in another workspace.

Same for PUT 405: other-workspace invoice → 404, not 405.

---

## 9. Alembic — **NO**

**Decision: no revision this WP.** HEAD stays **`b8d5f0c3a216`**. Later WPs `down_revision = "b8d5f0c3a216"` until HEAD moves.

Evidence:

1. `paymentmethod` + `pdcstatus` + `pdc_date` / `pdc_status` columns: `e217c0bc3af7`.
2. `paymentstatus` PENDING/SUCCESS/FAILED/CANCELLED/REFUNDED: `13b9c7b44074`.
3. No new tables. No new payment/invoice columns (`cleared_at` out).
4. Audit: insert already logs `PAYMENT_ADDED`. Invoice flip on clear already logs `STATUS_CHANGED` via `update_status_from_payments`. Bounce credit uses existing `CreditEventReason.PAYMENT`. Do **not** ALTER TYPE `invoiceeventtype` / `crediteventreason` this WP.

`alembic check` must stay clean (no new file).

---

## 10. API summary

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/invoices/{id}/payments` | any member | Idempotency-Key. PDC→PENDING. HOLD allowed. |
| GET | `/invoices/{id}/payments` | any member | Unchanged pagination |
| GET | `/invoices/{id}/balance` | any member | Unchanged SUCCESS-only paid |
| PUT | `/invoices/{id}/payments/{id}` | JWT | **405** `METHOD_NOT_ALLOWED` (404 if invoice not in workspace) |
| POST | `/invoices/{id}/payments/{id}/pdc/deposit` | **OWNER / ADMIN** | §3 |
| POST | `/invoices/{id}/payments/{id}/pdc/clear` | **OWNER / ADMIN** | §3 |
| POST | `/invoices/{id}/payments/{id}/pdc/bounce` | **OWNER / ADMIN** | §3 + evaluate |
| POST | `/invoices/{id}/payments/{id}/pdc/return` | **OWNER / ADMIN** | §3 |

**MEMBER** on the four PDC POSTs → **403** `INSUFFICIENT_PERMISSIONS` (inventory-adjust pattern). Not 404.

Register/login still creates OWNER; Playwright stays OWNER.

Response: existing `PaymentResponse` (already has `status`, `pdc_status`, `pdc_date`).

---

## 11. Module boundaries

| Layer | Owns |
|---|---|
| `routers/payments.py` | HTTP, 404/405/403, Idempotency header on create only |
| `PaymentService.record_payment` | Insert SUCCESS vs PENDING+RECEIVED; overpay; lock invoice |
| `PdcService` (new) **or** methods on `PaymentService` | Four transitions; split if `payment_service.py` would exceed ~500 lines |
| `InvoiceService.update_status_from_payments` / `calculate_balance_due` | **Reuse** — no second formula |
| `CreditControlService.evaluate` | Bounce + existing payment path |
| `ArStatementService` | **No math change** except tests/fixtures |

Do not put PDC transitions in `CreditNoteService`. Files < 500 lines.

Schemas: extend `backend/app/schemas/payments.py`; add `ErrorCode.METHOD_NOT_ALLOWED`. Tests: `backend/tests/test_pdc.py` + patch AR/payment tests that assume SUCCESS PDC.

---

## 12. Tests — `backend/tests/test_pdc.py`

PostgreSQL only (never SQLite). Decimal fils. Isolation 404. Password **8+**.

1. **Future PDC:** SENT invoice; POST PDC `pdc_date = utc_today + 7`; **200**; `status=PENDING`, `pdc_status=RECEIVED`; invoice **SENT**; `balance_due` unchanged; statement `totals.paid` excludes it (or GET balance).
2. **PDC `pdc_date` missing** → 422 `field=pdc_date`.
3. **PDC dated today or past:** still PENDING+RECEIVED, not SUCCESS. Deposit allowed (date gate passes).
4. **CASH / BANK / CARD / CHEQUE** still SUCCESS immediately; invoice may go PAID/PARTIAL.
5. **HOLD client:** POST PDC **200** (not `CREDIT_HOLD`).
6. **Deposit before `pdc_date`** → 400 `field=pdc_date`; stays RECEIVED.
7. **Deposit on/after date** → DEPOSITED; still PENDING; balance unchanged. Second deposit → **200** same row.
8. **Clear** after deposit: `status=SUCCESS`, `pdc_status=CLEARED`; `balance_due` drops; full amount → **PAID** (or PARTIAL). `update_status_from_payments` path.
9. **Bounce** after deposit: `status=FAILED`, `pdc_status=BOUNCED`; amount unchanged; invoice **not** PAID; `balance_due` unchanged; `GET /clients/{id}/credit` evaluate ran (COD unpaid → HOLD or still HOLD). Second bounce → **200**.
10. **Return** from RECEIVED: `CANCELLED` + RETURNED; not SUCCESS. Return from DEPOSITED → **403**.
11. **Illegal:** RECEIVED→clear, CHEQUE→bounce, CLEARED→bounce → **403** `INVALID_STATE`.
12. **Over-clear:** PENDING PDC = full balance, then CASH = full balance (both 200); `/pdc/clear` → **400** `PAYMENT_EXCEEDS_BALANCE`; PDC still PENDING/DEPOSITED; CASH SUCCESS; `credit_balance` unchanged; payment amount not rewritten.
13. **PUT** payment → **405** `METHOD_NOT_ALLOWED`. Other-workspace PUT → **404**.
14. **Isolation:** workspace B `POST .../pdc/deposit|clear|bounce|return` on A’s ids → **404** not 403.
15. **MEMBER** token: POST payment (PDC) **200**; `/pdc/clear` **403** `INSUFFICIENT_PERMISSIONS` (reuse `_member_token` pattern from `test_ar_statement.py`).
16. **Idempotency-Key** still required on POST payments; duplicate key returns same payment. Four PDC POSTs work **without** that header.
17. Do not break FTA send, CN issue on HOLD, overpay CASH, `alembic check` (no new revision). Patch `test_success_pdc_in_paid`.

---

## 13. WP split

### WP-A — API + pytest (**no Alembic**, no frontend)

`record_payment` PDC PENDING; four POSTs; PUT 405; ErrorCode; `test_pdc.py` + AR test patch.

**Acceptance:** §12 green; future PDC does not PAID; bounce FAILED + evaluate; over-clear 400; PUT 405; isolation 404; Decimal; no Alembic file; HEAD `b8d5f0c3a216`.

### WP-B — UI (after A green)

Invoice record-payment modal + AR/payment list:

- PDC requires cheque date; after submit show **pending**, not cash. Do **not** label uncleared PDC as paid.
- List payments: method, amount, `status`, `pdc_status`.
- OWNER/ADMIN: Deposit / Clear / Bounce / Return per legal transition (hide illegal). MEMBER: no action buttons; API still 403 if called.
- Invoice `amount_paid` / status must stay SUCCESS-only (existing GET).
- Statement footer note §7. `npm run build`.
- Login `User` type may omit `role` today (`frontend/src/types/auth.ts`); add `role` from `/auth/me` or login payload to hide actions. API is source of truth.

**Out:** new Statements nav, dashboard `pdc_outstanding`.

### WP-C — Playwright

Local API **8000**, Postgres host **5434**. Never SQLite. Password **8+** (`Passw0rd1`). Unique emails.

Happy (`frontend/e2e/pdc.spec.ts`):

1. Register → FTA Settings → client → SENT tax invoice.
2. Record **future** PDC (UI) → status **SENT**, balance unchanged, not PAID.
3. Separate invoice (or same with `pdc_date=today`): deposit + clear → PARTIAL or PAID; amount_paid increases.
4. Bounce path: SENT + PDC (today) → deposit → bounce → invoice not PAID; AR remains; credit evaluate (COD client with unpaid SENT may be HOLD — assert `GET /clients/{id}/credit` or badge, not a forced copy-paste of HOLD UI if still ACTIVE under limit).

Isolation (`pdc-isolation.spec.ts`): workspace B POST any `/pdc/*` on A’s invoice/payment → **404**. PUT payment → **404** (other ws) / **405** (same ws).

**Acceptance:** Docker API + Postgres. No volume pricing, bilingual, debit notes, WhatsApp, Peppol, refunds.

---

## 14. Drift vs paper / old architecture docs

| Source | This WP |
|---|---|
| Paper: PDC PENDING only if `pdc_date > today` | **All PDC PENDING until CLEARED**; CHEQUE remains immediate SUCCESS |
| Paper: bounce “payment stays”; PUT mapped BOUNCED→FAILED | Bounce **FAILED**; return **CANCELLED** |
| Paper / edge-cases C2: bounce after CLEARED restores AR | **Out** (CN to reopen) |
| V3 state-machines: `PDC_PENDING` / `PRESENTED` | Live enums **RECEIVED / DEPOSITED / CLEARED / BOUNCED / RETURNED** |
| Nightly PDC clearing job | **Out** — explicit POST clear |
| Dashboard `pdc_outstanding` | **Out** (AR addendum) |
| Illegal transition 409 | **403** `INVALID_STATE` (live CN/DN) |
| Alembic likely no | **Confirmed no** |

---

## 15. NOT in this WP

Volume pricing; bilingual/Arabic; debit notes; Peppol; WhatsApp; refunds / negative payments; PUT amount; deleting payments; auto-apply `credit_balance`; parking over-clear into `credit_balance`; `CLEARED→BOUNCED`; rewriting historical SUCCESS PDC to PENDING; workspace-wide aging; dashboard PDC pack; CHEQUE pending machine; Celery/nightly presentment; new payment columns.

---

## 16. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` (WP-A), then `frontend-execution-report.md` (WP-B). No database report — **no Alembic**.
2. Alembic **NO**. HEAD **`b8d5f0c3a216`**.
3. PDC insert = PENDING+RECEIVED; CHEQUE/CASH = SUCCESS.
4. PUT → **405**. Four POSTs only for `pdc_status`.
5. Bounce → FAILED + `evaluate`. Over-clear → **400**, not `credit_balance`.
6. Do not fork statement math. Fix tests that expect SUCCESS-on-PDC-insert.
7. WP-A pytest green before WP-B.
8. Next after A–C: **volume pricing (gap 8)** — not debit notes.
