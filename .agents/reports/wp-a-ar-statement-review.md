# WP-A AR Statement — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + pytest only. No git commit. No UI. No WP-B. No code changes (no P0 tenant leak, CN-as-cash, PENDING-as-paid, GET mutation, float money, or new Alembic).
**Spec:** `architecture/wave-ar-statement-addendum.md` (full), `.agents/reports/architect-ar-statement-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B UI + Account Statement PDF **may start**.

No P0. Cross-workspace client id is **404 `NOT_FOUND`**, never 403. CREDIT_HOLD does not block. ISSUED CN amounts go to `totals.credited`, never `totals.paid`. PENDING is `Payment (pending)`, credit 0, not in paid. SUCCESS PDC stays in `totals.paid` with method `PDC`. GET is SELECT-only (no commit; row snapshot test). Money is `Decimal` + `line_money.money()` — no `float`. Alembic HEAD remains **`b8d5f0c3a216`**. No `ar_statements` table. No server PDF.

This pass re-ran `backend/.venv` pytest: **`tests/test_ar_statement.py` 13 passed** against PostgreSQL `*_test` (17.51s). `alembic heads` → `b8d5f0c3a216 (head)`.

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Isolation 404 not 403; CREDIT_HOLD does not block | **PASS.** `_require_client` → `CreditControlService.load_client` (`id` + `workspace_id` + `deleted_at IS NULL`). Miss → 404 `NOT_FOUND` via `raise_error`. Other-workspace test asserts 404 and `!= 403`. No `assert_not_hold`. MEMBER + HOLD client GET 200 (tested). Auth is `get_current_user` (same as GET client / GET credit). |
| 2 | Decimal `money()` everywhere; never float | **PASS.** Service math uses `ZERO = Decimal("0.00")` and `money()` (ROUND_HALF_UP fils). No `float` in service or schemas. Invoice/payment/CN columns remain `Numeric(12, 2)`. Aging reuses live `Invoice.balance_due` (SUCCESS paid + `amount_credited`). |
| 3 | GET read-only | **PASS.** `get_statement` only `select`s. Router does **not** `commit` (unlike GET `/credit`, which still evaluates). No `session.add` / UPDATE / DELETE on invoices, payments, CNs, or `clients.credit_balance`. `test_get_does_not_mutate_rows` compares table counts + status / `amount_credited` / payment / CN / `credit_balance` / `updated_at`. |
| 4 | CN ISSUED → `totals.credited`, never `totals.paid`; DRAFT CN omitted | **PASS.** `_load_credit_notes` is `status == ISSUED` and `deleted_at IS NULL` on include-set invoices. `period_totals.credited` sums CN totals; `paid` is SUCCESS payments only. Labels `Tax Credit Note`. Tests: issued CN credit ≠ paid; draft CN → no `TAX_CREDIT_NOTE` line. |
| 5 | SUCCESS payment → `totals.paid`, `cleared_cash` true; PENDING → memo | **PASS.** `payment_activity`: SUCCESS credit = amount, `cleared_cash` true; PENDING credit 0, `pending_amount` set, `cleared_cash` false, `doc_type_label` **Payment (pending)**. PENDING inserted via test session (spec-allowed). `amount_due_now` still full invoice total. |
| 6 | SUCCESS PDC still in `totals.paid`; method PDC not Tax Credit Note | **PASS.** Live `record_payment` SUCCESS path untouched. Test pays with `method=PDC`; JSON `payment_method == "PDC"`, label **Payment**, in `totals.paid`, `cleared_cash` true. |
| 7 | Include SENT/PARTIAL/PAID/OVERDUE; exclude DRAFT, CANCELLED (+ pays/CNs), quotes/LPO/DN | **PASS (implementation).** `INCLUDE_STATUSES` = SENT / PARTIALLY_PAID / PAID / OVERDUE, `deleted_at` null. Payments/CNs loaded only for those invoice ids → CANCELLED/DRAFT parents drop their credits. FAILED omitted (`PAYMENT_STATUSES` = SUCCESS, PENDING). Quotes/LPO/DN are other tables — cannot appear. **Nit:** pytest does not create quote/LPO/DN (spec §10.3 said to if fixtures exist). OVERDUE **status** is included in the query; tests cover past-`due_date` SENT (still in AR set). |
| 8 | Opening = billed_before − paid_before − credited_before; running = opening + billed − paid − credited | **PASS.** `reconstruct_opening` uses date `< from`, SUCCESS pays only, ISSUED CNs. `assemble_lines` opening first, then `running = money(running + debit − credit)`. PENDING debit/credit 0. `totals.closing_running` = last running. Opening test: invoice before `from`, payment in range → opening = billed, period billed 0, paid = cash. |
| 9 | Aging reuses `open_ar_invoices` + `aging_buckets` | **PASS.** Footer calls those helpers (not a forked bucket fn). Open AR = SENT / PARTIALLY_PAID / OVERDUE (not PAID). `credit_balance` is a separate field. `amount_due_now` = Σ live `balance_due`. Test: past-due open invoice bucket matches `_bucket_key`; PAID total not in non-zero buckets; `sum(buckets) == amount_due_now`; `as_of=today` buckets + exposure match GET `/clients/{id}/credit`. GET `/credit` **unchanged**. |
| 10 | from/to required; >366 `DATE_RANGE_TOO_LONG`; cap 2000 `STATEMENT_TOO_LARGE`; future `as_of` 422 | **PASS.** Query `from`/`to` required. `from > to` → 422 `VALIDATION_ERROR` `field=from`. `(to−from).days > 366` → 422 `DATE_RANGE_TOO_LONG` `field=to`. Future `as_of` → 422 `VALIDATION_ERROR` `field=as_of`. Cap `activity_count > 2000` → 400 `STATEMENT_TOO_LARGE` `field=to` (monkeypatch cap=0, spec-allowed). |
| 11 | No Alembic; no `ar_statements` table; no server PDF | **PASS.** No new file under `backend/alembic/versions/`. `alembic heads` = **`b8d5f0c3a216`**. No model named Statement. No `ar-statement.pdf` / WeasyPrint / reportlab. No frontend `StatementPDF`. |
| 12 | Wrapper `{success,data,error}`; `doc_type_label` exact; MEMBER+ | **PASS.** `SuccessResponse[ArStatementResponse]` with `response_model_by_alias=True` so `from_` serializes as `from`. Errors via existing HTTP handler. Labels locked in `DOC_TYPE_LABELS` (Opening balance / Tax Invoice / Payment / Payment (pending) / Tax Credit Note) — asserted. MEMBER GET 200. |
| 13 | Wide-range identity `closing_running == money(amount_due_now − credit_balance)` | **PASS (claimed + tested).** Fully paid invoice + ISSUED CN: `amount_due_now` 0, `credit_balance` = CN total, closing = −CN. Range is last 30 days covering all activity (not `from=2000-01-01`, which would exceed 366 days — see I2). |
| 14 | Tests hit PostgreSQL and the assertions above | **PASS.** Same `DATABASE_URL` + `_test` + `asyncpg` pattern as CN tests. Default URL is PostgreSQL. **13 passed** on this review machine. Money tests use real rows; cap uses monkeypatch only. Isolation, CN≠paid, PENDING, PDC, aging vs `/credit`, identity, opening, HOLD/MEMBER, GET mutation covered. Gaps in nits below — not happy-path-only. |

---

## Findings

### Critical (P0)

None.

- Other-workspace GET → 404 `NOT_FOUND`, no client payload.
- CN totals are not added to `totals.paid`.
- PENDING is not cleared cash and is not in `totals.paid`.
- GET does not write invoices / payments / CNs / `credit_balance`.
- No `float` money.
- No new Alembic revision / second AR ledger.

### Warning

None that block WP-B. Functional locks hold.

### Nits / test gaps (do not block WP-B)

**N1 — Quote / LPO / DN omission untested**
Spec §10.3: create those docs if fixtures exist. Helpers live in `test_quotations.py` / `test_customer_lpos.py` / `test_delivery_notes.py`. WP-A tests never POST them. Safe: include-set is `Invoice` only. Optional follow-up assert.

**N2 — `credit_balance` not-in-buckets is weakly asserted on the aging test**
`test_aging_matches_credit_and_bucket_sum` only checks parked credit if `parked > 0`; that fixture parks 0. The wide-range test parks CN credit but does not assert bucket values. Implementation cannot put `credit_balance` in buckets (`aging_buckets` sums invoice `balance_due` only). WP-B: render Unapplied credit in the footer, not as a bucket.

**N3 — Past `as_of` untested**
Code allows `as_of < utc_today()` (days vs that date; amounts stay live). Only future `as_of` is 422. WP-B copy: outstanding amounts are current.

**N4 — Spec §10.13 regression file not in `test_ar_statement.py`**
FTA send, overpay, CN issue, HOLD, `alembic check` are not re-run here. HOLD on this GET is tested. This review confirmed Alembic HEAD did not move. Invoice/CN/payment modules were not edited.

**N5 — `_load_payments` is invoice-id scoped, not `workspace_id`**
Payments have no `workspace_id`. Ids come from a workspace+client include-set (UUIDs). Defense in depth would join `Invoice.workspace_id`. Not a tenant leak.

**N6 — `doc_type_label` is a free `str` on the schema**
Service uses `DOC_TYPE_LABELS`. Tests lock the five strings. A `Literal` would make WP-B typos fail closed.

---

## Info

**I1 — Pytest re-run here**
`backend/.venv/Scripts/python.exe -m pytest tests/test_ar_statement.py -q` → **13 passed**, 1 httpx `TestClient` deprecation warning (pre-existing style). Tests use `SQLModel.metadata.create_all` on `*_test`, same as other WP-A modules — not SQLite.

**I2 — Spec example `from=2000-01-01` contradicts the 366-day cap**
Addendum §4 vs §7. The shipped test uses a window that covers all surviving activity and stays ≤366 days. That is the identity that can actually 200.

**I3 — WP-B must not treat `closing_running` as “amount due now” on a short period**
Footer `amount_due_now` / `credit_balance` / aging are **live**. Identity with `closing_running` holds when `[from,to]` covers all include-set activity. A mid-month print can show a different running close than live exposure. Title **Account Statement**. Do not label CN as Payment. SUCCESS PDC footnote per §6.

**I4 — GET `/credit` still mutates; statement GET does not**
`GET /clients/{id}/credit` still `evaluate` + `commit` (SENT → OVERDUE on-read). Statement GET skips that on purpose (read-only). Both still include SENT and OVERDUE in `AR_STATUSES`, so `as_of=today` buckets match.

**I5 — File length**
`ar_statement_service.py` is 470 lines (under 500). `clients.py` stays well under 500 with the new GET. Tests ~665 lines (test files are allowed longer). `get_statement` is longer than the swarm 20-line guideline; logic is split into helpers.

**I6 — GET `/credit` unchanged**
Diff on `clients.py` only inserts the new route after the existing credit handler.

**I7 — Error codes**
`DATE_RANGE_TOO_LONG` and `STATEMENT_TOO_LARGE` added to `ErrorCode`. `NO_LIST_PRICE` is pre-existing (invoice product master), not this WP.

---

## WP-B

**May start.** Pytest is green. No P0. No Alembic for WP-B to wait on.

Do **not** add `GET .../ar-statement.pdf`, an `ar_statements` table, or a second aging function. PDF title **Account Statement**.
