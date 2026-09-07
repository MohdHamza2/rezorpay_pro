# Wave 26: Email Engine via Resend API — Architecture Addendum (Phase 5)

**Date:** 2026-09-07
**Status:** Coordinator lock. Coder implements **this file** (report-first).
**Extends:** `architecture/phase-5-comms-integrations-planning.md` (§2/§3 shared locks), live `app/config.py` / `app/main.py` / payment-lib idempotency patterns, `architecture/domain-model.md` §9 `EmailLog`.
**Depends on:** Wave 24 HEAD `234d5639ef8c` (Wave 25 added no revision). **Alembic: YES** — this wave moves HEAD.
**After this wave:** Wave 27 WhatsApp + PDF; then Wave 28 VAT pack. Not this slice: attachments/PDF-in-email, per-doc templates, auto-send coupling, scheduled/bulk/queued, inbound, per-workspace from/creds, OcrJob.
**Review locks applied:** decoupled from `/send`; generic linked-entity + workspace validation; AR_STATEMENT no physical FK; `body_text` OUT of MVP (optional enhancement only); dry-run default + `simulated` marker (no new lifecycle state); never log secrets/PII/bodies; env-keyed credentials; synchronous, manual resend only.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `app/config.py` | pydantic-settings, `.env`, `case_sensitive=True`, `extra=ignore`. Add keys §1.1. |
| Provider stack | No Resend lib. `httpx==0.26.0` present. Use `httpx.AsyncClient`. |
| Idempotency pattern | `record_payment`: workspace-scoped key table + 48h TTL + `FOR UPDATE`, returns existing row on reuse. Copy for sends. |
| Errors | `raise_error(http_status, code, message, field)` → `{success,data,error}` wrapper. Codes in `app/schemas/common.py` (`ErrorCode`). |
| Wrapper & pagination | `SuccessResponse[T]`, `PaginatedResponse` + `PaginationMeta` (page/per_page/pages/has_next/has_prev). |
| Roles | `UserRole.OWNER/ADMIN/MEMBER`; OWNER/ADMIN gate precedent (`supplier_pdc_service._require_owner_admin`). |
| Contrast | DO NOT touch `POST /invoices/{id}/send`, `quotations/{id}/send`, `spo/{id}/send` — they keep mark-sent semantics. |
| Alembic HEAD | `234d5639ef8c`. Any post-26 head changes move `down_revision` accordingly. |
| Tests | PostgreSQL `"+_test"`, drop_all/create_all per module, `TestClient`, module-scoped fixture, `hash_password` from `app.auth.utils`, guardian pins `test_pdc.py`/`test_pricing.py` assert head. |

---

## 1. Locked scope

### 1.1 In
- Model `EmailLog` (`email_log` table) + `emailstatus` PG ENUM (**QUEUED | SENT | DELIVERED | BOUNCED | FAILED**) + `simulated` boolean.
- Config keys (`.env` + `.env.example`): `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (default `"InvoiceSaaS <noreply@invoicesaas.example>`"), `RESEND_WEBHOOK_SECRET`, `COMMS_DRY_RUN` (default `true`).
- `providers.py` → `ResendProvider` adapter (single `httpx.AsyncClient`, bearer auth, Resend send endpoint `POST https://api.resend.com/emails`, payload `{from,to,subject,html}`). Dry-run adapter = simulator.
- `email_service.py`: `send_email`, `list_emails`, `get_email`, `resend_email`, `apply_webhook_event` + linked-entity resolver.
- Schemas: `EmailSendRequest`, `EmailResponse`, `EmailListResponse`, pagination filters.
- Router `comms_emails` — see §3.
- Tests, `STATE.md`, report, .env.example, black/ruff.

