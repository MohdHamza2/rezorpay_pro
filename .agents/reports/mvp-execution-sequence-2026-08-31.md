# InvoiceSaaS MVP Execution Sequence

**Date:** 2026-08-31
**Author:** Swarm coordinator (sequential planning pass only)
**Repo:** `C:\Users\Hamza\rezorpay_pro`
**Product (locked):** InvoiceSaaS (`rezorpay_pro`) — multi-tenant B2B trade-operations SaaS for the UAE electrical market
**Pass type:** SEQUENTIAL PLANNING ONLY — no product code, no new product, no project init

---

## Hard constraints for every subsequent agent

1. **Do not run** `claude-flow init-project` (or any equivalent “new project” bootstrap) on this repo. It is an existing product with a backend, frontend, Alembic chain, and architecture lock.
2. **Do not invent a second product.** Ignore `IDEA.md` as a greenfield seed (`SaaS product MVP` is not a new app). The identity is InvoiceSaaS.
3. **Do not run** `/gsd-new-project`. `.planning/` does not exist; starting GSD as a new project would rewrite identity and invent a second roadmap. See §7.
4. **Do not invent business rules.** Ambiguity → stop, log in `.agents/reports/`, wait for human or architect addendum (`MASTER_PLAN_V3.md` Non-Negotiable Rule).
5. Schema changes require **Alembic**. Tests use **PostgreSQL 16**, never SQLite. Money is **`Decimal` / `Numeric(12,2)`**, never float.

---

## 1. Current project identity and what is already shipped

### Identity (source of truth: `.claude/CLAUDE.md` + `.agents/MASTER_PLAN_V3.md`)

| Field | Value |
|---|---|
| Name | InvoiceSaaS (`rezorpay_pro`) |
| Market | UAE-first electrical wholesale / B2B trading |
| Default currency / tax | AED; workspace `default_tax_rate` defaults to **5.00** (UAE VAT); TRN on `Workspace` |
| Stack | FastAPI + SQLModel + PostgreSQL 16 + asyncpg + Alembic; Vite + React + TypeScript; JWT workspace tenancy |
| Architecture | Monolith, service layer, `workspace_id` on every business entity |
| Git | Branch `master`; latest feature commit `d3a7719` (`feat(wave-2): workspace settings…`) |

This is **not** an invoice-only app. V3 defines four domains (Product, Customer/Sales/AR, Inventory/Warehouse, Supplier/Procurement/AP) for electrical trade operations. The frontend shell is already labelled InvoiceSaaS and routes those domains.

### GSD / `.planning`

**`.planning/` does not exist** (no `STATE.md`, no `ROADMAP.md`, no `PROJECT.md`). There is **no GSD phase pointer**. Do not treat this as a blank GSD workspace.

Planning source of truth today:

- `.agents/MASTER_PLAN_V3.md` — 30-wave plan (Wave 0–29)
- `architecture/` — Wave 0 specification set
- `.agents/reports/` — execution trail (index is stale; see §1.3)
- `.hermes/plans/2026-08-27_153000-wave3-product-master.md` — **stale** Wave 3 gap list (use as hints, not as a migration script)

### 1.1 Shipped (evidence)

**Core AR (Step 2.5 + Wave 5)**

| Area | Evidence |
|---|---|
| Auth JWT register/login/refresh | `backend/app/auth/`; `backend/tests/test_auth.py` |
| Clients, invoices, payments | `backend/app/routers/{clients,invoices,payments}.py`; `services/invoice_service.py`, `payment_service.py` |
| Gapless invoice numbers + row locks | `invoice_number.py`; `tests/test_concurrent_numbering.py` |
| Payment idempotency | `models/idempotency_key.py`; payment router requires key |
| PDC / method fields | `models/payment.py` (`PaymentMethod`, `PDCStatus`); Wave 5 migration `e217c0bc3af7` |
| Wrapper responses | CLAUDE.md rule; SPO wrapped in P4 (`fd4b351`) |

**Workspace (Wave 2)**

- Model: `Workspace.trn`, `default_tax_rate`, credit-hold flags, SPO tolerances (`models/workspace.py`)
- API: `GET/PUT /api/v1/workspaces/me` (`routers/workspaces.py`)
- Migrations: `96b45ccabfb7` (TRN/tax) then later `06c9b4b1dcda` (credit-warning / block flags / price tolerance) — **linear, not a fork**
- UI: `frontend/src/pages/Settings.tsx`

