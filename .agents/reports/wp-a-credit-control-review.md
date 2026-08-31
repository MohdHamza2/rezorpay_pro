# WP-A Credit HOLD / overdue — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0 tenant-leak or float-money).
**Spec:** `architecture/wave-credit-control-addendum.md`, `.agents/reports/architect-credit-control-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B (client credit UI + send/receive `CREDIT_HOLD` toast + Settings warning days / `block_po_on_hold`) may start.

No P0 tenant leak on `GET /clients/{id}/credit` or exposure SUM. No `Float` / `float()` on credit money; columns are `Numeric(12, 2)` and exposure goes through `money()`. Alembic is a linear new revision on LPO HEAD `59084165d346`. Pytest was **not re-run** in this review pass; `test_credit_control.py` has **15** functions covering spec §11.1–15. Combined **82 passed** is taken from `.agents/reports/backend-execution-report.md` (credit 15 + invoices 25 + quotations 20 + LPO 17 + isolation 5).

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 on `GET /clients/{id}/credit` | **PASS.** `_visible_client` → `CreditControlService.load_client` filters `id` + `workspace_id` + `deleted_at IS NULL`. Other workspace → 404, not 403. Tested in `test_payment_on_hold_and_credit_isolation_404`. JWT workspace from auth deps, never from body. |
| 2 | Decimal exposure; SUCCESS payments only | **PASS.** `open_ar_invoices` selectinloads payments; `Invoice.amount_paid` / `calculate_balance_due` count `PaymentStatus.SUCCESS` only. Exposure = `money(Σ balance_due)` for `SENT` + `PARTIALLY_PAID` + `OVERDUE`, `deleted_at IS NULL`. DRAFT/PAID/CANCELLED omitted. Fils path tested (`20.02` − `5.00` = `15.02`). PENDING PDC would not reduce (record path still inserts SUCCESS immediately — live rule). |
| 3 | NULL inherit; 0 COD; HOLD vs WARNING | **PASS.** `effective_limit` = client limit if not None else `workspace.credit_limit_default`. Omit create → null limit, terms 0, ACTIVE, effective = workspace default (0.00). Client `0` is COD even when workspace default is 5000. HOLD if `exposure > limit` (strict `>`, not `>=`) **or** `oldest_overdue_days > credit_hold_days`. Else WARNING if `> credit_warning_days`. WARNING does not block send. Auto both directions on evaluate (no admin override, no `SUSPENDED`). |
| 4 | SEND always blocked on HOLD; DRAFT create not blocked | **PASS.** `InvoiceService.mark_as_sent` calls `assert_not_hold` (400 `CREDIT_HOLD`, `field=client.credit_status`) **after** FTA. `create_invoice` has no credit assert. COD: first SEND 200; unpaid SENT → HOLD; second SEND 400 and invoice stays DRAFT. Limit 1000.00 then 1000.01 → HOLD on the next send. |
| 5 | LPO receive only if `block_po_on_hold` | **PASS.** `CustomerPurchaseOrderService.receive` asserts HOLD iff `workspace.block_po_on_hold`. LPO loaded with `workspace_id` + `FOR UPDATE`. Flag true → 400, stays DRAFT; flag false → 200 RECEIVED. `block_do_on_hold` unused (no DN). Quote convert / LPO `/invoices` DRAFT create not gated. |
| 6 | Quote convert not blocked; `due_date` uses `payment_terms_days` | **PASS.** `quotation_service.convert_to_invoice` / `convert_to_lpo` do **not** call `assert_not_hold`. HOLD client convert-to-invoice 201, convert-to-lpo 200/201. `due_date = issue + payment_terms_days` (0 → same UTC day; 30 → +30). LPO `/invoices` uses `due_date or due_date_from_terms(issue, terms)` so an explicit body date still wins. |
| 7 | OVERDUE never on PAID/CANCELLED; payments immutable | **PASS with nits W1/W8.** Flip predicate: not deleted, status in `{SENT, PARTIALLY_PAID}`, `due_date < UTC today`, `balance_due > 0`. List invoices bulk-flips then `?status=SENT` excludes the row. GET invoice flips one row. `determine_status_from_balance` short-circuits DRAFT/CANCELLED; `balance <= 0` → PAID **before** overdue; partial past-due stays OVERDUE. WP-A did not add payment DELETE. See W8 for pre-existing PDC PUT. |
| 8 | Alembic linear | **PASS.** `9f3a7c2e1d04` `down_revision = "59084165d346"` only. No other revision parented on LPO HEAD. Chain is single-file linear through quotes/FTA. Client columns + `credit_status_events` + optional index `ix_invoices_workspace_id_client_id_status`. No new Workspace columns. No invoice business columns. ENUMs `creditstatus` / `crediteventreason` via `create(checkfirst=True)`. Execution report: `alembic check` clean. |
| 9 | Extra 422 on client credit fields | **PASS.** `ClientCreate` / `ClientUpdate` `extra="forbid"`. `credit_status` is response/computed only — posting it 422s. `payment_terms_days` allow-list `{0,30,45,60}` (schema + DB check). `credit_limit` `ge=0` when not null + DB `credit_limit IS NULL OR >= 0`. Extra key 422 tested on create. |
| 10 | FTA send still runs (order vs `CREDIT_HOLD`) | **PASS (code); test gap W4.** `mark_as_sent`: `assert_fta_sendable` **then** `assert_not_hold` **then** snapshots + SENT. Existing FTA tests (`FTA_SEND_BLOCKED`, stays DRAFT) remain; they use a first send (exposure 0) so they would pass even if order were reversed. HOLD 400 is a different code/field. |

---

## Findings

### Critical (P0)

None. Cross-tenant `GET /clients/{id}/credit` is 404 with no aging payload. Exposure query always includes `Invoice.workspace_id` and `client_id`. Money fields are `Numeric(12, 2)` + `money()` — not Python `float` / SQL `Float`.

### Warning

**W1 — Credit evaluate does not persist SENT → OVERDUE**
Spec §7 lists **credit evaluate** (and invoice send) as on-read apply sites. `evaluate` / `GET /clients/{id}/credit` recompute HOLD/WARNING from `due_date` + `balance_due` even while status is still SENT (correct for blocking), but they never call `apply_overdue_*`. `mark_as_sent` always writes `SENT`, including when `due_date` is already yesterday. GET invoice and list invoices **do** flip. Matches WP-C “overdue on-read after send”. WP-B invoice list/detail will be correct after those GETs; a send response body can still show SENT for a past-due tax invoice until the next GET/list.

**W2 — No row lock on HOLD check**
`assert_not_hold` reads open AR then raises or continues. Two concurrent first SENDs on a COD client can both see exposure 0 (DRAFT ignored) and both become SENT. Invoice numbering already uses `SELECT FOR UPDATE`; credit does not lock the client or AR rows. Same class of race as any check-then-set without a lock. Not a tenant leak.

**W3 — `GET /clients` evaluates the whole workspace then paginates in memory**
Every list loads all matching clients, runs `evaluate` (one AR query each), filters `credit_status` in Python, then slices the page. Correct vs spec (“filter after evaluate”) but O(n) writes of `credit_status_events` when caches change. Fine for early tenants; will hurt a large client list.

**W4 — No test that FTA wins over HOLD on the same request**
Code order is FTA then HOLD. Missing: HOLD client + second DRAFT + missing workspace TRN → `FTA_SEND_BLOCKED` (not `CREDIT_HOLD`). Existing FTA tests are first-send (not HOLD). Do not treat green FTA tests as proof of order.

**W5 — Receive/payment load `Client` by primary key only**
`session.get(Client, lpo.client_id)` / `session.get(Client, invoice.client_id)` skip `workspace_id`. The LPO/invoice row is already workspace-scoped, so this is not an API IDOR. If a corrupt FK pointed at another tenant’s client, evaluate would update **that** client’s cache. Defense in depth: reuse `load_client(id, workspace_id)`.

**W6 — Isolation 404 wrapper code is `HTTP_ERROR`**
`_visible_client` raises `HTTPException(404, "Client not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no credit JSON leaked. Same pattern as other client 404s.

**W7 — `GET /clients?credit_status=` untested**
Query param exists and filters after live evaluate. No pytest. WP-B badge filters should not assume the query until exercised.

**W8 — Pre-existing payment PUT (PDC status)**
`PUT /invoices/{id}/payments/{id}` can change `Payment.status` / `pdc_status`. WP-A did not add it and did not add DELETE. Spec §7 “no PUT/delete” is the product lock; PDC mutation is older. Exposure still ignores non-SUCCESS. Do not treat WP-A as having introduced mutability.

### Info

**I1 — Spec §11.16 not in pytest**
`alembic upgrade head` / `alembic check` claimed in database + backend execution reports, not automated in `test_credit_control.py`. Reviewer confirmed revision graph from files: single head `9f3a7c2e1d04` → `59084165d346`.

**I2 — LPO invoice `due_date` from terms untested**
Quote convert 0 and 30 days are tested. `CustomerPurchaseOrderService.create_invoices` uses the same helper; no LPO `/invoices` due_date assertion.

**I3 — Aging bucket at exactly 90 days**
`days_overdue <= 90` → `days_61_90`; 91+ → `days_90_plus`. Spec JSON does not pin the 90 boundary. 12-day case is tested (`days_1_30`).

**I4 — Client PUT extra / negative limit**
Create extra key + invalid terms tested. PUT `extra="forbid"` and `credit_limit ge=0` are in schema + DB check, not in pytest. Restoring inherit via JSON `credit_limit: null` untested (should work: `exclude_unset`).

**I5 — File length / double snapshot**
`test_credit_control.py` is ~604 lines (spec asked files &lt; 500). `credit_control_service.py` is 335. `aging()` and `evaluate()` each query open AR; GET credit calls both. `invoice_service.py` remains over 500 (pre-existing + a few credit lines).

**I6 — Combined pytest vs `create_all`**
Same module-scoped `drop_all` / `create_all` on shared `invoicesaas_test` as LPO/quotes. Combined 82 can ERROR if two suites overlap. Not a product defect.

**I7 — `WorkspaceUpdate` extra not forbid**
Out of checklist 9 (client write models). Warning/hold days `ge=0`; `credit_warning_days > credit_hold_days` → 422 `VALIDATION_ERROR` tested.

**I8 — Void does not evaluate credit**
Exposure drops on next GET client/credit (CANCELLED excluded from SUM). Cache can stay HOLD until that read. Spec auto-release is on-read, not on void.

---

## What WP-B may rely on

| API | Notes |
|---|---|
| Client create/update | `credit_limit` blank/omit = inherit; `0` = COD; terms 0/30/45/60; extra keys 422; do not POST `credit_status` |
| Client list/GET | `credit_status`, `effective_credit_limit`, `exposure` live; optional `?credit_status=` |
| `GET /clients/{id}/credit` | Aging buckets + oldest overdue; other workspace 404 |
| `POST /invoices/{id}/send` | 400 `CREDIT_HOLD` `field=client.credit_status` after FTA; WARNING still 200 |
| `POST .../customer-purchase-orders/{id}/receive` | Same toast when `block_po_on_hold`; allow when flag false |
| Settings | `credit_warning_days`, `block_po_on_hold` already on `GET/PUT /workspaces/me`; do not treat `block_do_on_hold` as working |
| Invoice form | Default due date = issue + client `payment_terms_days` (API still requires `due_date`) |

---

## Out of scope (correctly)

AR PDF, Celery/nightly job, admin HOLD override, `SUSPENDED`, `credit_unlimited`, `block_do_on_hold` enforcement, FTA snapshot rule changes, DN, WhatsApp, UI.
