# Stabilization Execution Report
*Session start: 2026-08-24 | Goal: bring the project to a correct, wired, buildable, CI-green, clean state (no new features)*

> Scope approved by human: **Full P0→P4 in sequence**, purge-junk-then-commit, check-in at each phase boundary.
> Deferred (explicitly out of scope this session): all V3 customer-side/comms features (Enquiry, Quotation, CPO, DO, Returns, Credit/Debit notes, PDF templates, Email/Resend, WhatsApp, OCR, credit-control engine, stock reservations/transfers/counts) and any live-DB `alembic stamp`.

## Baseline findings (from tri-agent audit, 2026-08-24)
- **Version control:** only base Step 2.5 committed; ~150 files (all waves 2–15) + entire `frontend/` untracked.
- **Security:** SPO domain broken multi-tenancy — `GET /spos/{id}` unauth+unscoped; SPO transitions + `SPOService` unscoped; `create_spo` takes `workspace_id` from query param; SPO numbering hardcoded `SPO-{year}-000001`.
- **Frontend:** `npm run build` fails (21 TS errors: GRN/SPO type drift + unused imports); `BASE_URL` hardcoded to localhost:8000.
- **CI:** lint fails (51 black + 102 ruff); `pytest.ini` header malformed (`[tool:pytest]`); test DB-name bug → `invoicesaas_test_test`; live-server scripts collected by pytest.
- **DB:** migration chain valid+linear (base `001` → head `12bdad2ae924`); runtime risks = possible stale `d0be13f0ca49` stamp, ENUM case mismatch, `alembic.ini` URL/secret divergence.
- **Tooling:** `requirements.txt` missing `redis`; no `.dockerignore`; no `conftest.py`.
- **Hygiene:** ~77 throwaway `patch_*/fix_*/…` scripts; `test_spo.db` ×2; `test_output.txt`; corrupted (UTF-16) `database-execution-report.md`; UTF-8 BOM in 6 routers; stale docs.

---

## P0 — Safety (purge junk, then commit) — ✅ DONE (commit `cce36f9`)
- [done] Extended `.gitignore`: `node_modules/`, `*.db/*.sqlite*`, throwaway-script globs, `test_output.txt`, `skills-lock.json`, `.agents/skills/`.
- [done] Deleted 77 throwaway scripts + `test_spo.db` ×2 + `test_output.txt`.
- [done] Branch `stabilization/wave-sync` off `master`; snapshot-commit of the purged working tree (incl. `frontend/`).

## P1 — Security (SPO multi-tenancy) — ✅ DONE (P1 boundary commit on `stabilization/wave-sync`)
**Root cause:** the SPO domain trusted client-supplied / absent workspace scoping. `POST /spos/` read `workspace_id` from a query param (IDOR), `GET /spos/{id}` had *no auth and no workspace filter* (anonymous cross-tenant read), and every state-transition endpoint loaded the SPO via `session.get(id)` with no tenant check (cross-tenant writes). SPO numbering was hardcoded `SPO-{year}-000001`, which also violates the `uq_workspace_spo_number` unique constraint on the **2nd** SPO per workspace (hard crash, not cosmetic).

**Fixes:**
- `routers/spo.py`: every endpoint now derives tenant from the JWT. Mutating endpoints use `get_current_active_user` (→ `current_user.workspace_id` + `.id`); reads use `get_current_workspace_id`. Removed the `workspace_id` **query param** from `create_spo`. Added auth **and** a `workspace_id` filter to `get_spo` (was fully open).
- `services/spo_service.py`: added `_get_scoped_spo(session, spo_id, workspace_id)` — loads by id **and** `workspace_id`, returns 404 for missing *or* cross-tenant (no existence probing). Threaded `workspace_id` through `submit_for_approval` / `approve` / `send` / `acknowledge` / `cancel`. (Router is the only caller — verified — so signature changes are safe.)
- **Gapless SPO numbering** (mirrors `InvoiceCounter`): new `models/spo_counter.py` (`SPOCounter`, PK `(workspace_id, year)`), new `services/spo_number.py` (`SPONumberService.generate_spo_number` with `SELECT … FOR UPDATE`), wired into `create_draft`. Registered `SPOCounter` in `models/__init__.py`. New migration `b7e2f4a9c1d3_add_spo_counters` (head; `down_revision = 12bdad2ae924`).

**Verification:**
- App imports cleanly in-container; `py_compile` clean on all 5 changed/new files.
- Tests (in `invoicesaas-api` container): `test_spo.py`, `test_e2e_spo.py`, `test_grn.py`, `test_e2e_grn.py`, `test_e2e_3way_match.py` → **6 passed, 0 failed**. `spo_counters` auto-created in test DB via `create_all`.
- Migration applied to live dev DB (`12bdad2ae924 → b7e2f4a9c1d3`); `spo_counters` columns verified. Live DB stamp was clean at `12bdad2ae924` (no stale `d0be13f0ca49` — that runtime risk is resolved).
- Live smoke: unauth `GET /spos/{id}` and `POST /spos/` → **403 "Not authenticated"** (wrapper-pattern body).

