# InvoiceSaaS Current-State Map — 2026-08-31

**Project:** InvoiceSaaS (`rezorpay_pro`)
**Target:** Production UAE electrical-market B2B SaaS MVP
**Scope:** Mapping only. No implementation.
**Companion GSD docs:** `.planning/codebase/STACK.md`, `INTEGRATIONS.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `TESTING.md`, `CONCERNS.md`

**Planning files that do not exist:** `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`

---

## Executive snapshot

The repo is a **working multi-tenant FastAPI + PostgreSQL AR core** (auth, clients, invoices, gapless `INV-YYYY-XXXX`, idempotent payments, PDC fields) plus a **partial procurement ERP** (products, suppliers, warehouses, PR, RFQ headers, SPO lifecycle, GRN, supplier-invoice 3-way match) and a **Vite/React operator UI**.

It is **not** yet a UAE electrical quote-to-cash product: no quotations, LPO/CPO, delivery notes, credit notes, BOQ/specs, Arabic, FTA VAT pack, email/WhatsApp delivery, or Razorpay. Product/supplier APIs are create/list stubs versus their models. Invoice “send” does not send.

Treat `.agents/MASTER_PLAN_V3.md` and `architecture/*.md` as **target specs**. Treat `backend/app/` + `frontend/src/` as **runtime truth**. Wave IDs in Alembic (Wave 7 = inventory) **do not match** V3 wave IDs (Wave 7 = enquiry).

---

## 1. Backend — exists vs missing

### 1.1 Working (HTTP + DB)

| Area | Paths | Notes |
|------|--------|--------|
| App entry | `backend/app/main.py` | CORS localhost; JSON error wrapper; mounts all routers |
| Config | `backend/app/config.py` | JWT, DB, Redis URL unused by limiter |
| DB engine | `backend/app/database.py` | asyncpg pool; sqlite branch present but forbidden for tests |
| Logging | `backend/app/logging.py` | JSON + request id |
| Health | `backend/app/routers/health.py` | `/health`, `/live`, `/ready` |
| Auth JWT | `backend/app/auth/router.py`, `utils.py`, `dependencies.py` | register/login/refresh/me; bcrypt; workspace on register |
| Clients CRUD | `backend/app/routers/clients.py`, `models/client.py`, `schemas/clients.py` | paginated list, search, soft delete; `tax_id` not labeled TRN |
| Invoices | `backend/app/routers/invoices.py`, `services/invoice_service.py`, `models/invoice.py` | create/list/get/update DRAFT/soft-delete/send/void |
| Gapless INV | `services/invoice_number.py`, `models/invoice_counter.py` | `SELECT FOR UPDATE`; `INV-YYYY-XXXX` |
| Payments | `routers/payments.py`, `services/payment_service.py`, `models/payment.py` | Idempotency-Key 48h; no overpay; methods CASH/BANK_TRANSFER/CHEQUE/PDC/CREDIT_CARD |
| Audit events | `models/invoice_event.py`, `services/audit_service.py` | invoice lifecycle JSONB `metadata_log` |
| Workspace settings | `routers/workspaces.py`, `models/workspace.py` | TRN, logo_url, WhatsApp, VAT rate default 5.00, credit flags (unenforced) |
| Dashboard | `routers/dashboard.py` | receivables, PR/RFQ/GRN counts |
| Products list/create | `routers/products.py`, `models/product.py` | categories/brands/UOM/products |
| Suppliers list/create | `routers/suppliers.py`, `models/supplier.py` | root supplier incl. `trn`, payment_terms |
| Inventory | `routers/inventory.py`, `models/inventory.py` | warehouses, bins, levels, adjust + ledger |
| PR list/create | `routers/procurement.py`, `models/procurement.py` | unsafe numbering |
| RFQ list/create | `routers/rfq.py`, `models/rfq.py` | header+items only; awards unused |
| SPO lifecycle | `routers/spo.py`, `services/spo_service.py`, `spo_number.py` | gapless SPO; JWT-scoped after stabilization |
| GRN lifecycle | `routers/grn.py`, `services/grn_service.py`, `models/grn.py` | receive/inspect/post stock; unsafe numbering |
| Supplier invoices | `routers/supplier_invoices.py`, `services/supplier_invoice_service.py` | 3-way match + approve |
| Rate limit | `limiter.py` | in-memory slowapi |
| Idempotency table | `models/idempotency_key.py` | payments only |

### 1.2 Stubbed / incomplete

| Area | Evidence |
|------|----------|
| Invoice send | `routers/invoices.py` `sent_method="email"` — no SMTP/Resend |
| SPO send | state transition only (`routers/spo.py`) |
| Product nested resources | tables `product_identifiers`, `product_uom_conversions`, `product_prices` — no routes |
| Product update/delete/detail/search | missing in `routers/products.py` |
| Supplier contacts/banks/docs/products | models only |
| RFQ responses, quote items, awards | models in `models/rfq.py` — no routes |
| SPO amendments / delivery schedules | models in `models/spo.py` — no routes |
| GRN purchase return | `pass` in `grn_service.py` |
| OCR on AP invoice | `ocr_job_id`, `ocr_extracted` unused |
| OVERDUE status | enum only |
| RBAC | `UserRole` never checked |
| Redis | config + Compose; not used |
| Payment gateway id | `gateway_transaction_id` unused |
| Health 503 import | mid-function import |

### 1.3 Missing (no models, no routers)

- Razorpay / any payment gateway SDK or webhooks
- Email (Resend), email templates, `EmailLog`
- WhatsApp webhook / outbound PDF
- Enquiry / Quotation / Customer PO (LPO) / Delivery Order
- Credit note / Debit note / Sales return / Purchase return entities
- Supplier payment / AP aging / statements
- Stock reservation / transfer / count
- VAT FTA report
- Multi-currency FX engine (currency fields exist as strings)
- Arabic translations
- Celery/RQ workers
- File upload (logo/docs are URL strings)

---

## 2. Frontend — exists vs missing

**Stack:** Vite 8, React 19, TS, TanStack Query, RHF+Zod, axios, CSS modules, `@react-pdf/renderer`.
**Entry:** `frontend/src/main.tsx`, routes `frontend/src/App.tsx`, nav `frontend/src/components/Layout.tsx`.
**Auth:** `contexts/AuthContext.tsx`, `components/AuthGuard.tsx`, `pages/Login.tsx`, `Register.tsx`.
**API base:** `VITE_API_URL` in `frontend/src/api/client.ts`.

### 2.1 Pages present

| Route | File | Status |
|-------|------|--------|
| `/` | `pages/Dashboard.tsx` | Stats cards (AED receivables, PRs, RFQs, GRNs) |
| `/clients` | `pages/Clients.tsx` | CRUD-style list |
| `/invoices` | `pages/Invoices.tsx` | Create/edit draft, send, void, payment modal, PDF download |
| `/settings` | `pages/Settings.tsx` | Name, TRN, WhatsApp, tax %, credit defaults |
| `/products` | `pages/Products.tsx` | **List only**; Add = alert stub |
| `/suppliers` | `pages/Suppliers.tsx` | List/create-level UI |
| `/inventory` | `pages/Inventory.tsx` | Warehouses/levels |
| `/procurement` | `pages/Procurement.tsx` | PR list/create |
| `/rfq` | `pages/RFQ.tsx` | RFQ list/create |
| `/spo`, `/spo/new`, `/spo/:id` | `SPO.tsx`, `SPOBuilder.tsx`, `SPODetail.tsx` | Builder + detail workflow |
| `/grn`, `/grn/:id` | `GRN.tsx`, `GRNDetail.tsx` | Receiving + disposition |
| `/supplier-invoices`, `/:id` | `SupplierInvoices.tsx`, `SupplierInvoiceDetail.tsx` | AP match UI |

### 2.2 Frontend missing

- Quotations, LPO, delivery notes, credit notes, ageing, VAT report, statements
- Arabic/RTL, i18n
- Pagination UI (invoice list will silently cap at 20)
- Product create/edit, identifiers, conversions, prices, electrical specs
- Supplier KYC (trade license, VAT cert, IBAN)
- Email/WhatsApp send from UI (PDF is local download)
- Tests (no Vitest/Playwright)
- Frontend Docker / CI build
- `recharts` unused on Dashboard
- Customer TRN on PDF bill-to (`components/pdf/InvoicePDF.tsx` — company TRN only)

---

## 3. Database — models, migrations, rules

### 3.1 Models registered (`backend/app/models/__init__.py`)

Workspace, User, Client, Invoice, InvoiceItem, Payment, InvoiceEvent, InvoiceCounter, IdempotencyKey, Category, Brand, UnitOfMeasure, Product, ProductIdentifier, ProductUOMConversion, ProductPrice, Supplier + Contact/Bank/Document/Product, Warehouse, WarehouseBin, InventoryLevel, InventoryTransaction, ProcurementRequest(+Item), RFQ family, SupplierPurchaseOrder(+Item), SPOCounter, GoodsReceiptNote, GRNItem, SupplierInvoice(+Item).

**Also defined in `spo.py` but not exported in `__init__.py`:** `SPODeliverySchedule`, `SPOAmendment`, `SPOAmendmentLine`, `SPOStatusHistory` — if they are `table=True`, Alembic still needs them imported. `spo.py` is imported via `SupplierPurchaseOrder`; nested classes in same module are registered when `spo.py` loads. Confirm via `import app.models`.

### 3.2 Migrations (`backend/alembic/versions/`)

Linear chain including: `001_initial_schema`, `13b9c7b44074_baseline_v2`, workspace settings (`96b45ccabfb7`, `06c9b4b1dcda`), product `d3e4c7fdb29f`, supplier `784076ef11b9`, payments/PDC `e217c0bc3af7`, inventory `d41016da5030`, PR `0abb440e0fc9`, RFQ `64d6ac9e5b49`, SPO `345906985988` + `63f069419100`, GRN `2a98d90a2f79` + `5f24e4eb1428`, supplier invoices `633b2df1fb55` + decimal fix `12bdad2ae924`, spo counters `b7e2f4a9c1d3`, client email nullable `4ec511b03a6f`, supplier FK fix `9ab488fc07a8`.

CI: `alembic upgrade head` + `alembic check`.

### 3.3 Rules compliance

| Rule | Status |
|------|--------|
| No SQLite in tests | Tests use Postgres `_test`. `database.py` still has sqlite connect_args. |
| Alembic for schema | Yes in prod/Compose. Tests use `create_all`. |
| Money `Decimal(12,2)` | Invoices/payments/workspace/AP yes. SPO/GRN qty `Numeric(12,4)`. Inventory qty `Numeric(12,2)`. |
| Gapless INV | Yes, `FOR UPDATE` |
| Gapless SPO | Yes |
| Gapless PR/RFQ/GRN | **No** (count+1) |
| Payments immutable | **Partial** — PUT for PDC status |
| Soft deletes | Workspace, Client, Invoice, Product masters, Supplier. Not on Payment, GRN, SPO. |
| `workspace_id` on entities | Yes on business tables; Payment scoped via invoice |

### 3.4 ENUMs (runtime)

InvoiceStatus, PaymentMethod, PDCStatus, PaymentStatus, UserRole, PR*/RFQ*/SPO*/GRNStatus, SupplierInvoiceStatus, MatchResult, TransactionType, InvoiceEventType.

