# WP-A–C AR Statement — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** Full slice — WP-A API+pytest, WP-B UI/PDF, WP-C Playwright. Review only. No git commit. No feature work (no P0 tenant leak, CN-as-cash, PENDING-as-paid, GET mutation, float money, or new Alembic/second AR table).
**Specs:** `architecture/wave-ar-statement-addendum.md` (full), `.agents/reports/wp-a-ar-statement-review.md` (WP-A APPROVE_WITH_NITS — re-check UI/E2E against those nits), `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

The slice **may be committed when asked**. No P0. Do not start PDC bounce/truth in this commit.

Generated `GET /api/v1/clients/{id}/ar-statement?from=&to=&as_of=` is read-only JSON. Alembic HEAD remains **`b8d5f0c3a216`**. No `ar_statements` table. No server PDF. UI `/clients/:id/statement` + client-side `StatementPDF` title **Account Statement**. Cross-workspace GET is **404 `NOT_FOUND`**, never 403. ISSUED CN → `totals.credited`, never `totals.paid`. PENDING is memo-only. SUCCESS PDC stays in `totals.paid` (label only). This pass re-ran pytest: **`tests/test_ar_statement.py` 13 passed** (17.59s, PostgreSQL `*_test`). `alembic heads` / `alembic current` → `b8d5f0c3a216 (head)`.

WP-A nits that mattered for UI: Unapplied credit is a **footer** row, not an aging bucket; outstanding-copy documents live amounts vs as-of days. Remaining WP-A nits are still test/schema gaps, not product locks.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 not 403 (API + Playwright) | **PASS.** `_require_client` → `CreditControlService.load_client` (`id` + `workspace_id` + `deleted_at`). Miss → `raise_error` 404 `NOT_FOUND`. Pytest `test_other_workspace_404_not_403` asserts 404, `!= 403`, `error.code == NOT_FOUND`. Playwright `ar-statement-isolation.spec.ts`: workspace B GET → 404 not 403; own GET 200. CREDIT_HOLD does not block (pytest MEMBER + HOLD GET 200). Auth is `get_current_user`. |
| 2 | Decimal; CN never in `totals.paid`; PENDING not paid; SUCCESS PDC still paid | **PASS.** Service math is `Decimal` + `line_money.money()` — no `float` in `ar_statement_service.py`. `period_totals.paid` is SUCCESS payments only; `credited` is ISSUED CN totals. PENDING: `doc_type_label` **Payment (pending)**, credit 0, `cleared_cash false`, in `totals.pending` not `paid`. SUCCESS PDC: method `PDC`, label **Payment**, in `paid`. UI: “Paid (SUCCESS payments)” vs “Credited (tax credit notes)”; pending credit column forced to 0. Playwright: paid AED 50.00 ≠ credited AED 105.00; CN line is Tax Credit Note, not Payment. |
| 3 | GET never mutates invoices/payments/CNs | **PASS.** `get_statement` only `select`s. Router does **not** `commit`. `get_session` closes without commit. No `evaluate` / SENT→OVERDUE on this GET (unlike GET `/credit`). `test_get_does_not_mutate_rows` compares counts + status / `amount_credited` / payment / CN / `credit_balance` / `updated_at`. |
| 4 | No Alembic / no `ar_statements` table / no server PDF | **PASS.** No new file under `backend/alembic/versions/`. No revision with `down_revision = b8d5f0c3a216`. HEAD **`b8d5f0c3a216`**. No SQLModel named Statement. No `ar-statement.pdf`, WeasyPrint, or reportlab. PDF is `@react-pdf/renderer` from GET JSON. |
| 5 | PDF title exact `Account Statement`; `data-testid` on page and preview | **PASS.** Page `h2[data-testid="statement-pdf-title"]`, preview `h3`, `Document title="Account Statement"`, PDF title text. Playwright asserts exact text and not Tax Invoice / Tax Credit Note; invoice `pdf-title` / CN `cn-pdf-title` absent. InvoicePDF / CreditNotePDF titles unchanged. |
| 6 | UI does not label CN as cash; Unapplied credit is footer not aging bucket | **PASS.** Line type uses API `doc_type_label`. Totals: paid vs credited vs pending CSS. Aging table is the five live keys only (`Current` / `1–30` / `31–60` / `61–90` / `90+`). `credit_balance` is “Unapplied credit” in the totals footer (and PDF/preview), not a sixth bucket. Addresses WP-A **N2** in UI. |
| 7 | Aging reuses CreditControlService; `as_of=today` matches GET `/credit` | **PASS.** Footer calls `open_ar_invoices` + `aging_buckets` (not a forked function). `amount_due_now` = Σ live `balance_due`. Pytest: bucket key vs `_bucket_key`; PAID excluded; `sum(buckets) == amount_due_now`; `as_of=today` buckets + exposure + `credit_balance` match GET `/credit`. GET `/credit` **unchanged** (still evaluate + commit). UI copy: “Outstanding amounts are current; aging days vs as-of.” (WP-A **N3**). |
| 8 | Playwright happy path three line types; credited ≠ paid; isolation 404 | **PASS (as specified).** `ar-statement.spec.ts`: register → FTA Settings → client → SENT tax invoice → UI CASH AED 50 (Idempotency-Key via `recordPayment`) → ISSUED CN qty 1 → Clients **Statement** → today range → Tax Invoice + Payment + Tax Credit Note; paid AED 50.00 ≠ credited AED 105.00; aging visible; preview title Account Statement. Isolation spec: 404 not 403. Suite claim 18/18 = 16 prior e2e tests + these 2 (delivery-notes has two tests). This review did not re-run Playwright (Docker UI). |
| 9 | Clients table Statement action; no empty top-level Statements nav | **PASS.** `Clients.tsx` row link `/clients/:id/statement` `data-testid="client-statement"`. `App.tsx` nested route only. `Layout.tsx` has Clients, not Statements. |
| 10 | Wrapper pattern; extra keys not POSTed | **PASS.** Statement GET: `SuccessResponse[ArStatementResponse]` with `response_model_by_alias=True` so `from_` serializes as `from`. Errors via existing HTTP handler `{success: false, error: {code, message, field?}}`. `getArStatement` query is `from` / `to` / optional `as_of` only. WP-C writes: `buildClientWritePayload`, `buildCreatePayload` (invoice extra=forbid), `createCreditNoteBody` (CN extra=forbid). CASH payment body is `amount` + `payment_method` only. |
| 11 | Payments still require Idempotency-Key | **PASS.** `payments.py` still 400 without the header. `recordPayment` always sends `crypto.randomUUID()`. WP-C records cash through that UI path. Pytest `_pay` also sends the header. No statement code calls `PUT .../payments/{id}`. |
| 12 | Do not “fix” PDC truth in this slice | **PASS.** `PaymentService.record_payment` still inserts `status=SUCCESS` including PDC. No deposit/clear/bounce routes. UI/PDF footnote: *“PDC recorded as SUCCESS reduces outstanding until bounce/clear (later wave).”* Pytest SUCCESS PDC in `totals.paid`. |

---

## Findings

### Critical (P0)

None.

- Other-workspace GET → 404 `NOT_FOUND`, no client payload (API). Playwright asserts 404 ≠ 403.
- CN totals are not added to `totals.paid`; UI/PDF label them tax credit notes, not Payment.
- PENDING is not cleared cash and is not in `totals.paid`.
- GET does not write invoices / payments / CNs / `credit_balance`.
- No `float` in statement service or schemas. Invoice/payment/CN columns remain `Numeric(12, 2)`.
- No new Alembic revision / second AR ledger / server PDF.

### Warning

None that block commit. Functional locks hold.

### Nits (do not block commit)

**N1 — Quote / LPO / DN omission still untested (WP-A N1)**
Include-set is `Invoice` only, so those docs cannot appear. Pytest still does not POST them. Optional follow-up.

**N2 — `credit_balance` not-in-buckets still weakly asserted in pytest (WP-A N2)**
Aging fixture parks 0. UI/PDF correctly keep Unapplied credit out of the five buckets. Wide-range test parks CN credit but does not assert bucket values against that parked amount.

**N3 — Past `as_of` still untested in pytest (WP-A N3)**
Code allows `as_of < utc_today()` (days vs that date; amounts stay live). UI shows `OUTSTANDING_COPY`. Only future `as_of` is 422 (API + zod).

**N4 — Spec §10.13 regressions not in `test_ar_statement.py` (WP-A N4)**
FTA send, overpay, CN issue, HOLD, `alembic check` are not re-run in this file. HOLD on this GET is tested. This review confirmed Alembic HEAD did not move. Invoice/CN/payment modules were not edited for this slice.

**N5 — `_load_payments` is invoice-id scoped, not `workspace_id` (WP-A N5)**
Payments have no `workspace_id`. Ids come from a workspace+client include-set (UUIDs). Defense in depth would join `Invoice.workspace_id`. Not a tenant leak.

**N6 — `doc_type_label` is still a free `str` on the schema (WP-A N6)**
Service uses `DOC_TYPE_LABELS`. Pytest and Playwright lock the visible strings. A `Literal` would fail closed on typos.

**N7 — Playwright aging is visibility-only**
WP-C spec “aging matches JSON” is true by construction (page renders GET JSON) and already locked in pytest vs GET `/credit`. E2E does not fetch `/credit` and compare bucket cells.

**N8 — Isolation E2E does not assert `error.code == NOT_FOUND`**
Status 404 ≠ 403 is the lock. API pytest already asserts `NOT_FOUND` and no 403.

**N9 — `@react-pdf/renderer` `data-testid` is a no-op**
`StatementPDF` spreads `data-testid` onto `Text` with a type cast. Playwright asserts the HTML page title and preview `h3`, which is what the DOM can see. `Document title="Account Statement"` is set.

**N10 — Client zod does not enforce the 366-day cap**
API returns 422 `DATE_RANGE_TOO_LONG`; interceptor toasts `DATE_RANGE_TOO_LONG: …`. Fine; UX could block earlier.

**N11 — Display formatting uses `Number().toFixed(2)`**
`statementHelpers.formatMoney` and existing `formatAed` are display-only. Ledger math stays `Decimal` + `money()` on the server. Not a second AR book.

**N12 — Duplicate `statement-pdf-title` when preview is open**
Page `h2` and preview `h3` share the test id. Playwright scopes `h2[…]` vs preview. Harmless.

---

## Info

**I1 — Pytest re-run here**
`backend/.venv` `pytest tests/test_ar_statement.py -q` → **13 passed**, 1 httpx `TestClient` deprecation warning (pre-existing). PostgreSQL `*_test` + `asyncpg`. Money tests use real rows; cap uses monkeypatch only.

**I2 — Alembic**
`alembic heads` and `alembic current` → **`b8d5f0c3a216 (head)`**. Later WPs must `down_revision = "b8d5f0c3a216"` until HEAD moves.

**I3 — Spec example `from=2000-01-01` vs 366-day cap**
Unchanged from WP-A I2. Shipped identity test uses a ≤366-day window that covers all surviving activity.

**I4 — GET `/credit` still mutates; statement GET does not**
`GET /clients/{id}/credit` still `evaluate` + `commit` (SENT → OVERDUE on-read). Statement GET skips that. Both still include SENT and OVERDUE in `AR_STATUSES`, so `as_of=today` buckets match.

**I5 — File length**
`ar_statement_service.py` 470 lines (under 500). `clients.py` stays under 500. `ArStatement.tsx` ~294. `StatementPDF.tsx` ~258. Tests ~665 (allowed).

**I6 — Invoice list `amount_credited`**
Present on `InvoiceListItem` / Invoices UI from the credit-notes wave, **not** added by this slice (`Invoices.tsx` is not in the AR working tree). Addendum WP-B “out” meant do not add it here.

**I7 — Playwright 18/18 not re-run on this pass**
Code matches the claimed specs (password `Passw0rd1`, API `8000`, unique emails, FTA 5% → CN AED 105). Isolation uses `authJson` GET with JWT. Happy path records payment through UI (`Idempotency-Key`).

**I8 — `PaymentCreate` is not `extra="forbid"`**
Pre-existing. WP-C CASH body is only allowed fields. Client / invoice / CN writes remain forbid.

**I9 — `isoDate()` is UTC-sliced**
E2E range uses `toISOString().slice(0, 10)` while the invoice date input is local. Possible midnight-UTC flake; not a product P0.

**I10 — Error codes**
`DATE_RANGE_TOO_LONG` and `STATEMENT_TOO_LARGE` on `ErrorCode`. Frontend interceptor formats those two as `CODE: message`.

---

## WP-A nits vs UI/E2E

| WP-A nit | UI / E2E |
|---|---|
| N1 quotes/LPO/DN untested | Still API-only; UI cannot render those tables on this GET |
| N2 unapplied in buckets | **Addressed in UI:** footer + PDF “Unapplied credit”; aging is five keys |
| N3 past `as_of` copy | **Addressed in UI:** `OUTSTANDING_COPY` on page, preview, PDF |
| N4 module regressions | Unchanged; not this file |
| N5 payment workspace join | Unchanged; not a leak |
| N6 label Literal | UI prints API `doc_type_label`; Playwright locks the three activity labels |

---

## Commit

**May commit when asked.** Include API + UI + Playwright + this report. Do not include `.venv`, `frontend/dist`, pytest/ruff caches, or `.claude-flow` policy tmp files.

Do **not** add `GET .../ar-statement.pdf`, an `ar_statements` table, a second aging function, or PDC bounce in that commit.

---

## Next remaining UAE gap (do not implement)

**PDC truth/bounce** (gap 11 / Phase 9): stop treating uncleared PDC as SUCCESS cash. Then **volume pricing** (gap 8). Bilingual/Arabic Account Statement PDF and debit notes stay later.
