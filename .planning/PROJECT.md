# InvoiceSaaS MVP

**Market:** UAE-first B2B Electrical Trading
**Description:** Full B2B Electrical Trading ERP / Trade Operations Platform. Four domains: Product, Customer/Sales/AR, Inventory/Warehouse, Supplier/Procurement/AP.

## Stack
- Backend: FastAPI, SQLModel, asyncpg, PostgreSQL 16, Alembic
- Frontend: Vite, React 18, TypeScript, TanStack Query, React Hook Form, @react-pdf/renderer
- Auth: JWT

## Core Principles
1. Never invent business rules (wait for human or architecture addendum).
2. All list endpoints MUST eager-load required relationships (prevent N+1).
3. Schema changes via Alembic only.
4. Decimal/Numeric(12,2) for money fields; NEVER float.
