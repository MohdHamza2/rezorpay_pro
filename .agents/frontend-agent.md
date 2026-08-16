# Frontend Agent Instructions

> You are the **Frontend Agent** responsible for building the InvoiceSaaS web application UI.

## Project Context

This is a **multi-tenant SaaS invoicing platform**. The backend API is fully built (FastAPI on port 8000). Your job is to build the frontend that consumes it.

## Tech Stack (Recommended)

- **Framework**: Next.js 14+ (App Router) or Vite + React
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS (if user approves) or Vanilla CSS
- **State Management**: React Query / TanStack Query for server state
- **Forms**: React Hook Form + Zod validation
- **Auth**: JWT tokens stored in httpOnly cookies or secure localStorage
- **Charts**: Recharts or Chart.js for financial dashboards

## Backend API Reference

### Base URL: `http://localhost:8000`

### Authentication
```
POST /auth/register   → { email, password, name, workspace_name }
POST /auth/login      → { email, password }
POST /auth/refresh    → { refresh_token }
GET  /auth/me         → Current user profile
```

### Clients
```
POST   /api/v1/clients           → Create client
GET    /api/v1/clients           → List (paginated, searchable)
GET    /api/v1/clients/{id}      → Get single client
PUT    /api/v1/clients/{id}      → Update client
DELETE /api/v1/clients/{id}      → Soft-delete client
```

### Invoices
```
POST   /api/v1/invoices               → Create invoice (DRAFT)
GET    /api/v1/invoices               → List (filtered by status, client, search)
GET    /api/v1/invoices/{id}          → Get invoice with line items
PUT    /api/v1/invoices/{id}          → Update (DRAFT only)
DELETE /api/v1/invoices/{id}          → Soft-delete (DRAFT only)
POST   /api/v1/invoices/{id}/send     → Transition DRAFT → SENT
POST   /api/v1/invoices/{id}/void     → Void/cancel invoice
```

### Payments
```
POST /api/v1/invoices/{id}/payments   → Record payment (requires Idempotency-Key header)
GET  /api/v1/invoices/{id}/payments   → List payments
GET  /api/v1/invoices/{id}/balance    → Get balance due
```

### Response Format
All API responses follow this structure:
```json
{
  "success": true,
  "data": { ... },
  "pagination": { "total": 50, "page": 1, "per_page": 20, "pages": 3, "has_next": true, "has_prev": false }
}
```

### Error Responses
```json
{
  "success": false,
  "error": { "code": "ERROR_CODE", "message": "Description" }
}
```

## Pages to Build

### Core Pages
1. **Login / Register** — Auth forms with validation
2. **Dashboard** — Overview: total invoices, revenue, outstanding balance, recent activity
3. **Clients List** — Searchable, paginated table with create/edit/delete
4. **Client Detail** — Client info + their invoices
5. **Invoices List** — Filterable by status, searchable, paginated
6. **Invoice Create/Edit** — Dynamic line items form with real-time total calculation
7. **Invoice Detail** — Full invoice view with status badge, payment history, actions (send/void)
8. **Payment Recording** — Form to record payments on an invoice

### Design Principles
- **Invoice status badges**: Color-coded (Draft=gray, Sent=blue, Partial=orange, Paid=green, Cancelled=red)
- **Financial numbers**: Always formatted with 2 decimal places and currency symbol
- **Mobile responsive**: All pages must work on mobile
- **Loading states**: Skeleton loaders for async data
- **Error handling**: Toast notifications for API errors
- **Optimistic updates**: Where appropriate (e.g., marking as sent)

## State Machine (Visual Reference for UI)
```
DRAFT (editable) → SENT (locked) → PARTIALLY_PAID → PAID
                 ↘ CANCELLED ← ← ← ← ← ← ← ← ← ← ↙
```

## Authentication Flow
1. User logs in → receives access_token + refresh_token
2. Store tokens securely
3. Attach `Authorization: Bearer <access_token>` to all API requests
4. On 401 → attempt refresh with refresh_token
5. On refresh failure → redirect to login

## Important Notes
- **Multi-tenancy is handled by the backend** — frontend just sends the JWT, backend scopes everything to the workspace automatically
- **Idempotency-Key header required** for payment creation — generate a UUID per payment attempt
- **Currency is AED by default** — format accordingly
- **Invoice numbers are auto-generated** — don't let users set them
