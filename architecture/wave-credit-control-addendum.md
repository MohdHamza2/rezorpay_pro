# Credit HOLD / Overdue — Architecture Addendum (Gap 6)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `Workspace` credit flags, `InvoiceStatus.OVERDUE` (enum already exists, **never set**), `InvoiceService.send_invoice` / `update_status_from_payments`, `CustomerPurchaseOrderService.receive`, existing `/clients` and `/workspaces/me`. Do **not** invent a second AR ledger, credit insurance, WPS, or a new invoice table.
**Depends on:** Customer LPO A–C (`8cf2480`), quotes, FTA tax invoices, Product Master.
**After this WP A–C:** delivery notes (gap 7). Not this slice: AR statement PDF (gap 12), PDC bounce engine (gap 11), tax credit notes, FTA field changes, WhatsApp, OCR, Peppol.

Copy the quotes/LPO split: **WP-A API+Alembic+tests → WP-B UI → WP-C Playwright**. Do not start WP-B until WP-A pytest is green.

UAE electrical wholesale: new buyers **COD (0 days)**; SME Net 30; mid Net 45–60. HOLD stops **new credit exposure** (tax-invoice SEND, LPO receive). Collections (payments) always allowed.

---

## 0. Runtime truth

| Source | Truth |
|---|---|
| `Workspace` | `credit_limit_default` 0.00, `credit_warning_days` 30, `credit_hold_days` 90, `block_po_on_hold` True, `block_do_on_hold` True. **Inert** — no service reads them for AR. |
| Settings UI | Edits `credit_limit_default` and `credit_hold_days` only. Warning days / `block_po_on_hold` not on the form. |
| `Client` | No credit columns. |
| `InvoiceStatus.OVERDUE` | On the enum. **No writer.** List/GET never flip SENT→OVERDUE. |
| `InvoiceService.determine_status_from_balance` | PAID / PARTIALLY_PAID / keep current. Partial pay of an overdue invoice would become PARTIALLY_PAID and stay there. |
| Quote/LPO convert | Hardcodes `due_date = today + 30`. |
| LPO | `/receive` DRAFT→RECEIVED. No `/confirm`. No credit check. |
| Invoice send | FTA gates then DRAFT→SENT. No credit check. |
| Payments | Immutable inserts; only `SUCCESS` reduces `balance_due`. PDC `SUCCESS` immediately (gap 11 later). |
| Alembic HEAD | `59084165d346` (`59084165d346_add_customer_lpos.py`). New revision **must** `down_revision = "59084165d346"`. Never rewrite LPO/quotes/FTA history. |

---

## 1. ASCII — evaluate → block send / receive

```
  Client.credit_limit  NULL → inherit workspace.credit_limit_default
                       0    → COD (effective limit 0)
                       >0   → that cap AED
  Client.payment_terms_days ∈ {0, 30, 45, 60}   default 0

  exposure = Σ balance_due of invoices
             status ∈ {SENT, PARTIALLY_PAID, OVERDUE}
             deleted_at IS NULL
             balance_due = total_amount − Σ SUCCESS payments
             DRAFT / PAID / CANCELLED  do not count

  oldest_overdue_days = UTC today − min(due_date)
                        among those invoices with due_date < today AND balance_due > 0
                        (null if none)

                    outstanding > effective_limit
                              OR oldest_overdue_days > workspace.credit_hold_days
                                         │
                                         ▼
                                      HOLD ──400 CREDIT_HOLD──► POST /invoices/{id}/send
                                           └── if block_po_on_hold ──► POST /…/receive

                    else oldest_overdue_days > workspace.credit_warning_days
                                         │
                                         ▼
                                    WARNING  (badge only; does not block)

  SENT/PARTIALLY_PAID + due_date < today + balance_due > 0
         │  on-read (GET/list invoice, payment, credit evaluate)
         ▼
      OVERDUE     never PAID / CANCELLED / DRAFT
```

---

## 2. Client credit fields (Alembic **yes**)

Add to `clients` — do **not** copy `credit_warning_days` / `credit_hold_days` / `block_*` onto Client. Those stay on **Workspace**.

| Column | Type | Lock |
|---|---|---|
| `credit_limit` | Numeric(12,2) nullable | `NULL` = inherit `workspace.credit_limit_default`. `0` = COD. `> 0` = cap. Check `>= 0` when not null. |
| `payment_terms_days` | `int` NOT NULL default **0** | Allow-list **0, 30, 45, 60** only. Other → **422**. New buyer COD. |
| `credit_status` | ENUM `ACTIVE` \| `WARNING` \| `HOLD` NOT NULL default `ACTIVE` | Cache; recomputed on-read. **No `SUSPENDED` this WP.** |
| `credit_status_changed_at` | timestamptz nullable | Set when cache changes |
| `credit_status_changed_by` | UUID FK `users.id` nullable | Evaluator user; system/on-read may use the JWT user |

