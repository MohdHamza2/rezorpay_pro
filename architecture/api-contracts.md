# API Contracts — InvoiceSaaS B2B Trading Platform

> Complete endpoint reference for all implemented routers (Wave 0–20)
> Base URL: `/api/v1` | Authentication: Bearer JWT unless noted

## Authentication (`/auth`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/auth/register` | Register user + workspace | No |
| POST | `/auth/login` | Login, returns access + refresh tokens | No |
| POST | `/auth/refresh` | Refresh access token | No |
| GET | `/auth/me` | Get current user profile | Yes |

Response shape: `{ "success": true, "data": {...} }`

---

## Health (`/health`, `/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/` | Root — service name and version | No |
| GET | `/health` | Liveness + DB connectivity check | No |

---

## Clients (`/api/v1/clients`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/clients/?workspace_id=` | List all clients | Yes |
| POST | `/clients/?workspace_id=` | Create client | Yes |
| GET | `/clients/{id}` | Get client by ID | Yes |
| PATCH | `/clients/{id}` | Update client | Yes |
| DELETE | `/clients/{id}` | Soft-delete client | Yes |

---

## Invoices (`/api/v1/invoices`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/invoices/` | List invoices (paginated, filterable) | Yes |
| POST | `/invoices/` | Create draft invoice | Yes |
| GET | `/invoices/{id}` | Get invoice with items | Yes |
| PATCH | `/invoices/{id}` | Update draft invoice | Yes |
| DELETE | `/invoices/{id}` | Soft-delete invoice | Yes |
| POST | `/invoices/{id}/send` | Send invoice (DRAFT → SENT) | Yes |
| POST | `/invoices/{id}/void` | Void invoice (requires reason) | Yes |
| POST | `/invoices/{id}/mark-overdue` | Mark as OVERDUE | Yes |

State machine: `DRAFT → SENT → PARTIALLY_PAID / PAID / OVERDUE / VOID`

---

## Payments (`/api/v1/invoices/{invoice_id}/payments`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/invoices/{id}/payments` | List payments for invoice | Yes |
| POST | `/invoices/{id}/payments` | Record a payment | Yes |
| GET | `/invoices/{id}/balance` | Get balance due | Yes |

---

## Dashboard (`/api/v1/dashboard`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/dashboard/stats` | Revenue, outstanding, overdue stats | Yes |

---

## Workspaces (`/api/v1/workspaces`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/workspaces/me` | Get current workspace settings | Yes |
| PATCH | `/workspaces/me` | Update workspace settings | Yes |

---

## Products (`/api/v1/products`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/products/` | List products | Yes |
| POST | `/products/` | Create product | Yes |
| GET | `/products/{id}` | Get product | Yes |
| PATCH | `/products/{id}` | Update product | Yes |
| POST | `/products/category/` | Create category | Yes |
| GET | `/products/category/` | List categories | Yes |
| POST | `/products/brand/` | Create brand | Yes |
| GET | `/products/brand/` | List brands | Yes |
| POST | `/products/uom/` | Create unit of measure | Yes |
| GET | `/products/uom/` | List units of measure | Yes |

---

## Suppliers (`/api/v1/suppliers`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/suppliers/` | List suppliers | Yes |
| POST | `/suppliers/` | Create supplier | Yes |
| GET | `/suppliers/{id}` | Get supplier | Yes |
| PATCH | `/suppliers/{id}` | Update supplier | Yes |

---

## Inventory (`/api/v1/inventory`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/inventory/warehouses` | List warehouses | Yes |
| POST | `/inventory/warehouses` | Create warehouse | Yes |
| POST | `/inventory/warehouses/{id}/bins` | Create warehouse bin | Yes |
| GET | `/inventory/warehouses/{id}/bins` | List bins in warehouse | Yes |
| GET | `/inventory/levels` | Get inventory levels (filter by product) | Yes |
| POST | `/inventory/adjust` | Manual stock adjustment | Yes |