### 1.2 Out (deferred)
Attachments / PDF-in-email (reuse `DocumentRenderer` later); per-document template automation; auto-email on document `/send`; inbound email; per-workspace from-addresses; scheduling; queues; retry workers; `body_text` column (opt-in enhancement later; MVP `body_html` only); multiple to/cc beyond `bcc` (keep `to` single + optional `bcc` list).

---

## 2. Decisions (architect lock)

### 2.1 Model

```
EmailLog:
  id UUID PK
  workspace_id UUID FK (indexed)
  from_email str NOT NULL
  to_email str NOT NULL (email validated)
  bcc list[str] NOT NULL default []
  subject str NOT NULL (max 255)
  body_html str NOT NULL
  linked_entity_type str NULL  # see §2.3
  linked_entity_id UUID NULL
  status emailstatus NOT NULL default QUEUED
  resend_message_id str NULL
  simulated bool NOT NULL default false
  error_message str NULL        # redacted provider detail; never secrets
  sent_at / delivered_at datetime NULL
  created_at / updated_at datetime
```

`bcc` stored as JSON via `(sa_column=Column(JSON))` — consistent with `supplier_statements.py` JSON usage; do not use ARRAY (avoid migration complexity).

### 2.2 Send flow (synchronous, dry-run-aware)

1. Lock nothing at send time (no invoice mutation). Validate recipient (`email-validator`), subject/body present.
2. Resolve `linked_entity_*` (§2.3) → 404 / 422. Insert `EmailLog(status=QUEUED)` + flush.
3. Write Idempotency-Key (48h, copy payment key pattern).
4. `provider.send(...)`:
   - Real: `httpx.AsyncClient.post` → on 2xx set `status=SENT`, `resend_message_id=body["id"]`, `sent_at=now`. On provider error → `status=FAILED`, `error_message=<redacted>`, log; **raise 502 `PROVIDER_ERROR`** (caller can see delivery failed) — but the row persists FAILED for retry.
   - Dry-run (`COMMS_DRY_RUN` or no `RESEND_API_KEY`): set `status=SENT`, `simulated=True`, `resend_message_id=None`, `sent_at=now`, `logger.info("email_sent_simulated", extra={"email_id":..., "simulated": True})`. **A simulated send can never look like real delivery** (`simulated=True`).
5. Commit; return `EmailResponse`.

### 2.3 Linked-entity resolver (workspace-scoped)

Map: {INVOICE, QUOTATION, CREDIT_NOTE, TAX_DEBIT_NOTE, AR_STATEMENT, SUPPLIER_INVOICE, SUPPLIER_STATEMENT, PURCHASE_RETURN, SUPPLIER_DEBIT_NOTE, ENQUIRY, CLIENT, SUPPLIER} → table. For persisted tables: row must exist **in the workspace** else 404 `NOT_FOUND`. **AR_STATEMENT: no physical FK** (generated report, not a persistent entity) — accepted as reference id; SUPPLIER_STATEMENT likewise. Unsupported type → 422 `VALIDATION_ERROR` field=linked_entity_type. `client_id`/`supplier_id` FKs are intentionally NOT added (generic pair only, per review).

### 2.4 Resend / webhook

`POST /api/v1/webhooks/email`: `Authorization: Bearer {RESEND_WEBHOOK_SECRET}` → 401 `UNAUTHORIZED` on mismatch; body references `resend_message_id` + `event` (email.delivered / email.bounced / email.complained / email.failed). Map: delivered→DELIVERED (set `delivered_at`), bounced/failed→BOUNCED/FAILED. Unknown `resend_message_id` → 404. Idempotent: already-DELIVERED + repeat → 200 no-op. No `@limiter.limit`.

### 2.5 Resend gating

`POST /comms/emails/{id}/resend`: OWNER/ADMIN, `30/minute`. Allowed from **FAILED or BOUNCED** only; SENT/DELIVERED → 200 no-op returning row; QUEUED (stuck) → allowed as 200 (re-run adapter). Uses the SAME provider + simulator gate; row gets a fresh `resend_message_id`.

