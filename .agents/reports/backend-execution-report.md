# Backend Execution Report
*Wave 1: Bug Fix + Core Sync*

---

## 2026-09-07 — Wave 28: UAE VAT Compliance Pack export (implementation) — IMPLEMENTED

Implementing `architecture/wave-vat-compliance-pack-addendum.md` (rev 2, coordinator-locked) report-first:
- **Scope (rev 2):** `GET /api/v1/reports/vat-compliance?from&to&format=csv|json` — OWNER/ADMIN, `10/minute`, 366-day cap + from≤to guards (reuse `ar_statement_service`). ZIP of 7 entries (`sales_invoices.csv`, `invoice_lines.csv`, `credit_notes.csv`, `tax_debit_notes.csv`, `purchase_invoices.csv`, `vat_summary.csv`, `manifest.json`); `format=json` → same aggregates wrapped in `SuccessResponse`. **No Alembic, no model edits** (HEAD `c5b7a3e9f21d` re-verified); config-only `VAT_ORG_TRN` (optional, never blocks).
- **Locked rules:** business dates only (`issue_date`; supplier `invoice_date` → **GST business date** via stdlib `timezone(timedelta(hours=4))`, NOT driver-UTC `.date()`); inclusion SENT/PARTIALLY_PAID/PAID/OVERDUE sales, ISSUED CN/TDN, supplier all-except-CANCELLED (≠ input-tax recoverability); `vat_summary` line-level per-rate buckets, CN − / TDN + net into output, input = **AED supplier invoices only** — non-AED stay in `purchase_invoices.csv` (currency preserved) + `manifest.warnings.non_aed_supplier_invoices`; **no FX/conversion invented**; snapshot-preferred seller/buyer identity; `manifest.currency = "AED"` is the aggregation currency.
- **Module plan:** `app/config.py`+`.env.example` (`VAT_ORG_TRN`) → `app/schemas/vat_compliance.py` → `app/services/vat_compliance_service.py` (all reads) → `app/routers/reports.py` → wired `main.py` → `tests/test_vat_compliance.py` (13 cases, addendum §7).
- **Result:** All implemented. Config `VAT_ORG_TRN: str = ""` added to `app/config.py` + `backend/.env.example`. Created `app/schemas/vat_compliance.py` (8 models). Created `app/services/vat_compliance_service.py` (business_date GST helper, build_report, csv_text, build_zip). Created `app/routers/reports.py` (single endpoint with limiter + RBAC). Wired `reports_router` into `main.py` at `/api/v1`. **13 tests passing** (`tests/test_vat_compliance.py`). Full suite **397 passed**, ruff clean, alembic check clean (no Alembic). StreamingResponse `iter([bytes])` fix applied.

---

## 2026-09-07 — Wave 28: UAE VAT Compliance Pack export (planning) — ADDENDUM LOCKED, NO CODE

