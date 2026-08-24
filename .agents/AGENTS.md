# InvoiceSaaS — Multi-Agent Configuration

> This file defines the specialized agents available for this project. Each agent has deep domain knowledge of its area and follows strict rules.

## Agent Roster

### 🔧 Backend Agent
- **File**: [backend-agent.md](./backend-agent.md)
- **Scope**: FastAPI application, routers, services, schemas, auth, middleware
- **Owns**: `backend/app/`, `backend/requirements.txt`, `backend/Dockerfile`
- **Key Skills**: API design, business logic, state machines, concurrency safety, JWT auth
- **When to use**: Any backend code changes, new endpoints, service logic, bug fixes

### 🎨 Frontend Agent
- **File**: [frontend-agent.md](./frontend-agent.md)
- **Scope**: Web UI application (to be built)
- **Owns**: `frontend/` (will be created)
- **Key Skills**: React/Next.js, TypeScript, responsive design, API integration, auth flows
- **When to use**: Building UI pages, components, client-side state management

### 🗄️ Database Agent
- **File**: [database-agent.md](./database-agent.md)
- **Scope**: PostgreSQL schema, Alembic migrations, query optimization, data integrity
- **Owns**: `backend/app/models/`, `backend/alembic/`, `backend/app/database.py`
- **Key Skills**: Schema design, ENUM management, migration scripting, index strategy
- **When to use**: Model changes, new tables, schema modifications, performance tuning

## Coordination Rules

1. **Mandatory Activity Reporting**: Every agent MUST document their actions, code edits, and implementation steps in a dedicated report file (e.g., `backend-execution-report.md`) within `.agents/reports/`. This must be updated continuously as work progresses to maintain complete traceability.
2. **Schema changes** → Database Agent creates model + migration → Backend Agent updates router/service/schema
3. **New feature** → Backend Agent builds API → Frontend Agent consumes it
4. **Bug fix** → Route to the owning agent based on which layer the bug exists in
5. **Cross-cutting changes** (e.g., new entity end-to-end) → Database Agent first, then Backend Agent, then Frontend Agent

## Shared Context

All agents MUST read `.claude/CLAUDE.md` before starting any work — it contains the project-wide rules that apply to everyone.