---

## 4. Tests

| Kind | Location | Status |
|------|----------|--------|
| Unit (isolated services) | — | Not separated |
| Integration HTTP + Postgres | `backend/tests/*.py` | 19 tests: auth, isolation (5), numbering (4), SPO (2), GRN (2), e2e SPO/GRN/3way |
| Browser E2E | — | Missing |
| Frontend unit | — | Missing |
| Limiter | `tests/conftest.py` | Disabled for suite |
| Leftovers | `backend/test_e2e.py`, `test_step2_*.py` | Not collected |

**Not tested:** invoice send/void matrix, overpay, idempotency replay, products CRUD, inventory, PR/RFQ, workspace PUT, dashboard, RBAC.

---

## 5. DevOps

| Item | Path | Status |
|------|------|--------|
| Compose | `docker-compose.yml` | postgres 16 (`5434`), redis 7 (`6380`), api `8000` + alembic+reload |
| API Docker | `backend/Dockerfile` | multi-stage, gunicorn 4 workers, non-root |
| Frontend Docker | — | Missing |
| CI | `.github/workflows/ci.yml` | lint ruff/black app; test postgres; pip-audit non-blocking |
| Frontend CI | — | Missing |
| Pre-commit | `.pre-commit-config.yaml` | black + ruff + hygiene |
| Deploy/CD/SSL/APM | — | Missing |
| Env templates | `backend/.env.example`, `frontend/.env.example` | Names only in this report |
| CORS | `main.py` | localhost only |

