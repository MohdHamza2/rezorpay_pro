# Wave 27: WhatsApp Business API (Meta) + PDF delivery + inbound→Enquiry — Architecture Addendum (Phase 5)

**Date:** 2026-09-07 (rev 3 — **Review verdict "APPROVE WITH REQUIRED CHANGES" + final 3 mandates applied**)
**Status:** Coordinator lock. Coder implements **this file** (report-first).
**Extends:** `architecture/phase-5-comms-integrations-planning.md` (§2 shared locks, §4 Wave 27), Wave 26 `providers.py` adapter pattern + email idempotency/webhook patterns, live `Enquiry`/`Client` models, `reportlab` supersession below.
**Depends on:** Wave 26 HEAD `3d3f24d6ee00`. **Alembic: YES** — this wave moves HEAD.
**After this wave:** Wave 28 UAE VAT Compliance Pack (read-only, no Alembic).
**Review verdict recap:** architecture substantially approved; all 15 mandatory blockers incorporated (rev 2 deltas marked 🛠). Key locks preserved: no LLM/AI; never auto-create Client; inbound reuses the Enquiry domain; provider adapter + dry-run `simulated`; HMAC webhook; idempotency; workspace isolation; no queues/workers; canonical service data in PDFs; governance exact.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| Live `Enquiry` model | Has `source` (`EnquirySource.WHATSAPP` exists), `client_id` **nullable** FK, `contact_name/contact_phone/contact_whatsapp/contact_email`, `whatsapp_message_id` (global unique, 255), `items_description`. Inbound uses these exact fields. |
| Live `EnquiryService` | `services/enquiry_service.py` owns creation + gapless `enquiry_number` + defaults/validation. **It is the sole authority for Enquiry creation invariants.** 🛠 Must accept an existing caller session and must NOT commit/rollback on its own when invoked from webhook ingestion (§2.7). |
| Live `Client` model | `phone` nullable `String(50)`. Matching via canonical normalization only (§2.5). `phone` column itself is **never written by WhatsApp** — an inbound never edits a Client. |
| Live status enums | `InvoiceStatus`: DRAFT/SENT/PARTIALLY_PAID/PAID/OVERDUE/CANCELLED. `QuotationStatus`: DRAFT/SENT/ACCEPTED/REJECTED/EXPIRED/CONVERTED. Sendable-state gates are derived from these LIVE enums (§2.4) — never invented. |
| `providers.py` (Wave 26) | `ProviderResult` + async `ResendProvider` + `resend_provider` singleton. Wave 27 adds `WhatsappProvider` to **the same file**. |
| HTTP stack | `httpx==0.26.0`, `python-multipart` present. No Meta SDK. Use `httpx.AsyncClient` (single client, bearer auth). |
| PDF direction (live) | `wave-bilingual-pdf-addendum.md` §2.4: client-side `@react-pdf` only, "Do not add WeasyPrint/reportlab", "no server PDF route". **Phase 5 §2.1 deliberately supersedes for OUTBOUND COMMS ONLY** — recorded here; future agents never re-open it. The server renderer is an **internal** byte generator — it adds **no** HTTP PDF route. |
| PDF data contract | Client PDFs rebuild from GET JSON; snapshots win when SENT/ISSUED. `DocumentRenderer` consumes **the same canonical service dicts** (snapshot-winning). 🛠 Precision wording: **there are two presentation renderers (client `@react-pdf`, server `reportlab`) but only ONE canonical financial data contract; neither renderer may independently calculate or mutate business data.** |
| Services for renderer | `invoice_service.py`, `quotation_service.py`, `ar_statement_service.py` all live; renderer reuses their outputs. |
| Idempotency pattern | Wave 26 email send-key (48h TTL, `FOR UPDATE`). WhatsApp adds a hard **unique constraint** on the key reservation (§2.6). |
| Errors | `raise_error(http_status, code, message, field)` → `{success,data,error}`; Wave 27 adds `ErrorCode.UNSUPPORTED_DOCUMENT` + `ErrorCode.IDEMPOTENCY_CONFLICT`. `PROVIDER_ERROR` exists. |
| Roles | `UserRole.OWNER/ADMIN/MEMBER`; OWNER/ADMIN gate precedent (`email_service`). |
| Config | Wave 26 added `RESEND_*` + `COMMS_DRY_RUN`. Wave 27 adds `WHATSAPP_*` (§2.1). |
| Alembic HEAD | `3d3f24d6ee00` (Wave 26). Wave 27 `down_revision = "3d3f24d6ee00"`. |
| Tests | PostgreSQL `"+_test"`, drop_all/create_all per module, `TestClient`, module-scoped fixture, guardian pins re-point to Wave 27 head. Pre-commit EOF-fixer may touch the new migration. |