**Product master (Wave 3) — schema yes, product DoD no**

- Models including identifiers / UOM conversion / prices: `backend/app/models/product.py`
- Migration **in the live linear chain**: `d3e4c7fdb29f` revises `96b45ccabfb7`; Wave 4 (`784076ef11b9`) revises `d3e4c7fdb29f`
- Router is **list + create only** (no GET-by-id, update, soft-delete, search, pagination, identifier/conversion/price endpoints): `routers/products.py`
- Frontend list only; Add Product is `alert('Add Product UI coming soon')`: `frontend/src/pages/Products.tsx`
- **No** `backend/tests/test_products.py`

**Supplier + procurement + inbound + AP match (implementation waves 4, 7–15 / V3 12–16 + 21)**

| Area | Routers / services | Tests |
|---|---|---|
| Suppliers | `routers/suppliers.py` | isolation in `test_multi_tenant_isolation.py` |
| Inventory / warehouses / bins | `routers/inventory.py`, `models/inventory.py`, migration `d41016da5030` | used by GRN e2e |
| Procurement requests | `routers/procurement.py`, migration `0abb440e0fc9` | — |
| RFQ | `routers/rfq.py`, migration `64d6ac9e5b49` | — |
| SPO + gapless counters | `routers/spo.py`, `spo_number.py`, `b7e2f4a9c1d3` | `test_spo.py`, `test_e2e_spo.py` |
| GRN + stock post | `routers/grn.py`, `grn_service.py` | `test_grn.py`, `test_e2e_grn.py` |
| Supplier invoice + 3-way match | `routers/supplier_invoices.py`; Decimal fix `12bdad2ae924` | `test_e2e_3way_match.py` |

**Frontend shell (Vite + React, not missing)**

- Routes: Dashboard, Clients, Invoices, Settings, Products, Suppliers, Inventory, Procurement, RFQ, SPO (+ builder/detail), GRN (+ detail), Supplier invoices — `frontend/src/App.tsx`, `Layout.tsx`
- Auth + TanStack Query: `contexts/AuthContext.tsx`, `api/*`
- Invoice PDF: `components/pdf/InvoicePDF.tsx`
- `npm run build` was green in Wave 1 / P2 reports
- **No frontend unit tests, no Playwright/Cypress** (`frontend/package.json` has `dev` / `build` / `lint` only)

**Stabilization + Wave 1**

- P0–P4 complete (`stabilization-execution-report.md`; merge onto `master`)
- Wave 1: httpx/TestClient, `toFixed` null-safety, isolation + concurrent numbering tests (`wave-1-execution-report.md`)
- Wave 1.1: `fix(wave-1.1): bcrypt upgrade + gapless numbering race` (`00fc498`); `requirements.txt` has `bcrypt==4.2.0`

**Alembic head (linear)**

```
001 → 13b9c7b44074 → 4ec511b03a6f → 96b45ccabfb7 → d3e4c7fdb29f
  → 784076ef11b9 → e217c0bc3af7 → d41016da5030 → 0abb440e0fc9
  → 64d6ac9e5b49 → 345906985988 → 2a98d90a2f79 → 63f069419100
  → 5f24e4eb1428 → 633b2df1fb55 → 9ab488fc07a8 → 12bdad2ae924
  → b7e2f4a9c1d3 → 06c9b4b1dcda  (HEAD)
```

Docker API starts with `alembic upgrade head` (`docker-compose.yml`). CI lint → pytest on ephemeral PostgreSQL 16 (`.github/workflows/ci.yml`).

**Pytest inventory (API, not browser):** 9 files under `backend/tests/`, ~18 `test_*` functions. Isolation covers client/invoice/payment/product/supplier + SPO. **Not covered:** product CRUD, identifier/UOM/price APIs, RFQ, procurement router, inventory router, payment PUT/immutability, Decimal rounding, browser E2E.

### 1.2 Not shipped (V3 waves still ahead — do not start these this pass)

Per `MASTER_PLAN_V3.md` vs tree: **no** Enquiry, Quotation, Customer PO/OCR, credit-control **engine** (settings exist, `Client` has no credit fields), full PDF pack, email/Resend, WhatsApp, stock reservations/transfers/counts, supplier **AP payments**, Delivery Order, AR statements, returns/credit-debit notes, VAT FTA export, India GST, production hardening.