---

## 6. UAE electrical B2B domain

| Need | Runtime | Notes |
|------|---------|--------|
| VAT 5% default | Partial | `Workspace.default_tax_rate` Decimal 5.00; invoice line `tax_rate`; SPO `vat_rate` |
| Seller TRN | Partial | Workspace `trn`; Settings + PDF header |
| Buyer TRN | Weak | Client `tax_id`; not on PDF bill-to; not named TRN |
| AED | Yes | Invoice/SPO/product price defaults; UI prefixes AED |
| Quotations | Missing | Spec in `architecture/domain-model.md` |
| LPO / Customer PO | Missing | |
| Delivery notes / DO | Missing | GRN `delivery_reference` is **supplier inbound**, not customer DO |
| BOQ / item specs | Missing | Product has name/SKU/tax/reorder only — no voltage, IP, core, brand spec sheet |
| Credit terms / trade credit | Partial | Supplier `payment_terms` string; workspace credit days **not enforced**; no client credit limit field |
| WPS | N/A | Correctly out of scope |
| Arabic + English | Missing | English UI/PDF Helvetica |
| Emirates / city | Weak | Supplier `city`/`country` optional; client `address` free text; no Emirate enum |
| FTA VAT return | Missing | |
| Cheque / PDC | Partial | Model + PUT lifecycle; no ageing dashboard |
| 3-way AP match | Yes | Supplier invoice vs SPO/GRN |