---

## 1. Locked scope

### 1.1 In
- Model `WhatsAppMessage` (`whatsapp_messages`) + `whatsappdirection` (INBOUND|OUTBOUND), `whatsappmessagestatus` (**QUEUED|SENT|DELIVERED|READ|RECEIVED|FAILED** 🛠), `whatsappmessagetype` (TEXT|DOCUMENT|MEDIA) PG ENUMs + `simulated` boolean.
- `providers.py` → `WhatsappProvider` (Meta Graph: media upload + messages type=document/text).
- `pdf_service.py` → `DocumentRenderer` (§2.3). Add `reportlab`.
- `whatsapp_service.py`: send document/text, list/get, resend, webhook intake (challenge + events + inbound→Enquiry), linked-document resolution.
- `utils/phones.py` → canonical phone normalization (§2.5) — single source, used everywhere.
- Config keys §2.1 (.env + `.env.example`); `ErrorCode.UNSUPPORTED_DOCUMENT` + `ErrorCode.IDEMPOTENCY_CONFLICT`.
- Schemas + router `comms_whatsapp` (§3), wired in `main.py`.
- Tests, `STATE.md`, report, black/ruff. Guardian pin re-point.

### 1.2 Out (deferred / never)
LLM classification/extraction (NO AI ever here); auto-creating Clients from unknown contacts (never); reply automation; templates/catalog/payments/interactive buttons; webhook media-download; scheduling; bulk; queues; retry workers; per-workspace provider credentials/phone numbers; **manual `to_number` override on document sends** (§2.5, out of MVP); OcrJob; AR chrome in server PDFs (§2.3); lifecycle-state re-pricing or re-computation in the renderer.

---

## 2. Decisions (architect lock)

### 2.1 Config keys (`app/config.py` + `.env.example`)

| Key | Default | Purpose |
|---|---|---|
| `WHATSAPP_ACCESS_TOKEN` | "" | Meta Graph access token (env-keyed, single account) |
| `WHATSAPP_PHONE_NUMBER_ID` | "" | Sender number id — **also verified against inbound webhook `metadata.phone_number_id`** (§2.7) |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | "" | Account id (audit metadata only; not a secret, never logged as one) |
| `WHATSAPP_APP_SECRET` | "" | HMAC-SHA256 webhook signature key |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | "" | GET-challenge token |
| `WHATSAPP_GRAPH_VERSION` | 🛠 "**v19.0 is a PLACEHOLDER, not a lock**. Coder MUST verify the currently supported Meta Graph/WhatsApp Cloud API version from official Meta documentation and set this default accordingly before implementation (acceptance gate)." |
| `WHATSAPP_INBOUND_WORKSPACE_ID` | "" | Deployment-level inbound routing (§2.2) |
| `WHATSAPP_WEBHOOK_MAX_BODY_BYTES` | 1_000_000 | Webhook body-size guard (§2.7); not an IP rate limiter |
| `COMMS_DRY_RUN` | true (exists) | Gates `WhatsappProvider` too — one switch for the whole comms platform |

