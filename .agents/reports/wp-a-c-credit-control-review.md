# WP-A–C Credit HOLD / overdue — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full slice — Alembic `9f3a7c2e1d04`, API (`credit_control_service` + SEND / LPO receive / OVERDUE persist), WP-B UI, WP-C Playwright. Review only. No git commit. No features (no P0 found).
**Spec:** `architecture/wave-credit-control-addendum.md`, `.agents/reports/wp-a-credit-control-review.md`, `.claude/CLAUDE.md`
**Prior WP-A verdict:** `APPROVE_WITH_NITS` (W1 persist, W2 lock, W4 FTA-vs-HOLD test). Those three were shipped after that review; this pass re-checks them plus B/C.

Pytest / Playwright were **not re-run** in this review. Counts below are from execution reports plus file inspection (`17` functions in `test_credit_control.py`; WP-C log `11 passed`). Stale `frontend/test-results/*credit-hold*` / FTA screenshots in the working tree match the **pre-calendar-fix** failure, not the reported green run.

---

## Verdict

**APPROVE_WITH_NITS**

WP-A–C may be committed when asked. No tenant leak on `GET /clients/{id}/credit`. No `float` / SQL `Float` on AR exposure. COD first SEND then HOLD, OVERDUE persist on send/evaluate, FTA-then-HOLD order, linear Alembic, and Playwright HOLD banner + isolation 404 are in place.

Do **not** treat this as a clean `APPROVE_CREDIT_A_C`: leftover nits remain (FTA-fail-first still untested, Playwright overdue deferred, UI money via `Number`, carried W3/W5/W6/W8). None are P0.