Credit control was verified **not implemented** in Wave 1 T4 (`wave-1-execution-report.md`). Keep it **after** Product Master DoD unless mapper/architect promote it with a written rule set.

### 1.3 Stale documents (do not execute blindly)

| Artifact | Why stale |
|---|---|
| `.agents/reports/README.md` Wave table | Still “Wave 0 IN PROGRESS / Wave 1 PENDING”; git shows Wave 0 docs + Wave 1/2 commits |
| `.hermes/plans/…wave3-product-master.md` | Tells coder to set `d3e4c7fdb29f.down_revision = 06c9b4b1dcda`. That would **break the linear chain**. Product migration is already an ancestor of HEAD. Gaps that **remain true**: incomplete schemas/router/UI, no product tests |
| `database-agent.md` “current chain” | Still mentions only `001` → `d0be13f0ca49` |
| `backend-agent.md` Known Issues | VOIDED/audit/CORS items resolved in P4; do not re-fix |
| Tests using `SQLModel.metadata.create_all` | Fine for current suite; **not** a substitute for Alembic in production |

### 1.4 Next unplanned / unexecuted **V3** phase

**MASTER_PLAN_V3 Wave 3 — Product Master — is the next phase to finish to Definition of Done**, not Wave 6+ sales modules.

Wave 3 schema landed; **DoD is unmet** (pagination, detail/update/soft-delete, identifiers, UOM conversions, prices, UAE electrical fields in the **contract**, tests, real UI). That is the first executable slice after architecture lands.

Wave numbering in historical reports (inventory as “Wave 7”, procurement as “Wave 8”, …) is **implementation chronology**, not V3 sequence. Future work uses **V3 wave numbers**.

---

## 2. Ordered workstreams (every work package)

Every package, including WP-1–WP-3, follows this order. Do not skip left-to-right.

```
Plan → Architecture → Implement → Test (pytest + browser E2E) → Review → Commit
```

| Step | What happens | Stop condition |
|---|---|---|
| **Plan** | Coordinator (this doc) + mapper evidence: scope, files, risks, “not in scope” | Human or parent confirms WP is the next one |
| **Architecture** | Architect files an addendum under `architecture/` resolving model↔contract drift. **No coder until this exists.** | Addendum answers every ambiguity listed in §5; no invented rules |
| **Implement** | Coder (backend/API/services) and/or frontend; Database Agent **role** for models + Alembic only | Matches addendum; `black` + `ruff`; reports updated first |
| **Test** | `gsd-debugger` owns failing pytest; frontend + browser tools own E2E against running API+UI | PostgreSQL only; new endpoints have isolation tests; browser path exercised |
| **Review** | Reviewer: tenancy, Decimal, Alembic, payment immutability, no SQLite, no wrapper/pagination regressions | Blocking findings back to coder; no “fix in next wave” for P0 |
| **Commit** | Only when the **user** asks. Pre-commit hooks stay on. No `--no-verify`. | Message states *why*; no `.env` / secrets |

CI already encodes lint → test. Browser E2E is **not** in CI yet; WP-3 introduces it locally first (do not invent a second CI product).

---

## 3. Specialist ownership

Project roster (`.agents/AGENTS.md`) maps onto the specialists the parent will spawn:

| Step | Specialist to spawn | Project owner / notes |
|---|---|---|
| Plan | **coordinator** (this pass) | Uses mapper output; does not code |
| Architecture | **architect** | Reads `architecture/*` + live models; writes addendum. Database Agent **consulted** for Alembic/ENUM; architect decides, coder applies |
| Implement (API/services) | **coder** | `.agents/backend-agent.md` |
| Implement (schema) | **coder** with Database Agent rules | `.agents/database-agent.md` — **Alembic only**, no `create_all` in production |
| Implement (UI) | **frontend** | `.agents/frontend-agent.md`; existing Vite/React app in `frontend/` |
| Test (API) | **coder** writes tests; **gsd-debugger** if red | Real PostgreSQL; never SQLite |
| Test (browser E2E) | **frontend** (Playwright or equivalent in **this** frontend) | Exercise real user flow; not a screenshot-only check |
| Review | **reviewer** | Security (tenant leaks), money types, immutability, CLAUDE.md |
| Commit | Parent / human request | Coordinator does not commit unless asked |

**Anti-drift:** keep 6–8 agents; do not spawn a second “new SaaS” swarm; do not overlap coder and architect on the same files in the same turn.

---