Never log `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, message bodies, full recipient PII, raw webhook bodies, or raw provider response bodies. Log `WhatsAppMessage.id`, `whatsapp_message_id`, `media_id`, status transitions, normalized codes, sanitized reasons only.

**ReportLab version** 🛠 — **no blind pin.** `reportlab==4.0.9` used anywhere in this draft is a placeholder, not a lock. Wrong-version guidance: at implementation the coder must determine the current stable, security-reviewed ReportLab release per the project dependency policy, exact-pin it in `requirements.txt`, and leave `pip-audit` clean (`pip-audit==2.7.0` is an existing CI gate). Do not inherit an old reference.

### 2.2 Multi-tenancy — explicit MVP limitation (review blocker 🛠)

**Locked wording (exact):** “Phase 5 MVP supports **one WhatsApp Business phone/account per deployment** and therefore **one inbound WhatsApp workspace**. `WHATSAPP_INBOUND_WORKSPACE_ID` is a **deployment-level routing constraint**, not a general multi-tenant routing mechanism. Per-workspace WhatsApp credentials/phone numbers are explicitly deferred.”

Consequences (all locked):
- Outbound: every workspace shares the one `WHATSAPP_PHONE_NUMBER_ID` sender. Permitted — communication endpoints are workspace-scoped on rows, provider identity is deployment-wide.
- Inbound: all messages route to the single `WHATSAPP_INBOUND_WORKSPACE_ID` workspace. If unset → inbound is acknowledged but **dropped** (no rows, sanitized log) — §2.7.
- A later multi-tenant extension (per-workspace numbers/creds) is a **separate future wave**, not an assumption of this one.

### 2.3 `reportlab` + `DocumentRenderer` (`app/services/pdf_service.py`)

- `DocumentRenderer.render(document: str, data: dict) -> RenderedDocument(bytes, filename, content_type)`; supported **INVOICE, QUOTATION, AR_STATEMENT** → `application/pdf`; anything else → 400 `UNSUPPORTED_DOCUMENT` (field `linked_entity_type`).
- 🛠 **Testability seam:** also expose `DocumentRenderer.build_sections(document, data) -> list[Section]` — a pure, deterministic model (headers, chrome, table rows, totals) that the reportlab layer maps onto the page. Financial-integrity tests assert `build_sections` exactly (§6) — no `%PDF-`-only assertions.
- `data` is the existing service output dict (snapshot-winning when SENT/ISSUED), fetched by `whatsapp_service` via live services — never a fresh query path, never re-priced/re-computed.
- 🛠 **No-recompute rule:** the renderer prints values **verbatim** from `data` (labels, quantities, UOM, unit price, subtotal, VAT, total, currency, dates, TRN, snapshots). It never derives `total = subtotal + vat`. Math lives in services; tests enforce it (§6).
- 🛠 **Language:** server-side outbound WhatsApp PDFs are **EN-only in Phase 5; bilingual server rendering is deferred**. (No legal/compliance claim is asserted here — this is a product/implementation-scope statement. The client-side bilingual `@react-pdf` documents are untouched.)
- Money/dates from existing 2-dp Decimal / ISO strings — never float, never reformatted, Western digits only.
- Filenames: invoice → `<invoice_number>.pdf` (e.g. `INV-2026-0001.pdf`), quotation → `<quotation_number>.pdf`, AR statement → `Account-Statement-<from>_<to>.pdf`.

### 2.4 Sendable document lifecycle states (derived from LIVE enums) 🛠

Always enforced at service level (send AND resend), never invented:

| Document | Allowed (WhatsApp-able) | Rejected (403 `INVALID_STATE`) |
|---|---|---|
| INVOICE | `SENT`, `PARTIALLY_PAID`, `PAID`, `OVERDUE` | `DRAFT`, `CANCELLED` |
| QUOTATION | `SENT`, `ACCEPTED`, `CONVERTED` | `DRAFT`, `REJECTED`, `EXPIRED` |
| AR_STATEMENT | always renderable (generated report) | n/a |

### 2.5 Provider + phone normalization + recipient authority

**`WhatsappProvider` (in `providers.py`, beside `ResendProvider`):** base `https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}`; bearer `WHATSAPP_ACCESS_TOKEN`.
- `upload_media(phone_number_id, filename, pdf_bytes) -> ProviderResult`: `POST /{phone_number_id}/media`, form `messaging_product=whatsapp` + `file` part (`application/pdf`, renderer filename). Success → `media_id`.
- `send_message(phone_number_id, to_number, payload: dict) -> ProviderResult`: `POST /{phone_number_id}/messages` JSON — document `{messaging_product, to, type:"document", document:{id: media_id, filename, caption?}}`; text `{messaging_product, to, type:"text", text:{body}}`. Success → `ProviderResult.success(wa_message_id)`.
- Failure (transport or non-2xx) → `ProviderResult.failure(code, category, safe_message)` 🛠 (**normalized** fields only — `provider_code`, `provider_error_category`, `safe_error_message`. Never persist raw provider response bodies; Meta errors may embed phone numbers/ids/user data).
- Dry-run (`COMMS_DRY_RUN` or no token): `simulated=True`, `status=SENT`, `whatsapp_message_id=None`/`media_id=None`, `logger.info("whatsapp_sent_simulated", ...)`. A simulated message can never look real.

**Canonical phone normalization 🛠 (single source):** `app/utils/phones.py` → `normalize_phone_to_e164(raw) -> Optional[str]`. Spec (unit-tested):
1. Trim whitespace. Strip internal spaces/dashes/parens/dots.
2. `+<country><number…>` → keep as `+` + digits.
3. Leading `00` → replace with `+` (international prefix).
4. **Anything else (bare local numbers, no international prefix) → `None` (do NOT guess a country code).**
This is the ONLY normalization logic the codebase uses for WhatsApp matching/sending. **If a `Client.phone` cannot normalize to canonical E.164 → the contact is treated as NOT matchable (`client_id=NULL`), never guess-matched, and a DOCUMENT send to that client is a 422** (no derivable recipient).

**Recipient authority for DOCUMENT sends 🛠 (locked decision):** `to_number` is **NOT accepted** on the document request (`extra=forbid`). It is **derived** from the linked Client's canonicalized `phone` (invoice/quote → its client; AR_STATEMENT → `linked_entity_id` client). No override in MVP — explicit-permission override is a future decision. Consequence: it is structurally impossible to send Invoice A to Client B's number. A document send resolves to 422 `VALIDATION_ERROR` (field `to_number`) when the client has no canonical phone. TEXT sends keep an explicit, E.164-validated `to_number`.

### 2.6 Outbound send + resend — model, timestamp semantics, transaction & idempotency (review blockers 🛠)

**Formal model — `WhatsAppMessage` (lock):**

```
id UUID PK
workspace_id UUID FK (indexed)
direction whatsappdirection NOT NULL            # INBOUND | OUTBOUND
message_type whatsappmessagetype NOT NULL       # TEXT | DOCUMENT | MEDIA (see MEDIA rule ↓)
to_number str NULL                              # OUTBOUND recipient (canonical E.164); NULL when not derivable
from_number str NULL                            # INBOUND sender (canonical E.164)
message_body str NULL                           # OUTBOUND text / INBOUND text or caption
caption str NULL                                # OUTBOUND document caption
document_type str NULL                          # INVOICE | QUOTATION | AR_STATEMENT (DOCUMENT sends only)
document_id UUID NULL                           # invoice/quote id; NULL for AR_STATEMENT (client id lives in linked_entity_id)
document_filename str NULL                      # e.g. INV-2026-0001.pdf
media_id str NULL                               # Meta media id after upload (DOCUMENT sends only)
statement_from / statement_to DATE NULL         # AR_STATEMENT sends only (stored replay params for resend)
linked_entity_type str NULL                     # auto-set on DOCUMENT sends; optional audit ref on TEXT sends
linked_entity_id UUID NULL
status whatsappmessagestatus NOT NULL default QUEUED
whatsapp_message_id str NULL UNIQUE             # Meta message id; webhook dedup/upsert key (global unique)
simulated bool NOT NULL default false
provider_error_code / provider_error_category str NULL    # normalized provider info; NEVER raw provider bodies
error_message str NULL                          # normalized safe message only
sent_at / delivered_at / read_at datetime NULL
received_at datetime NULL                       # INBOUND: set at ingest (status=RECEIVED)
created_at / updated_at datetime
```

**Timestamp semantics (formal — mandatory):**

| Timestamp | Set on | When |
|---|---|---|
| `created_at` | both directions | row insert (Txn 1 / inbound ingest) |
| `received_at` | **INBOUND only** | ingest time; rows with `direction=INBOUND` MUST have `status=RECEIVED` + `received_at` set and MUST leave `sent_at/delivered_at/read_at` NULL |
| `sent_at` | **OUTBOUND only** | provider ack in Txn 2 (real `SENT`), or the simulate moment (dry-run `SENT`); NULL otherwise |
| `delivered_at` | OUTBOUND only | delivery webhook event (`DELIVERED`) |
| `read_at` | OUTBOUND only | read webhook event (`READ`) |
| `updated_at` | both | every status-affecting UPDATE |

Rule: inbound rows never carry outbound timestamps and never pass through `SENT/DELIVERED/READ`; outbound rows (except an interrupted `QUEUED`) never carry `received_at`.

**MEDIA rule (mandatory):** `message_type=MEDIA` denotes an **INBOUND media/non-text event ONLY** (image, video, document, audio, sticker, location, contacts, button/location reply). Phase 5 performs **NO media download, inspection, storage, or processing** — the row is a pure transport record (`status=RECEIVED`, `received_at`, `from_number`, `whatsapp_message_id`) and nothing more; media payload bytes/handles are never fetched, cached, or retained. A MEDIA row **never** creates an Enquiry (§2.8). No OUTBOUND message may be `MEDIA` (outbound is `TEXT` or `DOCUMENT` only).

**No HTTP call inside a DB transaction.** Synchronous does NOT mean one giant open DB transaction:

```
Txn 1  ─ reserve Idempotency-Key + insert message:
            1. Reservation lookup by (workspace_id, key):
                 exists + not expired + key_fingerprint == request_fingerprint  → return existing row
                                                                                  (idempotent 200, PROVIDER NEVER CALLED)
                 exists + not expired + key_fingerprint != request_fingerprint  → 409 IDEMPOTENCY_CONFLICT
                 expired → delete stale reservation and continue
            2. INSERT WhatsAppMessage(status=QUEUED, direction=OUTBOUND)
            3. INSERT reservation (workspace_id, key, request_fingerprint, message_id, expires_at=+48h)
            → COMMIT
            (the (workspace_id, key) UNIQUE PK is the final authority for concurrent same-key requests:
             the racing second request fails the insert → re-read → same fingerprint → 200 existing result,
             or → 409. Provider is invoked EXACTLY ONCE per key no matter how many retries race in.)