**Next gap (do not implement here):** delivery notes / stock **ISSUE** (gap 7). Reuse `Workspace.block_do_on_hold` (column live, **unenforced**). Not this slice: AR PDF (gap 12), PDC bounce (gap 11), tax credit notes, FTA field changes, WhatsApp, OCR, Peppol.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 on credit GET | **PASS.** `CreditControlService.load_client` filters `id` + `workspace_id` + `deleted_at IS NULL`. `_visible_client` → HTTP 404 string (not 403). Pytest `test_payment_on_hold_and_credit_isolation_404`. Playwright `credit-isolation.spec.ts`: workspace A 200, workspace B 404 and not 403. JWT workspace from auth deps. Exposure SUM always includes `Invoice.workspace_id` and `client_id`. |
| 2 | Decimal exposure | **PASS (API).** Columns `Numeric(12, 2)`. `effective_limit` / `_exposure` / aging buckets go through `money()` (`ROUND_HALF_UP` fils). Open AR = `SENT` + `PARTIALLY_PAID` + `OVERDUE`, `deleted_at IS NULL`. `Invoice.amount_paid` counts `PaymentStatus.SUCCESS` only. DRAFT/PAID/CANCELLED omitted. Fils path `20.02 − 5.00 = 15.02` still tested. No `float()` in `credit_control_service.py`. **Nit:** Settings + client write still JSON-number via JS `Number` (see W9). |
| 3 | COD 0; HOLD blocks send; first SENT then second HOLD | **PASS.** `NULL` inherit; `0` = COD even if workspace default > 0. HOLD if `exposure > effective_limit` (strict `>`, not `>=`) **or** `oldest_overdue_days > credit_hold_days`. First COD SEND 200 `SENT` (exposure before send is 0). Unpaid SENT → HOLD. Second SEND 400 `CREDIT_HOLD`, `field=client.credit_status`, invoice stays **DRAFT**. DRAFT create never gated. Playwright repeats the same path in the browser. |
| 4 | Payments immutable; PAID/CANCELLED not OVERDUE | **PASS with nit W8.** Flip predicate: not deleted, `FLIP_STATUSES` `{SENT, PARTIALLY_PAID}` only, `due_date < UTC today`, `balance_due > 0`. `determine_status_from_balance`: DRAFT/CANCELLED short-circuit; `balance <= 0` → **PAID** before overdue; partial past-due stays **OVERDUE**. Evaluate persist test backdates a SENT row to yesterday and a PAID row — only SENT becomes OVERDUE. WP-A did not add payment DELETE. Pre-existing PDC `PUT` remains (W8). |
| 5 | FTA still first then CREDIT_HOLD | **PASS (code + FTA-valid HOLD test).** `mark_as_sent`: `assert_fta_sendable` **then** `assert_not_hold` **then** snapshots + SENT (+ overdue apply). HOLD 400 is not 403. Playwright: first send no `fta-send-blocked`; second send `credit-hold` and no FTA banner. Pytest `test_fta_valid_hold_send_is_credit_hold` (valid TRN/address, HOLD client, second send `CREDIT_HOLD` not `FTA_SEND_BLOCKED`). **Still missing:** HOLD + **missing** TRN on the same request → must be `FTA_SEND_BLOCKED` (W4). Existing FTA tests are first-send (exposure 0). |
| 6 | Playwright banner; second send stays DRAFT | **PASS (code + reported run).** `credit-hold.spec.ts`: COD 0, FTA Settings, first send SENT, clients badge HOLD, second send visible `credit-hold` /credit HOLD/i, `fta-send-blocked` count 0, draft row still DRAFT. Cheap extra: LPO receive on HOLD stays DRAFT with the same banner. Send button is **not** disabled (title-only); Playwright clicks through to the API 400 — that is the real gate. Reported: **11 passed** including isolation. OVERDUE backdate UI explicitly out of WP-C (pytest covers it). |
| 7 | due_date timezone IST vs UTC | **FLAG — UI bug, not a hidden API date bug.** See finding W10. Spec overdue is `due_date < UTC today`. WP-C fixed `addDaysToIso` to local Y-M-D after IST midnight + `toISOString()` produced **yesterday**, so frontend zod (`due_date < issue_date`) blocked invoice create. The API would have accepted a past `due_date` (send does **not** require due ≥ today) and then OVERDUE-on-send. That is correct per spec, not an API calendar defect that WP-C papered over. |
| 8 | Alembic linear | **PASS.** `9f3a7c2e1d04` `down_revision = "59084165d346"` only. No second child of LPO HEAD. Single file head through quotes/FTA/LPO. Client columns + `credit_status_events` + optional `ix_invoices_workspace_id_client_id_status`. No new Workspace columns. No invoice business columns. ENUMs `creditstatus` / `crediteventreason` `create(checkfirst=True)`. Execution report: `alembic check` clean. |

---

## What changed since WP-A review (nits shipped)

| Prior | Now |
|---|---|
| **W1** evaluate/send did not persist SENT→OVERDUE | **Fixed.** `evaluate` calls `apply_overdue_client` before snapshot. `mark_as_sent` sets SENT then `apply_overdue_invoice`. Past-due send response is OVERDUE (`test_overdue_on_read_excludes_from_sent_list`, `test_evaluate_persists_sent_to_overdue_skips_paid`). PAID/CANCELLED/DRAFT still not in `FLIP_STATUSES`. |
| **W2** no row lock on HOLD check | **Fixed enough.** Send loads invoice `SELECT FOR UPDATE`. `assert_not_hold` `lock_client` `FOR UPDATE` then evaluate. Concurrent first SENDs on one COD client serialize on the client row. |
| **W4** no FTA-vs-HOLD test | **Half-fixed.** FTA-valid HOLD → `CREDIT_HOLD` is tested. FTA-fail-first on a HOLD client is still untested (see W4 below). |

---

## Findings

### Critical (P0)

None. Cross-tenant credit GET is 404 with no aging payload. Exposure query is workspace-scoped. Money on the AR path is `Numeric(12, 2)` + `money()`.

### Warning