No `credit_unlimited`, `credit_terms_days` (use `payment_terms_days`), `payment_terms` string, `credit_balance` (credit notes = later).

### Effective limit

```
effective_limit = client.credit_limit if client.credit_limit is not None
                  else workspace.credit_limit_default
```

Both 0 → COD: first SEND allowed (`exposure` 0 `>` 0 is false). After that SENT invoice exists with `balance_due > 0`, evaluate → **HOLD** → later SENDs blocked until paid.

### `due_date` from terms

`InvoiceCreate.due_date` stays **required** (no API break). Quote convert, LPO `/invoices`, and WP-B invoice form **must** pass `issue_date + payment_terms_days` (replace hardcoded +30). Explicit due_date on those bodies still wins if provided.

---

## 3. Workspace flags — reuse, do not duplicate

| Flag | Live default | This WP |
|---|---|---|
| `credit_limit_default` | 0.00 | Inherit when client limit is null |
| `credit_warning_days` | 30 | WARNING threshold (days past due) |
| `credit_hold_days` | 90 | HOLD threshold (days past due) |
| `block_po_on_hold` | True | Gates **LPO `/receive`** (there is no `/confirm`) |
| `block_do_on_hold` | True | **Unused** until DN (gap 7). Keep column. Do not enforce. |

**No** new `block_invoice_on_hold`. Invoice **SEND is always blocked on HOLD** (that is when AR is committed). DRAFT create is never blocked.

Workspace PUT: **422** if `credit_warning_days > credit_hold_days`. Both `ge 0`. Decimal money on `credit_limit_default` unchanged.

WP-B Settings: add `credit_warning_days` and `block_po_on_hold` to the form (API already returns them).

---

## 4. Exposure (outstanding)

**Formula (Decimal, `money()` / Numeric 12,2 — never float):**

```
exposure = Σ invoice.balance_due
where
  workspace_id = JWT workspace
  client_id = this client
  deleted_at IS NULL
  status IN (SENT, PARTIALLY_PAID, OVERDUE)
```

`balance_due = total_amount − Σ payments.amount WHERE status = SUCCESS`.

| Status | Counts toward exposure |
|---|---|
| DRAFT | **No** |
| SENT | Yes |
| PARTIALLY_PAID | Yes |
| OVERDUE | Yes |
| PAID | **No** (balance 0) |
| CANCELLED | **No** |

PDC: only SUCCESS reduces balance (live). PENDING PDC does **not** reduce exposure. Bounce engine **out** (gap 11).

Do not include quotations or LPO ordered-not-invoiced amounts (not tax invoices yet).

---

## 5. WARNING vs HOLD

Evaluate in this order (HOLD wins):

```
if exposure > effective_limit:
    HOLD
elif oldest_overdue_days is not None and oldest_overdue_days > workspace.credit_hold_days:
    HOLD
elif oldest_overdue_days is not None and oldest_overdue_days > workspace.credit_warning_days:
    WARNING
else:
    ACTIVE
```

`oldest_overdue_days = (UTC today − oldest due_date).days` among countable invoices with `due_date < today` and `balance_due > 0`. If none, skip aging branches.

**Auto both directions** (unlike paper HOLD→ACTIVE requiring manual release). Paying down exposure / clearing overdue on-read returns WARNING or ACTIVE. Audit via `credit_status_events`.

**WARNING never blocks.** HOLD blocks §6 only.

No ADMIN `POST /clients/{id}/credit-status` and no HOLD override this WP (paper T4 deferred).

---

## 6. What HOLD blocks — explicit

HTTP **400** `ErrorCode.CREDIT_HOLD` (add to `common.py`). `error.field = "client.credit_status"`. Message may include exposure and effective_limit. **Not 403** (403 stays `INVALID_STATE` / isolation stays **404**).

| Action | HOLD | WARNING | Rationale |
|---|---|---|---|
| `POST /invoices/{id}/send` | **Block** | Allow | Commits AR / tax invoice |
| `POST /customer-purchase-orders/{id}/receive` | **Block iff** `block_po_on_hold` | Allow | New demand; flag already on Workspace |
| `POST /invoices` (DRAFT) | Allow | Allow | No exposure until send |
| LPO `POST .../invoices` (DRAFT slice) | Allow | Allow | Same; send will block |
| Quote send / accept / reject | Allow | Allow | Not AR |
| Quote `convert-to-invoice` / `convert-to-lpo` | Allow | Allow | Lands DRAFT |
| Payments (any method) | **Allow** | Allow | Collections |
| Invoice void / DRAFT delete | Allow | Allow | Reduces or avoids exposure |
| LPO PUT/DELETE DRAFT | Allow | Allow | |
| DN dispatch | N/A | N/A | Gap 7 uses `block_do_on_hold` |