Locked `architecture/wave-vat-compliance-pack-addendum.md` per parent plan §5. **No Alembic** (head stays `c5b7a3e9f21d`, guardian pins unchanged); only config addition `VAT_ORG_TRN` (optional — never blocks generation, LOCK #10).
- **Runtime truth verified against live code:** `invoice.issue_date` (not the parent plan's `invoice.invoice_date`) + `supply_date`/`due_date`; FTA snapshots; `credit_note`/`tax_debit_note` `issue_date` + ISSUED; `supplier_invoice.invoice_date` DateTime(TZ)→UTC-date + `vat_amount`/`vat_rate`; `invoice_items.line_net`/`tax_amount`; CN/TDN items; `client.tax_id`; `workspace.trn`/`address`; `supplier.name`/`trn`; reuse `ar_statement_service` period guards (366-day cap / from≤to) + `line_money.money` + `_require_owner_admin`; `_member_token` test pattern.
- **Locked scope:** `GET /api/v1/reports/vat-compliance?from&to&format=csv|json` — OWNER/ADMIN, `10/minute`, `to−from > 366` → 422. ZIP of 7 entries: `sales_invoices.csv`, `invoice_lines.csv`, `credit_notes.csv`, `tax_debit_notes.csv`, `purchase_invoices.csv`, `vat_summary.csv`, `manifest.json` (org name/TRN/address, period, output/input/net tax). `format=json` → same aggregates in `SuccessResponse` wrapper; CSV → raw `StreamingResponse` zip (`response_model=None`).
- **Burned decisions (review-confirmed 2026-09-07):** supplier invoices = all statuses except CANCELLED; `vat_summary` nets CN/TDN **item-level** into per-rate output buckets (CN −, TDN +); JSON wrapped; business-date filtering only (never `created_at`); OVERDUE never excluded; snapshot-preferred seller/buyer identity for issued docs.
- **Verification:** planning only — no code/tests/migrations written. Full suite remains **384 passed** @ `be912b1`; `alembic check` clean. Next: implement Wave 28 report-first.

---

## 2026-09-07 — Wave 28 (planning) — REVIEW VERDICT RESOLVED (rev 2) — NREV-2, NO CODE

Peer verdict applied to `architecture/wave-vat-compliance-pack-addendum.md` (three decisions re-confirmed). Resolutions against live code:
- **Currency (reviewer's biggest concern, resolved):** sales invoices are **AED-enforced** at create/PUT/send (`invoice_service._assert_aed` → 422; send → 400 `FTA_SEND_BLOCKED`; `Currency` enum AED-only); CN/TDN derive `currency = invoice.currency` → AED. Supplier invoices are **unrestricted** (`str(max_length=3)`; match engine `FAILED_CURRENCY` proves multi-currency input is designed). **No FX mechanism exists** — `RFQ.exchange_rate` (Numeric(12,6), default 1.0) is never read anywhere; no conversion field on supplier invoices. Locked: `vat_summary` **input buckets aggregate AED supplier invoices only**; non-AED supplier invoices remain in `purchase_invoices.csv` (currency preserved) and are enumerated in `manifest.warnings.non_aed_supplier_invoices` — never silently mixed. No conversion invented (§2.4/§4.2).
- **Supplier `invoice_date` timezone (resolved):** `DateTime(timezone=True)` + asyncpg UTC rendering makes `.date()` give the UTC calendar date (shifts a `00:30 +04:00` document to the previous day). Locked: the pack uses the **GST business date** (`astimezone(timezone(timedelta(hours=4)))`, fixed UTC+4 no DST, stdlib, no tzdata) for supplier invoices; whole window consistent on the Gulf business calendar. This is a documented, deliberate divergence from the live statement/AP-aging UTC `.date()` convention (unchanged) (§2.1/§9).
- **Alembic HEAD verified live:** `alembic heads` → `c5b7a3e9f21d` (Wave 27's head); the `3d3f24d6ee00` the reviewer saw was Wave 26's head — superseded by Wave 27. Guardian pins unchanged; `alembic check` stays clean (no migration this wave).
- **Wording hardened:** supplier inclusion = "exists in the accounting system and not cancelled" ≠ input-tax recoverability (§2.3); explicit no-netting-engine boundary (§4.4); `manifest.currency` = aggregation currency only.
- **Verify:** planning only. Full suite remains **384 passed** @ `be912b1`. Next: implement Wave 28 report-first.

---

## 2026-09-07 — Wave 27: WhatsApp Business API + PDF delivery + inbound→Enquiry (implementation) — IN PROGRESS

Implementing `architecture/wave-whatsapp-pdf-addendum.md` (rev 3, coordinator-locked) report-first:
- **Review passed:** "APPROVE WITH REQUIRED CHANGES" (rev 1 reviewer verdict) → all 18 corrective locks applied (rev 2); final 3 mandates applied (rev 3): `received_at` + formal inbound/outbound timestamp semantics; `message_type=MEDIA` = inbound media/non-text transport record only (no download/inspection/storage/processing); exact idempotency reservation (request fingerprint, `409 IDEMPOTENCY_CONFLICT` on key+different-request, global unique `whatsapp_message_id`, `QUEUED` = interrupted synchronous send not a queue).
- **Scope (rev 3):** `WhatsAppMessage` + `whatsappdirection`/`whatsappmessagestatus`(incl. **RECEIVED**)/`whatsappmessagetype` PG enums + `whatsapp_idempotency_keys` (PK `(workspace_id,key)` + fingerprint); `providers.py` → `WhatsappProvider` (Media upload + Messages document/text, normalized error triples); `pdf_service.py` → `DocumentRenderer` (INVOICE/QUOTATION/AR_STATEMENT; `build_sections` seam + no-recompute rule; EN-only, bilingual deferred — no legal claim); `utils/phones.py` `normalize_phone_to_e164` (no country guessing); `whatsapp_service.py` (two-txn outbound, provider call OUTSIDE DB session; recipient derived from linked Client's canonical phone — no `to_number` override; lifecycle gates from live enums; AR_STATEMENT uses `linked_entity_id`+`statement_from/to`, resend regenerates with current data); webhook GET challenge + POST HMAC + `metadata.phone_number_id` verification + body-size cap + response-precision matrix; inbound→Enquiry single transaction (EnquiryService session-injection, no self-commit), dedup = DB unique constraints (race→idempotent 200); one-workspace-per-deployment explicit MVP limitation. `ErrorCode.UNSUPPORTED_DOCUMENT` + `IDEMPOTENCY_CONFLICT`.
- **Verify:** full suite green + ruff + black + `alembic check`; then `STATE.md` + commit.

---

## 2026-09-07 — Wave 26: Email Engine via Resend API (implementation) — COMPLETE ✅

Implemented `architecture/wave-email-engine-addendum.md` report-first:
- **Model + Alembic:** `EmailLog` (`email_log` table) + `emailstatus` PG ENUM (QUEUED|SENT|DELIVERED|BOUNCED|FAILED) + `simulated` bool; migration `3d3f24d6ee00_add_email_log` (down_revision `234d5639ef8c`, new head) incl. `email_idempotency_keys` (48h TTL), composite indexes `ix_email_log_workspace_id_created_at` / `ix_email_log_workspace_linked`, unique `uq_email_log_resend_message_id`. Top-of-tree round-trip verified (`upgrade → downgrade -1 → upgrade`) + `alembic check` clean.
- **Config:** `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_WEBHOOK_SECRET`, `COMMS_DRY_RUN` (default true) in `app/config.py` + `backend/.env.example`.
- **Adapter:** `app/services/providers.py` → `ProviderResult` + `ResendProvider` (httpx) — dry-run simulator returns `simulated=True`, `resend_message_id=None`.
- **Service:** `app/services/email_service.py` — send/list/get/resend/webhook + linked-entity resolver (workspace-validated; **AR_STATEMENT/SUPPLIER_STATEMENT reference-only, no physical FK**); provider failure commits row as FAILED then 502 `PROVIDER_ERROR` so resend is possible; never logs secrets/PII/bodies.
- **Schemas:** `app/schemas/email_comms.py` — `EmailSendRequest` (to_email, subject, body_html, bcc?, linked_entity*), `EmailResponse` (datetime timestamps + `EmailStatus` enum), `EmailWebhookRequest`. `ErrorCode.PROVIDER_ERROR` added to `app/schemas/common.py`.
- **Router:** `app/routers/comms_emails.py` — POST `/api/v1/comms/emails` (OWNER/ADMIN, 30/min, Idempotency-Key), GET list (member, workspace-scoped, paginated), GET `{id}` (member), POST `{id}/resend` (OWNER/ADMIN, FAILED/QUEUED only), POST `/api/v1/webhooks/email` (Bearer `RESEND_WEBHOOK_SECRET`, no limiter). Wired in `main.py`; models + enum exported in `app/models/__init__.py`.
- **Tests:** `tests/test_email_comms.py` — **11 passed** (§6 of addendum; fake providers via class-attr swap, dry-run uses real provider, idempotency, resend gating, linked-entity valid/bad-ref/cross-workspace, MEMBER RBAC, webhook secret+events+idempotency). Guardian pins in `test_pdc.py` / `test_pricing.py` re-pointed to `3d3f24d6ee00`.
- **Fix notes:** `EmailResponse` timestamps retyped `str`→`datetime` (pydantic v2 rejects datetime input on `str` fields); fakes set on `EmailService` **class** attr (send path is a classmethod reading `cls.provider`); `_FakeSuccess` returns unique message ids to satisfy the unique constraint.
- **Verify:** full suite **333 passed** (+11), ruff clean, black clean on touched files, `alembic check` clean. Pre-existing black drift noted in `tests/test_enquiries.py` / `tests/test_ar_statement.py` (unrelated to this wave, excluded from this commit). Next: `STATE.md` + commit.

---

## 2026-09-07 — Phase 5 planning v1 review — 12 locks applied + Wave 26 addendum (NO CODE)

**Planning only.** Review verdict v1 approved the Phase 5 plan with 12 architecture locks; all applied:

1. **ROADMAP supersession recorded** — `.planning/ROADMAP.md` (26=Email, 27=WhatsApp+PDF, 28=UAE VAT) is authoritative over MASTER_PLAN_V3 (26=WhatsApp, 27=Reports/Dashboard, 28=India). India-market rules (`business-rules.md` Cat.11) noted as deferred, not Phase 5.
2. **PDF formalized** — server-side `DocumentRenderer` (reportlab) = canonical outbound-comms primitive; reconciles `wave-bilingual-pdf-addendum.md` client-side `@react-pdf` (which stays the interactive UI path); single canonical doc representation, no dual systems; future email attachments reuse the renderer.
3. **WhatsApp inbound → Enquiry**: webhook → HMAC → dedupe by `wa_message_id` → persist → link known Client only → create Enquiry status NEW; **no LLM**; unknown contacts → `client_id` nullable, never auto-Client.
4. **WhatsApp idempotency**: `wa_message_id` is the provider dedup id; webhook retries can't duplicate message or Enquiry; repeated DELIVERED/READ idempotent.
5. **Dry-run**: default true, CI never hits Resend/Meta; simulated sends record `simulated=True` + log, no new lifecycle state.
6. **Email/`/send` decoupled** — `POST /invoices/{id}/send` untouched.
7. **Linked-entity + workspace validation**; AR_STATEMENT no physical FK (documented); `body_text` optional (OUT of MVP).
8. **Security**: env-keyed creds; never log tokens/keys/secrets/bodies/full PII; webhooks public but secret-authenticated.
9. **VAT = read-only** export, not FTA submission/e-invoicing/XML/EDI; business-date filter (invoice_date etc., never `created_at`); lifecycle-based inclusion; never exclude overdue-only (payment vs tax-document status separate).
10. **VAT content approved** incl. input+output, ZIP+JSON; org TRN optional, never blocking.
11. **Synchronous infra** — no Celery/Redis queues/scheduled/bulk/retry workers per-workspace encrypted creds; manual resend only.
12. **Governance** — unchanged lifecycle; no implementation until lock recorded.

Locked `architecture/phase-5-comms-integrations-planning.md` (v1) + Wave 26 implementation addendum `architecture/wave-email-engine-addendum.md` (email_log + emailstatus + simulated, Alembic moves HEAD, bearer webhook, OWNER/ADMIN sends, Idempotency-Key, AR_STATEMENT no FK, tests §6). **No code/tests/migrations written.** Full suite remains **322 passed** @ `1a38655`; `alembic check` clean. Next: implement Wave 26 report-first.

---

## 2026-09-07 — Phase 5 planning (Communications & Integrations) — NO CODE

**Planning only** (lifecycle rule: nothing implemented without planning). Locked `architecture/phase-5-comms-integrations-planning.md` after researching live runtime truth — no comms tables (domain model was aspirational), no PDF generator/object-storage, Redis unwired, `/send` endpoints only "mark as sent" (no provider call), VAT fields exist across invoice/invoice_item/credit_note/tax_debit_note/supplier_invoice + `client.tax_id`/`supplier.trn`.

**Locked phase decisions:** Waves 26→27→28 (Email via Resend / WhatsApp+PDF / VAT pack). Shared locks: in-process `reportlab` PDF `DocumentRenderer` (INVOICE/QUOTATION/AR_STATEMENT in W27); `providers.py` async adapter layer + `COMMS_DRY_RUN` (CI never hits the network); env-keyed single provider account (per-workspace profiles OUT — encrypted-at-rest later); sends OWNER/ADMIN + `Idempotency-Key`; webhooks signature-gated & not IP-rate-limited (email bearer-secret, WhatsApp GET-challenge + X-Hub-Signature-256); email channel decoupled from document `/send`; §6 phase-gate confirmations needed before Wave 26 implementation. Alembic on 26/27 (new `emailstatus`/`whatsappdirection`/`whatsappmessagestatus` enums), none on 28.

**Verification:** planning doc only; no code/tests/migrations written. Full suite remains **322 passed** at HEAD `1a38655` (Wave 25); `alembic check` clean. Next: resolve §6 gates with the user, then implement Wave 26 report-first + per-wave commit.

---

## 2026-09-07 — Wave 25: AP payment reversal (bank-bounce recovery, Phase 4 — last leftover)

**Spec:** `architecture/wave-ap-payment-reversal-addendum.md`. Closes the last Phase 4 leftover (Wave 24 §13 deferred "reversal of an already-SUCCESS CASH/BANK/CHEQUE after bank bounce"). Backend only. **Alembic NO** — HEAD stays `234d5639ef8c`; `alembic check` clean; no new columns/enums; guardian pins unchanged.

### Locked (addendum)

- Eligible target: a payment that is **SUCCESS today**, CASH / BANK_TRANSFER / CHEQUE. MVP records these SUCCESS-on-receipt; if the bank bounces the cheque or recalls the transfer, the consumed AP must be restored. **PDC is excluded** — it uses its own machine and a CLEARED PDC is terminal (mirror AR "reopen with a credit note"); PENDING/BOUNCED/RETURNED PDC → 403.
- Effect: `status -> FAILED` + `_reverse_settlement` inside the row lock (exact inverse of `_settle_invoice`: `amount_paid -= amount; balance_due += amount`; PAID → PARTIALLY_PAID → APPROVED when paid hits 0; `paid_at` cleared when balance_due > 0). Amount/method/dates **never** rewritten (immutable money identity).
- Statement / `ap-balance` / `ap-aging`: read live stored columns, omit FAILED (existing `PAYMENT_STATUSES`), so a reversed payment silently re-enters open AP and `closing_running == amount_due_now` identity holds. **Zero statement/aging code change.**

### Delivered

- `backend/app/services/supplier_payment_reversal_service.py` — new `SupplierPaymentReversalService` (dedicated file; keeps `supplier_payment_service.py` <500 via the Wave 24 split valve): `reverse_payment` locks invoice (FOR UPDATE, id+workspace → 404) then payment (FOR UPDATE, id+invoice_id → 404); OWNER/ADMIN only; ordering is **PDC guard first** so a BOUNCED PDC (already FAILED) gets 403, not the idempotent 200; non-PDC + SUCCESS-only (already-FAILED → 200 no-op); open-invoice guard (APPROVED/PARTIALLY_PAID/PAID, else 403 `INVALID_STATE`); defensive `amount <= amount_paid` → 400 `PAYMENT_EXCEEDS_BALANCE` (unreachable via API — `amount_paid` is exactly Σ SUCCESS amounts); `_reverse_settlement`.
- `backend/app/schemas/supplier_payments.py` — `SupplierPaymentReversalRequest` (empty body, `extra="forbid"`, 422 on stray keys) mirroring `PdcActionRequest`.
- `backend/app/routers/supplier_payments.py` — `POST /api/v1/supplier-invoices/{invoice_id}/payments/{payment_id}/reverse` (OWNER/ADMIN, `10/minute`, no Idempotency-Key); reuses `_pdc_response` commit+serialize helper; router docstring updated.

### Verified

- New `tests/test_supplier_payment_reversal.py` — 8 tests (full reversal on PARTIALLY_PAID invoice; full reversal of a PAID invoice → APPROVED + `paid_at` cleared; partial reversal keeps immutability; statement mapping with `paid` drop + `closing_running == amount_due_now` identity; ap-aging re-entry + bucket sum == balance; illegal reversals — CLEARED/PENDING/BOUNCED/RETURNED PDC + CANCELLED invoice all 403; MEMBER 403 `INSUFFICIENT_PERMISSIONS`; cross-workspace 404). The defensive over-reverse 400 is unreachable via the API by construction (documented in addendum §2.9).
- Targeted regression (supplier_payments / supplier_statement / supplier_pdc / pricing): **46 passed**.
- Full backend suite: **322 passed** (314 + 8 new) in 7:43. ruff + black clean. `alembic check` clean. Not committed yet (commit is the wave-final step).

---

## 2026-09-07 — Wave 24: PDC-to-supplier (AP post-dated cheque issued, Phase 4)

**Spec:** `architecture/wave-pdc-to-supplier-addendum.md`. Clears the Wave 22 "Out" item "PDC-to-supplier + cheque bounce/reversal" by generalizing the AR PDC machine to the payable side. The **PDC** machine ships; reversal of an already-SUCCESS CASH/BANK/CHEQUE after bank bounce stays deferred (SDN route, mirror of AR "CLEARED is terminal"). Backend only. **Alembic YES** (migration `234d5639ef8c`). Committed.

### Locked (addendum)

- PDC insert rule: `payment_method=PDC` → `status=PENDING`, `pdc_status=RECEIVED`, `pdc_date` **required** (422 `VALIDATION_ERROR` field=pdc_date, enforced in `record_payment` mirroring AR `_insert_status`). No `_settle_invoice` — `balance_due`/`amount_paid`/invoice status unchanged. Overpay-at-insert cap still applies (PENDING does not consume the cap).
- CASH / BANK_TRANSFER / CHEQUE stay SUCCESS-on-receipt; CHEQUE is **not** on the machine (bounce → 403 `INVALID_STATE`).
- Four POSTs `POST /supplier-invoices/{invoice_id}/payments/{payment_id}/pdc/{deposit|clear|bounce|return}`: deposit RECEIVED→DEPOSITED (gate `pdc_date <= utc_today()` else 400 field=pdc_date, stays PENDING); clear DEPOSITED→CLEARED (SUCCESS, overpay lock `amount > balance_due` → 400 `PAYMENT_EXCEEDS_BALANCE`, then `_settle_invoice` incrementally); bounce DEPOSITED→BOUNCED (FAILED, no credit evaluate — AP has none); return RECEIVED→RETURNED (CANCELLED). Illegal transitions → 403 `INVALID_STATE` field=pdc_status. Idempotent target-state 200s. Already-CLEARED/historical SUCCESS PDC → 200 no-op, no amount rewrite.
- OWNER/ADMIN only on the four POSTs (MEMBER 403 `INSUFFICIENT_PERMISSIONS`); `@limiter.limit("10/minute")`; empty `{}` body (`PdcActionRequest`, extra=forbid); no `Idempotency-Key`. Isolation: invoice by id+workspace, then payment by id+invoice_id → 404, never 403.
- Statement/aging unchanged: PENDING already renders as `SUPPLIER_PAYMENT_PENDING` (credit 0, `pending_amount`, not in `totals.paid`); FAILED/CANCELLED (BOUNCED/RETURNED) omitted by existing `PAYMENT_STATUSES`. CLEARED is terminal (no `CLEARED → BOUNCED`).

### Done

- Alembic `234d5639ef8c_add_supplier_pdc_columns.py` (down_revision `b4a2c6e8f10d`, head): adds `pdc_date` (Date, nullable) + `pdc_status` (PG `pdcstatus` ENUM, `create_type=False` — type already exists from `e217c0bc3af7`) to `supplier_payments`. Upgrade on dev DB; downgrade → upgrade round-trip verified; `alembic check` clean. Head re-pins: `test_pdc.py`/`test_pricing.py` → `234d5639ef8c`.
- Model — `backend/app/models/supplier_payment.py`: `pdc_date` (`sa_column=Column(Date)`) + `pdc_status` (`Optional[PDCStatus]`), using the shared `PDCStatus` from `app/models/payment.py`.
- Schema — `backend/app/schemas/supplier_payments.py`: `AP_PAYMENT_METHODS` widened to include PDC; `SupplierPaymentCreate.pdc_date` + validator (catches explicit null); `SupplierPaymentResponse.pdc_date`/`pdc_status`.
- Service — `backend/app/services/supplier_payment_service.py` `record_payment`: new `pdc_date` argument forwarded from the router; PDC branch inserts PENDING+RECEIVED and **skips** `_settle_invoice`; 422 pdc_date-required guard (mirrors AR); non-PDC path unchanged.
- New `backend/app/services/supplier_pdc_service.py` (`SupplierPdcService` < 500 lines, mirrors `PdcService`): `_require_owner_admin`, `_invalid_state`, `_require_pdc`, `_cleared_already`, `_lock_pair` (FOR UPDATE invoice then payment), deposit/clear/bounce/return; clear reuses `SupplierPaymentService._settle_invoice` under the overpay lock (DN-credit safe). No AR `update_status`/credit-evaluate on AP.
- Router — `backend/app/routers/supplier_payments.py`: four POST endpoints + shared `_pdc_response`; forwards `pdc_date` on create; existing PUT 405/GET isolation unchanged. Same router module, no `main.py` change (already wired at `/api/v1`).
- Tests — `backend/tests/test_supplier_pdc.py` (15 tests): future PDC PENDING+RECEIVED with no balance effect; pdc_date required 422; today-dated PDC still PENDING; non-PDC SUCCESS; deposit-before-date 400; deposit/clear lifecycle → SUCCESS+CLEARED + `_settle_invoice`; bounce after deposit → FAILED (balance unchanged, second bounce 200); return from RECEIVED → CANCELLED, from DEPOSITED 403; illegal RECEIVED→clear + CHEQUE→bounce 403 `INVALID_STATE`; over-clear 400 `PAYMENT_EXCEEDS_BALANCE` with PDC not rewritten; statement pending→cleared mapping + totals; bounced/returned omitted from statement; MEMBER 403 `INSUFFICIENT_PERMISSIONS` on PDC action (can still post a PDC); cross-workspace 404.
- Full suite **314 passed** (299 + 15 new in ~7.5 min); ruff + black clean; `alembic check` clean.

## 2026-09-07 — Wave 23: Purchase Returns + Supplier Debit Notes (AP, Phase 4)

**Spec:** `architecture/wave-purchase-returns-addendum.md`. Completes the AP half of MASTER_PLAN_V3 Wave 25 (purchase returns / supplier debit notes). Backend only. **Alembic YES** (migration `b4a2c6e8f10d`). Committed (`e256772`).

### Locked (addendum)

- Purchase return lifecycle `DRAFT → PENDING_SUPPLIER → APPROVED → DISPATCHED → COMPLETED`; `PENDING_SUPPLIER → REJECTED`; `DRAFT/PENDING_SUPPLIER → CANCELLED`. Gapless `PRN-YYYY-XXXX`.
- Supplier debit note `/api/v1/supplier-debit-notes`, gapless `SDN-YYYY-XXXX` (DN-/TDN- reserved). Statuses DRAFT/ISSUED/APPLIED/CANCELLED.
- SDN auto-created **ISSUED** at return **dispatch** (not COMPLETED). GRN-004 auto-return at disposition (rejected→QUALITY_ISSUE, damaged→DAMAGE, `spo_item.unit_price`), accumulate, cap ≤ `quantity_received`.
- Cap invariant: cumulative returned per grn_item never exceeds `quantity_received`. Stock-out rule: `stock_out_qty = min(item.quantity, remaining_accepted, on_hand)`; zero-stock-out legal (rejected/damaged never stocked); PRN ledger rows only when stock actually moves.
- Apply: single txn + FOR UPDATE, workspace 404, supplier mismatch 400, invoice must be APPROVED/PARTIALLY_PAID, `amount <= balance_due` else `DEBIT_NOTE_EXCEEDS_BALANCE`, reduces **only** `balance_due` (never amount_paid/status/paid_at, never flips PAID), double-apply 409, APPLIED permanent.
- Statement integration: Pydantic-only; DN activity `on` = applied_at (UTC); ACTIVITY_ORDER invoice 0 / DN 1 / payment 2 / pending 3; opening reconstruction subtracts pre-window applied credits; `totals.credited`.

### Done

- Models `PurchaseReturn` + `PurchaseReturnItem` + `PurchaseReturnCounter` + `ReturnType` (QUALITY_ISSUE/DAMAGE/EXCESS) + `PurchaseReturnStatus`; `SupplierDebitNote` + `SupplierDebitNoteCounter` + `SupplierDebitNoteStatus` — `backend/app/models/purchase_return.py`, `supplier_debit_note.py`; `nullable=False` on `prn_number`/`dn_number` (SQLModel does not infer NOT NULL from explicit `sa_column`; caught by `alembic check`), registered in `models/__init__.py`.
- Alembic `b4a2c6e8f10d_add_purchase_returns_and_supplier_debit_notes.py` (down_revision `a3f4c7d9e1b2`): 5 tables (`purchase_returns`/`purchase_return_items`/`purchase_return_counters`/`supplier_debit_notes`/`supplier_debit_note_counters`) + 3 enums + 4 check constraints. Applied via `alembic upgrade head`; downgrade → upgrade round-trip verified; `alembic check` clean. Head re-pins: `test_pdc.py`/`test_pricing.py` → `b4a2c6e8f10d`. Alembic CLI targets dev DB on port 5434.
- Number services — `backend/app/services/purchase_return_number.py`, `supplier_debit_note_number.py` (SELECT FOR UPDATE + IntegrityError first-insert race retry, mirrors existing counter services).
- Purchase return service — `backend/app/services/purchase_return_service.py` (with `from __future__ import annotations` fix for `'staticmethod' object is not subscriptable` on `_group_quantities`): `create/submit/approve/dispatch/complete/reject/cancel`, received-cap invariant (`_assert_quantity_available`/`_cumulative_returned` accept `exclude_return_id`; submit/dispatch group per grn_item via `_group_quantities` and exclude THIS record so an at-cap return isn't self-rejected; `create` tracks pending per grn_item for unflushed rows), `_already_stocked`/`_compute_stock_out` thread `exclude_return_id`, `_resolve_stock_bin` FOR UPDATE picks level with most available (fallback `first_active_bin`), ledger rows `reference_type="PRN"`, `reason="PURCHASE_RETURN"`, ISSUE negative, written only for `stock_out_qty > 0`; auto-SDN created at dispatch; `record_disposition_auto_items` (GRN-004) accumulates into existing DRAFT return or creates one (`_existing_auto_item` via explicit SELECT — new-record `record.items` triggers MissingGreenlet).
- Supplier debit note service — `backend/app/services/supplier_debit_note_service.py`: `create/issue/apply/cancel`, eligibility + over-balance + supplier-match + workspace-404 guards, balance_due-only reduction, double-apply 409, cancel rules (DRAFT/ISSUED free, APPLIED blocked), auto-SDN from return dispatch, list filters `supplier_id`/`purchase_return_id`/`status` + pagination.
- GRN-004 hook — `backend/app/services/grn_service.py` `record_disposition`: deferred-import `record_disposition_auto_items` when `quantity_rejected > 0` **or** `quantity_damaged > 0`.
- Statement integration — `backend/app/services/supplier_statement_service.py`: `ACTIVITY_ORDER`, `debit_note_activity`/`debit_note_activity_date`, `collect_activity` with notes, `reconstruct_opening` subtracts pre-window applied credits, `period_totals["credited"]`, `_load_adjustments` by `applied_invoice_id`, wired into `get_statement`.
- **Cross-cutting fix** — `backend/app/services/supplier_payment_service.py` `_settle_invoice`: `balance_due = max(ZERO, balance_due - amount)` instead of `total_amount - amount_paid` (the old recompute erased DN-applied credits). No-DN path unchanged.
- Schemas — `backend/app/schemas/purchase_returns.py`, `supplier_debit_notes.py` (`reason` min_length 5), `supplier_statements.py` doc-type/label/`credited`, `common.py` errors `RETURN_QTY_EXCEEDS_RECEIVED`/`DEBIT_NOTE_EXCEEDS_BALANCE`.
- Routers — `backend/app/routers/purchase_returns.py` (create 201, list, get, submit/approve/dispatch/complete/reject/cancel; OWNER/ADMIN mutations, member 403, cross-workspace 404), `backend/app/routers/supplier_debit_notes.py` (create 201, list/get, issue/apply/cancel); wired into `backend/app/main.py` (191 routes total).

### Pytest (PostgreSQL `_test`) + lint

- `tests/test_purchase_returns.py`: **10 passed** (full lifecycle w/ auto-SDN + stock-out, cap invariant, cancel-frees-cap, illegal transitions, GRN-004 auto-return quantities & price, zero stock-out, isolation 404, member 403, PRN sequence, supplier-mismatch 400).
- `tests/test_supplier_debit_notes.py`: **7 passed** (manual create/issue/apply balance-only, exact-balance stays APPROVED, apply guards incl. 409 + foreign 404 + MATCHED gate, cancel rules, dispatch auto-SDN, list filters + SDN sequence).
- `tests/test_supplier_statement_dn.py`: **4 passed** (DN line + ordering, opening reconstruction with backdated applied_at, DN+payment same-day ordering, cancelled note excluded).
- Full suite: **299 passed, 0 failed** (was 279; ~7m07s). `test_ap_aging.py` seed dates made UTC-robust (this machine's local date lags UTC by a day in the evening → spurious `days_overdue` off-by-one).
- `alembic heads`: **`b4a2c6e8f10d`**; `alembic check`: clean. ruff clean; black clean on non-migration touched files.

---

## 2026-09-06 — Wave 18: Stock Reservations from Customer POs (Phase 3 sub-feature 1)

**Spec:** `architecture/wave-stock-reservations-addendum.md`. Research complete (`reserved` on `inventory_levels` was always 0, no `StockReservation` model, no writer). Locks the plan: `StockReservation` + `StockReservationItem` models, TTL 7 days, `reserved == SUM(quantity - quantity_consumed)` over ACTIVE items, release before `post_issue` on DN confirm, `/api/v1/inventory/reservations` CRUD + cancel + OWNER/ADMIN expire, new wave test module.

### Done

- Models `StockReservation` + `StockReservationItem` + `ReservationStatus` enum (ACTIVE/DISPATCHED/CANCELLED/EXPIRED, `reservationstatus` DB enum), `RESERVATION_TTL_DAYS = 7` — `backend/app/models/stock_reservation.py`; registered in `models/__init__.py`.
- Alembic `b2a4d6f8e1c0_add_stock_reservations.py` (down_revision `9f3a2c1e5d84`) creates `stock_reservations` + `stock_reservation_items` (indexes on status, expires_at, product/warehouse, customer_po references); applied via `alembic upgrade head`; `alembic check` clean.
- Schemas — `backend/app/schemas/stock_reservation.py`: `StockReservationCreate` (single warehouse enforced), `ReservationCancelRequest`/`ReservationExpireRequest` (`extra=forbid`), `StockReservationResponse`/`ReservationListItem` with `remaining`/`quantity_consumed`, `ReservationExpireResponse(expired)`.
- Service — `backend/app/services/stock_reservation_service.py`: `create_reservation`, `cancel_reservation`, `expire_due(at)`, `release_for_dispatch` (FIFO by `created_at, id`, partial shipment advances `quantity_consumed`, full → DISPATCHED), `get_visible`, `active_remaining_by_cpo_item`, `serialize`/`serialize_list_item`. Single writer enforcing the `reserved` invariant via `lock_or_create_level`; rejects over-undelivered, over-available, and non-shippable (DRAFT) LPOs; multi-tenant scoped.
- Router — `backend/app/routers/inventory.py`: `POST /inventory/reservations` (201), `GET /inventory/reservations` (paginated; `status`/`cpo_id`/`warehouse_id` filters), `GET /inventory/reservations/{id}`, `POST /inventory/reservations/{id}/cancel`, `POST /inventory/reservations/expire` (OWNER/ADMIN; declared before `/{id}`).
- DN dispatch integration — `backend/app/services/delivery_note_service.py` `_issue_stock`: for `from_lpo` lines, calls `release_for_dispatch` **before** `post_issue` so shipped qty leaves `reserved` first; DN cancel path unchanged (stays DISPATCHED).
- Tests — `backend/tests/test_stock_reservations.py`: create/cancel & reserved/available tracking, DRAFT-LPO reject, concurrent-style FIFO partial dispatch, full dispatch → DISPATCHED, TTL expire + OWNER/ADMIN 403, multi-tenant isolation, pagination/filters. Updated 3 alembic-head guard tests to `b2a4d6f8e1c0` (`test_pdc.py`, `test_pricing.py`, `test_product_electrical_specs.py`).

### Pytest (PostgreSQL `_test`) + lint

- `tests/test_stock_reservations.py`: **7 passed**
- Full suite: **238 passed, 0 failed** (was 231; 5m17s)
- `alembic heads`: **`b2a4d6f8e1c0`**; `alembic check`: clean. ruff clean; black clean on non-migration touched files (migrations keep alembic style).

---

## 2026-09-06 — Wave 19: Multi-warehouse Stock Transfers (Phase 3 sub-feature 2)

**Spec:** `architecture/wave-stock-transfers-addendum.md`. Stock transfers move stock between warehouses (source bin → destination bin) through a DRAFT → APPROVED → IN_TRANSIT → RECEIVED lifecycle; IN_TRANSIT can be cancelled (returns to source). Uses an `in_transit` swing account so items in transit stay visible while removed from available.

### Done

- Models `StockTransfer` + `StockTransferItem` + `StockTransferCounter` + `TransferStatus` enum (DRAFT/APPROVED/IN_TRANSIT/RECEIVED/CANCELLED, `transferstatus` DB enum) in `backend/app/models/stock_transfer.py`; check constraints: distinct source/destination warehouse, `quantity > 0`, `0 <= received_quantity <= quantity`; registered in `models/__init__.py`. `inventory_levels.in_transit` swing column (Numeric, NOT NULL default 0, check `>= 0`) in `backend/app/models/inventory.py`.
- Gapless line numbering `ST-YYYY-0001` — `backend/app/services/transfer_number.py` (`TransferNumberService`, SELECT FOR UPDATE + IntegrityError first-insert race retry, mirrors DnNumberService).
- Alembic `c6b3e7a9d2f0_add_stock_transfers.py` (down_revision `b2a4d6f8e1c0`) creates `stock_transfers` + `stock_transfer_items` + `stock_transfer_counters`, adds `in_transit`; verified via downgrade → upgrade round-trip; `alembic check` clean. Note: the three lifecycle timestamps must be `sa.DateTime(timezone=True)` to match the SQLModel tz-aware columns.

### Dispatch / Receive / Cancel accounting

- **Dispatch** (APPROVED→IN_TRANSIT): per item, source `on_hand -= qty`, that level's `in_transit += qty`; writes a TRANSFER ledger `-qty` (source_bin set). Fails 400 if the item's source bin has insufficient `available()`.
- **Receive** (IN_TRANSIT→RECEIVED): per item, source level `in_transit -= dispatched` (the full dispatched qty, so a partial receipt leaves the in-transit window for the discrepancy); destination `on_hand += received`; writes a TRANSFER ledger `+received` (dest bin set); line `received_quantity` records the partial/discrepancy.
- **Cancel** (DRAFT/APPROVED free; IN_TRANSIT→CANCELLED): IN_TRANSIT returns source `on_hand += qty`, source `in_transit -= qty`, and writes a balancing `TRANSFER_RETURN` ledger `+qty`; requires `cancellation_reason`. RECEIVED/CANCELLED cannot be cancelled.

### Also

- Schemas — `backend/app/schemas/stock_transfer.py`: `StockTransferCreate` (min 1 item), `TransferItemCreate` (default bin resolution SKU-compatible), `TransferReceiveRequest` (per-line `received_quantity`), `TransferCancelRequest` (`extra=forbid`), `StockTransferResponse`/`StockTransferListItem` with `remaining`.
- Service — `backend/app/services/stock_transfer_service.py`: `create_transfer`, `approve_transfer`, `dispatch_transfer`, `receive_transfer`, `cancel_transfer`, `get_visible`, `serialize`/`serialize_list_item`. Deliberately does **not** set `header.items` on a pending header (avoid lazy-load `MissingGreenlet`); items added directly and header reloaded via `get_visible`.
- Router — `backend/app/routers/inventory.py`: `POST /inventory/transfers` (201), `GET /inventory/transfers` (paginated; `status`/`source_warehouse_id`/`destination_warehouse_id` filters), `GET /inventory/transfers/{id}`, `POST /inventory/transfers/{id}/approve|/dispatch|/receive|/cancel`. `InventoryLevelResponse` gained `in_transit`.
- Tests — `backend/tests/test_stock_transfers.py` (8 tests): create (draft, `ST-` gapless number, default bin resolving), dispatch + TRANSFER ledger + source available drop, insufficient source 400, full receive (dest on_hand +, source in_transit cleared, ledger +), partial receive discrepancy, cancel rules + state-machine guards (dispatch-before-approve 400, double approve 400), multi-tenant isolation, pagination/validation. Updated 3 alembic-head guard tests to `c6b3e7a9d2f0`.

### Pytest (PostgreSQL `_test`) + lint

- `tests/test_stock_transfers.py`: **8 passed** (together with reservations + delivery-notes modules: 29 passed)
- Full suite: **246 passed, 0 failed** (was 238; 5m33s)
- `alembic heads`: **`c6b3e7a9d2f0`**; `alembic check`: clean. ruff clean; black clean on non-migration touched files (migrations keep alembic style).

---

## 2026-09-06 — Wave 19b: Stock Counting / Reconciliation (Phase 3 sub-feature 3)

**Spec:** `architecture/wave-stock-counting-addendum.md`. Scheduling a count snapshots expected quantities from each `InventoryLevel.on_hand` per bin (includes reserved/damaged; `in_transit` excluded), counting records physical results per line, and reconciliation adjusts `on_hand` by the variance once a manager approves flagged lines. Only `on_hand` is ever touched.

### Done

- Models `StockCount` + `StockCountItem` + `StockCountCounter` + `StockCountStatus` enum (SCHEDULED/IN_PROGRESS/COMPLETED/RECONCILED/CANCELLED, `stockcountstatus` DB enum) in `backend/app/models/stock_count.py`; line check constraints `expected_quantity >= 0`, `counted_quantity >= 0`, unique `(count_id, product_id, bin_id)`; tz-aware lifecycle timestamps; registered in `models/__init__.py`.
- Gapless line numbering `SC-YYYY-0001` — `backend/app/services/stock_count_number.py` (`StockCountNumberService`, SELECT FOR UPDATE + IntegrityError first-insert race retry, mirrors DnNumberService).
- Alembic `e1f5b8a2c3d4_add_stock_counts.py` (down_revision `c6b3e7a9d2f0`) creates `stock_counts` + `stock_count_items` + `stock_count_counters`; applied via `alembic upgrade head`; downgrade → upgrade round-trip verified; `alembic check` clean.

### Accounting

- **Create**: snapshots `expected_quantity = on_hand` for every level in the warehouse (empty bins with a level still get a line). No stock movement.
- **Variance** = counted − expected. `COUNT_TOLERANCE_PERCENT = 2.00`; `needs_approval` uses a multiplication compare (`abs(variance) * 100 > expected * 2.00`, no floats/division) so exact-zero and at-tolerance lines pass; `expected == 0` with variance != 0 → flagged. Computed at complete.
- **Reconcile** (COMPLETED only): blocks while any flagged line is unapproved; then per line applies `level.on_hand += variance` (via `lock_or_create_level`) and writes one ADJUSTMENT ledger row per changed line — `reference_type="COUNT"`, `reference_id=count.id`, `reason="COUNT_CORRECTION"`, `notes="<count_number> variance"`, `source_bin_id` for negative variance / `destination_bin_id` for positive. Reserved/damaged/in_transit untouched.

### Also

- Schemas — `backend/app/schemas/stock_count.py`: `StockCountCreate`, `CountRecordRequest` (`extra=forbid`, non-negative `counted_quantity`), `StockCountItemResponse` with `variance`, `StockCountResponse`, `StockCountListItem` with `item_count`/`count_in_progress`/`flagged_lines`.
- Service — `backend/app/services/stock_count_service.py`: `create_count`, `record_count` (SCHEDULED→IN_PROGRESS, sets `started_at`), `complete_count` (400 if any uncounted line), `approve_count`, `reconcile_count`, `cancel_count` (SCHEDULED/IN_PROGRESS only, no stock movement), `get_visible`, `serialize`/`serialize_list_item`. OWNER/ADMIN gate on every mutation (`_require_manager`), GET open to members.
- Router — `backend/app/routers/inventory.py`: `POST /inventory/counts` (201), `GET /inventory/counts` (paginated; `status`/`warehouse_id` filters), `GET /inventory/counts/{count_id}`, `POST /inventory/counts/{count_id}/record|/complete|/approve|/reconcile|/cancel`. Routes declared after `/levels`/`/warehouses`; no collision.
- Tests — `backend/tests/test_stock_counts.py` (9 tests): create + gapless `SC-` numbering + snapshot + multi-tenant ghost-warehouse 404, record/complete lifecycle with uncounted-line 400 + negative 422, tolerance/`needs_approval` unit matrix + flagging at complete, reconcile applies `on_hand` deltas + ADJUSTMENT/COUNT ledger + approve-before-reconcile 400, zero-expected (drained source via transfer dispatch) flagged + reconciled, cancel rules + terminal-state guards, MEMBER 403 vs GET 200, cross-workspace 404 isolation, pagination + filters + bad-status 422. Updated the 3 alembic-head guard tests: `test_pdc.py`/`test_pricing.py` pinned to `e1f5b8a2c3d4`; `test_product_electrical_specs.py` rewritten to walk the head→root lineage dynamically (survives quote-style differences and future waves instead of pinning a head).

### Note (recovery incident)

A PowerShell inline `python -c` file-rewrite truncated `tests/test_pdc.py`, `tests/test_pricing.py`, `tests/test_product_electrical_specs.py` to 0 bytes. Restored via `git checkout --` (HEAD predates Wave 18/19 pin bumps) and re-pinned the head assertions to `e1f5b8a2c3d4`. Lesson: never use inline `python -c` with PowerShell quoting to edit files — use the edit tool.

### Pytest (PostgreSQL `_test`) + lint

- `tests/test_stock_counts.py`: **9 passed**; restored guard modules (`test_pdc.py`, `test_pricing.py`, `test_product_electrical_specs.py`): **41 passed**
- Full suite: **255 passed, 0 failed** (was 246; 6m01s)
- `alembic heads`: **`e1f5b8a2c3d4`**; `alembic check`: clean. ruff clean; black clean on non-migration touched files (migrations keep alembic style).

---

## 2026-09-06 — M-5: gapless PR/RFQ/GRN numbering (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` finding M-5. Count-based (`len(all rows)+1`) PR/RFQ/GRN numbers were unsafe under concurrency (duplicate-key 500s). Replaced with the established `InvoiceCounter`/`SPOCounter` pattern.

### Done

- New counter models `PRCounter`/`RFQCounter`/`GRNCounter` (`pr_counters`/`rfq_counters`/`grn_counters`, composite PK workspace_id+year) — `backend/app/models/pr_counter.py`, `rfq_counter.py`, `grn_counter.py`, registered in `models/__init__.py`.
- New `PRNumberService`/`RFQNumberService`/`GRNNumberService` — SELECT FOR UPDATE + IntegrityError first-insert race retry (mirrors `EnquiryNumberService`) — `backend/app/services/pr_number.py`, `rfq_number.py`, `grn_number.py`.
- Wiring: `POST /procurement/requests` (`procurement.py`), `POST /rfq/requests` (`rfq.py`), `GRNService.create_draft_grn` (`grn_service.py`; removed `_generate_grn_number`).
- Both routers now hoist `import time` mid-function (resolves the E402 half of M-7) and capture `user.id` **before** the counter service, because the service's `session.rollback()` on the first-insert race expires ORM objects — accessing them after would raise `MissingGreenlet`.
- Alembic `9f3a2c1e5d84_add_gapless_pr_rfq_grn_counters.py` (down_revision `c624e2ac4f47`) creates the 3 counter tables; applied via `alembic upgrade head`.
- Tests: added concurrent PR/RFQ/GRN creation (10 threads each, sequential gapless assertions) to `tests/test_concurrent_numbering.py`; updated the 3 alembic-head guard tests to new head `9f3a2c1e5d84` (`test_pdc.py`, `test_pricing.py`, `test_product_electrical_specs.py`).

### Pytest (PostgreSQL `_test`)

- `tests/test_concurrent_numbering.py`: **7 passed** (was 4)
- Full suite: **228 passed, 0 failed** (5m04s)
- `alembic heads`: **`9f3a2c1e5d84`**; `alembic check`: clean. ruff clean; black clean on non-migration touched files (migrations keep alembic style).

---

## 2026-09-06 — F-2: backend test suite fixed (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` finding F-2. Suite was red with 4 failures.

### Done

- `tests/test_ar_statement_tdn.py`: rewritten with its own sync engine / `TestingSessionLocal` / `override_get_session` + module-scoped autouse `setup_database` (drop_all/create_all); fixed stale route `tax-debit-notes` → `/api/v1/debit-notes`; fixed `reason: PRICE_UPDATE` → `PRICE_INCREASE`. Black-formatted.
- Alembic-head guard tests pinned to current head `c624e2ac4f47`: `test_pdc.py`, `test_pricing.py`, `test_product_electrical_specs.py`.

### Pytest (PostgreSQL `_test`)

- Full suite: **228 passed, 0 failed** (was 224 passed, 4 failed). ruff + black clean.

---

## 2026-09-06 — M-10: leftover root test scripts deleted (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` finding M-10.

- Deleted `backend/test_e2e.py`, `backend/test_step2_api.py`, `backend/test_step2_production.py` (outside `tests/`; `pytest.ini` `testpaths=tests` already excluded them — no test loss). Only remaining references are `graphifyy/cache/ast/*.json` AST caches.

---

## 2026-09-06 — M-1 + M-2: secret guard + configurable CORS (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` findings M-1 and M-2.

### Done

- `backend/app/config.py`: added `DEFAULT_SECRET_KEY` / `DEFAULT_CORS_ORIGINS`, `CORS_ORIGINS: list[str]` field (JSON env var), and a `@model_validator(mode="after")` that raises `RuntimeError` if `ENVIRONMENT == "production"` and `SECRET_KEY` is still the default.
- `backend/app/main.py`: CORS middleware now uses `settings.CORS_ORIGINS`.
- `backend/app/routers/health.py`: hoisted `HTTPException` import (E402).
- `backend/.env.example`: added commented `CORS_ORIGINS` JSON example.
- CI unaffected (already sets `SECRET_KEY: ci-test-secret-key-not-for-production`).

---

## 2026-09-01 — WP-A Bilingual PDF assets pytest (planned BEFORE code)

**Spec:** `architecture/wave-bilingual-pdf-addendum.md` §7. Filesystem only; no DB; never SQLite. **No Alembic.** No git commit. No routers/schemas/models.

### Locked

- New `backend/tests/test_bilingual_pdf_assets.py` covering font size/magic, OFL text, `pdfTitles.ts` six EN+AR, `pdfFonts.ts` local register (no CDN/`http://`), models have no `name_ar`/`address_ar`, alembic versions still contain `b8d5f0c3a216_add_credit_notes.py` and no `*_bilingual*` / `*_name_ar*` revision.
- Repo root = parent of `backend/`. No PostgreSQL fixtures.

---

## 2026-09-01 — WP-A Bilingual PDF assets pytest (implemented)

**Spec:** `architecture/wave-bilingual-pdf-addendum.md` §7. Filesystem only; no DB; never SQLite. **No Alembic.** No git commit.

### Files

- `backend/tests/test_bilingual_pdf_assets.py` — addendum §7

### Pytest (filesystem; no PostgreSQL)

- `tests/test_bilingual_pdf_assets.py`: **6 passed**, 0 failed (0.02s)
- `alembic heads`: **`b8d5f0c3a216`**

Font file: `NotoNaskhArabic-Regular.ttf` **247336** bytes (TTF magic `\x00\x01\x00\x00`). No models/Alembic edits.

---

## 2026-09-01 — WP-A Volume / customer pricing (implemented)

**Spec:** `architecture/wave-volume-pricing-addendum.md` WP-A. Architect note: `.agents/reports/architect-volume-pricing-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Done

- `PricingService.resolve` loads live product/client (404 cross-tenant), rejects qty ≤ 0 (422 `field=quantity`), ignores non-AED rows, then CUSTOMER_SPECIFIC for **this** client (highest qualifying min) → TIER_1 `client_id IS NULL` → DEFAULT_SALES → 422 `NO_LIST_PRICE`. `resolve` does not 400 inactive SKUs.
- `_line_unit_price` / `_resolve_line` take document `client_id`. Explicit `unit_price` still wins. Omit-price catalog lines call `PricingService.resolve`. Quote convert / LPO→invoice keep passing frozen `unit_price` (no re-resolve).
- Preview `GET /api/v1/products/{id}/resolved-price?client_id=&quantity=` returns one winning price + `price_type`. Inactive product → 400 `field=product_id`. Isolation → 404. `list_prices` unchanged.
- Tests: `backend/tests/test_pricing.py` (§9) + workspace B `resolved-price` 404 in `test_multi_tenant_isolation.py`.

### Files

- `backend/app/services/pricing_service.py` — new
- `backend/app/schemas/products.py` — `ResolvedPriceResponse`
- `backend/app/routers/products.py` — preview GET next to `/prices`
- `backend/app/services/invoice_service.py` — hook
- `backend/app/services/quotation_support.py` — pass `quotation.client_id`
- `backend/app/services/customer_po_support.py` — pass `lpo.client_id`
- `backend/app/services/__init__.py` — export
- `backend/tests/test_pricing.py` — addendum §9
- `backend/tests/test_multi_tenant_isolation.py` — resolved-price 404

### Endpoint

| Method | Path | Result |
|---|---|---|
| GET | `/api/v1/products/{product_id}/resolved-price` | one `{unit_price, price_type, min_quantity, price_id}`; quantity required; client_id optional |

### Pytest (PostgreSQL `_test`)

- `tests/test_pricing.py`: **13 passed**
- Sanity (catalog copy, inactive 400, convert freeze, LPO invoice, product isolation): **7 passed**
- Combined this slice: **20 passed**, 0 failed

`alembic heads`: **`b8d5f0c3a216`**. `alembic check`: No new upgrade operations detected. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A Volume / customer pricing (planned BEFORE code)

**Spec:** `architecture/wave-volume-pricing-addendum.md` WP-A. Architect note: `.agents/reports/architect-volume-pricing-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Locked

- Alembic **NO**. HEAD stays **`b8d5f0c3a216`**. No new columns. No `price_source` on lines. No `TIER_2`. Do not edit `models/product.py`.
- New `backend/app/services/pricing_service.py`: `resolve(session, workspace_id, product_id, client_id, quantity) -> ResolvedPrice` with `unit_price=money()`, `price_type`, `min_quantity`, `price_id`.
- Precedence: CUSTOMER_SPECIFIC for **this** client (qty ≥ min, null min=0, highest min) → TIER_1 `client_id IS NULL` (same) → DEFAULT_SALES → 422 `NO_LIST_PRICE` `field=product_id`.
- Never apply another client’s CUSTOMER_SPECIFIC. Skip customer bucket if `client_id` is None. Cross-tenant product/client → **404** not 403.
- Inactive: `resolve` itself does not 400; document add still 400 via `_load_invoice_product`; **preview GET does 400**.
- quantity ≤ 0 → 422 `field=quantity`. AED only (ignore non-AED debris). Explicit `unit_price` always wins. Ad-hoc without `product_id` still requires `unit_price`.
- Hook: pass document `client_id` into `_resolve_line` / `_line_unit_price` from invoice/quotation/LPO. Replace omit-price `_default_sales_price` with `PricingService.resolve`. Convert / LPO→invoice / CN / send / DN: do not call resolve.
- Preview **WP-A required:** `GET /api/v1/products/{id}/resolved-price?client_id=&quantity=`. Quantity required; client_id optional. One price + `price_type`. No other client ids in data. Isolation 404. Inactive 400.
- `ProductService.list_prices` **unchanged** (staff dealer book). Price CRUD uniqueness stays in ProductService.

### Files (planned)

- `backend/app/services/pricing_service.py` — new resolve/preview
- `backend/app/schemas/products.py` — `ResolvedPriceResponse`
- `backend/app/routers/products.py` — preview GET next to `/prices`
- `backend/app/services/invoice_service.py` — hook `_line_unit_price` / `_resolve_line`
- `backend/app/services/quotation_support.py` — pass `quotation.client_id`
- `backend/app/services/customer_po_support.py` — pass `lpo.client_id`
- `backend/tests/test_pricing.py` — addendum §9
- `backend/tests/test_multi_tenant_isolation.py` — workspace B resolved-price 404

---

## 2026-09-01 — WP-A Payment / PDC truth + bounce (implemented)

**Spec:** `architecture/wave-pdc-addendum.md` WP-A. Architect note: `.agents/reports/architect-pdc-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Done

- `PaymentService.record_payment`: `method=PDC` always inserts `PENDING` + `RECEIVED` (today/past included), ignores body `pdc_status`, requires `pdc_date` (422 `field=pdc_date`). Does not reduce `balance_due` or flip PAID. CASH/BANK/CARD/CHEQUE stay SUCCESS. CHEQUE ignores `pdc_date`. HOLD never blocks POST. Overpay still 400 `PAYMENT_EXCEEDS_BALANCE` via `raise_error`. Date default `utc_today()`.
- PUT `/invoices/{id}/payments/{id}` → 405 `METHOD_NOT_ALLOWED` after workspace invoice 404.
- Four POSTs: `.../pdc/deposit|clear|bounce|return`. OWNER/ADMIN; MEMBER 403 `INSUFFICIENT_PERMISSIONS`. Isolation 404. SELECT FOR UPDATE invoice then payment. Amount/method/dates never rewritten. Bounce → FAILED + `evaluate(..., PAYMENT)`. Clear reuses `InvoiceService.calculate_balance_due` / `update_status_from_payments`. Over-clear 400, no `credit_balance` park. Historical SUCCESS PDC: clear 200 no-op, bounce 403.
- AR statement math unchanged. `test_success_pdc_in_paid` now deposit+clear so SUCCESS PDC still lists as Payment.

### Files

- `backend/app/schemas/common.py` — `METHOD_NOT_ALLOWED`
- `backend/app/schemas/payments.py` — `PdcActionRequest`
- `backend/app/services/payment_service.py` — PDC insert path
- `backend/app/services/pdc_service.py` — four transitions
- `backend/app/routers/payments.py` — PUT 405 + four POSTs
- `backend/app/services/__init__.py` — export `PdcService`
- `backend/tests/test_pdc.py` — addendum §12 (17 tests)
- `backend/tests/test_ar_statement.py` — `test_success_pdc_in_paid`

### Endpoints

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/invoices/{id}/payments` | PDC→PENDING+RECEIVED; still Idempotency-Key |
| PUT | `/api/v1/invoices/{id}/payments/{id}` | 405 (404 if invoice not in workspace) |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/deposit` | RECEIVED→DEPOSITED |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/clear` | DEPOSITED→CLEARED/SUCCESS |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/bounce` | DEPOSITED→BOUNCED/FAILED |
| POST | `/api/v1/invoices/{id}/payments/{id}/pdc/return` | RECEIVED→RETURNED/CANCELLED |

### ErrorCodes added

- `METHOD_NOT_ALLOWED` (405)

Existing reused: `VALIDATION_ERROR`, `PAYMENT_EXCEEDS_BALANCE`, `INVALID_STATE`, `INSUFFICIENT_PERMISSIONS`, `NOT_FOUND`.

### Pytest (PostgreSQL `_test`)

- `tests/test_pdc.py`: **17 passed**
- `tests/test_ar_statement.py`: **13 passed**
- Combined: **30 passed**, 0 failed
- Related overpay/HOLD/isolation: 4 passed

`alembic heads`: **`b8d5f0c3a216`**. `alembic check`: No new upgrade operations detected. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A Payment / PDC truth + bounce (planned BEFORE code)

**Spec:** `architecture/wave-pdc-addendum.md` WP-A. Architect note: `.agents/reports/architect-pdc-note.md`. Backend + pytest only. No UI/Playwright. **No Alembic.** No git commit. No database report.

### Locked

- Alembic **NO**. HEAD stays **`b8d5f0c3a216`**. No new columns/tables. Later WPs `down_revision = "b8d5f0c3a216"` until HEAD moves.
- `method=PDC`: require `pdc_date` (422 `VALIDATION_ERROR` `field=pdc_date`). Insert **always** `PENDING` + `RECEIVED` (today/past included). Ignore body `pdc_status`. Does **not** reduce `balance_due`. Must **not** flip invoice PAID.
- CASH / BANK_TRANSFER / CREDIT_CARD / **CHEQUE** still immediate SUCCESS. CHEQUE is not on the PDC machine (bounce → 403 `INVALID_STATE`).
- HOLD never blocks POST payment. Bounce calls `CreditControlService.evaluate(..., PAYMENT)`. Date gates use `CreditControlService.utc_today()`, not naive `date.today()`.
- Overpay at insert: amount > `InvoiceService.calculate_balance_due` → 400 `PAYMENT_EXCEEDS_BALANCE`. PENDING does not consume the cap. `/pdc/clear` same 400; do **not** park `credit_balance`.
- Four POSTs (OWNER/ADMIN; MEMBER 403 `INSUFFICIENT_PERMISSIONS`): `POST /api/v1/invoices/{invoice_id}/payments/{payment_id}/pdc/deposit|clear|bounce|return`. Empty body. No Idempotency-Key. Idempotent 200 if already in target. Rate-limit 10/minute.
- RECEIVED→DEPOSITED if `pdc_date <= utc_today()` else 400 `field=pdc_date`. Stays PENDING.
- DEPOSITED→CLEARED: status SUCCESS, FOR UPDATE invoice, `update_status_from_payments`. If amount > live `balance_due` → 400. Reuse existing balance formula.
- DEPOSITED→BOUNCED: status FAILED; amount unchanged; evaluate PAYMENT. Not PENDING.
- RECEIVED→RETURNED: CANCELLED. Return from DEPOSITED → 403 `INVALID_STATE`.
- Illegal (RECEIVED→clear, CHEQUE→bounce, CLEARED→bounce, etc.) → **403 INVALID_STATE** (not 409).
- Historical SUCCESS PDC: leave rows; `/pdc/clear` 200 no-op; bounce 403.
- PUT `/invoices/{id}/payments/{id}` → **405 METHOD_NOT_ALLOWED** (add ErrorCode). Other-workspace invoice → **404** first, never 405.
- Isolation: missing invoice/payment or other workspace → **404 NOT_FOUND**, never 403. Load invoice by id+workspace then payment by id+invoice_id.
- SELECT FOR UPDATE invoice **and** payment on transitions. Amount/method/payment_date/pdc_date never UPDATE. No DELETE route. POST create still requires Idempotency-Key.
- Errors via `raise_error` / `ErrorCode` (wrapper `{success,false,error}`). AR statement math **not** forked; patch `test_success_pdc_in_paid`.

### Files (planned)

- `backend/app/schemas/common.py` — `METHOD_NOT_ALLOWED`
- `backend/app/schemas/payments.py` — empty `PdcActionRequest` (`extra=forbid`)
- `backend/app/services/payment_service.py` — PDC insert PENDING+RECEIVED
- `backend/app/services/pdc_service.py` — four transitions
- `backend/app/routers/payments.py` — PUT 405 + four POSTs
- `backend/app/services/__init__.py` — export `PdcService`
- `backend/tests/test_pdc.py` — addendum §12 (17 bullets)
- `backend/tests/test_ar_statement.py` — `test_success_pdc_in_paid`

### Out

Frontend, Playwright, Alembic, git commit, volume pricing, bilingual, debit notes, CLEARED→BOUNCED, rewriting historical SUCCESS PDC, parking over-clear into `credit_balance`.

---

## 2026-09-01 — WP-A AR aging + Account Statement API (implemented)

**Spec:** `architecture/wave-ar-statement-addendum.md` WP-A. No UI/PDF/Playwright. **No Alembic.** No git commit.

### Done

- Generated `GET /api/v1/clients/{client_id}/ar-statement?from=&to=&as_of=` over live invoices / SUCCESS payments / ISSUED CNs / `clients.credit_balance`. Read-only: no INSERT/UPDATE/DELETE on those rows.
- Reuses `CreditControlService.open_ar_invoices` + `aging_buckets`. `amount_due_now` = exposure. `credit_balance` parked, not in buckets or `totals.paid`. `as_of=today` buckets match GET `/clients/{id}/credit`.
- Isolation **404** `NOT_FOUND` (never 403). CREDIT_HOLD does not block. OWNER/ADMIN/MEMBER via `get_current_user`.
- CN never in `totals.paid`. PENDING = Payment (pending), not cleared, not in paid. SUCCESS PDC is in paid with method PDC.
- Cap helper `assert_activity_cap` (monkeypatch `ACTIVITY_LINE_CAP` in the overflow test only).

### Files

- `backend/app/schemas/ar_statements.py`
- `backend/app/services/ar_statement_service.py`
- `backend/app/routers/clients.py` — GET on clients router (file stays well under 500 lines)
- `backend/app/schemas/common.py` — `DATE_RANGE_TOO_LONG`, `STATEMENT_TOO_LARGE`
- `backend/app/services/__init__.py`
- `backend/tests/test_ar_statement.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_ar_statement.py`: **13 passed**, 0 failed

`alembic heads` / `alembic current`: **`b8d5f0c3a216`**. No new revision. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A AR aging + Account Statement API (planned BEFORE code)

**Spec:** `architecture/wave-ar-statement-addendum.md` WP-A. Architect note: `.agents/reports/architect-ar-statement-note.md`. Backend + pytest only. No UI/PDF/Playwright. **No Alembic.** No git commit.

### Locked

- Generated GET only: live invoices + SUCCESS payments + ISSUED CNs + `clients.credit_balance`. No `ar_statements` table, no new columns. HEAD stays **`b8d5f0c3a216`**.
- `GET /api/v1/clients/{client_id}/ar-statement?from=&to=&as_of=`. `from`/`to` required. `as_of` optional, default UTC today. `as_of` after today → 422. `from > to` → 422. `(to-from).days > 366` → 422 `DATE_RANGE_TOO_LONG`. Activity lines (excl. opening) > 2000 → 400 `STATEMENT_TOO_LARGE`.
- Isolation: other-workspace client → **404** `NOT_FOUND`, never 403. CREDIT_HOLD does not block. Roles: OWNER/ADMIN/MEMBER via `get_current_user` (same as GET client / GET credit).
- Reuse `CreditControlService.open_ar_invoices` + `aging_buckets`. Do not fork buckets. `as_of=today` buckets must equal GET `/clients/{id}/credit`. `amount_due_now` = exposure. `credit_balance` parked, not a bucket, not in `totals.paid`.
- Include-set S: `deleted_at` null, status SENT/PARTIALLY_PAID/PAID/OVERDUE. Exclude DRAFT/CANCELLED invoices (+ their payments/CNs), DRAFT CNs, quotes/LPO/DN, FAILED/CANCELLED/REFUNDED payments.
- CN amounts never in `totals.paid`. PENDING not in paid (`cleared_cash` false). SUCCESS PDC **is** in `totals.paid`; method PDC; not labelled Tax Credit Note.
- GET is read-only: do not mutate invoices, payments, CNs, or `credit_balance`. No server PDF. No pagination. Do not change GET `/clients/{id}/credit`. Do not add PDC bounce/clear/deposit. Do not change `record_payment`.
- `doc_type` + exact `doc_type_label` from addendum §7.1. Sort: opening first; date ASC; TAX_INVOICE, PAYMENT, PAYMENT_PENDING, TAX_CREDIT_NOTE; number ASC. All money via `money()` ROUND_HALF_UP.

### Files (planned)

- `backend/app/schemas/ar_statements.py`
- `backend/app/services/ar_statement_service.py`
- `backend/app/routers/clients.py` (GET on clients router; file stays well under 500 lines)
- `backend/app/schemas/common.py` — `DATE_RANGE_TOO_LONG`, `STATEMENT_TOO_LARGE`
- `backend/app/services/__init__.py`
- `backend/tests/test_ar_statement.py` — addendum §10, PostgreSQL `_test`

### Out

Frontend, Playwright, Alembic, git commit, PDC truth, bilingual, debit notes, invoice-list `amount_credited`, dashboard overdue.

---

## 2026-09-01 — WP-A W2 GET /invoices/{id}/balance credits-as-cash (implemented)

**Nit:** W2 in `.agents/reports/wp-a-credit-notes-review.md`. Backend only. No Alembic rewrite. No git commit.

### Done

- `GET /invoices/{id}/balance` no longer sets `total_paid = total − balance_due` (that treated issued CNs as cash).
- Response now exposes `amount_paid` (SUCCESS payments only) and `amount_credited` separately.
- `total_paid` is cash-only (same as `amount_paid`).
- `balance_due` stays `max(0, total − paid − credited)` via `InvoiceService.calculate_balance_due`.
- Pytest: unpaid CN → `total_paid`/`amount_paid` stay 0; partial payment + CN → `total_paid` equals cash, not cash+credit.

### Files

- `backend/app/schemas/payments.py` — `BalanceDueResponse` + `amount_paid` / `amount_credited`
- `backend/app/routers/payments.py` — `_balance_payload`
- `backend/tests/test_credit_notes.py` — `_get_balance`; unpaid GET `/balance` asserts; `test_balance_endpoint_does_not_treat_credits_as_paid`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_notes.py`: **14 passed**
- `tests/test_invoices.py`: **25 passed**
- Combined: **39 passed, 0 failed**

black + ruff clean on touched files.

---

## 2026-09-01 — WP-A W2 GET /invoices/{id}/balance credits-as-cash (planned BEFORE code)

**Nit:** W2 in `.agents/reports/wp-a-credit-notes-review.md`. Backend only. No Alembic rewrite. No git commit.

### Locked

- `GET /invoices/{id}/balance` must not treat credit notes as cash.
- Expose `amount_paid` (SUCCESS payments only) and `amount_credited` separately.
- Keep `total_paid` as cash received: same as `amount_paid`, never `total_amount − balance_due`.
- `balance_due` stays `max(0, total − paid − credited)`.
- Pytest: after an issued CN, `total_paid` / `amount_paid` are not inflated by the credited amount.
- Files: `backend/app/schemas/payments.py`, `backend/app/routers/payments.py`, `backend/tests/test_credit_notes.py`.

---

## 2026-09-01 — WP-A Tax Credit Notes API (planned BEFORE code)

**Spec:** `architecture/wave-credit-notes-addendum.md` WP-A. Architect note: `.agents/reports/architect-credit-notes-note.md`. No UI/PDF/Playwright. No git commit.

### Locked

- `CreditNoteNumberService` SELECT FOR UPDATE `CN-YYYY-XXXX` on `credit_note_counters` at create. Gapless. Soft-delete does not rewind.
- Parent invoice SENT/PARTIALLY_PAID/PAID/OVERDUE only. DRAFT/CANCELLED → 403 `INVALID_STATE`. Other workspace → 404.
- Lines ≥ 1, each `invoice_item_id`. Qty ≤ remaining vs ISSUED CNs. Frozen `unit_price`/`tax_rate`/discounts (mismatch 422). Header total ≤ `invoice.total − Σ ISSUED CN.total` else 400 `CREDIT_EXCEEDS_REMAINING` `field=total_amount`. Same `money()`.
- DRAFT → ISSUED posts AR. No `/apply`. No PUT/DELETE after ISSUED. Soft-delete DRAFT only. Issue idempotent 200. SELECT FOR UPDATE CN + invoice.
- `balance_due = money(max(0, total − paid − credited))`. Never mutate payment rows or invoice line money.
- Unpaid/partial: shrink due; PAID if remainder covered. PAID + CN: stay PAID; increment `clients.credit_balance` by this CN’s over-credit. No auto-apply.
- Issue never `CREDIT_HOLD`. Re-evaluate after issue. Create/PUT never blocked.
- FTA snapshots on issue from invoice snapshots (live fallback like send, no FTA hard-fail).
- Tests: `backend/tests/test_credit_notes.py` §10 + invoices/payments/credit_control regression. PostgreSQL `_test`.

### Files (planned)

- `backend/app/models/credit_note_counter.py`, `credit_note.py`, `credit_note_item.py`, `credit_note_event.py`
- `backend/alembic/versions/b8d5f0c3a216_add_credit_notes.py` (`down_revision = "a7c4e9d2b105"`)
- `backend/app/services/credit_note_number.py`, `credit_note_support.py`, `credit_note_service.py`
- `backend/app/schemas/credit_notes.py`, `routers/credit_notes.py`, `main.py`
- Invoice/client/payment hooks: `invoice.py`, `invoice_event.py`, `invoice_service.py`, `schemas/invoices.py`, `client.py`, `schemas/clients.py`, `credit_control_service.py`
- `backend/tests/test_credit_notes.py`

---

## 2026-09-01 — WP-A Tax Credit Notes API (implemented)

**Spec:** addendum WP-A. No UI/PDF/Playwright. No git commit.

### Done

- `CreditNoteNumberService` SELECT FOR UPDATE `CN-YYYY-XXXX` via `credit_note_counters` (savepoint on first-year insert race). Soft-delete does not rewind.
- Parent SENT/PARTIALLY_PAID/PAID/OVERDUE only. DRAFT/CANCELLED → 403. Other workspace → 404.
- Frozen invoice-line money; omit `tax_rate` copies invoice 5%. Qty > remaining → 400. Header > remaining → 400 `CREDIT_EXCEEDS_REMAINING`. Extra keys 422.
- DRAFT → ISSUED posts AR (`amount_credited`, `balance_due = max(0, total − paid − credited)`). Idempotent issue 200. PUT/DELETE ISSUED → 403. No `/apply`.
- PAID + CN stays PAID; over-credit increments `clients.credit_balance`. Payments never updated/deleted. Issue never `CREDIT_HOLD`.
- FTA snapshots copied on issue from invoice (live fallback, no FTA hard-fail).

### Files

- models: `credit_note_counter.py`, `credit_note.py`, `credit_note_item.py`, `credit_note_event.py` + invoice/client/invoice_event/user
- `backend/alembic/versions/b8d5f0c3a216_add_credit_notes.py`
- `credit_note_number.py`, `credit_note_support.py`, `credit_note_service.py`
- `schemas/credit_notes.py`, `routers/credit_notes.py`, `main.py`
- `invoice_service.py` balance/status, `credit_control_service.py` aging `credit_balance`
- `backend/tests/test_credit_notes.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_notes.py`: **13 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_credit_control.py`: **17 passed**
- Combined: **55 passed, 0 failed**

`alembic upgrade head` + `alembic check` clean. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A Delivery Notes API (planned BEFORE code)

**Spec:** `architecture/wave-delivery-notes-addendum.md` WP-A. Architect note: `.agents/reports/architect-delivery-notes-note.md`. No UI/PDF/Playwright. No git commit.

### Locked

- `DnNumberService` SELECT FOR UPDATE `DN-YYYY-XXXX` on `dn_counters`.
- XOR parent: exactly one of LPO or invoice. Both/neither 422. Over-deliver 400. LPO remaining = ordered − CONFIRMED DN qty (not invoiced). Invoice remaining = invoice qty − CONFIRMED DN qty.
- State: DRAFT → CONFIRMED (ISSUE −qty) → CANCELLED (ISSUE +qty, `reference_type=DN_CANCEL`). DRAFT soft-delete. Confirm idempotent 200. `/cancel` CONFIRMED only.
- Catalog `product_id` required to move stock; ad-hoc confirm with no ledger. Must reference parent line. Inactive product 400. Other-workspace 404.
- HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` via `CreditControlService.assert_not_hold` + `CreditEventReason.DN_CONFIRM`. Create/PUT never blocked.
- `inventory_ledger.py`: GRN-style FOR UPDATE + bin, filter `workspace_id`. Never float. Never call adjust from DN.
- Tighten `POST /inventory/adjust`: OWNER/ADMIN; reason allow-list; notes min 3; workspace 404; MEMBER 403. Keep endpoint.
- LPO GET: `quantity_delivered` / `quantity_undelivered`.
- Tests: `backend/tests/test_delivery_notes.py` §13 + GRN/inventory regression + credit HOLD confirm. PostgreSQL `_test`.

### Files (planned)

- `backend/app/models/dn_counter.py`, `delivery_note.py`, `delivery_note_item.py`, `delivery_note_event.py`
- `backend/alembic/versions/a7c4e9d2b105_add_delivery_notes.py` (`down_revision = "9f3a7c2e1d04"`)
- `backend/app/services/dn_number.py`, `inventory_ledger.py`, `delivery_note_support.py`, `delivery_note_service.py`
- `backend/app/schemas/delivery_notes.py`, `routers/delivery_notes.py`, `main.py`
- `backend/app/routers/inventory.py` + `schemas/inventory.py` adjust tighten
- `backend/tests/test_delivery_notes.py`

---

## 2026-09-01 — WP-A Delivery Notes API (implemented)

**Spec:** addendum WP-A. No UI/PDF/Playwright. No git commit.

### Done

- `DnNumberService` SELECT FOR UPDATE `DN-YYYY-XXXX` via `dn_counters` (savepoint on first-year insert race).
- XOR parent: LPO remaining = ordered − CONFIRMED DN qty (independent of `quantity_invoiced`). Invoice remaining = invoice qty − CONFIRMED DN qty. Both/neither 422. Over-deliver 400.
- DRAFT → CONFIRMED posts `ISSUE` (−qty, `reference_type=DN`). Cancel CONFIRMED posts `ISSUE` (+qty, `DN_CANCEL`) and restores `quantity_delivered`. Confirm idempotent 200. DRAFT soft-delete. DN never calls adjust.
- HOLD confirm iff `block_do_on_hold` → 400 `CREDIT_HOLD` + `DN_CONFIRM`. Create/PUT never blocked.
- `POST /inventory/adjust`: OWNER/ADMIN; reason allow-list + notes; workspace 404; MEMBER 403.
- LPO GET: `quantity_delivered` / `quantity_undelivered`.

### Files

- models: `dn_counter.py`, `delivery_note.py`, `delivery_note_item.py`, `delivery_note_event.py` + CPO item / inventory / credit enum / user
- `backend/alembic/versions/a7c4e9d2b105_add_delivery_notes.py`
- `dn_number.py`, `inventory_ledger.py`, `delivery_note_support.py`, `delivery_note_service.py`
- `schemas/delivery_notes.py`, `routers/delivery_notes.py`, `main.py`, `routers/inventory.py`
- `backend/tests/test_delivery_notes.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_delivery_notes.py`: **14 passed**
- `tests/test_grn.py`: **2 passed**
- `tests/test_credit_control.py`: **17 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_invoices.py`: **25 passed**
- Combined: **75 passed, 0 failed**

`alembic upgrade head` + `alembic check` clean. black + ruff clean on touched files.

---

## 2026-09-01 — WP-A credit nits W1/W2/W4 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-credit-control-review.md` W1, optional W2, test for FTA-valid HOLD send. Spec: `architecture/wave-credit-control-addendum.md` §6–7. Backend only. No UI. No Alembic rewrite. No git commit. Skip client-list in-memory pagination (W3).

### Bugs / nits

1. **W1 — SENT→OVERDUE not persisted on send/evaluate.** GET/list invoices flip; `mark_as_sent` always writes SENT (even when `due_date` is already yesterday). `evaluate` recomputes HOLD from due_date/balance but never calls `apply_overdue_*`. Send of a past-due tax invoice can return SENT until the next GET/list.
2. **Test gap — FTA-valid HOLD send.** Code order is FTA then `assert_not_hold`. Need an explicit test: HOLD client + valid workspace TRN/address → send 400 `CREDIT_HOLD` (not `FTA_SEND_BLOCKED`), invoice stays DRAFT.
3. **W2 (optional, few lines) — no row lock on HOLD check.** Concurrent first SENDs on COD can both see exposure 0. Addendum does not forbid `SELECT FOR UPDATE`. Lock invoice on send + client during `assert_not_hold`.

### Planned

1. After DRAFT→SENT snapshots, call `apply_overdue_invoice` so past-due + `balance_due > 0` persists OVERDUE on the send path. Never flip PAID/CANCELLED/DRAFT (`FLIP_STATUSES` only).
2. `evaluate` bulk-flips this client's SENT/PARTIALLY_PAID rows matching the overdue predicate (same as list/GET on-read) before snapshot. GET `/clients/{id}/credit` and other evaluate callers persist OVERDUE.
3. Pytest: send of already-past-due invoice returns OVERDUE; evaluate (credit GET) flips a backdated SENT row; PAID/CANCELLED still untouched; FTA-valid HOLD send is 400 CREDIT_HOLD.
4. Send: `SELECT FOR UPDATE` on the invoice row. `assert_not_hold`: `SELECT FOR UPDATE` on the client row before evaluate.

### Files

- `backend/app/services/credit_control_service.py`
- `backend/app/services/invoice_service.py`
- `backend/app/routers/invoices.py`
- `backend/tests/test_credit_control.py`
- this report

---

## 2026-09-01 — WP-A credit nits W1/W2/W4 (implemented)

**Spec:** addendum §6–7. No UI. No Alembic rewrite. No git commit. W3 client-list pagination skipped.

### Done

- `evaluate` calls `apply_overdue_client` before snapshot so GET credit / send HOLD check persist SENT/PARTIALLY_PAID → OVERDUE. Predicate unchanged: not deleted, `FLIP_STATUSES` only, `due_date < UTC today`, `balance_due > 0`. PAID/CANCELLED/DRAFT never flipped.
- `mark_as_sent` sets SENT then `apply_overdue_invoice` so a past-due send response is OVERDUE, not SENT.
- Send loads the invoice `SELECT FOR UPDATE`. `assert_not_hold` locks the client row before evaluate (W2, addendum does not forbid).
- Tests: send of yesterday-due invoice returns OVERDUE; credit evaluate flips a backdated SENT row and leaves PAID; FTA-valid HOLD send is 400 `CREDIT_HOLD` (not `FTA_SEND_BLOCKED`).

### Files

- `backend/app/services/credit_control_service.py`
- `backend/app/services/invoice_service.py`
- `backend/app/routers/invoices.py`
- `backend/tests/test_credit_control.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_control.py`: **17 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- Combined: **64 passed, 0 failed**

black + ruff clean on the touched files.

---

## 2026-09-01 — WP-A Credit HOLD / overdue API (planned BEFORE code)

**Spec:** `architecture/wave-credit-control-addendum.md` WP-A. Architect note: `.agents/reports/architect-credit-control-note.md`.

### Locked

- `CreditControlService`: exposure SUM (SENT+PARTIALLY_PAID+OVERDUE, SUCCESS payments, Decimal), evaluate HOLD/WARNING/ACTIVE, persist status+`credit_status_events`, `assert_not_hold`.
- Invoice SEND always blocked on HOLD (after FTA). LPO `/receive` blocked iff `block_po_on_hold`. DRAFT create, quote convert, payments not blocked.
- OVERDUE on-read + payment status lock: past-due partial stays OVERDUE. Never mutate PAID/CANCELLED.
- Replace quote/LPO convert hardcoded +30 with `issue_date + client.payment_terms_days`.
- `GET /clients/{id}/credit` aging JSON. `CREDIT_HOLD` is 400. Isolation 404. Extra keys 422.
- Tests: `backend/tests/test_credit_control.py` + existing invoices/payments/LPO isolation. PostgreSQL `_test`. No UI/Playwright. No git commit.

### Files (planned)

- `backend/app/models/client.py`, `credit_status_event.py`, `models/__init__.py`, `invoice.py` (composite index only)
- `backend/alembic/versions/*_add_client_credit_control.py` (`down_revision = "59084165d346"`)
- `backend/app/services/credit_control_service.py`
- invoice send + payment status + LPO receive + quote/LPO due_date
- `backend/app/schemas/clients.py`, `common.py`, `routers/clients.py`, `workspaces.py`
- `backend/tests/test_credit_control.py` (+ quotation due_date default 0)

---

## 2026-09-01 — WP-A Credit HOLD / overdue API (implemented)

**Revision:** `9f3a7c2e1d04` (`down_revision = "59084165d346"`). No UI. No git commit.

### Done

- Client credit fields + `credit_status_events`. NULL limit inherits workspace default; 0 = COD; >0 cap.
- `CreditControlService`: Decimal exposure of SENT+PARTIALLY_PAID+OVERDUE (SUCCESS payments). HOLD if exposure > effective_limit OR oldest overdue days > hold_days. WARNING never blocks. Auto both directions.
- Invoice SEND always 400 `CREDIT_HOLD` after FTA. LPO `/receive` blocked iff `block_po_on_hold`. DRAFT create, quote convert, payments allowed.
- OVERDUE on-read (GET/list) and payment recalc. Partial past-due stays OVERDUE. PAID/CANCELLED never flipped.
- Quote/LPO convert `due_date` = issue + `payment_terms_days` (default 0 → same day).
- `GET /clients/{id}/credit` aging JSON. Extra keys 422. Isolation 404.

### Files

- `backend/app/models/client.py`, `credit_status_event.py`, `invoice.py`, `models/__init__.py`
- `backend/alembic/versions/9f3a7c2e1d04_add_client_credit_control.py`
- `backend/app/services/credit_control_service.py`, `invoice_service.py`, `payment_service.py`, `customer_po_service.py`, `quotation_service.py`
- `backend/app/schemas/clients.py`, `common.py`
- `backend/app/routers/clients.py`, `invoices.py`, `workspaces.py`
- `backend/tests/test_credit_control.py`, `tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_credit_control.py`: **15 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_quotations.py`: **20 passed**
- `tests/test_customer_lpos.py`: **17 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- Combined: **82 passed, 0 failed**

`alembic check`: No new upgrade operations detected. black + ruff clean.

---

## 2026-09-01 — WP-A customer LPO nit W1 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-customer-lpo-review.md` warning **W1**. Backend only. No UI. No Alembic rewrite. No git commit.

### Bug

`_resolve_slices` compares each requested qty to the line’s remaining **before this request**. Repeating the same `customer_purchase_order_item_id` in one `POST .../invoices` body (e.g. 60 + 60 against remaining 100) both pass; `InvoiceService` writes qty 120. `recalc_invoiced` then clamps `quantity_invoiced` to ordered qty, so GET LPO looks clean while the tax invoice over-states qty. Concurrent POSTs stay serialized by LPO `SELECT FOR UPDATE` — do not weaken that.

### Planned

1. Per-request remaining accumulator in `_resolve_slices`: each occurrence of a line id consumes leftover qty. Second occurrence that exceeds leftover → **400** `VALIDATION_ERROR` `field=quantity` **before** invoice create. Lines already fully invoiced before this POST still skip (spec remaining 0).
2. Pytest: two allocations of the same `customer_purchase_order_item_id` in one POST that exceed ordered qty → 400; LPO `quantity_invoiced` cache unchanged; no invoice created.

### Files

- `backend/app/services/customer_po_service.py`
- `backend/tests/test_customer_lpos.py`

### Verification

`pytest tests/test_customer_lpos.py tests/test_quotations.py tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` on PostgreSQL `_test`. black + ruff.

---

## 2026-09-01 — WP-A customer LPO nit W1 (implemented)

Backend only. No UI. No Alembic rewrite. No git commit. Concurrent LPO `SELECT FOR UPDATE` on `/invoices` unchanged.

### Done

`_resolve_slices` keeps a per-request leftover map. Each occurrence of a line id consumes leftover qty. Qty that exceeds leftover → **400** `VALIDATION_ERROR` `field=quantity` before `InvoiceService.create_invoice`. Lines already fully invoiced before this POST still skip (spec remaining 0). Duplicate 60+60 against ordered 100 is rejected; `quantity_invoiced` cache stays 0.

### Files

- `backend/app/services/customer_po_service.py`
- `backend/tests/test_customer_lpos.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `_test`)

- `tests/test_customer_lpos.py`: **17 passed** (includes `test_duplicate_line_ids_over_invoice_400_cache_unchanged`)
- `tests/test_quotations.py`: **20 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **71 passed, 0 failed** (72.37s)

black + ruff clean.

---

## 2026-09-01 — WP-A Customer LPO API (planned BEFORE code)

**Spec:** `architecture/wave-customer-lpo-addendum.md` WP-A. Architect note: `.agents/reports/architect-customer-lpo-note.md`.

### Locked

- Router `/api/v1/customer-purchase-orders` (JWT). Convert `POST /quotations/{id}/convert-to-lpo`. No `/confirm`, no UI/PDF.
- States: DRAFT → RECEIVED → PARTIAL → INVOICED. CANCELLED from RECEIVED with zero countable invoices. DRAFT DELETE = soft-delete.
- Internal `LPO-YYYY-XXXX` via `lpo_counters` + SELECT FOR UPDATE. `customer_po_number` unique per (workspace, client) when set.
- Lines: `quantity` vs `quantity_invoiced`; remaining = ordered − SUM countable (DRAFT counts; CANCELLED/deleted do not). Over-invoice 400. Shared `line_money`.
- Quote convert ACCEPTED → DRAFT LPO frozen lines. Mutex with convert-to-invoice 409. Idempotent 200. Manual LPO without quotation_id allowed.
- `POST .../invoices` → `InvoiceService.create_invoice` DRAFT; many invoices per LPO; `quotation_id` null. FTA send waits. Recalc on void and DRAFT delete. PUT forbidden on LPO-linked invoices.
- Wrapper pagination. Extra keys 422. Decimal AED. Cross-tenant 404.
- Tests: `backend/tests/test_customer_lpos.py` + quotation convert mutex. PostgreSQL `_test`.

### Out

WP-B UI/PDF, WP-C Playwright, OCR, credit HOLD, delivery notes, SPO/GRN changes.

---

## 2026-09-01 — WP-A Customer LPO API (implemented)

**Revision:** `59084165d346` (`down_revision = "cb01b6bef962"`). Partial invoices use `InvoiceService.create_invoice`. Shared `line_money`. FTA send stays on invoice `/send`. No UI/PDF. No git commit.

### Done

- Models + Alembic: `lpo_counters`, `customer_purchase_orders`, `customer_purchase_order_items`, `customer_purchase_order_events`, `invoices.customer_purchase_order_id` (indexed, not unique), `invoice_items.customer_purchase_order_item_id`. Unique `customer_purchase_orders.quotation_id`. Partial unique customer PO number per client.
- Number `LPO-YYYY-XXXX` via `LpoNumberService` SELECT FOR UPDATE. Prefix LPO- not CPO-.
- States: DRAFT → RECEIVED (`/receive`) → PARTIAL → INVOICED. CANCELLED from RECEIVED with zero countable invoices. DRAFT soft-delete. Recalc on invoice create/void/DRAFT delete.
- Quote `POST /quotations/{id}/convert-to-lpo` ACCEPTED → DRAFT LPO, frozen lines, quote CONVERTED. Idempotent 200. Mutex 409 with convert-to-invoice.
- `POST /customer-purchase-orders/{id}/invoices` → many DRAFT invoices, `quotation_id` null. Over-invoice 400. PUT on LPO-linked invoices 403.
- Router mounted at `/api/v1/customer-purchase-orders`. JWT, wrapper pagination, extra keys 422, AED, cross-tenant 404.

### Files

- `backend/app/models/lpo_counter.py`
- `backend/app/models/customer_purchase_order.py`
- `backend/app/models/customer_purchase_order_item.py`
- `backend/app/models/customer_purchase_order_event.py`
- `backend/app/schemas/customer_purchase_orders.py`
- `backend/app/services/lpo_number.py`
- `backend/app/services/customer_po_support.py`
- `backend/app/services/customer_po_service.py`
- `backend/app/routers/customer_purchase_orders.py`
- `backend/app/main.py`, quotation/invoice services and routers
- `backend/tests/test_customer_lpos.py`, `backend/tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_customer_lpos.py`: **16 passed**
- `tests/test_quotations.py`: **20 passed** (includes convert mutex)
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **70 passed, 0 failed** (68.45s)

black + ruff clean. `alembic check`: No new upgrade operations detected.

---

## 2026-09-01 — WP-A review nits W1–W3 (planned BEFORE code)

**Source:** `.agents/reports/wp-a-quotations-review.md` (APPROVE_WITH_NITS). Backend only. No UI. No Alembic rewrite. No git commit.

### Planned

1. **W1 Expiry persist on 403:** `accept` / `reject` / `convert` apply on-read EXPIRED and **commit that write** before the illegal action returns 403. Today the router commits only on success, so HTTPException rolls back EXPIRED and the row stays SENT until GET/list.
2. **W3 Converted-invoice hydration:** `map_converted_ids` and `existing_converted_invoice` must filter `Invoice.workspace_id` to the JWT workspace (same as the quote). Unique `quotation_id` is not enough.
3. **W2 Inactive-product copy:** Quote create/update `_resolve_line` must not say “invoice”. Use quotation/line wording. Invoice path unchanged.

### Tests / quality

- Extend `tests/test_quotations.py`: persist EXPIRED after accept/reject/convert without a prior GET (read status from PostgreSQL, not GET — GET would expire on-read and hide the bug). Assert inactive-product 400 message mentions quotation, not invoice.
- `pytest tests/test_quotations.py tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` on PostgreSQL `_test`.
- black + ruff.

---

## 2026-09-01 — WP-A review nits W1–W3 (implemented)

No Alembic rewrite. No UI. No git commit.

### Done

1. **W1:** `expire_if_due` / `_load_and_expire` persist SENT→EXPIRED **before** accept/reject/convert. Router commits that write, then the action 403s `INVALID_STATE`. Illegal-action rollback no longer undoes expiry. Tests read status from PostgreSQL (not GET).
2. **W3:** `map_converted_ids` and `existing_converted_invoice` filter `Invoice.workspace_id` to the JWT workspace. Convert create uses the same workspace id.
3. **W2:** Quote `_resolve_line(..., line_owner="quotation")` → “Cannot add an inactive product to a quotation line”. Invoice path still says “an invoice”.

### Files

- `backend/app/routers/quotations.py`
- `backend/app/services/quotation_service.py`
- `backend/app/services/quotation_support.py`
- `backend/app/services/invoice_service.py`
- `backend/tests/test_quotations.py`

### Pytest (PostgreSQL `_test`)

- `tests/test_quotations.py`: **18 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- `tests/test_concurrent_numbering.py`: **4 passed**
- Combined: **52 passed, 0 failed** (51.03s)

black + ruff clean.

---

## 2026-09-01 — WP-A Quotations API (planned BEFORE code)

**Spec:** `architecture/wave-quotations-addendum.md` WP-A. Architect note: `.agents/reports/architect-quotations-note.md`.

### Locked

- Router `/api/v1/quotations` (JWT on all routes). No public accept. No LPO stubs. No PDF/UI.
- States: DRAFT → SENT → ACCEPTED | REJECTED | EXPIRED. Convert **only ACCEPTED** → CONVERTED.
- Convert calls `InvoiceService.create_invoice` (DRAFT invoice, frozen line prices, notes prefix `Converted from QUO-…`, issue/supply=today, due=today+30). FTA send gates stay on invoice `/send`.
- Convert once: unique `invoices.quotation_id`. Second convert HTTP 200 same invoice. Soft-deleted invoice → 409, do not recreate.
- On-read expiry (`valid_until` default quotation_date + 14 days). Number `QUO-YYYY-XXXX` via new counter + SELECT FOR UPDATE.
- Shared `money()` ROUND_HALF_UP (extract `line_money.py`). Extra keys 422. AED Decimal. Cross-tenant 404.
- Tests: `backend/tests/test_quotations.py` against PostgreSQL `_test`. Existing invoice/FTA/numbering tests must still pass.

### Out

WP-B PDF/UI, WP-C Playwright, LPO, public accept, REVISED/CANCELLED quote states, nightly expiry job.

---

## 2026-09-01 — WP-A Quotations API (implemented)

**Revision:** `cb01b6bef962` (`down_revision = "c8e1a4f2b6d0"`). Convert uses `InvoiceService.create_invoice`. Shared `app/services/line_money.py` (`money` ROUND_HALF_UP). Quote send does not require TRN; invoice send still FTA-gated.

### Done

- Models + Alembic: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`, `invoices.quotation_id`.
- `QuotationNumberService` `QUO-YYYY-XXXX` via SELECT FOR UPDATE on new counter.
- Router `/api/v1/quotations` JWT: CRUD, send, accept, reject, convert-to-invoice. Extra keys 422. Cross-tenant 404.
- Convert: DRAFT invoice, frozen prices, notes prefix, issue/supply=today, due=+30. First convert 201; second 200 same invoice; soft-deleted invoice 409. SENT/DRAFT/EXPIRED/REJECTED cannot convert (403).
- On-read expiry. DRAFT-only edit/delete. Soft-delete does not rewind numbers.

### Pytest (PostgreSQL `invoicesaas_test`)

- `tests/test_quotations.py`: **16 passed**
- `tests/test_invoices.py`: **25 passed**
- `tests/test_concurrent_numbering.py` + `tests/test_multi_tenant_isolation.py`: **4 + 5 passed**
- Combined: **50 passed, 0 failed**

black + ruff clean. No git commit. No SQLite. No frontend/PDF (WP-B).

---


## Changes Made
- Updated pp/models/invoice.py: Added @property for mount_paid and alance_due that calculate directly from successful payments dynamically.
- Updated pp/schemas/invoices.py: Added mount_paid and alance_due to InvoiceResponse and InvoiceListItem to ensure API surfaces these values.
- Updated pp/routers/invoices.py: Added .options(selectinload(Invoice.payments)) to list_invoices to eagerly load payments, preventing N+1 queries.
- Ensured InvoiceVoidRequest validates
eason (min_length=5).

## Testing
- Tested DB schema compatibility (no migrations needed since properties are computed).
- Pydantic validation handles properties automatically on response model dump.

---

## 2026-08-19 - Wave 2 Execution: Workspace Settings
- Updated pp/models/workspace.py: Added new fields for TRN, Logo URL, Default Tax Rate, WhatsApp Number, and Credit Control settings.
- Ran Alembic migration to update database schema.
- Added new workspaces schemas and router to support GET /api/v1/workspaces/me and PUT /api/v1/workspaces/me.
- Registered workspaces_router in pp/main.py.

---

## 2026-08-19 - Wave 3 Execution: Product Master
- Defined complex Database Models for Product, Category, Brand, UnitOfMeasure, ProductIdentifier, ProductUOMConversion, and ProductPrice with strict foreign keys and unique constraints in ackend/app/models/product.py.
- Exposed models in __init__.py and generated Alembic migration d3e4c7fdb29f to instantiate the schema securely in the database.
- Implemented core Pydantic schemas in products.py for API validation.
- Created ackend/app/routers/products.py with GET and POST operations for products, categories, brands, and UOMs.
- Bound products_router into the core application via main.py.

---

## 2026-08-19 - Wave 4 Execution: Supplier Master
- Designed ackend/app/models/supplier.py incorporating complex relationships: Supplier, SupplierContact, SupplierBankAccount, SupplierDocument, and SupplierProduct.
- Exported the newly created models into __init__.py to make them Alembic-discoverable.
- Applied 784076ef11b9_add_wave_4_supplier_master.py DB migration smoothly.
- Created fully-typed Pydantic schemas in suppliers.py enforcing core commercial constraints like Credit Limits and Terms.
- Developed suppliers.py router logic for scalable GET and POST access and mounted it in main.py globally.

---

## 2026-08-19 - Wave 5 Execution: Payment Methods
- Re-architected ackend/app/models/payment.py replacing generic gateways with concrete B2B payment methods (CASH, BANK_TRANSFER, CHEQUE, PDC, CREDIT_CARD).
- Added robust PDC lifecycle tracking (pdc_date, pdc_status: RECEIVED -> DEPOSITED -> CLEARED -> BOUNCED).
- Upgraded PaymentService.record_payment() to dynamically consume these commercial fields while retaining ACID row-level locking for concurrency protection.
- Generated Alembic PostgreSQL ENUM migration script e217c0bc3af7 safely rolling out the schema updates.
- Added a PUT /invoices/{invoice_id}/payments/{payment_id} router endpoint to natively handle PDC lifecycle state mutations.

---

## 2026-08-19 - Wave 7 Execution: Inventory Management Foundation
- Established robust inventory core via ackend/app/models/inventory.py featuring 5 master tables: Warehouse, WarehouseBin, InventoryLevel, TransactionType, and InventoryTransaction.
- Implemented **Rule 1.2** (Immutable Ledger) ensuring InventoryTransaction acts as an append-only source of truth for stock movements.
- Implemented **Rule 1.3** and Check Constraints (chk_inventory_on_hand_positive) to guarantee stock integrity at the database layer (preventing accidental negative stock).
- Generated and successfully applied PostgreSQL migration d41016da5030.
- Authored strict Pydantic schemas in inventory.py calculating dynamic fields like vailable = on_hand - reserved - damaged.
- Attached the core APIs via /api/v1/inventory router into main.py utilizing SELECT ... FOR UPDATE row-level locks for concurrent adjustment protection.

---

## 2026-08-19 - Wave 8 Execution: Procurement Foundation
- Constructed ProcurementRequest and ProcurementRequestItem database schemas enforcing the strict separation of internal demand from supplier execution.
- Added comprehensive Enums representing Procurement business logic (PRSourceType, PRDestinationType, PRStatus, etc.) matching the architectural design documents.
- Implemented quantity allocation vectors mapping precisely to Rule C-02 (
equested_quantity, pproved_quantity, ordered_quantity,
eceived_quantity).
- Successfully tracked and deployed Alembic DB Migration  abb440e0fc9.
- Bootstrapped fully-typed Pydantic schemas handling bidirectional relationships (Header 1:N Items) in schemas/procurement.py.
- Wired backend CRUD router mapping to /api/v1/procurement/requests integrating native sequence generators (PR-YYYY-00000X).

---

## 2026-08-19 - Wave 9 Execution: Request for Quotation (RFQ)
- Built the complex multi-stage RFQ and Sourcing models in ackend/app/models/rfq.py.
- Enforced Architectural Principle INV-3.1 ensuring RFQ, Quote, and Award entities strictly isolate themselves from the Inventory Ledger.
- Modeled SupplierRFQResponse and SupplierQuoteItem to act as immutable financial snapshots (handling exchange rates and quote currencies independent of the live master data).
- Engineered the core logic for the Evaluation Engine via Enums like RFQEvalCriteria.LOWEST_LANDED_COST.
- Generated and correctly applied PostgreSQL migration 64d6ac9e5b49 to safely register these 7 new relational tables.
- Deployed /api/v1/rfq router and strict Pydantic schemas enforcing zero-drift validation between PR items and RFQ sourcing.

---

## 2026-08-19 - Wave 10 Execution: Purchase Orders (SPO)
- Developed robust formal SupplierPurchaseOrder and SupplierPurchaseOrderItem tables in ackend/app/models/spo.py.
- Formatted linkage capabilities directly to RFQAward allowing 1:1 tracebacks from Market Sourcing to actual Purchasing commitments.
- Implemented financial snapshots including exchange_rate, subtotal, 	ax_amount, and 	otal_amount ensuring absolute static historical accuracy against fluctuating supplier pricing.
- Captured Fulfillment tracking vectors (
eceived_quantity) mirroring exactly into later GRN architecture.
- Added API endpoints with standard sequential generation (SPO-YYYY-00000X).
- Pushed and validated PostgreSQL Alembic migration 345906985988.

---

## 2026-08-19 - Wave 11 Execution: Goods Receipt Notes (GRN)
- Engineered physical fulfillment architecture via GoodsReceiptNote and GRNItem schemas natively within ackend/app/models/grn.py.
- Formally executed Rule 2.1 via three tracking vectors: quantity_received, quantity_accepted, and quantity_rejected ensuring precise tracking of damaged bounds before injection into live inventory.
- Created GRNStatus ENUM (DRAFT, RECEIVED, INSPECTED, POSTED) mapping exactly to physical warehouse operational flows.
- Bound items explicitly to warehouse_bins and supplier_purchase_order_items guaranteeing exact traceback to the legal PO execution limits.
- Generated and validated 2a98d90a2f79 Alembic PostgreSQL migration.
- Secured the /api/v1/grn Router to automatically validate that ccepted + rejected == received natively inside the POST controller.

---

## 2026-08-19 - Wave 12 Execution: General Navigation & Dashboard Polish
- Engineered cross-modular data aggregation endpoint /api/v1/dashboard/stats.
- Queried active states across Invoice, ProcurementRequest, RFQ, and GoodsReceiptNote simultaneously utilizing high-efficiency unc.count and unc.sum groupings natively in SQLAlchemy.
- Exposed holistic business health metrics: Total Receivables (AED), Pending Internal Demand, Active Market Sourcing volume, and Pending Inbound QA constraints.

## E2E Testing Bug Fixes (Wave 12)

- **Fixed InvoiceStatus ENUM mismatch**: The backend dashboard endpoint was incorrectly filtering InvoiceStatus.VOID (which didn't exist) instead of InvoiceStatus.CANCELLED.
- **Fixed property conversion to DB schema issue**: Fixed unc.sum(Invoice.balance_due) crashing asyncpg because alance_due and mount_paid are python properties and cannot be implicitly translated directly into SQL aggregate functions. Handled this using python-side evaluation over a query loaded with selectinload.

### Task 4E-4K: SPO Implementation
- Implemented `backend/app/schemas/spo.py` for pydantic models based on latest architecture.
- Created `backend/app/services/spo_service.py` to handle state machine transitions and core logic.
- Implemented `backend/app/routers/spo.py` for API endpoints.
- Added basic test scaffold in `backend/tests/test_spo.py`.
- Tested the code. All implementations comply with the new SPO requirements.

### Task 4M-4N: SPO E2E Testing (Wave 13)
- Fixed critical MissingGreenlet serialization errors in spo_service.py caused by lazy-loaded relationships inside async session commits by refactoring the methods to eagerly fetch items before returning to FastAPI.
- Authored ackend/tests/test_e2e_spo.py simulating the exact flow: Award -> SPO -> partial ack -> price amendment -> multi-GRN -> short-close remainder -> invoice match -> closed.
- Built robust test database initialization fixtures that cleanly create Suppliers, Warehouses, Products, and UOMs directly via the test client to fulfill PostgreSQL strict foreign key constraints.
- Validated E2E test passes cleanly using the invoicesaas_test PostgreSQL sandbox.
- **Wave 13 (Step 4) is fully completed.**

## 2026-08-20 - Wave 14/15 Execution: GRN Module
- Created/updated GRN schemas in app/schemas/grn.py to match the architecture specs for DTOs.
- Authored the core GRN Service layer in app/services/grn_service.py to execute disposition logic and stock posting.
- Validated atomic stock posting using SELECT FOR UPDATE on InventoryLevel (Task 5I).
- Configured tolerance bounds calculation and hook placeholder for Auto-PurchaseReturn drafting.
- Added API routes to app/routers/grn.py that consume the service layer.
- Authored a comprehensive E2E GRN testing suite in backend/tests/test_grn.py that validates the GRN state lifecycle.


### Task 5M-5N: GRN E2E Testing (Wave 15)
- Fixed MissingGreenlet serialization errors across the GRN router (create_grn, update_grn, start_receiving, cancel_grn, and ecord_disposition) and SPO router (get_spo) by replacing session.refresh() with explicit selectinload queries.
- Fixed IntegrityError caused by a PostgreSQL CHECK constraint (quantity_received = quantity_accepted + quantity_damaged + quantity_rejected) on GRNItem during insertion by temporarily setting quantity_accepted = quantity_received when items are added during receiving.
- Created `backend/tests/test_e2e_grn.py` to simulate the exact physical flow: SPO ACKNOWLEDGED → GRN (2 tranches, mixed disposition) → damaged reclass → rejected auto-return → SPO reconciliation reflects all.
- The test validates that the final SPO tracking variables (quantity_received, quantity_accepted, quantity_damaged_rejected) mathematically reflect both GRN tranches perfectly.
- Verified all E2E tests pass locally.
- **Wave 14/15 (Step 5) is fully completed.**

---

## 2026-08-24 — Application Stabilisation Fix Session (Groups 1–7)

### Group 1: main.py Cleanup ✅
- Rewrote `backend/app/main.py` completely
- All imports moved to top (resolved E402 violations per CLAUDE.md)
- Removed duplicate `dashboard_router` registration (was at lines 155 AND 165)
- Removed mid-file duplicate router block (`clients_router`, `health_router`, `invoices_router`, `payments_router`)
- All 15 routers now registered cleanly under `# Routers` section

### Group 2: Test DB Setup Fix ✅
- Fixed `backend/tests/test_auth.py`: Changed `async def setup_database()` to sync using `asyncio.run()` — tables were never created before
- Fixed `backend/tests/test_e2e_spo.py`: Same async→sync fixture fix (line 40)
- Added `from app.models import *` wildcard import so SQLModel.metadata is populated before `create_all`

### Group 3: GRN Test Failures ✅
- Fixed `backend/tests/test_grn.py`:
  - Corrected SPO route from `/api/v1/spo` to `/api/v1/spos/` (missing trailing slash + wrong prefix)
  - Added workspace_id query param to SPO create call
  - Added SPO state machine transitions (submit-approval → approve → send) before GRN creation
  - Added warehouse bin creation step (required for GRN stock posting)
  - Introduced module-level `_MODULE_TOKEN` / `_MODULE_WS_ID` cache to avoid hitting rate limiter (5/min) on `/auth/register` across two test functions
- Fixed `backend/tests/test_e2e_grn.py`: Replaced asyncio.run bin-creation DB hack with proper API call to new `/inventory/warehouses/{id}/bins` endpoint

### Group 4: SupplierInvoice float→Decimal Migration ✅
- Rewrote `backend/app/models/supplier_invoice.py`: All monetary fields now use `Decimal` with `Numeric(12,2)` SA columns; quantity fields use `Numeric(12,4)`
- Rewrote `backend/app/schemas/supplier_invoices.py`: All float types replaced with Decimal; migrated to ConfigDict
- Rewrote `backend/app/services/supplier_invoice_service.py`: Removed all `float()` cast workarounds; pure Decimal arithmetic; removed debug print statements
- Generated and applied Alembic migration `12bdad2ae924_fix_supplier_invoice_decimal_types.py` (16 column type changes: DOUBLE_PRECISION → Numeric)
- Fixed test assertion: `float(matched_inv["items"][0]["variance_quantity"]) == 20.0` since DB returns Decimal as string

### Group 5: Frontend Routes ✅
- `frontend/src/App.tsx`: Added missing routes:
  - `<Route path="supplier-invoices" element={<SupplierInvoices />} />`
  - `<Route path="supplier-invoices/:id" element={<SupplierInvoiceDetail />} />`
- `frontend/src/components/Layout.tsx`: Added AP Payables link (`/supplier-invoices`) and GRN link to Purchasing & Suppliers nav group; cleaned up Inventory Management group

### Group 6: Missing Architecture Docs ✅
- Created `architecture/entity-relationship.md`: Full Mermaid ERD for all 30+ entities
- Created `architecture/api-contracts.md`: Complete endpoint reference for all 15 routers
- Created `architecture/edge-cases.md`: 28 edge cases across procurement, inventory, products, finance, security — each with implementation status
- Created `architecture/procurement-rules.md`: PR/RFQ/SPO/GRN/3-Way Match business rules; document number formats; conflict register

### Group 7: Pydantic V2 ConfigDict Migration ✅
- Migrated all 12 schema files from deprecated `class Config: from_attributes = True` to `model_config = ConfigDict(from_attributes=True)`:
  - `clients.py`, `invoices.py`, `payments.py`, `workspaces.py`, `products.py`, `suppliers.py`, `inventory.py`, `procurement.py`, `rfq.py`, `spo.py`, `grn.py`, `supplier_invoices.py`
- Fixed `spo.py` which had both `class Config` AND `model_config` simultaneously (PydanticUserError crash)

### New Feature: Warehouse Bin Endpoint ✅
- Added `POST /api/v1/inventory/warehouses/{warehouse_id}/bins` — required for GRN stock posting
- Added `GET /api/v1/inventory/warehouses/{warehouse_id}/bins` — list bins in a warehouse
- Made `WarehouseBinCreate.warehouse_id` Optional (derived from URL path param)

### Final Test Results ✅
```
9 passed, 0 failed
- tests/test_auth.py::test_health_check         PASSED
- tests/test_auth.py::test_root                 PASSED
- tests/test_auth.py::test_register_and_login   PASSED
- tests/test_e2e_3way_match.py::test_3way_match_engine PASSED
- tests/test_e2e_grn.py::test_e2e_grn_complex_flow PASSED
- tests/test_e2e_spo.py::test_e2e_spo_flow     PASSED
- tests/test_grn.py::test_grn_lifecycle         PASSED
- tests/test_grn.py::test_grn_cancellation      PASSED
- tests/test_spo.py::test_create_spo            PASSED
```

---

## 2026-08-31 — WP-1 Product Master API (planned BEFORE product code)

**Spec:** `architecture/wave-3-product-master-addendum.md` (full) + mvp-sequence §5 WP-1 AC.
**Locked:** no Alembic (HEAD stays `06c9b4b1dcda`); no `models/product.py` edits; no payment/PDC PUT; no frontend; no git commit.

### Files to change

| File | Action |
|---|---|
| `backend/app/services/product_service.py` | **Create.** All uniqueness, 404 isolation, conversion/VAT/price/UOM rules. No commit. HTTPException 400/404/409. |
| `backend/app/schemas/products.py` | **Expand.** Category/Brand/UOM/Product Create+Update+Response; ProductDetailResponse; Identifier/Conversion/Price Create+Response. Decimal never float. Enum allow-lists. `extra="forbid"` on write bodies (rejects `from_uom_id`, `hs_code`, electrical keys → 422). |
| `backend/app/routers/products.py` | **Rewrite.** HTTP only; prefix `/products`. Static `/categories`, `/brands`, `/uom` before `/{product_id}`. POST 201. DELETE 200 `{success:true, data:null}`. Lists = `PaginatedResponse`. Nested child GET lists = unpaginated `SuccessResponse[list]`. Router commits after service. |
| `backend/app/services/__init__.py` | Export `ProductService` (project pattern). |
| `backend/tests/test_products.py` | **Create.** PostgreSQL `invoicesaas_test` harness matching isolation tests. Cases per addendum §13. |
| `backend/tests/test_multi_tenant_isolation.py` | Extend product section: B cannot GET/PUT/DELETE A's product **or children** (404). |

### Business rules to encode in service (not router)

- JWT `workspace_id` only; query `workspace_id` ignored.
- Cross-tenant / missing / soft-deleted parent → **404**, never 403.
- Category/Brand duplicate `name` among non-deleted → 409 (no new unique constraint).
- Category circular / self parent → 400.
- UOM/SKU uniqueness: live unique constraints include deleted rows → 409; **do not reuse SKU** after soft-delete.
- Soft-delete UOM blocked (400) if referenced by non-deleted `Product.base_uom_id` or any `ProductUOMConversion.to_uom_id`.
- PUT product `base_uom_id` while conversions exist → 400.
- Conversion: implied from = `Product.base_uom_id`; persist `to_uom_id` + `conversion_factor` Numeric(14,6); `to_uom_id == base` → 400; factor `> 0`; no `from_uom_id`.
- Identifier types allow-list: MPN, BARCODE, SUPPLIER_CODE, EAN, UPC, CUSTOMER_CODE.
- Prices: DEFAULT_SALES (one per product, no client/min_qty), TIER_1 (min_quantity > 0), CUSTOMER_SPECIFIC (client_id required, same workspace). Currency AED only. Decimal(12,2).
- Product `tax_rate` optional; if set 0–100; null = inherit workspace later (do not copy 5.00).
- Category/Brand/UOM/Product: soft `deleted_at`. Identifier/conversion/price: hard DELETE.
- Lists exclude `deleted_at IS NOT NULL`. Product list: no default `is_active` filter; optional `search` / `category_id` / `brand_id` / `is_active`.
- GET product by id: `ProductDetailResponse` with identifiers/conversions/prices; **no** stock embed. Children loaded by query (models have no Relationship — will not edit `product.py` to add `selectinload`).

### Out of scope (will not touch)

Alembic, `models/product.py`, payments/PDC PUT, frontend, WP-2/WP-3, quotations, FTA PDF, invoice `product_id`.

### Verification after implement

`pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` from `backend/` against PostgreSQL. black + ruff. No `Float` in new schema fields. No `print()`.

---

## 2026-08-31 — WP-1 Product Master API (implemented)

### Done

- `backend/app/services/product_service.py` — all WP-1 rules; no commit; conversion semantic in module docstring.
- `backend/app/schemas/products.py` — Create/Update/Response + detail/children; Decimal; Enum allow-lists; `extra="forbid"`.
- `backend/app/routers/products.py` — HTTP only; static routes first; POST 201; DELETE `{success:true, data:null}`; `PaginatedResponse` lists; unpaginated child GETs.
- `backend/app/services/__init__.py` — exports `ProductService`.
- `backend/tests/test_products.py` — PostgreSQL `_test` harness; addendum §13 cases.
- `backend/tests/test_multi_tenant_isolation.py` — B cannot GET/PUT/DELETE A's product or identifier/conversion/price (404).
- `backend/tests/test_e2e_spo.py`, `test_e2e_grn.py`, `test_e2e_3way_match.py` — accept 201; drop extra keys (`type`, `base_currency`) that are now 422.

Untouched: Alembic, `models/product.py`, payments/PDC PUT, frontend.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_products.py` + `tests/test_multi_tenant_isolation.py`: **20 + 5 = 25 passed, 0 failed.**

Related existing suite after e2e payload alignment: **32 passed** (includes spo/grn/e2e).

black + ruff clean on WP-1 files.

### Deviation (with evidence)

Addendum asked for `selectinload` on GET product. `Product` in `models/product.py` has **no SQLAlchemy `Relationship`** to identifiers/conversions/prices, and WP-1 forbids editing that model. Children are loaded with three scoped `select` queries instead. Response shape is unchanged (`identifiers` / `conversions` / `prices`, no stock).

---

## 2026-08-31 — WP-1 review nits W1–W6 (planned BEFORE code)

**Spec:** `.agents/reports/wp1-product-api-review.md` (APPROVE_WITH_NITS).
**Locked:** backend only; no frontend; no Alembic; no `models/product.py`; no payment/PDC; no git commit.

### Files to change

| File | Action |
|---|---|
| `backend/app/services/product_service.py` | W1: on product soft-delete, hard-delete identifier/conversion/price rows in the same call. Nested child DELETE still 404 via `_require_live_product`. W2: `_assert_acyclic_parent` 404 only on **immediate** parent (`_get_live`); further ancestors load without 404, deleted/missing = end-of-chain, still detect cycles among live nodes. W4: keep live-product conversion block (no code change). |
| `backend/tests/test_products.py` | W1 MPN reuse after soft-delete; nested child DELETE 404 after parent delete. W2 A←B←C, delete B, POST `parent_id=C` → 201. W4 DELETE BOX used as conversion `to_uom` → 400. W5: circular/self parent 400; brand duplicate 409; list without `is_active` includes inactive; duplicate TIER_1 same min_qty 409; same MPN on two live products 409; INTERNAL_SKU 422; PUT extra key 422; omit tax_rate → GET null. |
| `backend/tests/test_multi_tenant_isolation.py` | W3: token B + `?workspace_id=<A's uuid>` on GET/PUT/DELETE product **and one child** still 404. Category/brand/UOM cross-tenant 404. POST identifier/conversion/price as B on A's product_id → 404. |

### W6 (document-only, no code)

WP-1 `DEFAULT_SALES` / price uniqueness is service-only (pre-check then insert). Concurrent POSTs can both pass the SELECT until a later unique index. Accept this race for WP-1; catch-IntegrityError is a no-op until Alembic adds a unique. Not P0.

### Verification

`pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` from `backend/` against PostgreSQL `_test`. black + ruff. No Alembic. No `models/product.py` edit.

---

## 2026-08-31 — WP-1 review nits W1–W6 (implemented)

### Done

- W1: `delete_product` hard-deletes identifier, conversion, and price rows via `_hard_delete_children` before setting `deleted_at`. Nested child DELETE still 404s (`_require_live_product`). Test: MPN reused on a new product after soft-delete.
- W2: `_assert_acyclic_parent` 404s only on the immediate parent (`_get_live`). Further ancestors use `_load_category_maybe`; deleted/missing ends the walk; live-node cycles still 400. Test: A←B←C, delete B, POST `parent_id=C` → 201.
- W3: isolation uses token B + `?workspace_id=<A's uuid>` on product GET/PUT/DELETE and one child; category/brand/UOM cross-tenant 404; POST identifier/conversion/price as B on A's product_id → 404.
- W4: live-product conversion block unchanged. Test: conversion `to_uom=BOX` (not base) → DELETE BOX → 400.
- W5: circular/self parent 400; brand duplicate 409; list without `is_active` includes inactive SKUs; duplicate TIER_1 same min_quantity 409; same MPN on two live products 409; INTERNAL_SKU 422; PUT extra `hs_code` 422; omit tax_rate → GET null.

Untouched: Alembic, `models/product.py`, payments/PDC PUT, frontend.

### W6 (accepted, no code)

WP-1 price uniqueness (`DEFAULT_SALES` / TIER_1 / customer) is service-only until a later unique index. Concurrent POSTs can both pass the SELECT; catch-IntegrityError is a no-op without a DB unique. Accept this race for WP-1; not P0.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_products.py` + `tests/test_multi_tenant_isolation.py`: **29 + 5 = 34 passed, 0 failed.** black + ruff clean.

---

## 2026-08-31 — WP-A FTA Tax Invoice API (planned BEFORE code)

**Spec:** `architecture/wave-fta-tax-invoice-addendum.md` + `.agents/reports/architect-fta-tax-invoice-note.md`.
**Locked:** API + Alembic + pytest only. No frontend/PDF/Playwright/Arabic/IBAN/Net terms/quotes/LPO. No rewrite of `d3e4c7fdb29f` or ancestors. `down_revision = "06c9b4b1dcda"`.

### Files to change

| File | Action |
|---|---|
| `backend/app/models/workspace.py` | Add nullable `address` Text. No IBAN. |
| `backend/app/models/invoice.py` | Add `supply_date`, `invoice_kind`, seller/buyer name-address-TRN snapshots. |
| `backend/app/models/invoice_item.py` | Add optional `product_id`/`uom_id`/`sku_snapshot`, discounts, `line_net`, line `tax_amount`. Keep `total_price` as gross. |
| `backend/alembic/versions/<rev>_fta_tax_invoice_fields.py` | New revision from HEAD `06c9b4b1dcda`. Backfill `supply_date=issue_date`; backfill line net/VAT/gross. No `clients.trn`. |
| `backend/app/schemas/invoices.py` | FTA fields; `extra="forbid"`; AED-only write; optional `product_id`/`tax_rate`/`supply_date`; XOR line discounts; response snapshots + `amount_paid`/`balance_due`. |
| `backend/app/schemas/workspaces.py` | `address` on GET/PUT `/workspaces/me`. |
| `backend/app/schemas/clients.py` | Optional `trn` validation_alias writing `tax_id`. No new column. |
| `backend/app/schemas/common.py` | `ErrorCode.FTA_SEND_BLOCKED`, `NO_LIST_PRICE`. |
| `backend/app/services/invoice_service.py` | `money()` ROUND_HALF_UP per line; tax inherit product then workspace 5%; catalog copy; `assert_fta_sendable`; freeze snapshots; PUT item-replace math; HTTPException not ValueError 500. |
| `backend/app/routers/invoices.py` | HTTP only; `selectinload` items+payments; call service send/update. |
| `backend/app/main.py` | Unwrap `ErrorDetail` dict so `error.code`/`error.field` surface. |
| `backend/tests/test_invoices.py` | New PostgreSQL `_test` suite covering addendum §11. |
| `backend/tests/test_multi_tenant_isolation.py` | FTA workspace/client fields before send in `test_payment_is_workspace_isolated`; PUT isolation 404. |

### Math (service-owned)

`line_net = money(qty×price − discount)`; `line_vat = money(line_net × tax_rate/100)`; `total_price = line_net + line_vat` (gross). Header `subtotal = Σ line_net`. Omitted `tax_rate` → product.tax_rate else workspace `default_tax_rate` (5.00). Explicit `0` stays 0. Header discount deferred (extra key 422).

### Send hard-fails (400 `FTA_SEND_BLOCKED`)

AED; workspace TRN `^100[0-9]{12}$`; workspace address non-empty. STANDARD if client TRN valid or total > 10000 → also client `tax_id` + address. SIMPLIFIED otherwise. Snapshots frozen on send. Drafts save without TRN. 403 remains INVALID_STATE for non-DRAFT.

### Verification

`pytest tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py` from `backend/` against PostgreSQL `_test` (never SQLite). `alembic upgrade head` then `alembic check`. black + ruff.

---

## 2026-08-31 — WP-A FTA Tax Invoice API (implemented)

**Alembic revision:** `c8e1a4f2b6d0` (`down_revision = "06c9b4b1dcda"`). `alembic upgrade head` + `alembic check` clean on `invoicesaas` and `invoicesaas_test` (host 5434). Never rewrote `d3e4c7fdb29f`.

### Done

- Models: `workspaces.address`; invoice `supply_date` / `invoice_kind` / seller+buyer snapshots; line `product_id` / `uom_id` / `sku_snapshot` / discounts / `line_net` / `tax_amount`. No `clients.trn`. No IBAN.
- `InvoiceService`: `money()` ROUND_HALF_UP per line; omitted tax_rate → product then workspace 5.00; optional `product_id` catalog copy; FTA send hard-fails `FTA_SEND_BLOCKED` + snapshots; PUT item-replace math in service.
- Router HTTP-only; GET `selectinload` items+payments; `amount_paid`/`balance_due` on response.
- Workspace GET/PUT `/workspaces/me` includes `address`. Client `trn` alias writes `tax_id`.
- Exception handler unwraps `ErrorDetail` so `error.code` / `error.field` surface.
- Tests: `tests/test_invoices.py` (addendum §11) + isolation send FTA fixture + PUT 404 + overpay 400.

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_invoices.py` + `tests/test_multi_tenant_isolation.py` + `tests/test_concurrent_numbering.py`: **22 + 5 + 4 = 31 passed, 0 failed.**

black + ruff clean on WP-A files.

### Out of WP-A (deferred, as locked)

Frontend, PDF “Tax Invoice”, Playwright, Arabic, Net 30/45/60, quotes/LPO, IBAN, header discount column, payment PUT.

---

## 2026-08-31 — WP-A FTA review warnings (planned BEFORE code)

**Spec:** `.agents/reports/wp-a-fta-tax-invoice-review.md` (W1, W3, W5) + `architecture/wave-fta-tax-invoice-addendum.md` §3/§6/§10.
**Locked:** backend only. No frontend. No Alembic rewrite of `c8e1a4f2b6d0`. No historical SENT PDF backfill (W2 = WP-B). No payment PUT. No SQLite. No new product features.

### Must fix

| # | Review | Action |
|---|---|---|
| W5 | `mark_as_sent` skips FTA | Call `assert_fta_sendable` + freeze snapshots inside `mark_as_sent`. `send_invoice` delegates so a future caller cannot skip FTA. |
| W1 | SIMPLIFIED may snapshot invalid / >15-char `client.tax_id` | Snapshot `buyer_trn_snapshot` only if `_is_valid_trn` (`^100[0-9]{12}$`); else `None`. Same shape as seller TRN. |
| W3 | STANDARD send + snapshot immutability untested | Add pytest: STANDARD 200 + snapshots; after send PUT invoice blocked and live workspace/client PUT does not change GET snapshots; SIMPLIFIED does not persist garbage `tax_id`. |

### Files to change

| File | Action |
|---|---|
| `backend/app/services/invoice_service.py` | W5: FTA + freeze in `mark_as_sent`. W1: buyer TRN snapshot only if valid FTA TRN. |
| `backend/tests/test_invoices.py` | STANDARD send success; snapshot immutability; SIMPLIFIED garbage `tax_id` → null snapshot. |

### Out of this follow-up

W2 migration header-total backfill, W4 catalog tax inherit / `NO_LIST_PRICE` tests, W6 `void_invoice` ValueError, W7 response currency enum, Alembic rewrite, payment PUT, frontend.

### Verification

`pytest tests/test_invoices.py tests/test_multi_tenant_isolation.py tests/test_concurrent_numbering.py -v` from `backend/` against PostgreSQL `_test`. black + ruff. No git commit.

---

## 2026-08-31 — WP-A FTA review warnings (implemented)

**Spec:** W1 / W3 / W5 from `.agents/reports/wp-a-fta-tax-invoice-review.md`. Alembic `c8e1a4f2b6d0` not rewritten. Payment PUT untouched.

### Done

- W5: `InvoiceService.mark_as_sent` now calls `assert_fta_sendable` then `_apply_send_snapshots` (kind + freeze) before DRAFT→SENT. `send_invoice` delegates to `mark_as_sent` so a future caller cannot skip FTA.
- W1: `_snapshot_trn` writes `buyer_trn_snapshot` / `seller_trn_snapshot` only when the value matches `^100[0-9]{12}$` (spaces stripped); otherwise `None`. Invalid / >15-char `client.tax_id` is not persisted on SIMPLIFIED send.
- W3: STANDARD send 200 with snapshots; after send invoice PUT is blocked (`INVALID_STATE`) and live workspace/client PUT does not change GET snapshots; SIMPLIFIED send with garbage `tax_id` leaves `buyer_trn_snapshot` null.

### Files changed

- `backend/app/services/invoice_service.py`
- `backend/tests/test_invoices.py`
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `invoicesaas_test`)

`tests/test_invoices.py` + `tests/test_multi_tenant_isolation.py` + `tests/test_concurrent_numbering.py`: **25 + 5 + 4 = 34 passed, 0 failed.**

black + ruff clean on changed Python files.

### Untouched (as locked)

Alembic `c8e1a4f2b6d0`, historical SENT PDF/header backfill (W2/WP-B), payment PUT, W4/W6/W7, frontend, SQLite.

---

## 2026-09-01 — WP-A electrical catalogue spec columns (planned BEFORE code)

**Spec:** `architecture/wave-electrical-specs-addendum.md` + `.agents/reports/architect-electrical-specs-note.md`.
**Locked:** WP-A API + Alembic + pytest only. No frontend. No git commit. Do not edit InvoiceService / quotes / LPO / CN / DN / PDFs / pricing. No JSONB `specs`. No Item table. No invoice line columns. Do not touch `_resolve_line`.

### Must implement

| # | Action |
|---|---|
| 1 | Five nullable columns on live `products`: `amp_rating` Numeric(8,2), `cable_size_mm2` Numeric(8,2), `cores` Integer, `poles` Integer, `voltage` String(32). No `Field(index=True)` on spec columns. |
| 2 | Five partial indexes on `Product.__table_args__`: `(workspace_id, col) WHERE col IS NOT NULL`. |
| 3 | New Alembic revision only. `down_revision = "b8d5f0c3a216"`. Never rewrite old files. Autogenerate then edit. |
| 4 | `ProductCreate` / `ProductUpdate` / `ProductResponse`: five optional keys. `extra="forbid"` stays (`hs_code` / `specs` still 422). Voltage regex after strip `^[0-9]+(/[0-9]+)?$`; empty → null. Decimal never float. Invalid specs 422 Pydantic. |
| 5 | GET list optional exact AND query params. `search` stays ILIKE sku/name/description only. Isolation 404. MEMBER+ unchanged. |
| 6 | `backend/tests/test_product_electrical_specs.py` covering addendum §6 (11 bullets). PostgreSQL `_test`. Keep `test_products.py` and `test_multi_tenant_isolation.py` green. |

### Files to change

| File | Action |
|---|---|
| `backend/app/models/product.py` | Five columns + five partial Indexes |
| `backend/app/schemas/products.py` | Optional fields + voltage validator; extra=forbid |
| `backend/app/routers/products.py` | List query params only |
| `backend/app/services/product_service.py` | Persist via existing dump; AND filters. No commit. |
| `backend/alembic/versions/<new>_add_product_electrical_specs.py` | New file; parent `b8d5f0c3a216` |
| `backend/tests/test_product_electrical_specs.py` | New §6 tests |

### Out of WP-A

Frontend, Playwright, debit notes, Peppol, hs_code, snapshot columns, git commit, InvoiceService, quotes, LPO, CN, DN, PDFs, pricing.

---

## 2026-09-01 — WP-A electrical catalogue spec columns (implemented)

**Spec:** `architecture/wave-electrical-specs-addendum.md` §2–§6. **Alembic parent:** `b8d5f0c3a216`. **New HEAD:** `1a30af047312`. Never rewrote `b8d5f0c3a216_add_credit_notes.py`. No git commit. No frontend.

### Done

- Live `products`: nullable `amp_rating` Numeric(8,2), `cable_size_mm2` Numeric(8,2), `cores` Integer, `poles` Integer, `voltage` String(32). Partial indexes on `Product.__table_args__` `(workspace_id, col) WHERE col IS NOT NULL`. No `Field(index=True)` on spec columns.
- Write bodies accept the five optional keys; `extra="forbid"` stays (`hs_code` / `specs` still 422). Voltage regex after strip `^[0-9]+(/[0-9]+)?$`; blank → null. Invalid specs 422 Pydantic. Decimal never float.
- GET list exact AND filters `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage`. `search` still ILIKE sku/name/description only. Isolation 404. MEMBER+ unchanged.
- Persist via existing `model_dump` / `exclude_unset`. InvoiceService / `_resolve_line` / quotes / LPO / CN / DN / PDFs / pricing untouched.

### Alembic revision

- **ID:** `1a30af047312`
- **File:** `backend/alembic/versions/1a30af047312_add_product_electrical_specs.py`
- **`down_revision`:** `"b8d5f0c3a216"`
- `alembic heads` = `1a30af047312 (head)`
- `alembic check` = No new upgrade operations detected

### Files changed

- `backend/app/models/product.py`
- `backend/app/schemas/products.py`
- `backend/app/routers/products.py`
- `backend/app/services/product_service.py`
- `backend/alembic/versions/1a30af047312_add_product_electrical_specs.py` (new)
- `backend/tests/test_product_electrical_specs.py` (new)
- `.agents/reports/backend-execution-report.md`

### Pytest (PostgreSQL `invoicesaas_test`)

- `tests/test_product_electrical_specs.py` + `tests/test_products.py`: **11 + 29 = 40 passed**, 0 failed
- `tests/test_multi_tenant_isolation.py`: **5 passed**
- black + ruff clean on WP-A Python files

### Out of WP-A (deferred)

Frontend / Playwright (WP-B/C), debit notes (next; parent = `1a30af047312`), Peppol, hs_code, snapshot columns, git commit.

---

## 2026-09-06 — F-2: backend test suite green (full-project audit remediation)

**Spec:** `.agents/reports/full-project-audit-2026-09-06.md` finding F-2.

### Problem

Full suite was RED at HEAD: 4 failures.

1. `tests/test_ar_statement_tdn.py::test_stmt_with_tdn` — standalone-fragile: imported helpers from `test_ar_statement.py` but had no `setup_database` fixture of its own, so schema (`users`) did not exist when the module ran without its sibling. Also used stale route `/api/v1/tax-debit-notes` (router is `/debit-notes`) and invalid `reason: PRICE_UPDATE`.
2. `tests/test_pdc.py::test_fta_cn_hold_overpay_alembic` — pinned old head `b8d5f0c3a216` in `alembic heads` output.
3. `tests/test_pricing.py::test_schema_not_float_and_alembic_head` — same stale pin.
4. `tests/test_product_electrical_specs.py::test_alembic_new_revision_parent_and_check` — asserted the electrical-specs revision itself was the head.

### Files changed

- `tests/test_ar_statement_tdn.py` — added own sync `engine` + `TestingSessionLocal` + `override_get_session` + module-scoped autouse `setup_database` (drop_all/create_all on `invoicesaas_test`), switched routes to `/api/v1/debit-notes`, fixed `reason` to `PRICE_INCREASE`.
- `tests/test_pdc.py` — head pin `b8d5f0c3a216` → `c624e2ac4f47`.
- `tests/test_pricing.py` — head pin `b8d5f0c3a216` → `c624e2ac4f47`.
- `tests/test_product_electrical_specs.py` — head assertion now `c624e2ac4f47`; "no `b8d5f0c3a216 (head)`" retained.

### Pytest (PostgreSQL `invoicesaas_test`)

- Full suite: **228 passed, 0 failed** (5m04s).
- `tests/test_ar_statement_tdn.py` + `tests/test_ar_statement.py`: **15 passed**.
- black + ruff clean on all four files.

Note: config.py `SECRET_KEY` default still weak (`M-1`), and head is now the enquiry module `c624e2ac4f47`.

---

---

## 2026-09-06 - Wave 22: Supplier AP Payments & Aging (Phase 4)

**Spec:** `architecture/wave-ap-payments-addendum.md` (Wave 22 = Phase 4 slot; Wave 21 supplier 3-way match ends at `approve`, and its `PARTIALLY_PAID`/`PAID` statuses + stored `amount_paid`/`balance_due`/`paid_at` columns were the untouched hook this wave fills).

### Delivered

- Models `supplier_payment.py`: `SupplierPayment` (immutable SUCCESS-only, `amount > 0` CheckConstraint, tz-aware `payment_date` indexed) + `SupplierPaymentIdempotencyKey` (workspace-scoped composite PK, 48h TTL) mirroring AR `Payment`/`IdempotencyKey`; reuses existing `paymentmethod`/`paymentstatus` Postgres enums (`create_type=False`).
- Alembic `a3f4c7d9e1b2` (down_revision `e1f5b8a2c3d4`): `supplier_payments` + `supplier_payment_idempotency_keys` + 5 indexes; downgrade/upgrade round-trip verified; `alembic check` clean.
- Schemas: `supplier_payments.py` (AP methods only CASH/BANK_TRANSFER/CHEQUE -> 422 otherwise; `payment_date` not after today; `SupplierApBalanceResponse`), `ap_aging.py` (summary/detail/by_supplier), `supplier_statements.py` (doc-type enum + statement JSON, `from` via alias).
- Services: `supplier_payment_service.py` (FOR UPDATE row lock, in-txn workspace-scoped idempotency (48h replay returns same payment), eligibility gate APPROVED/PARTIALLY_PAID else 400 `INVALID_STATE`, no overpayment else 400 `PAYMENT_EXCEEDS_BALANCE`, `_settle_invoice` writes stored columns + APPROVED->PARTIALLY_PAID->PAID with `paid_at`; `ap_aging` reuses live AR `aging_buckets` via `_AgingRow` DateTime->Date adapter, buckets `current`/`days_1_30`/`days_31_60`/`days_61_90`/`days_90_plus`); `supplier_statement_service.py` (generated AP ledger, reuses AR `validate_statement_dates`/`assert_activity_cap`, opening = pre-period invoices - pre-period SUCCESS payments, running balances, totals, `amount_due_now` + aging footer).
- Router `supplier_payments.py` (prefix `/api/v1`): POST /supplier-payments (Idempotency-Key header required, `10/minute`), GET list w/ filters + pagination, GET /{id}, PUT -> 405 immutable, GET /supplier-invoices/{id}/ap-balance, GET /supplier-invoices/{id}/payments, GET /ap-aging[/detail|/by-supplier], GET /suppliers/{id}/statement.

### Tests (PostgreSQL `invoicesaas_test`)

- New: `test_supplier_payments.py` (12), `test_ap_aging.py` (6), `test_supplier_statement.py` (6) = **24 tests** incl. idempotent replay, overpayment/eligibility gates, 405, method/date 422s, workspace isolation, aging buckets/invariants, statement opening/running/totals/amount_due_now.
- Guardian alembic-head pins re-pinned `e1f5b8a2c3d4` -> `a3f4c7d9e1b2` in `test_pdc.py` / `test_pricing.py`.
- Full suite: **279 passed (255 baseline + 24)**, 0 failed; ruff + black clean.