Provider call OUTSIDE any DB session (render+upload first for DOCUMENT; then send_message)
Txn 2  ─ SUCCESS → UPDATE status=SENT, whatsapp_message_id, media_id, document_filename, sent_at → COMMIT
         FAILURE → UPDATE status=FAILED, provider_error_code, provider_error_category, safe error_message → COMMIT
                   then raise_error(502, PROVIDER_ERROR)   (row persists FAILED for resend; caller sees failure)
```

- **Idempotency-Key (formal — mandatory):** required on send; 48h TTL; reservation row PK `(workspace_id, idempotency_key)` on `whatsapp_idempotency_keys` (mirrors the payment/email key-table pattern, plus a fingerprint):
  - `request_fingerprint = sha256_hex(canonical_json(normalized_request))`, where `canonical_json` serializes the parsed request dict keys in sorted order, `None`/empty fields omitted, so equivalent payloads (any field order / spacing) hash identically.
  - **same key + same request** (fingerprint matches) → return the **existing result** (200), provider never called → retry-safe.
  - **same key + different request** (fingerprint differs) → **409 `IDEMPOTENCY_CONFLICT`** (new `ErrorCode`), nothing mutated.
  - Expired reservation → treated as fresh (new send under a new Txn 1).
  - **Tests assert provider invocation count `== 1`** for same-key retries and `0` for the conflict path — never merely `rows == 1`.
- **Resend** (`POST /{id}/resend`, OWNER/ADMIN, `30/minute`): allowed from **FAILED** and **QUEUED**; `SENT/DELIVERED/READ` → 200 no-op. Rows are processed with `FOR UPDATE` to serialize concurrent resends (single provider call). On resend:
  - INVOICE/QUOTATION: re-check lifecycle gate (§2.4) → re-render (current snapshot data) → re-upload → re-send → fresh `whatsapp_message_id`.
  - 🛠 **AR_STATEMENT resend (locked decision):** REGENERATE the statement using the **stored** `linked_entity_id` (client) + `statement_from`/`statement_to` with **current underlying accounting data** (this architecture has no immutable rendered snapshot; the stored period params are the replay key, the data is live). Explicitly NOT a byte-for-byte replay.
  - Error fields cleared on success; `QUEUED` still non-terminal (see next bullet).
- **🛠 QUEUED is NOT a background queue** (locked): synchronous `QUEUED → provider → SENT/FAILED` normally resolves within the request. A `QUEUED` row therefore means an **interrupted/incomplete synchronous send reservation** (e.g. process died between Txn 1 and the provider call). It is manually recoverable via resend — never pumped by any worker (there is no worker).

**Outbound `linked_entity_*` semantics (document clarity, review blocker 🛠):** on DOCUMENT sends the service **auto-populates** `linked_entity_type/linked_entity_id` from the resolved artifact (INVOICE→invoice id, QUOTATION→quotation id, AR_STATEMENT→client id) — they are derived, not user input, so `document_* ≡ linked_entity_*` by construction and can never diverge. On TEXT sends `linked_entity_*` is an optional user audit ref (workspace-validated; AR_STATEMENT/SUPPLIER_STATEMENT reference-only, no FK). **Field rule (model comment + doc):** `document_*` fields identify the generated outbound document artifact; `linked_entity_*` fields identify the business entity associated with the communication; they are not interchangeable.

### 2.7 Webhooks

**`GET /api/v1/webhooks/whatsapp`** (no IP limiter): Meta challenge — `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. `verify_token == WHATSAPP_WEBHOOK_VERIFY_TOKEN` → 200 `text/plain` echo challenge; mismatch → 403 `FORBIDDEN`.