Send order: existing FTA checks first, then `CreditControlService.assert_not_hold(client)` **before** flipping SENT. If FTA fails, they never see HOLD on that request.

Re-evaluate credit (and persist status if changed) immediately **before** the HOLD assert, using exposure **before** this send (the DRAFT invoice is not in the SUM).

---

## 7. OVERDUE — on-read, not Celery

**Flip to OVERDUE** when all of:

1. `deleted_at` is null
2. `status ∈ {SENT, PARTIALLY_PAID, OVERDUE}`
3. `due_date < UTC today`
4. `balance_due > 0`

**Never** set OVERDUE on DRAFT, PAID, CANCELLED.

**On-read apply** (same pattern as quotation expiry): GET invoice, list invoices, record payment, credit evaluate, invoice send (other invoices of this client need not all be flipped in send — evaluate uses due_date/balance even if status still SENT; still bulk-flip SENT/PARTIALLY_PAID that match the predicate for list/GET correctness).

**No Redis/Celery job this WP.** Optional nightly later — out.

After payment, `update_status_from_payments` must:

```
if balance <= 0: PAID
elif overdue_predicate: OVERDUE          # even if partially paid
elif 0 < paid < total: PARTIALLY_PAID
else: SENT
```

Do not bounce OVERDUE → PARTIALLY_PAID while still past due.

Payments remain **immutable** (no PUT/delete). Overpay still 400. Recording a payment on OVERDUE is allowed.

---

## 8. Schema extras

### `credit_status_events`

Per-doc audit (do not stuff into `invoice_events`):

`id`, `client_id`, `workspace_id`, `previous_status`, `new_status`, `exposure`, `effective_limit`, `oldest_overdue_days` nullable, `reason` (`EVALUATE` / `PAYMENT` / `SEND_CHECK` / `RECEIVE_CHECK`), `changed_by` FK users, `timestamp`, `metadata_log` JSONB.

### Indexes

`(client_id, status)` on invoices already indexed via `client_id`. Add index `invoices (workspace_id, client_id, status)` if not present — optional; coder may add for exposure SUM.

No invoice new columns.

---

## 9. API

Existing `/api/v1/clients` — extend schemas (`extra="forbid"` on write). JWT workspace. Wrapper unchanged. Cross-tenant **404**.

**`ClientCreate` / `ClientUpdate`:** optional `credit_limit` (≥ 0 or null), `payment_terms_days` (allow-list). Do not accept `credit_status` from the client (computed). Extra keys 422.

**`ClientResponse` / list row:** + `credit_limit`, `payment_terms_days`, `credit_status`, `effective_credit_limit`, `exposure` (computed on-read; list may use cached status + live SUM).

**`GET /clients?credit_status=`** optional filter after evaluate/bulk cache.

**`GET /clients/{id}/credit`** — aging (JSON, not PDF):

```json
{
  "credit_status": "HOLD",
  "credit_limit": "0.00",
  "effective_credit_limit": "0.00",
  "payment_terms_days": 0,
  "exposure": "1500.00",
  "oldest_overdue_days": 12,
  "buckets": {
    "current": "0.00",
    "days_1_30": "1500.00",
    "days_31_60": "0.00",
    "days_61_90": "0.00",
    "days_90_plus": "0.00"
  }
}
```

Buckets = SUM `balance_due` of countable AR by age of `due_date` vs UTC today (`current` = not yet due). Decimal strings or JSON numbers from Decimal — match live invoice responses (they serialize Decimal as numbers/strings per existing encoder; **be consistent with invoices**).

No `POST /internal/jobs/nightly`. No override body on send/receive.

List invoices: after on-read overdue flip, `?status=SENT` does not include now-OVERDUE rows.

---

## 10. Module boundaries

| Layer | Owns |
|---|---|
| `services/credit_control_service.py` | exposure SUM, evaluate, persist status+event, `assert_not_hold` |
| `InvoiceService.mark_as_sent` | call assert after FTA; on-read overdue helper |
| `InvoiceService.update_status_from_payments` | OVERDUE vs PARTIALLY_PAID lock §7 |
| `CustomerPurchaseOrderService.receive` | if `block_po_on_hold`: evaluate + assert |
| `routers/clients.py` | fields + GET credit; HTTP only |
| Quote/LPO convert | due_date from `payment_terms_days` only — **no HOLD assert** |

Files < 500 lines. Do not modify SPO/GRN/FTA snapshot rules.

---

## 11. Tests — `backend/tests/test_credit_control.py` (+ patch send/receive)

PostgreSQL only.