**W3 — `GET /clients` still evaluates the whole workspace then paginates in memory** *(carried)*
Correct vs spec (“filter after evaluate”) but O(n) `credit_status_events` writes when caches change. Skip for this WP; will hurt a large client list.

**W4 — FTA still wins on the same request is untested** *(carried, narrowed)*
Code order is FTA then HOLD. Missing pytest: HOLD client + second DRAFT + workspace TRN cleared → `FTA_SEND_BLOCKED` (not `CREDIT_HOLD`), stays DRAFT. `test_fta_valid_hold_send_is_credit_hold` only covers the FTA-ok HOLD path. Do not treat green first-send FTA tests as proof of order.

**W5 — Receive/payment still `session.get(Client, pk)`** *(carried, mitigated on receive)*
LPO receive / payment evaluate load Client by primary key. Invoice/LPO rows are workspace-scoped (not API IDOR). Receive then `lock_client(id, workspace_id)` — corrupt FK to another tenant’s client now 404s on the HOLD assert. Payment evaluate still has no workspace filter on the Client row. Defense in depth: reuse `load_client`.

**W6 — Isolation 404 wrapper code is `HTTP_ERROR`** *(carried)*
`_visible_client` raises `HTTPException(404, "Client not found")` (string). Handler maps that to `{code: HTTP_ERROR}` not `NOT_FOUND`. Status is still 404; no credit JSON leaked. Same pattern as other client 404s. Playwright only asserts status.

**W7 — `GET /clients?credit_status=` still untested** *(carried)*
Query exists; filters after live evaluate. WP-B has no badge filter UI. Low risk.

**W8 — Pre-existing payment PUT (PDC status)** *(carried)*
`PUT /invoices/{id}/payments/{id}` can change `Payment.status` / `pdc_status`. Spec “payments immutable” is the product lock; this WP did not add it and did not add DELETE. Exposure still ignores non-SUCCESS. Do not treat A–C as having introduced mutability. Bounce engine remains gap 11.

**W9 — UI credit limit is JS `Number`, not decimal strings**
Backend write models are `Decimal`. Settings `credit_limit_default` and `parseCreditLimitInput` send JSON numbers. Fine for `0` / whole AED; some fils values can pick up IEEE noise before Pydantic `Decimal`. Display `formatAed` uses `Number(value ?? 0).toFixed(2)` (null-safe, display only). AR SUM is not computed in the browser. Not P0.

**W10 — IST/`toISOString` calendar bug was frontend-only (checklist 7)**
`Invoices.tsx` previously did `new Date(y, m-1, d)` (local midnight) then `toISOString().slice(0, 10)`. In IST (UTC+5:30) that is the **previous UTC calendar day**. `issue_date` used `localIso` (civil today) so terms `0` produced `due_date < issue_date` and the **UI** blocked create. That hid Playwright FTA/COD create; it did **not** hide an API date bug.

API overdue is `due_date < datetime.now(timezone.utc).date()` as spec §1 / §7. `DATE` columns have no timezone. Send does not require `due_date ≥ today`. A yesterday due_date is a valid past-due tax invoice and becomes OVERDUE on send/evaluate.

Leftovers (not HOLD-path blockers):

- `frontend/e2e/helpers.ts` `isoDate()` still UTC-slices after local `setDate`. Credit-hold does not use it (fills due from the HTML date input). Isolation API specs that use `isoDate()` (FTA/LPO/quotes) can disagree with local “today” between midnight and 05:30 IST.
- `quotationHelpers.todayIso` / `plusDaysIso` still `toISOString()` — quote UI, not invoice due_date after the WP-C fix.
- UAE GST (UTC+4) 00:00–03:59 vs UTC “today” can shift OVERDUE by a few hours vs shop-floor calendar. That is the addendum lock, not a regression. Do not “fix” the API to IST without a spec change.

### Info

**I1 — Spec §11.16 not in pytest**
`alembic upgrade head` / `alembic check` claimed in database + backend reports. Graph from files: single head `9f3a7c2e1d04` → `59084165d346` → quotes/FTA. Reviewer did not run Alembic.