---

## 3. API summary

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/comms/emails` | OWNER/ADMIN, `30/minute`, `Idempotency-Key` | send (§2.2) |
| GET | `/api/v1/comms/emails` | any member | filters: status, linked_entity_type, linked_entity_id, from/to (created_at); pagination |
| GET | `/api/v1/comms/emails/{id}` | any member | 404 cross-workspace |
| POST | `/api/v1/comms/emails/{id}/resend` | OWNER/ADMIN, `30/minute` | §2.5 |
| POST | `/api/v1/webhooks/email` | Bearer secret | §2.4, no IP limiter |

Router `app/routers/comms_emails.py`, wired `app.include_router(comms_emails_router, prefix="/api/v1")`.

---

## 4. Module boundaries

| Layer | Owns |
|---|---|
| `routers/comms_emails.py` | HTTP, RBAC, rate limit, wrapper |
| `services/email_service.py` | workflow §2.2, resolver §2.3, resend §2.5, webhook §2.4 |
| `services/providers.py` | `ResendProvider` + simulator (single adapter file, reused by Wave 27) |
| `models/email_log.py` | `EmailLog` + enum `EmailStatus` |
| `schemas/email_comms.py` | `EmailSendRequest`, `EmailResponse`, filter params |
| `alembic/versions/xxxx_add_email_log.py` | table + `create_type` enum |

---

## 5. Alembic (this wave)

- Migration: create `emailstatus` via SaEnum (`create_type`), `email_log` table with `bcc` JSON, indexes on `(workspace_id, created_at)`, `(workspace_id, linked_entity_type, linked_entity_id)`, unique `resend_message_id`, NOT NULLs per model. `down_revision = "234d5639ef8c"`.
- Verify: `alembic upgrade head && downgrade -1 && upgrade head` round-trip; `alembic check` clean. Re-point guardian pins `test_pdc.py`/`test_pricing.py` to the new head.

---

## 6. Tests — `tests/test_email_comms.py`

1. Send happy path (real adapter mocked): QUEUED→SENT, `resend_message_id` captured, `simulated=False`.
2. Dry-run: no provider HTTP (spy records zero calls), `status=SENT`, `simulated=True`, `resend_message_id is None` — simulated never looks real.
3. Dry-run default: with `COMMS_DRY_RUN=true` and a key absent, send still succeeds.
4. Provider error: adapter raises → row FAILED + redacted error; endpoint 502 `PROVIDER_ERROR`.
5. Idempotency: same key twice → same row returned, one row only.
6. Resend: FAILED→resend→SENT; SENT resend → 200 no-op, no second provider call.
7. Linked entity: valid invoice id in workspace → linked; outside workspace → 404; AR_STATEMENT accepted reference (no FK); unsupported type → 422.
8. RBAC: MEMBER send → 403 `INSUFFICIENT_PERMISSIONS`; MEMBER list/get → 200.
9. Webhook: wrong secret → 401; delivered event → DELIVERED + `delivered_at`; bounced → BOUNCED; repeated delivered → 200 no-op; unknown `resend_message_id` → 404.
10. List filters + pagination math.
11. Cross-workspace get → 404 (never 403).
12. Guardian pin: head asserted by `test_pdc.py`/`test_pricing.py` after migration.

Full suite green + ruff/black + `alembic check`; report-first; `STATE.md`; commit per wave.

---

## 7. Coder checklist

1. Report first (`backend-execution-report.md` Wave 26 section).
2. `.env.example` keys + `config.py` (COMMS_DRY_RUN default true, RESEND_*).
3. Model + migration (+ round-trip + `alembic check` + guardian re-pin).
4. Providers + email service + schemas + router; wire in `main.py`.
5. Tests §6; targeted + full suite; ruff + black.
6. `STATE.md`; commit (Wave 26).
7. Then Wave 27 addendum (WhatsApp + PDF + inbound→Enquiry).