1. Create client omit credit → `payment_terms_days=0`, `credit_limit` null, `credit_status=ACTIVE`, `effective_credit_limit` = workspace default.
2. `payment_terms_days=15` or 90 → 422. Extra key 422.
3. Exposure: DRAFT ignored; SENT counts; SUCCESS payment reduces; CANCELLED ignored. Decimal fils.
4. COD (limit 0, default 0): first SEND OK; unpaid SENT → HOLD; second SEND → **400 CREDIT_HOLD**; invoice stays DRAFT.
5. `credit_limit` 1000, exposure 1000 → not HOLD (`>` not `>=`). Exposure 1000.01 → HOLD.
6. Null client limit + workspace default 5000: inherit. Set client 0 → COD even if workspace default > 0.
7. SENT `due_date` yesterday, balance > 0: GET → **OVERDUE**. List `status=SENT` excludes it. PAID/CANCELLED never OVERDUE.
8. Partial payment on OVERDUE: still OVERDUE if past due and balance > 0. Full payment → **PAID**, not OVERDUE.
9. Aging: `oldest_overdue_days > credit_hold_days` → HOLD even if under limit.
10. WARNING (overdue > warning, ≤ hold, under limit): SEND **allowed**; status WARNING.
11. LPO receive on HOLD + `block_po_on_hold=true` → 400 CREDIT_HOLD, stays DRAFT. Flag false → receive 200.
12. Quote convert-to-invoice / convert-to-lpo on HOLD → **201/200**, not blocked.
13. Payment on HOLD client succeeds. Isolation: workspace B GET `/clients/{A}/credit` → 404.
14. `credit_warning_days > credit_hold_days` on workspace PUT → 422.
15. Convert invoice `due_date` = issue + client terms (0 → same day).
16. `alembic upgrade head` + `alembic check` clean.

Do not break FTA send tests, quotation convert-once, LPO over-invoice, payment overpay, immutable payments.

---

## 12. WP split

### WP-A — API + Alembic + tests

Client columns + `credit_status_events`, `CreditControlService`, send + receive hooks, overdue on-read + payment status lock, GET `/clients/{id}/credit`, convert due_date from terms, pytest §11. **No frontend.**

**Acceptance:** §11 green; `alembic check`; HOLD 400 on send; LPO receive respects `block_po_on_hold`; OVERDUE on-read; PAID/CANCELLED untouched; payments still immutable; Decimal; 404 isolation.

### WP-B — UI

- Clients: terms 0/30/45/60, credit limit (blank = inherit, 0 = COD), status badge, exposure.
- Invoice form: default due_date from client terms (not always +30).
- Send: toast `CREDIT_HOLD` (and existing FTA). Disable or explain on HOLD.
- LPO Receive: same toast when blocked.
- Settings: `credit_warning_days`, `block_po_on_hold` next to existing limit/hold days. Do not surface `block_do_on_hold` as working.

**Acceptance:** `npm run build`; HOLD client cannot send; WARNING can; Settings save warning days.

### WP-C — Playwright

Register → Settings limit/hold days → client COD 0 → invoice send (FTA TRN+address) → unpaid → second invoice send **blocked** with CREDIT_HOLD. Overdue: backdate due_date via API or create with yesterday due (if send allowed when due is past — **lock: send does not require due_date ≥ today**; overdue on-read after send if due < today). Other workspace client credit URL 404.

**Acceptance:** local API + Postgres. No DN, PDC bounce, AR PDF, WhatsApp.

---

## 13. Drift vs paper

| Paper | This WP |
|---|---|
| Nightly Celery/job OVERDUE+HOLD | **On-read** (+ send/receive evaluate) |
| HOLD → ACTIVE needs manual release | **Auto** when exposure/aging clear |
| `SUSPENDED` + POST credit-status | **Out** |
| HOLD blocks CPO `/confirm` | **LPO `/receive`** via `block_po_on_hold` |
| HOLD blocks invoice **create** | **SEND only** |
| `credit_unlimited` / null = unlimited | **No unlimited**; huge limit if needed |
| 0 limit = inherit | **NULL inherit; 0 = COD** |
| `credit_terms_days` name | **`payment_terms_days`** |
| ADMIN HOLD override | **Out** |
| `block_do_on_hold` | **Deferred to DN** |

---

## 14. NOT in this WP

AR statement PDF, aging PDF, PDC bounce→HOLD, tax credit notes / `credit_balance`, delivery notes, FTA send-rule changes, WhatsApp, OCR, Peppol, credit insurance, WPS, supplier credit, Redis/Celery, `/internal/jobs/nightly`, manual SUSPENDED.

---

## 15. Coder checklist

1. Report first: `.agents/reports/database-execution-report.md` then `backend-execution-report.md`.
2. Alembic **yes**, `down_revision = "59084165d346"` only.
3. Reuse Workspace flags; add Client columns only.
4. `CREDIT_HOLD` is 400. Isolation 404. FTA still 400 `FTA_SEND_BLOCKED`.
5. WP-A tests green before WP-B.
6. Next after A–C: **delivery notes (gap 7)**.