**`POST /api/v1/webhooks/whatsapp`** (no IP limiter):
1. **Body-size guard first 🛠:** raw body read capped at `WHATSAPP_WEBHOOK_MAX_BODY_BYTES` (default 1 MB) → 413 `PAYLOAD_TOO_LARGE`. Prevents oversized public-payload abuse (separate from IP rate limiting).
2. Auth: `X-Hub-Signature-256 == "sha256=" + hmac_sha256_hex(WHATSAPP_APP_SECRET, raw_body)` → 401 `UNAUTHORIZED` on missing/mismatch. Raw body/logs never persisted.
3. 🛠 **Verify `metadata.phone_number_id`**: the payload's phone-number metadata must equal `WHATSAPP_PHONE_NUMBER_ID`. Mismatch → 200 with sanitized log and **zero rows created** (critical given a single-account deployment).
4. Status events (`statuses[]`: `{id, status}`): upsert OUTBOUND by `whatsapp_message_id` → `sent→SENT`, `delivered→DELIVERED` (+`delivered_at`), `read→READ` (+`read_at`), `failed→FAILED`. Unknown id → 200 no-op. Already-past-target → 200 no-op (idempotent).
5. Inbound messages (`messages[]`: `{from, id, type, text/caption}`) → §2.8.
6. **Response precision 🛠 (explicit):**
   - 401 — HMAC missing/mismatch
   - 403 — GET challenge token mismatch
   - 413 — body over cap
   - 200 — phone_number_id mismatch (dropped)
   - 200 — valid auth, unknown message id / unrecognized-but-legit event (no-op, sanitized log)
   - 200 — valid inbound processed
   A malformed payload that still verifies HMAC → 200 + sanitized log reason (never trigger a Meta retry storm by 4xx-ing post-auth).