## 4. Dependencies (what must finish before the next starts)

```
[mapper + architect return]     ← parent in-flight; this coordinator pass waits
        ↓
Architecture addendum: Wave 3 Product Master
  (resolve domain-model.md vs product.py; identifier/UOM/price APIs;
   UAE VAT fields; pagination; PDC vs payment immutability is a
   SEPARATE decision — log it, do not block WP-1 unless mapper marks P0)
        ↓
WP-1 Product Master API          ← coder + Alembic if columns missing
        ↓
WP-2 Product Master UI           ← frontend; blocked on WP-1 contracts
        ↓
WP-3 Browser E2E + isolation      ← frontend + coder tests; blocked on WP-1+WP-2
        ↓
Reviewer on the WP-1–3 diff
        ↓
Commit (user-requested)
        ↓
Only then: next V3 wave (do not start Enquiry/Email/WhatsApp/India)
```

**Hard blockers**

| Before | Must already be true |
|---|---|
| Any schema edit | Architect named the columns; Alembic revision **appends to `06c9b4b1dcda`**, never rewrites `d3e4c7fdb29f` |
| WP-2 | WP-1 endpoints exist and pytest isolation for products passes |
| WP-3 browser | API + Vite app runnable; test workspace with UAE VAT 5% and a cable/UOM fixture |
| Parallel WPs | WP-2 and WP-3 must not start before WP-1; do not parallelize “Wave 6 Email” beside this |
| Payment / PDC | Architect addendum **or** explicit deferral note. Today: CLAUDE.md + `business-rules.md` say no payment PUT; `api-contracts.md` + `payments.py` have PDC status PUT. Coder must not “fix” this without architecture |

**Does not block WP-1:** Redis “planned”, India GST, WhatsApp, GSD bootstrap, Hermes down_revision rewrite.

---

## 5. First 3 executable work packages

Coder starts **only after** the Wave 3 architecture addendum is filed. Acceptance criteria below are written so they can be copied into a coder prompt.

### WP-1 — Product Master API to Wave 3 DoD (backend)

**Owner:** coder (Database Agent rules for any new columns)
**Depends on:** architect addendum (field names, conversion shape, VAT/HS code, identifier types for electrical: MPN, barcode, supplier code)

**In scope**

- Service layer for products (router must not own business rules — CLAUDE.md).
- Complete Pydantic schemas vs the **addendum** (not a free-hand copy of the entire `GET /products/{id}` warehouse blob if architect defers stock embed).
- Endpoints (minimum, unless addendum cuts):
  - Paginated `GET /api/v1/products?search=&page=&per_page=`
  - `GET/PUT/DELETE /api/v1/products/{id}` (soft delete)
  - Category / Brand / UOM get-update-soft-delete
  - Nested identifier, UOM conversion, price CRUD under product id
- Workspace scoping from JWT only.
- Alembic **only if** addendum requires columns not in `product.py` / `d3e4c7fdb29f` (e.g. `hs_code`, `vat_category`, `from_uom_id`). `down_revision = 06c9b4b1dcda`.
- `backend/tests/test_products.py` on **PostgreSQL** `invoicesaas_test` (same URL derivation as existing tests). Include workspace isolation (404 not 403). Money fields `Decimal`, never `float` in models/schemas.
- Report: `.agents/reports/backend-execution-report.md` and `database-execution-report.md` **before** edits.

**Out of scope:** frontend, Enquiry/Quotation, rewriting Alembic history, SQLite, `init-project`.

**Acceptance criteria**

1. `alembic check` (or equivalent model↔migration) remains clean after any new revision.
2. `pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` passes on PostgreSQL.
3. List endpoints use `page` / `per_page` and the project wrapper `{success, data, error}` / `PaginationMeta`.
4. Cross-workspace GET/PUT/DELETE on product (and children) → **404**.
5. Soft delete sets `deleted_at`; list excludes deleted.
6. No `Float` money columns; no `print()`.
7. If conversions are in scope: factor stored as `Decimal`; `from_uom` vs base-UOM-only is **whatever the addendum says** (live model has `to_uom_id` only; `domain-model.md` has `from_uom_id` — **coder does not pick**).

### WP-2 — Product Master UI (electrical catalog)

**Owner:** frontend
**Depends on:** WP-1 merged to the working tree the UI will call

**In scope**

