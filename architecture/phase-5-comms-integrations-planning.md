# Phase 5: Communications & Integrations — Project Plan (Waves 26-28)

**Date:** 2026-09-07 (v1 reviewed; **Review verdict v1 corrections APPLIED** below)
**Status:** Coordinator lock, **approved for implementation planning**. Planning only — this phase has NOT been implemented. Per the lifecycle rule, nothing is touched ahead of this plan, and every wave re-applies report-first + the wave lifecycle (lock addendum → implement → tests → verify → docs → commit → wave sign-off → next wave). No implementation begins until the Wave 26 addendum (`architecture/wave-email-engine-addendum.md`) is locked.
**Source of truth:** `.planning/ROADMAP.md` Phase 5 = (1) Email Engine via Resend API, (2) WhatsApp Business API (Meta) for automated PDF delivery, (3) UAE VAT Compliance Pack export.

---

## 0. Runtime truth this phase builds on (verified 2026-09-07)

| Fact | Detail |
|---|---|
| No comms tables | `WhatsAppMessage` / `EmailLog` / `OcrJob` exist only in `architecture/domain-model.md` + `entity-relationship.md` (aspirational). No rows, no models, no enums. |
| PDF direction (live) | `wave-bilingual-pdf-addendum.md` locks **client-side** `@react-pdf/renderer` (`InvoicePDF/QuotationPDF/StatementPDF`…) and "**do not add a server PDF route**". Phase 5 deliberately changes that for **outbound comms only** (§2.1). |
| No outbound mail/HTTP stack | No Resend/Meta SDK; `httpx==0.26.0` + `requests` present; e-mail-validator present. Redis configured (`REDIS_URL`) but **NOT wired** (slowapi limiter in-memory; **no task queue** — keep synchronous, §2.8). |
| Config | `app/config.py` pydantic-settings, env-file loaded, `.env.example`. No provider keys exist yet. |
| `send` endpoints exist but only "mark as sent" | `POST /invoices/{id}/send` (`InvoiceSendRequest`, `sent_method="email"`, `recipient`) → service persists recipient + flips status. Same for `quotations/{id}/send`, `spo/{id}/send`. **No provider call.** |
| Enquiry architecture (live) | Enquiry domain + router exist (Phase 2/Wave 7, statuses incl. `NEW`). WhatsApp inbound must link into it, not replace it (§4.3). |
| VAT raw material | `invoice.tax_amount` + `invoice_item.tax_rate/tax_amount`, `quotation` same, `credit_note.seller_trn_snapshot/buyer_trn_snapshot`, `tax_debit_note` (TRN snapshots + `tax_rate/tax_amount`), `supplier_invoice.vat_rate/vat_amount`, `client.tax_id` (TRN), `supplier.trn`. **`created_at` is NOT the tax document date** — use `invoice_date`, CN date, TDN date, supplier-invoice date (§5). |
| Conventions to carry | `{success,data,error}` + `ErrorCode`/`ErrorDetail` (raise_error), pagination (`PaginationMeta`), workspace_id on every row, never cross-workspace, `FOR UPDATE`, `Idempotency-Key` 48h, slowapi, `Decimal(12,2)`, structured JSON logging (no PII/secrets), ruff+black, alembic-only schema, PostgreSQL tests, guardian head pins, pre-commit. |
| Alembic HEAD | `234d5639ef8c` (Wave 24; Wave 25 added no revision). |

---

## 0.1 Wave numbering — supersession recorded (MUST be explicit)

- **MASTER_PLAN_V3 (external, superseded):** Wave 26 = WhatsApp, Wave 27 = Reports/Dashboard, Wave 28 = India.
- **`.planning/ROADMAP.md` (authoritative from this point):** Wave 26 = **Email Engine (Resend)**, Wave 27 = **WhatsApp Business API + PDF delivery**, Wave 28 = **UAE VAT Compliance Pack**.
- This supersession is **intentional**. Future agents MUST treat `.planning/ROADMAP.md` + this file as the execution roadmap and MUST NOT follow MASTER_PLAN_V3 numbering. The obsolete mapping is recorded here only so it is never re-adopted.
- Note for continuity (deferred, NOT Phase 5): the Dashboard already ships live; "Reports/Dashboard" as a future wave would be enhancements only. India-market rules (`architecture/business-rules.md` Category 11) remain a **deferred market wave**, not Phase 5.

---

## 1. Scope → waves