---

## 7. Known issues, TODOs, incomplete docs, unimplemented plans

### 7.1 Documented as resolved (do not re-open without evidence)

`.claude/CLAUDE.md` Known Issues + `.agents/reports/stabilization-execution-report.md`: VOIDED enum, audit metadata, CI live-server, client tax_id/email, ENUM drift. Stabilization also fixed SPO IDOR and gapless SPO.

### 7.2 Open (code)

See `.planning/codebase/CONCERNS.md`. Highest for UAE MVP:

1. No sales documents (quote → LPO → DO → CN)
2. Product master + invoice lines not catalog-backed
3. Send is a status flag
4. PR/RFQ/GRN numbering races
5. Credit control UI without engine
6. Invoice list pagination vs frontend
7. No Arabic, no buyer TRN on PDF
8. No production hosting/CORS/secret-guard

### 7.3 Plans vs code

| Doc | Claim vs reality |
|-----|------------------|
| `.agents/MASTER_PLAN_V3.md` | 30-wave ERP; status “awaiting approval”; Wave numbers ≠ Alembic wave names |
| `.agents/reports/README.md` | Wave 0 IN PROGRESS, Wave 1+ PENDING — **stale** vs implemented inventory/SPO/GRN |
| `.hermes/plans/2026-08-27_153000-wave3-product-master.md` | Product CRUD still incomplete — **still accurate** |
| `architecture/wave0-execution-report.md` | api-contracts/ERD PENDING — **files now exist** on disk |
| `IDEA.md` | “SaaS product MVP” only |
| V3 locked stack | Resend, Gemini OCR, Meta WhatsApp, React 18 — **not how the repo runs** |

### 7.4 Architecture specs (target, largely unimplemented)

`architecture/domain-model.md`, `business-rules.md`, `state-machines.md`, `api-contracts.md`, `entity-relationship.md`, `inventory-rules.md`, `procurement-rules.md`, `edge-cases.md`, plus module docs: `supplier-architecture.md`, `rfq-architecture.md`, `spo-architecture.md`, `grn-architecture.md`, `procurement-request-architecture.md`, `supplier-invoice-architecture.md`.

---

## API surface (implemented)

```
POST/GET    /auth/register|login|refresh|me
GET         /health|/health/live|/health/ready
GET         /
CRUD        /api/v1/clients
CRUD+send+void  /api/v1/invoices
POST/GET    /api/v1/invoices/{id}/payments  (+ PUT payment, GET balance)
GET/PUT     /api/v1/workspaces/me
GET         /api/v1/dashboard/stats
GET/POST    /api/v1/products[/categories|/brands|/uom]
GET/POST    /api/v1/suppliers
GET/POST    /api/v1/inventory/warehouses[+bins], GET levels, POST adjust
GET/POST    /api/v1/procurement/requests
GET/POST    /api/v1/rfq/requests
POST/GET    /api/v1/spos/ + submit-approval|approve|send|acknowledge|cancel
POST/PATCH/GET /api/v1/grns + receiving/items/cancel/reconciliation
POST/GET    /api/v1/supplier-invoices + submit-matching|resolve-discrepancy|approve
```

---

## Recommended next-build order (mapping guidance only)

For a **UAE electrical B2B MVP**, the gap vs this map is sales-cycle + catalog + compliance, not more AP matching:

1. Finish Product Master (Hermes plan) + electrical spec fields + invoice line `product_id`
2. Client TRN/Emirate/credit terms; PDF bilingual-ready with buyer+seller TRN
3. Quotation (+ revision) → convert to invoice; optional LPO attachment
4. Delivery note; credit note
5. Real send (email first)
6. Gapless counters for PR/RFQ/GRN; pagination; invoice tests
7. Production CORS/secrets/CI frontend build

Do not start Razorpay unless card-capture is an explicit MVP requirement — trade credit + cheque/PDC already match the electrical wholesaler pattern.

---

*Map date: 2026-08-31*