- Replace `alert('Add Product UI coming soon')` with create/edit (react-hook-form + zod aligned to WP-1).
- Tabs or equivalent: Products, Categories, Brands, UOMs.
- Product detail: identifiers (MPN/barcode/supplier code), UOM conversions, AED prices.
- Empty / skeleton / toast error states; currency formatted as AED.
- Keep Vanilla CSS / existing modules unless addendum says otherwise — **do not** start a second Next.js app.
- Report: `frontend-execution-report.md` before edits.

**Acceptance criteria**

1. `cd frontend && npm run build` succeeds.
2. User can: create category → brand → UOM → product → identifier → conversion → price without using API docs.
3. Edit and soft-delete (or deactivate) work; lists refresh via TanStack Query.
4. No new `.toFixed` on nullable amounts without `?? 0` (Wave 1 lesson).
5. AuthGuard still wraps the route; 401 → login.

### WP-3 — Browser E2E + isolation for the catalog path

**Owner:** frontend (browser E2E) + coder (API gaps found in E2E) + **gsd-debugger** if pytest/E2E is red
**Depends on:** WP-1 + WP-2

**In scope**

- Add a **single** browser E2E harness in the existing `frontend/` (Playwright is the default recommendation; architect/frontend may confirm in addendum). Do not create a second frontend package.
- Flow: register/login → Settings shows 5% VAT/TRN fields exist → Products: create electrical SKU (e.g. cable MTR) → identifiers → conversion → price in AED → reload still shows it.
- Negative: second workspace cannot open the first workspace’s product URL/API.
- pytest: extend isolation to new product child resources if WP-1 added them.
- Report updates for any bug **before** fix.

**Acceptance criteria**

1. Browser flow passes against local API (docker-compose postgres, not SQLite).
2. Cross-tenant product access fails in API tests (404).
3. Failures diagnosed by **gsd-debugger** with reproduction; no silent skips.
4. Document in report: what was **not** covered (invoice send/pay, GRN, 3-way match — those already have API e2e, not browser).

---

## 6. Risk list

| Risk | Current evidence | Mitigation (planning, not this pass) |
|---|---|---|
| **Schema without Alembic** | Tests use `SQLModel.metadata.create_all` / `drop_all` (`test_auth.py` and siblings). Production path is Alembic (`docker-compose` `upgrade head`). Agents historically generated throwaway schema. | Never `create_all` in app startup. New columns → Alembic from HEAD `06c9b4b1dcda`. Reviewer rejects schema-only model edits. |
| **SQLite tests** | `database.py` still branches on `sqlite` `connect_args`. CLAUDE.md forbids SQLite tests. Comment in `payment_service.py` about SQLite timezones. | Reviewer: `DATABASE_URL` in tests/CI must stay `postgresql+asyncpg`. Do not “simplify” tests to SQLite. Remove sqlite branch only if architect files it as cleanup WP (not WP-1–3). |
| **Float money** | Supplier invoice originally `sa.Float()` (`633b2df1fb55`); **fixed** by `12bdad2ae924` to `Numeric`. Frontend `Product.tax_rate: number`. Test asserts `float(...)` on JSON. | Models/schemas stay `Decimal`. Do not reintroduce Float. Frontend may parse string decimals; do not store float in API. |
| **Missing frontend** | **Not missing.** Vite app exists. Gap is **depth** (Product CRUD, no E2E, no Enquiry UI). | Do not scaffold Next.js or a second SPA. Extend `frontend/`. |
| **Payment immutability** | CLAUDE.md + `business-rules.md`: no UPDATE/DELETE. `state-machines.md`: PDC status may update while amount stays immutable. Live: `PUT /invoices/{id}/payments/{id}` mutates `status` and `pdc_status` (`payments.py`). Architecture also specifies `PUT /payments/{id}/pdc-status`. | Architect must write the exception: **amount/method/invoice_id immutable**; PDC lifecycle is the only allowed mutation; no DELETE. Coder does not delete the PUT “to match CLAUDE.md” without that addendum. |
| **Multi-tenant leaks** | P1 fixed SPO IDOR. Isolation tests exist for several entities. Products isolation is **read-only** (`test_product_is_workspace_isolated`). New product child endpoints will leak if unscoped. RFQ/procurement/inventory routers need the same pattern as `_get_scoped_spo`. | WP-1/WP-3 isolation tests. Reviewer: every query filters `workspace_id` from JWT. |
| **Hermes Wave 3 plan** | Instructs rewriting `d3e4c7fdb29f` down_revision | **Forbidden.** Would fork Alembic. |
| **GSD / claude-flow init** | Empty `.planning/`; `IDEA.md` one-liner | See §7–§8. |
| **bcrypt** | Was blocking Wave 1; `00fc498` + `bcrypt==4.2.0` | gsd-debugger re-runs full pytest before WP-1 if suite is red; not a new product. |
| **API contract drift** | `api-contracts.md` product detail includes `hs_code`, `vat_category`, `from_uom`, warehouse_stock; `product.py` is thinner | Architect addendum is the gate. Coder implements addendum, not the whole V3 catalog in one PR. |
| **Credit control** | Settings on workspace; `Client` has no credit fields (Wave 1 T4) | Out of WP-1–3. Do not silently add. |