**I2 — Playwright OVERDUE / aging HOLD not covered**
WP-C plan explicitly deferred overdue backdate in the browser. Pytest covers GET/list flip, payment lock, aging HOLD, WARNING send-allowed. Matches “Fix UI bugs hit in the run; API bugs → log only.”

**I3 — LPO `/invoices` due_date from terms still untested**
Quote convert 0 and 30 days are tested. `CustomerPurchaseOrderService.create_invoices` uses `due_date or due_date_from_terms`. Explicit body date still wins.

**I4 — File length**
`test_credit_control.py` ~675 lines (spec asked files &lt; 500). `credit_control_service.py` ~374. `invoice_service.py` still over 500 (pre-existing + credit hooks). `Invoices.tsx` is a large page (banner + form + list).

**I5 — `aging()` double-reads AR**
GET `/clients/{id}/credit` evaluates (flip + persist) then `aging()` snapshots again. Correct; extra query.

**I6 — Void does not evaluate credit**
CANCELLED drops out of SUM on the next client/credit GET. Cache can stay HOLD until that read. Spec auto-release is on-read.

**I7 — `WorkspaceUpdate` extra not forbid**
`block_do_on_hold` remains writable on the API (unused). Settings UI does not send it and copy says DN is not enforced. `credit_warning_days > credit_hold_days` → 422, also blocked in Settings zod.

**I8 — Send button not disabled on HOLD**
Title explains; click still hits API. Spec allowed “disable **or** explain.” Playwright depends on the 400. Fine.

**I9 — Combined pytest vs `create_all`**
Same module-scoped `drop_all` / `create_all` on shared `invoicesaas_test`. Combined runs can ERROR if two suites overlap. Not a product defect.

**I10 — Stale Playwright artifacts**
`frontend/test-results/credit-hold-…` and FTA failure screenshots in git status are from the IST calendar miss, not the reported 11-pass run.

---

## WP-B / WP-C surface (acceptance)

| Surface | Notes |
|---|---|
| Clients | Terms 0/30/45/60; blank limit = inherit (omit on create); `0` = COD; badge + exposure / effective limit; edit panel aging buckets. Write payload is `ClientWritePayload` only — no `credit_status`. |
| Invoice form | Default due = issue + `payment_terms_days` via local Y-M-D. API still requires `due_date`. HOLD copy in the modal. |
| Send | Toast + `data-testid="credit-hold"` on `CREDIT_HOLD`; FTA keeps `fta-send-blocked`. `HANDLED_TOAST_CODES` avoids double toast. |
| LPO Receive | Same banner when API returns `CREDIT_HOLD`; title when HOLD and `block_po_on_hold`. |
| Settings | `credit_warning_days`, `credit_hold_days`, `credit_limit_default`, `block_po_on_hold`. Does not present `block_do_on_hold` as working. |
| Playwright | COD HOLD send + LPO receive + credit GET 404. Product/FTA/quote/LPO specs reported still green. |

---

## Next gap — delivery notes (stock ISSUE)

After commit (when asked), gap 7:

- New DN entity + dispatch path. **ISSUE** stock on dispatch (inventory out), not on invoice SEND.
- Gate dispatch with **`block_do_on_hold`** (column already on Workspace, default true, **do not enforce in this credit WP**).
- Do not invent a second AR ledger. HOLD already blocks tax-invoice SEND; DN is warehouse movement.
- Out: AR statement PDF, PDC bounce→HOLD, credit notes, FTA snapshot changes, WhatsApp.

No code in this review pass.

---

## Out of scope (correctly)

AR PDF, Celery/nightly job, admin HOLD override, `SUSPENDED`, `credit_unlimited`, `block_do_on_hold` enforcement, FTA snapshot rule changes, DN/ISSUE, WhatsApp, git commit.