| Wave | Feature | Alembic | Depends on |
|---|---|---|---|
| **26** | Email Engine via Resend API (transactional channel) | YES (`email_log` + `emailstatus` enum) | comms shared decisions (§2) |
| **27** | WhatsApp Business API (Meta) + automated **PDF delivery** + WhatsApp→Enquiry inbound | YES (`whatsapp_messages` + `whatsappdirection`/`whatsappmessagestatus` enums) | Wave 26 patterns; PDF primitive §2.1; Enquiry architecture §4.3 |
| **28** | UAE VAT Compliance Pack export | **NO** (pure read-only report) | existing VAT fields; statement/aging period conventions |

Build order 26 → 27 → 28. Each wave commits separately; full suite green + ruff/black + `alembic check` clean before each commit. Wave 28 is read-only and independent of 26/27.

---

## 2. Shared decisions (phase-level locks, review verdict applied)

### 2.1 PDF primitive — `DocumentRenderer` (**formalized architecture change**)
- **Locked: server-side `DocumentRenderer` is the canonical PDF primitive for OUTBOUND COMMUNICATION.** Phase 5 requires deterministic server-side PDF bytes for WhatsApp delivery. This deliberately extends the earlier direction in `wave-bilingual-pdf-addendum.md` (client-side `@react-pdf/renderer`, "no server PDF route").
- **Reconciliation (no dual systems):** the client-side `@react-pdf` documents remain the **interactive UI download** path (user-initiated, blob, snapshots-win). `DocumentRenderer` is the **outbound-comms delivery** path used by email/WhatsApp automation. **Both consume the same canonical document data contract** — the existing GET/response shape with snapshots winning when the document is SENT/ISSUED. Same titles/labels/fields per `wave-bilingual-pdf-addendum.md`; **no divergent "two versions" of Invoice/Quotation/AR Statement.**
- **Implementation:** `backend/app/services/pdf_service.py` — `DocumentRenderer.render(document)` returns `(bytes, filename, content_type)`. **Wave 27 renderer scope:** INVOICE, QUOTATION, AR_STATEMENT. Unsupported doc → 400 `UNSUPPORTED_DOCUMENT`. **Future email PDF attachments MUST reuse this renderer** — never a second PDF system.
- Add `reportlab` to `backend/requirements.txt` (pure Python, deterministic bytes, no infra). Alternatives rejected: weasyprint (heavy native deps), wkhtmltopdf (external binary), Playwright/headless (weight).

### 2.2 Provider adapters & dry-run
- New `backend/app/services/providers.py`: thin async adapter classes `ResendProvider` / `WhatsappProvider` (`httpx.AsyncClient`). Services depend on adapters; tests swap in spies.
- **`COMMS_DRY_RUN: bool` default `true`. CI/tests NEVER call Resend or Meta** (spy adapters + dry-run guard).
- **Dry-run is never mistaken for real delivery:** when dry-run marks a message SENT it sets `provider_ref = null` AND writes a simulation marker/log — `simulated=true` boolean column on both `EmailLog`/`WhatsAppMessage` plus `logger.info("...", extra={"simulated": True})`. **No new lifecycle state** (status remains the real enum; `simulated` is orthogonal metadata).

### 2.3 Secrets policy (provider security)
- Environment-variable, single-account provider config for MVP: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`; `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. Per-workspace encrypted provider credentials are **OUT**.
- **Never log:** access tokens, API keys, webhook secrets, message bodies, full recipient PII. Log only ids (`EmailLog.id`, `resend_message_id`, `wa_message_id`), status transitions, redacted errors.
- Webhook endpoints are public **only because they are provider callbacks**; they MUST be cryptographically/secretly authenticated (§2.6).

### 2.4 Send semantics (document lifecycle decoupled from delivery)
- Outbound channels are separate actions (`POST /api/v1/comms/emails`, `POST /api/v1/comms/whatsapp/messages`). **Do NOT modify `POST /invoices/{id}/send` (or quotations/SPO) into automatic provider sends.** The existing endpoints keep their mark-sent/recipient semantics; communication endpoints own actual delivery.

### 2.5 Writes & RBAC
- Sends: **OWNER/ADMIN** (MEMBER 403 `INSUFFICIENT_PERMISSIONS`). Reads (list/get): any workspace member.
- Send endpoints accept `Idempotency-Key` (48h, payment pattern) → repeats return the existing row. Rate limit sends `30/minute`.
- WhatsApp provider message ids (`wa_message_id`) are the provider dedup/idempotency identifier (§4.4).

### 2.6 Webhooks
- **Email:** `POST /api/v1/webhooks/email`, `Authorization: Bearer {RESEND_WEBHOOK_SECRET}` (401 mismatch), updates `EmailLog` by `resend_message_id` → DELIVERED/BOUNCED/FAILED. New config `RESEND_WEBHOOK_SECRET`.
- **WhatsApp:** `GET /api/v1/webhooks/whatsapp` hub challenge (verify-token); `POST` verified by `X-Hub-Signature-256` (HMAC-SHA256 of raw body, `WHATSAPP_APP_SECRET`). Delivery/read events IDEMPOTENT (§4.4). Inbound flow per §4.3.
- Webhook routers: public, signature-gated, **no `@limiter.limit`** (provider bursts).