### 2.8 Inbound → Enquiry (single transaction; dedup-safe; race-proof)

```
POST verified (§2.7) → for each inbound text/caption-bearing message (id = wa_message_id):
  if WhatsAppMessage(whatsapp_message_id=id) row already exists → 200 no-op (Enquiry already bound)
  one DB transaction:
    ├─ INSERT WhatsAppMessage(direction=INBOUND, message_type=TEXT|MEDIA, status=RECEIVED,
    │    from_number=canonical(from), message_body=text or caption, whatsapp_message_id=id,
    │    received_at=now, workspace_id=WHATSAPP_INBOUND_WORKSPACE_ID)
    └─ IF text/caption:
         client match: normalize(from) → single canonical phone match on Client.phone in the
           inbound workspace  → client_id = that client
           ZERO matches → client_id = NULL      (never auto-create a Client)
           MULTIPLE matches → client_id = NULL + sanitized audit/warn log (never guess)
         items_description = the text/caption  (ONLY ever from inbound text/caption)
         EnquiryService.create(..., existing session)  ← caller's session; source=WHATSAPP,
           status=NEW, contact_whatsapp=from, contact_name = matched Client.name else NULL,
           client_id (unique match only), whatsapp_message_id=id
           EnquiryService MUST NOT commit/rollback on its own when invoked from this ingestion;
           they are one unit — either both rows commit or neither commits.
    └─ COMMIT only at the WHATSAPP-webhook transaction boundary
  non-text / no caption → the WhatsAppMessage row is persisted (message_type=MEDIA, MEDIA rule §2.6:
    transport record only — NO media download, inspection, storage, or processing), NO Enquiry.
```

- **message_type on inbound:** a text message → `TEXT`. A media message **with a caption** → stored `TEXT` (caption becomes `message_body`; arguably it carries text). A media message **without a caption** → `MEDIA` (transport record only, no Enquiry). A media message **with a caption** NEVER stores `MEDIA` — the caption is text the Enquiry may need.

