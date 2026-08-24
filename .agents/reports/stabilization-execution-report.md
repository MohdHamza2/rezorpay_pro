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

## P0 — Safety (purge junk, then commit)
- [in progress] Extended `.gitignore`: `node_modules/`, `*.db/*.sqlite*`, throwaway-script globs, `test_output.txt`, `skills-lock.json`, `.agents/skills/`.
- [pending] Delete 77 throwaway scripts + `test_spo.db` ×2 + `test_output.txt`.
- [pending] Branch `stabilization/wave-sync` off `master`; snapshot-commit the purged working tree (incl. `frontend/`).

## P1 — Security (SPO multi-tenancy)  — pending
## P2 — Builds & imports clean            — pending
## P3 — Tests & CI green                   — pending
## P4 — Consistency & hygiene              — pending