### 2.7 Models/migrations style
- Follow Wave 23/24 migration pattern (`create_type` for new ENUMs, chained `down_revision`). Alembic heads: 26 moves the head; 27 moves it again; 28 adds none. Re-point `test_pdc.py`/`test_pricing.py` guardian pins on 26 and 27.
- **Linked-entity design (Email + WhatsApp):** generic `linked_entity_type + linked_entity_id`, workspaces validated on every linked entity (resolver → 404). **AR_STATEMENT has NO physical FK** — AR statements are generated reports, not persistent entities; the resolver treats AR_STATEMENT as a reference id with no FK. Documented once here; not repeated per wave.

### 2.8 Infrastructure (keep synchronous)
- **No Celery, no Redis task queues, no scheduled delivery, no bulk delivery, no retry workers, no per-workspace encrypted provider credentials.** Manual resend is sufficient (`POST /comms/emails/{id}/resend`, and a WhatsApp text/document re-send). This phase is synchronous provider calls inside the request.

---

## 3. Wave 26 — Email Engine via Resend API

Locked in `architecture/wave-email-engine-addendum.md`. Scope summary: `EmailLog` + `emailstatus` (QUEUED|SENT|DELIVERED|BOUNCED|FAILED) + `simulated` bool; `email_service` (send/list/get/resend/webhook-update); `ResendProvider`; endpoints §3.3 of that addendum; keys §2.3. IN: transactional HTML emails, generic linked-entity audit, `body_text` optional enhancement (kept OUT of MVP per review; MVP = `body_html` only). OUT: attachments/PDF-in-email, per-doc templates, auto-send coupling, per-workspace from-addresses, scheduling, queues, inbound email, per-workspace webhook routing.

---

## 4. Wave 27 — WhatsApp Business API (Meta) + PDF delivery + inbound→Enquiry

### 4.1 Locked scope
- **IN:** `WhatsAppMessage` model + table + `whatsappdirection` (INBOUND|OUTBOUND) + `whatsappmessagestatus` (QUEUED|SENT|DELIVERED|READ|FAILED) enums + `simulated` bool; `whatsapp_service` (send document/PDF, send text, webhook intake incl. inbound→Enquiry); `WhatsappProvider` adapter (Meta Media upload → Messages `type=document`, text path); PDF primitive §2.1 (INVOICE/QUOTATION/AR_STATEMENT); config §2.3; endpoints; .env.example; tests; docs.
- **OUT:** LLM classification/extraction (NO AI in this wave), auto-creating Clients from unknown contacts, reply automation, templates/catalog/payments, webhook media-download, scheduling, bulk, queues.

### 4.2 Sends
Document path renders PDF bytes → `POST /{phone_number_id}/media` (multipart `application/pdf`, filename `<doc-no>.pdf`) → `POST /{phone_number_id}/messages` (`type=document`, `media_id`, caption). Text path: `message_body` only. Non-renderable linked doc → 400 `UNSUPPORTED_DOCUMENT`. Unmatched/unknown `to_number` never auto-registers a Client.

### 4.3 Inbound flow → Enquiry (preserves live Enquiry architecture)
```
Meta POST webhook → X-Hub-Signature-256 verify → dedupe by wa_message_id
  → persist WhatsAppMessage (direction=INBOUND, status=SENT), whatsapp_message_id = wa_message_id
  → IF a known Client matches confidently (workspace-scoped phone-number exact match on Client)  → link client_id
  → ELSE leave client_id = NULL (unknown contact: NEVER auto-create a Client)
  → create/link Enquiry  → Enquiry status = NEW  (phone + name preserved on the Enquiry; client_id nullable)
```
- **No LLM classification/extraction in this wave.** Unknown contacts do NOT become Clients unless separately approved.
- Dedup: repeated delivery/read events update the SAME `WhatsAppMessage`; inbound text duplication guarded by `wa_message_id` unique-per-workspace.

### 4.4 WhatsApp idempotency (webhook retries safe)
- `wa_message_id` IS the provider's idempotency/dedup id. Webhook retries must **never** create a duplicate `WhatsAppMessage` **or** duplicate Enquiry.
- Implementation: unique constraint on `(workspace_id, whatsapp_message_id)` for OUTBOUND+INBOUND where present; inbound handler upserts on `wa_message_id`; Enquiries created exactly once per inbound `wa_message_id` (bound Enquiry in a single transaction with the message insert; re-delivery of an existing `wa_message_id` → no new Enquiry).
- Repeated DELIVERED/READ events: idempotent status upserts (no-op when already at/re-past target).