---

## 7. How to use existing GSD / planning artifacts vs starting new phases

### What exists

| Artifact | Use |
|---|---|
| `.agents/MASTER_PLAN_V3.md` | Roadmap. Next **unfinished DoD** = Wave 3 Product Master. Later waves stay queued. |
| `architecture/*.md` | Wave 0 lock. Architect **patches drift**; does not replace with a new product spec. |
| `.agents/reports/*` | Mandatory activity log. Append-only. |
| `.hermes/plans/2026-08-27_…wave3…` | Gap **hints** only. Do not execute the migration rewrite. |
| Stabilization + Wave 1 reports | Security/CI/test patterns to copy (scoped 404, `create_all` test DB, wrapper envelope) |
| `.claude/CLAUDE.md` | Non-negotiable engineering rules |

### What does **not** exist

- `.planning/STATE.md`, `ROADMAP.md`, GSD phase folders
- Therefore there is **no** “next unplanned GSD phase” to execute. Do not pretend GSD is already initialized.

### If the parent wants GSD later (optional, not this pass)

Allowed, in this order, **on InvoiceSaaS only**:

1. `/gsd-map-codebase` (brownfield map into `.planning/codebase/`) — mapper may already be doing this.
2. `/gsd-new-milestone` (not new-project) named e.g. `UAE electrical MVP — Wave 3 Product Master`, with requirements **copied from** V3 Wave 3 + this sequence, not a new vision doc.
3. `/gsd-plan-phase` for that milestone’s phase 1 = WP-1.

**Forbidden**

- `/gsd-new-project` (creates a new `PROJECT.md` / fake greenfield)
- `claude-flow init-project`
- New milestone for “a different SaaS”, India-first, or consumer invoicing

Until GSD exists, **execute from this sequence + MASTER_PLAN_V3**. Do not wait on `.planning/` to start architecture addendum.

---

## 8. Explicit non-actions

- **Do not** run `claude-flow init-project` (or `npx … init-project`) on `C:\Users\Hamza\rezorpay_pro`.
- **Do not** invent a second product, rename the app, or treat `IDEA.md` as a product brief.
- **Do not** implement product code in this coordinator pass (none was implemented).
- **Do not** start Wave 6–11 sales (Enquiry, Quotation, CPO, WhatsApp, Email) until Wave 3 DoD is met.
- **Do not** rewrite Alembic history.

---

## Recommended NEXT single action (parent, after mapper + architect return)

**Do not spawn a coder yet.**

Merge mapper + architect findings into one **Wave 3 Product Master architecture addendum** (file under `architecture/`, e.g. `architecture/product-master-addendum.md`) that:

1. Lists the **exact** endpoints and fields WP-1 will implement (subset of `api-contracts.md` vs live `product.py`).
2. Resolves `ProductUOMConversion` (`to_uom_id` only vs `from_uom_id` in domain-model).
3. States UAE electrical identifier types and VAT fields in/out of WP-1.
4. States Alembic: new revision from `06c9b4b1dcda` vs “no migration, API-only”.
5. Logs payment-immutability vs PDC PUT as **deferred** or a follow-up WP — not as silent coder work.

**Then** spawn **coder on WP-1 only**, with that addendum as the spec.

If mapper+architect already produced that addendum, the next action is: **spawn coder on WP-1** with the addendum path in the prompt (still no GSD new-project, no second product).

---

## Coordination record

- Session: sequential planning 2026-08-31
- Memory: `swarm` / `swarm/2026-08-31/mvp-sequence`
- Activity log: `.agents/reports/coordinator-execution-report.md`
- This file: `.agents/reports/mvp-execution-sequence-2026-08-31.md`
