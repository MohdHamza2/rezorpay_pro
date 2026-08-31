# InvoiceSaaS — Agent Reports Index
*Last Updated: 2026-08-31*

## Purpose
This directory contains the mandatory execution reports for all agents working on the InvoiceSaaS ERP platform.
Every agent MUST update their report before, during, and after every action taken.
No code change is traceable without a corresponding report entry.

## Report Files

| File | Agent | Scope |
|---|---|---|
| database-execution-report.md | Database Agent | Schema changes, Alembic migrations, model edits |
| backend-execution-report.md | Backend Agent | API routers, services, schemas, bug fixes |
| frontend-execution-report.md | Frontend Agent | React pages, components, CSS, API client |
| wave0-execution-report.md | Planner | Wave 0 architecture document production |
| stabilization-execution-report.md | Stabilization | P0–P4 sync/wire effort (`stabilization/wave-sync`): purge, SPO security, builds, CI, consistency |
| wave-1-execution-report.md | Wave 1 | Bug fix + core sync + engineering review T1–T4, T11–T12 |
| wave-1-coordination-plan.md | Coordinator | Wave 1 task routing (historical) |
| coordinator-execution-report.md | Swarm coordinator | Swarm lifecycle, planning passes, anti-drift |
| mvp-execution-sequence-2026-08-31.md | Swarm coordinator | Sequential planning: shipped evidence, WP-1–3, risks, GSD policy |

## Governance Rules
1. Reports are append-only — never delete entries
2. Every entry must have: timestamp, action taken, files changed, result
3. If a bug or issue is found, log it in the report BEFORE attempting to fix it
4. All reports are reviewed by the human before each wave begins

## Wave Status

| Wave (MASTER_PLAN_V3) | Focus | Status (2026-08-31 coordinator inventory) |
|---|---|---|
| Wave 0 | Architecture Lock | Specs exist in `architecture/` (git `b8f442b`). Drift vs live models remains (esp. Product). |
| Wave 1 | Bug Fix + Core Sync | Code landed (`b3d0729`, `00fc498`). bcrypt upgraded. Isolation + numbering tests added. |
| Wave 2 | Workspace Settings | Schema + API + Settings UI (`d3a7719`, `06c9b4b1dcda`). Credit **engine** not built. |
| Wave 3 | Product Master | **Next DoD to finish.** Models + migration in chain; API list/create only; UI placeholder; no `test_products.py`. |
| Waves 4–5, 12–16, 21 (impl. chronology mixed) | Suppliers, inventory, PR, RFQ, SPO, GRN, supplier invoice | Code + some API e2e exist; not full V3 DoD (pagination, UI depth, browser E2E). |
| Waves 6–11, 17–20, 22–29 | Email, sales docs, credit engine, PDF pack, stock ops, AP pay, DO, statements, returns, WA, reports, India, prod | **Not started.** Do not start until Wave 3 DoD. |

GSD: `.planning/` **does not exist**. Do not run `/gsd-new-project` or `claude-flow init-project`. See `mvp-execution-sequence-2026-08-31.md` §7–§8.