**Deferred to P3:** a dedicated cross-tenant regression test (needs 2 workspaces → 2 registrations; will be added alongside the rate-limit test isolation / `conftest.py` work to avoid flaky 429s now). The fix itself is correct-by-construction against the proven `list_spos` reference pattern.

## P2 — Builds & imports clean — ✅ DONE (P2 boundary commit on `stabilization/wave-sync`)
**Frontend (21 TS errors → 0):**
- Removed 13 unused imports/vars across `SPO.tsx` (`useState`, `Printer`, `Truck`), `SPOBuilder.tsx` (`useState`, `Controller`, `formState.errors`), `SPODetail.tsx` (`useMutation`, `cancelSPO`), `GRNDetail.tsx` (`useEffect`, `GRN`, `GRNItem`, `SPO` type, `watch`, `reset`), `spo.ts` (`SuccessResponse` — genuinely unused; see wiring flag #1).
- **GRN type-drift → aligned to backend contract:** `GRN.tsx` now uses `grn.stock_posted` (was non-existent `status === 'POSTED'`), `grn.received_date` (was `receipt_date`), `grn.delivery_reference` (was `supplier_delivery_note`). Added missing `stock_posted: boolean` to the `GRN` interface in `api/grn.ts`.
- Null-safety: `GRNDetail.tsx` `internal_sku: spoItem.internal_sku ?? ''` (`SPOItem.internal_sku` is `string | null`; `GRNItemCreate.internal_sku` is `string`).
- **Env-driven API base URL:** `client.ts` `BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'`; added `src/vite-env.d.ts` (`vite/client` ref) so `import.meta.env` type-checks; added `frontend/.env.example`. Also hoisted a mid-file import in `client.ts` to the top (CLAUDE.md "imports at top").

**Verification:**
- `npx tsc -b` → exit 0. `npm run build` (`tsc -b && vite build`) → exit 0, 2152 modules, `dist/` emitted. (Only a >500 kB chunk-size *advisory* — perf, not an error; code-splitting deferred.)
- Backend: `from app.main import app; from app.models import *` in-container → **BACKEND IMPORT OK**. (No backend files changed since P1.)

**Wiring flags discovered during P2 (NOT runtime breaks — each frontend↔backend pairing is internally consistent — deferred to P4 consistency):**
1. **SPO envelope divergence (CLAUDE.md API Rule #1):** `spo.py` is the *only* router returning **raw** models (`SPOResponse` / `List[SPOResponse]`); all 14 other routers wrap in `SuccessResponse[...]` / `PaginatedResponse`. `spo.ts` correctly does *not* unwrap, so SPO works — but it violates the "all responses use the `{success,data,error}` wrapper" rule. Fix = wrap SPO endpoints + add unwrap in `spo.ts` + update SPO tests (coordinated 3-way change).
2. **`SPOBuilder.tsx` dead mock workspace:** passes hardcoded `'00000000-…'` to `createSPO(workspaceId, data)`, but the backend `POST /spos/` now derives `workspace_id` from JWT (P1). The arg is silently ignored (FastAPI drops unknown query params) → not broken, but misleading. Cleanup `createSPO` signature + callers.
3. **`client.ts:getDashboardMetrics` dead code:** unused fn hitting non-existent `/api/v1/dashboard/metrics`. The live dashboard uses `dashboard.ts:getDashboardStats` → `/api/v1/dashboard/stats` (correct). Remove the dead fn.
## P3 — Tests & CI green — ✅ DONE (P3 boundary commit on `stabilization/wave-sync`)
**Root causes fixed (CI was red on both lint and test jobs):**
- **`pytest.ini` header malformed** — `[tool:pytest]` is only valid in `setup.cfg`/`tox.ini`; in a file named `pytest.ini` the whole section was silently ignored, so `testpaths = tests` never applied and bare `pytest` (as CI runs) collected the root live-server scripts. Fixed header → `[pytest]`; collection now scoped to `tests/`.
- **Test DB double-suffix** — every test file did `settings.DATABASE_URL.replace("invoicesaas", "invoicesaas_test")`. In CI `DATABASE_URL` already ends `…/invoicesaas_test`, so the replace produced `…/invoicesaas_test_test` → every test failed to connect. Replaced with an **idempotent** derivation in all 5 DB-bound test files (`test_auth`, `test_grn`, `test_e2e_spo`, `test_e2e_grn`, `test_e2e_3way_match`) + the new `test_spo`: `DATABASE_URL if endswith("_test") else DATABASE_URL + "_test"` (correct in both dev and CI, no env var required).
- **Auth rate-limit flakiness** — new `tests/conftest.py` sets `limiter.enabled = False` before any request (slowapi checks the flag per-request), so the many throwaway registrations/logins don't hit 429. Verified safe: no test asserts rate-limiting, and CI already relaxes `RATE_LIMIT_AUTH=100/minute`.
- **Dead CI step** — removed `Run production test suite` (`python test_step2_production.py`); it needs a live uvicorn (never started in CI) and duplicates in-process `TestClient` coverage. Test job now ends at `pytest`.
- **`requirements.txt` missing `redis`** — added `redis==5.0.1` (referenced by `config.REDIS_URL`; unblocks pip-audit/security job import parity).

**CI lint job (was `51 black + 102 ruff`, now 0) — repo-wide normalization:**
- `ruff check app/ --fix` + `ruff check tests/ --fix` cleared 54 app/ + 9 tests/ auto-fixable violations (unused imports F401, f-string-no-placeholder F541, `== True`→`is True` E712, safe F841). `black app/ tests/` reformatted 48 files (the wave 4–15 sources were committed unformatted at the P0 snapshot — this is the bulk of the diff; **formatting-only, no logic change**).
- **Non-auto-fixable, fixed by hand (zero behavior change):**
  - **F821 undefined forward-refs** (SQLModel relationships used quoted class names with no import): added idiomatic `if TYPE_CHECKING:` import blocks in `models/workspace.py` (User/Client/Invoice — file had none), `models/invoice.py` (+InvoiceItem/Payment/InvoiceEvent), `models/client.py` (+Invoice), `models/user.py` (+InvoiceEvent). `TYPE_CHECKING` is `False` at runtime → imports never execute → no circular-import risk; runtime resolution still via SQLModel's registry.
  - **E402 mid-file imports** (CLAUDE.md "imports at top"): hoisted `from app.limiter import limiter` / `from app.auth.dependencies import get_current_user` to the top block in `auth/router.py`, `routers/clients.py`, `routers/invoices.py`, `routers/payments.py` (removed a duplicate limiter import in payments). No circular reason (limiter is slowapi-only; auth.dependencies imports no routers).
  - **F841 dead locals**: `routers/grn.py` ×2 — dropped the unused `grn =` binding but **kept** the `await GRNService.…()` call (it performs the state transition; handler re-queries for the response). `services/invoice_service.py` — removed dead `old_status` (a leftover of the dropped-audit-metadata issue; wiring it in would be a P4 behavior change, out of scope).

**New regression test — `tests/test_spo.py` (was a `assert True` placeholder):**
- `test_spo_is_workspace_isolated` — locks in the P1 fix: workspace B gets **404** on both `GET /spos/{A's id}` and `POST /spos/{A's id}/submit-approval` (no cross-tenant read or write, no existence leak), while owner A still reads its own SPO. This is the cross-tenant regression deferred from P1.
- `test_spo_numbers_are_gapless_within_a_workspace` — two SPOs in one workspace get distinct numbers (guards the gapless `SPONumberService`; the old hardcoded number 500'd on the 2nd create via `uq_workspace_spo_number`).

**Verification (all in `invoicesaas-api` container, real PostgreSQL 16):**
- `python -c "import app.main"` → **IMPORT OK** (validates the forward-ref + hoisted-import edits).
- `ruff check app/` **clean**, `ruff check tests/` **clean**, `black --check app/ tests/` **clean (76 files)** → CI lint job green.
- `pytest -q` → **10 passed** (incl. the 2 new SPO tests), re-verified from a *truly empty* schema (fixtures' `create_all` is self-sufficient, no alembic dependency).
- **Clean-room CI test-job replication** on a freshly-emptied `invoicesaas_test`: `alembic upgrade head` applied the full wave chain in sequence with no error; `alembic check` → **"No new upgrade operations detected"** (zero model↔migration drift).
- `ci.yml` structure intact: lint → test → security; security job's `pip-audit --strict` remains `continue-on-error`.

## P4 — Consistency & hygiene              — pending
*Carry-in from P2 wiring flags:* (1) wrap SPO endpoints in `SuccessResponse` + unwrap in `spo.ts` + update tests; (2) drop dead mock `workspaceId` from `createSPO` + callers; (3) remove dead `client.ts:getDashboardMetrics`. Plus the originally-scoped P4 work: unify `alembic.ini` ↔ `config.py` + secrets to env, ENUM case reconciliation, consolidate `get_current_workspace_id` (the duplicated per-router copies in `clients.py`/`invoices.py`/`payments.py` vs `auth.dependencies`), export wave services in `services/__init__.py`, standardize auth import paths, fix supplier_invoices eager-load, add `.gitattributes`, refresh stale docs (CLAUDE.md Known Issues, reports index, `edge-cases.md` F-2).