### 4.5 Tests
`test_whatsapp_comms.py` + `test_pdf_service.py`: GET challenge (valid echoes/403); HMAC verify (good/bad 403); inbound dedup (same `wa_message_id` twice → one row + one Enquiry NEW); repeated DELIVERED/READ idempotent; known-client link + unknown-contact `client_id` null + **no Client auto-created**; document send spy captures `%PDF-` bytes and Media id flows to Messages call; text send; unsupported doc 400; renderers produce PDFs; RBAC; 404 isolation; idempotency; dry-run no-network + `simulated=True`. Guardian re-pin (Wave 27 head). Full suite + ruff/black + `alembic check`.

---

## 5. Wave 28 — UAE VAT Compliance Pack export

### 5.1 Locked character
- **Strictly read-only accounting/compliance export.** It is NOT an FTA submission, NOT FTA certification, NOT e-invoicing implementation, NOT an XML/EDI filing system. ZIP CSV + JSON mirror approved.
- **NO Alembic, no new tables, no columns** (pure query).

### 5.2 Data rules
- **Business dates, not `created_at`:** filter by invoice DATE (`invoice.invoice_date`), credit-note date, tax-debit-note date, supplier-invoice date (etc.), within the inclusive `[from, to]` range.
- **Lifecycle-based inclusion/exclusion — no invented VAT states:** sales invoices `SENT/PARTIALLY_PAID/PAID` (DRAFT/CANCELLED excluded); CN/TDN issued (not DRAFT/CANCELLED); supplier invoices received. Follow the existing document lifecycle and tax rules exactly.
- **Do NOT exclude an invoice merely because it is OVERDUE** — payment status and tax-document status are separate concepts (nothing in the business rules ties tax compliance to being overdue). Outstanding amount is irrelevant to the VAT pack.

### 5.3 Payload (approved)
ZIP of: `sales_invoices.csv`, `invoice_lines.csv`, `credit_notes.csv`, `tax_debit_notes.csv`, `purchase_invoices.csv` (input VAT via `vat_rate`/`vat_amount`), `vat_summary.csv` + `manifest.json` (per-rate taxable/VAT/count for outputs and inputs, period, org). `format=json` returns the same aggregates. **Organization TRN stays OPTIONAL** (`VAT_ORG_TRN`) — report generation is NEVER blocked by an absent optional TRN (manifest rows carry it only when configured).

### 5.4 Endpoints & tests
`GET /api/v1/reports/vat-compliance?from&to&format=csv|json` — OWNER/ADMIN, `10/minute`, `to-from > 366 days` → 422. CSV → zip via `StreamingResponse` (wrapper not used for binary; schema `response_model=None`). Tests: 6 entries + headers, per-line VAT math, per-rate summary (output+input), excluded statuses absent, OVERDUE-but-SENT included, period bounds 422, RBAC, JSON mirror. No head change.

---

## 6. Phase gates

Review verdict v1 applied (this file) — the four §6 defaults in v0 are LOCKED and need no further confirmation:
1. Email channel decoupled from `/send` (LOCK #6).
2. WhatsApp PDFs = Invoice + Quotation + AR Statement (LOCK #2).
3. VAT pack = ZIP CSVs, no XML/EDI (LOCK #9/#10).
4. Env-keyed single provider account (LOCK #8).

Proceed per lifecycle: Wave 26 addendum → sign-off → implement → verify → commit → wave 27 → 28.

---

## 7. NOT in Phase 5 (any wave)

Per-workspace provider credentials / encrypted storage; document-lifecycle auto-email; email attachments/PDF-in-email (later, reusing §2.1 renderer); WhatsApp LLM classification/extraction, reply automation, templates/catalog/payments, media-download; unknown-contact Client auto-creation; OcrJob/Gemini; scheduled/batched/queued delivery (Celery/Redis task queues); retry workers; FTA submission/certification/XML/EDI/e-invoicing; India-market rules; frontend work (Phase 5 is backend API only).

---

## 8. Phase checklist

1. Report-first: each wave prepends its section to `.agents/reports/backend-execution-report.md` before coding.
2. Wave 26 addendum (`architecture/wave-email-engine-addendum.md`) is filled and locked; implement Wave 26 report-first.
3. Per wave: models+migration (26/27), providers, services, routers wired in `app/main.py`, schemas, `.env.example`, tests, full suite green, ruff + black, `alembic check`, guardian pins, **commit per wave**, docs.
4. `STATE.md` updated per wave.
5. This file + `wave-bilingual-pdf-addendum.md` remain in sync for the §2.1 PDF reconciliation.
