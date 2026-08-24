# InvoiceSaaS — Agent Reports Index
*Last Updated: 2026-08-24*

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

## Governance Rules
1. Reports are append-only — never delete entries
2. Every entry must have: timestamp, action taken, files changed, result
3. If a bug or issue is found, log it in the report BEFORE attempting to fix it
4. All reports are reviewed by the human before each wave begins

## Wave Status

| Wave | Focus | Status |
|---|---|---|
| Wave 0 | Architecture Lock | IN PROGRESS |
| Wave 1 | Bug Fix + Core Sync | PENDING |
| Wave 2 | Workspace Settings | PENDING |
| Wave 3 | Product Master | PENDING |
| ... | ... | ... |