---

## Procurement Requests (`/api/v1/procurement`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/procurement/` | List procurement requests | Yes |
| POST | `/procurement/` | Create procurement request | Yes |
| GET | `/procurement/{id}` | Get procurement request | Yes |
| POST | `/procurement/{id}/approve` | Approve procurement request | Yes |
| POST | `/procurement/{id}/cancel` | Cancel procurement request | Yes |

---

## RFQ (`/api/v1/rfq`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/rfq/` | List RFQs | Yes |
| POST | `/rfq/` | Create RFQ | Yes |
| GET | `/rfq/{id}` | Get RFQ | Yes |
| POST | `/rfq/{id}/close` | Close RFQ | Yes |

---

## SPO — Supplier Purchase Orders (`/api/v1/spos`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/spos/` | List SPOs | Yes |
| POST | `/spos/?workspace_id=` | Create SPO (DRAFT) | Yes |
| GET | `/spos/{id}` | Get SPO with items | Yes |
| POST | `/spos/{id}/submit-approval` | DRAFT → PENDING_APPROVAL | Yes |
| POST | `/spos/{id}/approve` | PENDING_APPROVAL → APPROVED | Yes |
| POST | `/spos/{id}/send` | APPROVED → SENT | Yes |
| POST | `/spos/{id}/items/acknowledge` | SENT → ACKNOWLEDGED (supplier confirms qtys) | Yes |
| POST | `/spos/{id}/cancel` | Cancel SPO (requires reason query param) | Yes |

State machine: `DRAFT → PENDING_APPROVAL → APPROVED → SENT → ACKNOWLEDGED → CLOSED`

---

## GRN — Goods Receipt Notes (`/api/v1/grns`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/grns` | List GRNs (filter by status/supplier/spo) | Yes |
| POST | `/grns` | Create GRN (DRAFT) | Yes |
| PATCH | `/grns/{id}` | Update GRN header | Yes |
| GET | `/grns/{id}` | Get GRN with items | Yes |
| POST | `/grns/{id}/start-receiving` | DRAFT → RECEIVING | Yes |
| POST | `/grns/{id}/items` | Add item line to GRN | Yes |
| POST | `/grns/{id}/stage-for-inspection` | RECEIVING → STAGED_FOR_INSPECTION | Yes |
| POST | `/grns/{id}/items/{item_id}/disposition` | Record QC decision; posts to inventory | Yes |
| POST | `/grns/{id}/cancel` | Cancel GRN (DRAFT only) | Yes |
| GET | `/spos/{id}/grns` | List all GRNs for an SPO | Yes |

State machine: `DRAFT → RECEIVING → STAGED_FOR_INSPECTION → ACCEPTED / PARTIALLY_ACCEPTED`

---

## Supplier Invoices / AP Payables (`/api/v1/supplier-invoices`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/supplier-invoices/` | List AP invoices | Yes |
| POST | `/supplier-invoices/` | Register supplier invoice (RECEIVED) | Yes |
| GET | `/supplier-invoices/{id}` | Get invoice with items | Yes |
| POST | `/supplier-invoices/{id}/submit-matching` | Run 3-way match engine | Yes |
| POST | `/supplier-invoices/{id}/approve` | Approve MATCHED invoice | Yes |
| POST | `/supplier-invoices/{id}/resolve-discrepancy` | Override DISCREPANCY with notes | Yes |

State machine: `RECEIVED → PENDING_MATCHING → MATCHED / DISCREPANCY → APPROVED → PARTIALLY_PAID → PAID`

---

## Response Envelope

All API responses follow this shape:

```json
{
  "success": true,
  "data": { ... }
}
```

Error responses:
```json
{
  "success": false,
  "error": {
    "code": "HTTP_ERROR",
    "message": "Human-readable description"
  }
}
```

> **Note**: SPO endpoints return raw objects without the `data` wrapper (legacy; to be refactored in future wave).