- **Atomicity lock (review blocker 🛠):** `WhatsAppService` owns the single transaction/session; `EnquiryService.create(existing_session)` participates in it and never independently commits/rollbacks during webhook ingestion. If the Enquiry insert fails, the whole transaction rolls back — no orphaned `WhatsAppMessage` with a missing Enquiry, and vice versa.
- **Dedup authority = DB constraints, not pre-checks (review blocker 🛠):** the global unique `whatsapp_message_id` on `WhatsAppMessage` (plus the unique `Enquiry.whatsapp_message_id`) is the final arbiter. `if existing: return` is a fast path only. A concurrent duplicate webhook delivery racing both pre-checks fails on the unique constraint → IntegrityError is converted to an idempotent 200 (the winner's rows stand). **Tested explicitly** (§6 T2).
- **No LLM; no extraction; no auto-Client; no reply automation.** `EnquiryService` remains the sole authority for numbering, defaults, validation, and creation invariants — ingestion supplies only the approved inbound fields.

---

## 3. API summary

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/comms/whatsapp/messages` | OWNER/ADMIN, `30/minute`, `Idempotency-Key` | send TEXT or DOCUMENT (§2.6) |
| GET | `/api/v1/comms/whatsapp/messages` | any member | filters: status, direction, message_type, linked_entity_type/id, to_number, created_at range; pagination |
| GET | `/api/v1/comms/whatsapp/messages/{id}` | any member | 404 cross-workspace |
| POST | `/api/v1/comms/whatsapp/messages/{id}/resend` | OWNER/ADMIN, `30/minute` | §2.6 |
| GET | `/api/v1/webhooks/whatsapp` | challenge token | §2.7, no IP limiter |
| POST | `/api/v1/webhooks/whatsapp` | `X-Hub-Signature-256` | §2.7, no IP limiter |

Router `app/routers/comms_whatsapp.py`, wired `app.include_router(comms_whatsapp_router, prefix="/api/v1")`.

---

## 4. Module boundaries

| Layer | Owns |
|---|---|
| `routers/comms_whatsapp.py` | HTTP, RBAC, rate limit, wrapper |
| `services/whatsapp_service.py` | workflow §2.6, document resolution + render orchestration, resend, webhook intake §2.7/§2.8 |
| `services/pdf_service.py` | `DocumentRenderer` (`build_sections` + `render`) |
| `services/providers.py` | `WhatsappProvider` (same file as `ResendProvider`) |
| `services/enquiry_service.py` | Enquiry creation (session-injection; unchanged invariants) |
| `utils/phones.py` | `normalize_phone_to_e164` (single canonical utility; unit-tested) |
| `models/whatsapp_message.py` | `WhatsAppMessage` + 3 enums; `WhatsAppIdempotencyKey` (workspace PK + fingerprint) |
| `schemas/whatsapp_comms.py` | send/list/resend schemas + filters |
| `alembic/versions/xxxx_add_whatsapp_messages.py` | tables + `create_type` enums |

New files < 500 lines each. All imports top of file. No mid-file E402.

---

## 5. Alembic (this wave)

- Migration `_add_whatsapp_messages`: `create_type` for `whatsappdirection`, `whatsappmessagestatus` (incl. **RECEIVED**), `whatsappmessagetype`; `whatsapp_messages` table per §2.6/§2.8 with `(workspace_id, created_at)` index and **global unique `whatsapp_message_id`**, `received_at` DATETIME, `statement_from`/`statement_to` DATE columns, `provider_error_code`/`provider_error_category`; plus `whatsapp_idempotency_keys` (workspace_id + idempotency_key PK, `request_fingerprint` varchar(64), `message_id` FK, `created_at`, `expires_at` 48h — §2.6). `down_revision = "3d3f24d6ee00"`.
- Verify: `alembic upgrade head && downgrade -1 && upgrade head` round-trip + `alembic check` clean. Re-point guardian pins `test_pdc.py`/`test_pricing.py`.
- **Versions (acceptance gates, not guesses):** Meta Graph API version verified from official Meta docs; `reportlab` current stable + `pip-audit` clean — both before implementation.

---

## 6. Tests — `tests/test_whatsapp_comms.py` + `tests/test_pdf_service.py`

**PDF (`test_pdf_service.py`):**
- `build_sections` assertions (exact, not `%PDF-` only): invoice number, client/buyer name from snapshot when SENT/ISSUED, TRN, line descriptions, quantity, UOM, unit price, subtotal, VAT, total, currency, document date — all match the injected service dict **verbatim**.
- **No-recompute proof:** service dict carries original `subtotal/vat/total`; mutating any one of them in the dict changes the section by exactly that value with no dependency on the others (renderer prints fields, never adds). I.e. assert output values == input values even where recomputation would differ.
- `render(...)` returns `data[:5] == b"%PDF-"`, `application/pdf`, correct filename. Unsupported doc → 400 `UNSUPPORTED_DOCUMENT`.

**WhatsApp (`test_whatsapp_comms.py`):**
1. TEXT send happy path (spy adapter): QUEUED→SENT, `whatsapp_message_id`, no `media_id`/`document_*`.
2. DOCUMENT send happy path: spy captures `upload_media(%PDF- bytes, INV-*.pdf)` → `send_message(media_id, filename, caption)`; row SENT with `document_type`/`document_filename`; `linked_entity_*` auto-populated == document artifact.
3. Dry-run: zero HTTP (spy records none), `status=SENT`, `simulated=True`, provider ids `None`.
4. Provider error: row FAILED + only normalized `provider_error_code/category` + safe message persisted (assert raw provider text NOT in the row); endpoint 502 `PROVIDER_ERROR`.
5. Idempotency: same key + same request twice → same row, **provider invocation count `==1`** (assert spy count, not just `rows==1`); **same key + different request → 409 `IDEMPOTENCY_CONFLICT`**, provider count `0`, nothing persisted; expired reservation → fresh send allowed.
6. Resend FROM FAILED → SENT (fresh ids); SENT → 200 no-op, **provider count unchanged**; concurrent resends serialized by `FOR UPDATE` (single provider call).
7. **AR_STATEMENT resend regenerates with stored `linked_entity_id`+`statement_from/to`** (spy records re-render call with the original params; current-data regeneration documented).
8. Lifecycle gates: DRAFT / CANCELLED invoice → 403 `INVALID_STATE`; DRAFT / REJECTED / EXPIRED quotation → 403; SENT/PAID/OVERDUE invoice + SENT/ACCEPTED/CONVERTED quotation → OK. **These use the real enums, not new lists.**
9. Recipient authority: DOCUMENT request with a `to_number` field → rejected (schema `extra=forbid`); DOCUMENT send to a client with `phone` that cannot normalize (e.g. bare local "0501…") → 422; derived number used → spy asserts `to == canonical(client.phone)`.
10. RBAC: MEMBER send/resend → 403 `INSUFFICIENT_PERMISSIONS`; MEMBER list/get → 200.
11. Webhook GET challenge: valid verify-token echoes `hub.challenge`; wrong → 403.
12. Webhook POST HMAC: missing/wrong signature → 401; good → processed.
13. **T1 🛠 wrong `metadata.phone_number_id`** (valid HMAC) → 200, zero `WhatsAppMessage`, zero Enquiry.
14. **T2 🛠 concurrent duplicate webhook**: same message id in two simultaneous requests → exactly 1 message + 1 Enquiry (unique-constraint race lands as idempotent success).
15. **T3 🛠 inbound status**: persisted `direction=INBOUND`, `status=RECEIVED`, `received_at` set — never `SENT`.
16. **T4 🛠 ambiguous client match** (two Clients with same canonical phone) → `client_id=NULL`, no guessing, sanitized audit log.
17. Unknown contact → `client_id=NULL`, no Client row created; known unique match → linked; unset `WHATSAPP_INBOUND_WORKSPACE_ID` → dropped (200, no rows).
18. Dedup: repeated delivery/read events idempotent; same message id twice → one row + one Enquiry.
19. Inbound media-only (image, no caption) → row persisted (`message_type=MEDIA`), NO Enquiry.
20. **T7 🛠 provider never hits real HTTP in tests** — assert `httpx.AsyncClient` is fully patched (zero real-network calls) across dry-run and spy modes.
21. **T8 🛠 no transaction leakage**: force Enquiry insert to fail → assert `WhatsAppMessage` also not persisted (single transaction, both-or-neither).
22. Body-size guard: oversized raw body → 413; list filters + pagination math; cross-workspace get → 404 (never 403).
23. Phone normalization unit tests (`test_phones.py`): `+971501234567` stays; spaces/dashes/parens stripped; `00971501234567` → `+971501234567`; bare local `0501234567` → `None` (no guess); empty/garbage → `None`.
24. Guardian pin: head asserted after migration.

---

## 7. Coder checklist

1. Report first (`backend-execution-report.md` Wave 27 section).
2. Verify Meta Graph API version (official docs) + ReportLab current stable (`pip-audit` clean) — **record both in the report**; then `.env.example` + `config.py` WHATSAPP_* + body-cap keys.
3. `utils/phones.py` + unit tests; model + 3 enums + migration (+ round-trip + `alembic check` + guardian re-pin).
4. `pdf_service.py` → `whatsapp_service.py` → `providers.py` `WhatsappProvider` → schemas → router; wire in `main.py`; `ErrorCode.UNSUPPORTED_DOCUMENT` + `IDEMPOTENCY_CONFLICT`. `EnquiryService` session-injection (no self-commit during ingestion).
5. Tests §6; targeted + full suite; ruff + black.
6. `STATE.md`; commit (Wave 27).
7. Then Wave 28 (VAT pack) addendum.
