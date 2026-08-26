# API Contracts Specification

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## Overview

This document specifies all REST API endpoints across all 27 waves, including request/response schemas, authentication requirements, and business rules.

---

## Global API Rules

### Base URL
```
Production: https://api.rezorpay.com/v1
Development: http://localhost:8000/api/v1
```

### Authentication
All endpoints (except `/auth/login`, `/auth/refresh`) require:
- **Header:** `Authorization: Bearer {access_token}`
- **Token Type:** JWT with 30-minute expiry
- **Payload:** `{user_id, workspace_id, email, role, exp}`

### Standard Response Wrapper
```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

**Error Response:**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Insufficient stock available: 10 UNITS",
    "details": { ... }
  }
}
```

### Pagination
All list endpoints support:
- **Query Params:** `page=1`, `per_page=20` (default), `sort_by`, `sort_order`
- **Response:**
```json
{
  "success": true,
  "data": {
    "items": [...],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total_items": 156,
      "total_pages": 8
    }
  }
}
```

### Multi-Tenant Filtering
- All queries automatically filter by `workspace_id` from JWT token
- No `workspace_id` in request body (security)
- Cross-workspace access returns 403 Forbidden

---

## Authentication Endpoints

### POST /auth/login
**Request:**
```json
{
  "email": "user@company.com",
  "password": "securepass123"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": "uuid",
      "email": "user@company.com",
      "full_name": "John Doe",
      "role": "MANAGER",
      "workspace_id": "uuid"
    }
  }
}
```

### POST /auth/refresh
**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:** Same as `/auth/login`

### POST /auth/logout
**Headers:** `Authorization: Bearer {token}`
**Response:** `{"success": true, "data": null}`

---

## Product Domain Endpoints

### GET /products
**Query Params:**
- `page`, `per_page`
- `category_id` (filter by category)
- `is_active` (true/false)
- `search` (searches SKU, name, description)

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "internal_sku": "ELE-CBL-001",
        "name": "4-Core 10mm Cable",
        "category": {"id": "uuid", "name": "Cables"},
        "brand": {"id": "uuid", "name": "Ducab"},
        "base_uom": {"id": "uuid", "code": "MTR"},
        "standard_sell_price": 12.50,
        "standard_cost_price": 8.75,
        "is_active": true,
        "quantity_on_hand": 1500.0000
      }
    ],
    "pagination": {...}
  }
}
```

### GET /products/{id}
**Response:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "internal_sku": "ELE-CBL-001",
    "name": "4-Core 10mm Cable",
    "description": "High quality electrical cable...",
    "category": {...},
    "brand": {...},
    "hs_code": "8544.49.00",
    "is_active": true,
    "track_inventory": true,
    "min_stock_level": 500.0000,
    "reorder_level": 1000.0000,
    "max_stock_level": 5000.0000,
    "reorder_quantity": 2000.0000,
    "base_uom": {...},
    "purchase_uom": {...},
    "sales_uom": {...},
    "standard_sell_price": 12.50,
    "standard_cost_price": 8.75,
    "vat_category": "STANDARD",
    "identifiers": [
      {"type": "SUPPLIER_CODE", "value": "DUC-4C10-A", "source": "Ducab"},
      {"type": "BARCODE", "value": "7891234567890"}
    ],
    "uom_conversions": [
      {"from_uom": "DRUM", "to_uom": "MTR", "conversion_factor": 500.0000}
    ],
    "warehouse_stock": [
      {"warehouse": "Main Warehouse", "quantity_on_hand": 1500.0000, "quantity_available": 1200.0000}
    ]
  }
}
```

### POST /products
**Request:**
```json
{
  "internal_sku": "ELE-CBL-001",
  "name": "4-Core 10mm Cable",
  "description": "High quality electrical cable",
  "category_id": "uuid",
  "brand_id": "uuid",
  "hs_code": "8544.49.00",
  "track_inventory": true,
  "min_stock_level": 500.0000,
  "reorder_level": 1000.0000,
  "reorder_quantity": 2000.0000,
  "base_uom_id": "uuid",
  "purchase_uom_id": "uuid",
  "sales_uom_id": "uuid",
  "standard_sell_price": 12.50,
  "standard_cost_price": 8.75,
  "vat_category": "STANDARD"
}
```

**Response:** Created product (201)

### PUT /products/{id}
**Request:** Same as POST (partial updates allowed)
**Response:** Updated product

### DELETE /products/{id}
**Response:** `{"success": true}` (soft delete, sets `deleted_at`)

---

## Supplier Domain Endpoints

### GET /suppliers
**Query Params:** `page`, `per_page`, `status`, `search`

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "Ducab LLC",
        "code": "SUP-001",
        "contact_person": "Ahmed Ali",
        "email": "sales@ducab.com",
        "phone": "+971-4-1234567",
        "payment_terms": "NET_30",
        "currency": "AED",
        "lead_time_days": 7,
        "status": "ACTIVE",
        "rating": 4.5
      }
    ],
    "pagination": {...}
  }
}
```

### GET /suppliers/{id}
**Response:** Full supplier details with contacts, bank accounts, documents

### POST /suppliers
**Request:**
```json
{
  "name": "Ducab LLC",
  "code": "SUP-001",
  "tax_registration_number": "100123456700003",
  "contact_person": "Ahmed Ali",
  "email": "sales@ducab.com",
  "phone": "+971-4-1234567",
  "address": "Jebel Ali Industrial Area, Dubai",
  "country": "UAE",
  "payment_terms": "NET_30",
  "currency": "AED",
  "credit_limit": 500000.00,
  "lead_time_days": 7
}
```

### POST /suppliers/{id}/contacts
**Request:**
```json
{
  "name": "Mohammed Hassan",
  "designation": "Sales Manager",
  "email": "mohammed@ducab.com",
  "phone": "+971-50-1234567",
  "is_primary": true
}
```

### POST /suppliers/{id}/bank-accounts
**Request:**
```json
{
  "bank_name": "Emirates NBD",
  "account_number": "1234567890",
  "iban": "AE070331234567890123456",
  "swift_code": "EBILAEAD",
  "currency": "AED",
  "is_primary": true
}
```

---

## Customer Domain Endpoints

### GET /clients
**Query Params:** `page`, `per_page`, `credit_status`, `search`

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "ABC Contracting LLC",
        "code": "CLI-001",
        "email": "accounts@abccontracting.ae",
        "phone": "+971-4-9876543",
        "payment_terms": "NET_30",
        "credit_limit": 100000.00,
        "credit_status": "ACTIVE",
        "outstanding_balance": 45000.00
      }
    ],
    "pagination": {...}
  }
}
```

### GET /clients/{id}
**Response:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "name": "ABC Contracting LLC",
    "code": "CLI-001",
    "email": "accounts@abccontracting.ae",
    "phone": "+971-4-9876543",
    "tax_id": "100234567800003",
    "billing_address": "Office 301, Business Bay, Dubai",
    "shipping_address": "Warehouse 5, Al Quoz Industrial Area",
    "country": "UAE",
    "payment_terms": "NET_30",
    "credit_limit": 100000.00,
    "credit_status": "ACTIVE",
    "credit_status_changed_at": "2026-08-15T10:30:00Z",
    "credit_status_reason": null,
    "outstanding_balance": 45000.00,
    "overdue_amount": 0.00,
    "oldest_overdue_days": 0,
    "open_invoices": [
      {"invoice_number": "INV-2026-0045", "balance_due": 25000.00, "due_date": "2026-09-15"}
    ]
  }
}
```

### POST /clients
**Request:**
```json
{
  "name": "ABC Contracting LLC",
  "code": "CLI-001",
  "email": "accounts@abccontracting.ae",
  "phone": "+971-4-9876543",
  "tax_id": "100234567800003",
  "billing_address": "Office 301, Business Bay, Dubai",
  "shipping_address": "Warehouse 5, Al Quoz Industrial Area",
  "country": "UAE",
  "payment_terms": "NET_30",
  "credit_limit": 100000.00
}
```

### PUT /clients/{id}/credit-status
**Request:**
```json
{
  "credit_status": "HOLD",
  "reason": "Credit limit exceeded by AED 15,000"
}
```

**Authorization:** Requires `can_manage_credit_status` permission

---

## Procurement Endpoints

### POST /procurement-requests
**Request:**
```json
{
  "product_id": "uuid",
  "quantity": 1000.0000,
  "uom_id": "uuid",
  "reason": "Reorder level reached",
  "required_by": "2026-09-15"
}
```

**Response:** Created PR with gapless `pr_number`

### POST /procurement-requests/{id}/approve
**Request:**
```json
{
  "approved": true,
  "notes": "Approved for urgent project"
}
```

**Authorization:** Requires `can_approve_procurement` permission

### POST /rfqs
**Request:**
```json
{
  "pr_id": "uuid",
  "valid_until": "2026-09-30",
  "supplier_ids": ["uuid1", "uuid2", "uuid3"],
  "items": [
    {
      "product_id": "uuid",
      "quantity": 1000.0000,
      "uom_id": "uuid",
      "specifications": "4-core, 10mm, red color"
    }
  ],
  "notes": "Required for project XYZ"
}
```

**Response:** Created RFQ with gapless `rfq_number`

### POST /rfqs/{id}/send
**Response:** RFQ status → `SENT`, emails sent to suppliers

### GET /supplier-rfq-responses
**Query Params:** `rfq_id`, `supplier_id`, `status`

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "rfq": {"id": "uuid", "rfq_number": "RFQ-2026-0001"},
        "supplier": {"id": "uuid", "name": "Ducab LLC"},
        "response_date": "2026-08-20",
        "status": "SUBMITTED",
        "lead_time_days": 7,
        "payment_terms": "NET_30",
        "total_amount": 12500.00,
        "items": [
          {
            "product": {"id": "uuid", "name": "4-Core 10mm Cable"},
            "quantity": 1000.0000,
            "unit_price": 12.50,
            "line_total": 12500.00
          }
        ]
      }
    ]
  }
}
```

### POST /supplier-rfq-responses/{id}/select
**Request:**
```json
{
  "selection_reason": "Best price and shortest lead time"
}
```

**Response:** Response status → `ACCEPTED`, creates SPO draft

### POST /supplier-purchase-orders
**Request:**
```json
{
  "supplier_id": "uuid",
  "rfq_id": "uuid",
  "supplier_rfq_response_id": "uuid",
  "expected_delivery_date": "2026-09-15",
  "warehouse_id": "uuid",
  "payment_terms": "NET_30",
  "delivery_terms": "DAP - Our Warehouse",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 1000.0000,
      "uom_id": "uuid",
      "unit_price": 12.50,
      "tax_rate": 5.00
    }
  ],
  "notes": "Urgent delivery required"
}
```

**Response:** Created SPO with gapless `spo_number`

### POST /supplier-purchase-orders/{id}/approve
**Authorization:** Required if `total_amount > workspace.spo_approval_threshold`

### POST /supplier-purchase-orders/{id}/send
**Response:** SPO status → `SENT`, email sent to supplier

### POST /supplier-portal/spos/{token}/acknowledge
**Public endpoint** (magic link from email)

**Request:**
```json
{
  "acknowledged_items": [
    {"spo_item_id": "uuid", "confirmed_quantity": 1000.0000},
    {"spo_item_id": "uuid", "confirmed_quantity": 800.0000}
  ],
  "notes": "Item 2 partially available, remaining 200 units backoordered"
}
```

**Response:** SPO status → `ACKNOWLEDGED`

### POST /grns
**Request:**
```json
{
  "spo_id": "uuid",
  "warehouse_id": "uuid",
  "received_date": "2026-09-15",
  "delivery_reference": "SHIP-12345",
  "items": [
    {
      "product_id": "uuid",
      "quantity_ordered": 1000.0000,
      "quantity_received": 1000.0000,
      "quantity_accepted": 950.0000,
      "quantity_damaged": 30.0000,
      "quantity_rejected": 20.0000,
      "uom_id": "uuid",
      "rejection_reason": "20 units failed QC - incorrect gauge",
      "batch_number": "BATCH-2026-08-001"
    }
  ],
  "notes": "Received in good condition overall"
}
```

**Response:** Created GRN with gapless `grn_number`

### POST /grns/{id}/accept
**Request:**
```json
{
  "inspected_by": "uuid",
  "inspection_notes": "QC inspection completed"
}
```

**Response:**
- GRN status → `ACCEPTED` or `PARTIALLY_ACCEPTED`
- Inventory increased by `quantity_accepted`
- StockTransactions created
- SPO `received_quantity` updated

### POST /supplier-invoices
**Request:**
```json
{
  "supplier_id": "uuid",
  "spo_id": "uuid",
  "grn_id": "uuid",
  "supplier_invoice_number": "SI-2026-08-001",
  "invoice_date": "2026-08-20",
  "due_date": "2026-09-20",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 950.0000,
      "uom_id": "uuid",
      "unit_price": 12.50,
      "tax_rate": 5.00
    }
  ]
}
```

**Response:**
- Created supplier invoice
- 3-way match automatically triggered
- `three_way_match_status` populated

### POST /supplier-invoices/{id}/approve
**Request:**
```json
{
  "override_match_failure": false,
  "override_reason": null
}
```

**Authorization:**
- Match status must be `PASSED` OR
- `override_match_failure=true` with `can_override_match_failures` permission

**Response:** Invoice `approval_status` → `APPROVED`

---

## Inventory Endpoints

### GET /warehouses
**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "Main Warehouse",
        "code": "WH-001",
        "address": "Jebel Ali Industrial Area",
        "city": "Dubai",
        "is_active": true
      }
    ]
  }
}
```

### GET /warehouse-stock
**Query Params:** `warehouse_id`, `product_id`, `low_stock=true`

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "warehouse": {"id": "uuid", "name": "Main Warehouse"},
        "product": {"id": "uuid", "sku": "ELE-CBL-001", "name": "4-Core 10mm Cable"},
        "quantity_on_hand": 1500.0000,
        "quantity_reserved": 300.0000,
        "quantity_available": 1200.0000,
        "quantity_damaged": 0.0000,
        "quantity_in_transit": 0.0000,
        "reorder_level": 1000.0000,
        "average_unit_cost": 8.75,
        "last_restocked_at": "2026-08-15T14:30:00Z"
      }
    ]
  }
}
```

### GET /stock-transactions
**Query Params:** `warehouse_id`, `product_id`, `transaction_type`, `start_date`, `end_date`

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "transaction_date": "2026-08-15T14:30:00Z",
        "transaction_type": "GRN_RECEIPT",
        "warehouse": {"name": "Main Warehouse"},
        "product": {"sku": "ELE-CBL-001"},
        "quantity_change": 1000.0000,
        "quantity_after": 1500.0000,
        "unit_cost": 8.75,
        "reference": {"type": "GRN", "number": "GRN-2026-0025"}
      }
    ],
    "pagination": {...}
  }
}
```

### POST /stock-reservations
**Request:**
```json
{
  "warehouse_id": "uuid",
  "product_id": "uuid",
  "quantity": 300.0000,
  "uom_id": "uuid",
  "cpo_id": "uuid"
}
```

**Response:**
- Created reservation with status `ACTIVE`
- `WarehouseStock.quantity_reserved` increased
- Returns 400 if insufficient stock and `allow_negative_stock=false`

### DELETE /stock-reservations/{id}
**Request:**
```json
{
  "cancellation_reason": "Customer cancelled order"
}
```

**Response:**
- Reservation status → `CANCELLED`
- `quantity_reserved` released

### POST /stock-transfers
**Request:**
```json
{
  "source_warehouse_id": "uuid",
  "destination_warehouse_id": "uuid",
  "product_id": "uuid",
  "quantity": 500.0000,
  "uom_id": "uuid",
  "expected_arrival_date": "2026-08-25",
  "notes": "Transfer for project site inventory"
}
```

**Response:** Created transfer with gapless `transfer_number`, status `DRAFT`

### POST /stock-transfers/{id}/approve
**Authorization:** Requires `can_approve_transfers` permission

**Response:** Transfer status → `APPROVED`

### POST /stock-transfers/{id}/dispatch
**Response:**
- Transfer status → `IN_TRANSIT`
- Source warehouse: `quantity_on_hand` decreased, `quantity_in_transit` increased
- StockTransaction type `TRANSFER_OUT` created

### POST /stock-transfers/{id}/receive
**Request:**
```json
{
  "received_quantity": 500.0000,
  "notes": "All items received in good condition"
}
```

**Response:**
- Transfer status → `RECEIVED`
- Destination warehouse: `quantity_on_hand` increased
- Source warehouse: `quantity_in_transit` decreased
- StockTransaction type `TRANSFER_IN` created

### POST /stock-adjustments
**Request:**
```json
{
  "warehouse_id": "uuid",
  "product_id": "uuid",
  "quantity_change": -50.0000,
  "uom_id": "uuid",
  "adjustment_type": "DAMAGE_WRITE_OFF",
  "reason": "Water damage discovered in storage area"
}
```

**Response:** Created adjustment with gapless `adjustment_number`, status `DRAFT`

### POST /stock-adjustments/{id}/approve
**Authorization:** Requires `can_approve_adjustments` permission

**Response:**
- Adjustment status → `APPROVED`
- `WarehouseStock.quantity_on_hand` updated
- StockTransaction created

### POST /stock-counts
**Request:**
```json
{
  "warehouse_id": "uuid",
  "count_type": "FULL",
  "scheduled_date": "2026-09-01"
}
```

**Response:** Created count with gapless `count_number`, status `SCHEDULED`

### POST /stock-counts/{id}/record-counts
**Request:**
```json
{
  "items": [
    {
      "product_id": "uuid",
      "expected_quantity": 1500.0000,
      "counted_quantity": 1485.0000,
      "notes": "Minor discrepancy"
    }
  ]
}
```

**Response:** Stock count status → `COMPLETED`

### POST /stock-counts/{id}/reconcile
**Response:**
- Stock count status → `RECONCILED`
- Auto-creates StockAdjustments for variances exceeding tolerance
- Small variances auto-approved (if within `workspace.stock_count_tolerance_percent`)

---

## Customer Sales Endpoints

### POST /enquiries
**Request:**
```json
{
  "client_id": "uuid",
  "enquiry_date": "2026-08-26",
  "source": "EMAIL",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 500.0000,
      "uom_id": "uuid",
      "specifications": "Red color preferred"
    }
  ],
  "notes": "Customer interested in bulk purchase"
}
```

**Response:** Created enquiry with gapless `enquiry_number`

### POST /quotations
**Request:**
```json
{
  "client_id": "uuid",
  "enquiry_id": "uuid",
  "quotation_date": "2026-08-26",
  "valid_until": "2026-09-26",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 500.0000,
      "uom_id": "uuid",
      "unit_price": 15.00,
      "tax_rate": 5.00,
      "description": "4-Core 10mm Cable - Red"
    }
  ],
  "terms_and_conditions": "Payment: NET 30 days. Delivery: 7 days from order confirmation.",
  "notes": "Bulk discount applied"
}
```

**Response:** Created quotation with gapless `quotation_number`

### POST /quotations/{id}/send
**Response:**
- Quotation status → `SENT`
- Email/WhatsApp sent to customer

### POST /quotations/{id}/accept
**Public endpoint** (customer confirmation link)

**Response:** Quotation status → `ACCEPTED`

### POST /customer-purchase-orders
**Request:**
```json
{
  "client_id": "uuid",
  "quotation_id": "uuid",
  "customer_po_number": "CUST-PO-12345",
  "order_date": "2026-08-26",
  "expected_delivery_date": "2026-09-05",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 500.0000,
      "uom_id": "uuid",
      "unit_price": 15.00,
      "tax_rate": 5.00
    }
  ],
  "delivery_address": "Customer warehouse, Al Quoz",
  "notes": "Urgent delivery required"
}
```

**Response:** Created CPO with gapless `cpo_number`

### POST /customer-purchase-orders/{id}/confirm
**Request:**
```json
{
  "override_credit_hold": false,
  "override_reason": null
}
```

**Business Rules:**
- Credit check runs automatically
- If client `credit_status = HOLD` and `workspace.block_po_on_hold = true`:
  - Requires `override_credit_hold=true` with `can_override_credit_hold` permission
- Stock reservations created if inventory tracked

**Response:** CPO status → `CONFIRMED`

### POST /invoices
**Request:**
```json
{
  "client_id": "uuid",
  "cpo_id": "uuid",
  "invoice_date": "2026-08-26",
  "due_date": "2026-09-26",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 500.0000,
      "uom_id": "uuid",
      "unit_price": 15.00,
      "tax_rate": 5.00,
      "description": "4-Core 10mm Cable - Red"
    }
  ],
  "notes": "Thank you for your business"
}
```

**Response:** Created invoice with gapless `invoice_number`, status `DRAFT`

### PUT /invoices/{id}
**Authorization:** Invoice must be in `DRAFT` status

**Response:** Updated invoice

### POST /invoices/{id}/send
**Response:**
- Invoice status → `SENT`
- Email/WhatsApp sent to customer
- `sent_at` timestamp set

### POST /delivery-orders
**Request:**
```json
{
  "client_id": "uuid",
  "cpo_id": "uuid",
  "warehouse_id": "uuid",
  "delivery_date": "2026-09-05",
  "delivery_address": "Customer warehouse, Al Quoz",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 500.0000,
      "uom_id": "uuid"
    }
  ]
}
```

**Response:** Created DO with gapless `do_number`, status `DRAFT`

### POST /delivery-orders/{id}/dispatch
**Request:**
```json
{
  "override_credit_hold": false
}
```

**Business Rules:**
- Credit check runs if `workspace.block_do_on_hold = true`
- Active stock reservation required
- Reservation status → `DISPATCHED`
- Stock `quantity_on_hand` decreased
- StockTransaction type `DELIVERY_DISPATCH` created

**Response:** DO status → `DISPATCHED`

### POST /payments
**Headers:** `Idempotency-Key: {uuid}` (mandatory)

**Request:**
```json
{
  "client_id": "uuid",
  "invoice_id": "uuid",
  "payment_date": "2026-08-26",
  "amount": 7875.00,
  "payment_method": "BANK_TRANSFER",
  "reference_number": "TXN-987654321",
  "notes": "Payment received via bank transfer"
}
```

**Business Rules:**
- Amount cannot exceed `invoice.balance_due` (overpayment blocked)
- Idempotency key prevents duplicate payments (48h TTL)
- Invoice `amount_paid` increased, `balance_due` decreased
- Invoice status auto-updates: `PARTIALLY_PAID` or `PAID`
- Credit status recalculated

**Response:** Created payment with gapless `payment_number` (201)

### POST /payments/pdc
**Headers:** `Idempotency-Key: {uuid}`

**Request:**
```json
{
  "client_id": "uuid",
  "invoice_id": "uuid",
  "payment_date": "2026-08-26",
  "amount": 7875.00,
  "payment_method": "PDC",
  "reference_number": "CHEQUE-123456",
  "pdc_clearing_date": "2026-09-30",
  "notes": "Post-dated cheque"
}
```

**Business Rules:**
- Payment status `PDC_PENDING` until clearing date
- Invoice balance NOT reduced until PDC clears
- Background job checks clearing date daily

**Response:** Created PDC payment (201)

### PUT /payments/{id}/pdc-status
**Request:**
```json
{
  "pdc_status": "CLEARED",
  "notes": "Cheque cleared successfully"
}
```

**Business Rules:**
- Status `CLEARED`: Invoice balance reduced, credit recalculated
- Status `BOUNCED`: Invoice balance unchanged, customer notified, credit status → `HOLD`

**Authorization:** Requires `can_manage_payments` permission

---

## Returns & Adjustments Endpoints

### POST /sales-returns
**Request:**
```json
{
  "client_id": "uuid",
  "invoice_id": "uuid",
  "delivery_order_id": "uuid",
  "return_date": "2026-08-26",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 50.0000,
      "uom_id": "uuid",
      "unit_price": 15.00,
      "return_type": "QUALITY_ISSUE",
      "notes": "Customer reported damaged insulation"
    }
  ],
  "reason": "Quality issue reported by customer"
}
```

**Response:** Created sales return with gapless `return_number`, status `DRAFT`

### POST /sales-returns/{id}/approve
**Response:**
- Sales return status → `APPROVED`
- Auto-creates CreditNote

### POST /purchase-returns
**Request:**
```json
{
  "supplier_id": "uuid",
  "grn_id": "uuid",
  "return_date": "2026-08-26",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 20.0000,
      "uom_id": "uuid",
      "unit_price": 12.50,
      "return_type": "QUALITY_ISSUE",
      "notes": "Failed QC inspection"
    }
  ],
  "reason": "Quality issue - incorrect gauge"
}
```

**Response:** Created purchase return with gapless `return_number`, status `DRAFT`

### POST /purchase-returns/{id}/dispatch
**Response:**
- Purchase return status → `DISPATCHED`
- Auto-creates DebitNote

### POST /credit-notes
**Request:**
```json
{
  "client_id": "uuid",
  "invoice_id": "uuid",
  "sales_return_id": "uuid",
  "issue_date": "2026-08-26",
  "amount": 787.50,
  "reason": "Sales return - quality issue"
}
```

**Response:** Created credit note with gapless `credit_note_number`

### POST /credit-notes/{id}/apply
**Response:**
- Credit note status → `APPLIED`
- Linked invoice `balance_due` reduced
- Credit recalculated

### POST /debit-notes
**Request:**
```json
{
  "supplier_id": "uuid",
  "supplier_invoice_id": "uuid",
  "purchase_return_id": "uuid",
  "issue_date": "2026-08-26",
  "amount": 262.50,
  "reason": "Purchase return - quality issue"
}
```

**Response:** Created debit note with gapless `debit_note_number`

---

## Reports Endpoints

### GET /reports/sales-summary
**Query Params:** `start_date`, `end_date`, `client_id`

**Response:**
```json
{
  "success": true,
  "data": {
    "total_sales": 125000.00,
    "total_invoices": 45,
    "total_paid": 98000.00,
    "total_outstanding": 27000.00,
    "by_client": [
      {"client_name": "ABC Contracting", "total_sales": 45000.00, "outstanding": 12000.00}
    ]
  }
}
```

### GET /reports/inventory-valuation
**Query Params:** `warehouse_id`, `valuation_date`

**Response:**
```json
{
  "success": true,
  "data": {
    "total_value": 875000.00,
    "by_category": [
      {"category": "Cables", "quantity": 15000.0000, "value": 350000.00}
    ],
    "by_warehouse": [
      {"warehouse": "Main Warehouse", "value": 875000.00}
    ]
  }
}
```

### GET /reports/aging-report
**Query Params:** `report_type=AR|AP`, `as_of_date`

**Response:**
```json
{
  "success": true,
  "data": {
    "report_type": "AR",
    "as_of_date": "2026-08-26",
    "summary": {
      "current": 125000.00,
      "30_days": 45000.00,
      "60_days": 15000.00,
      "90_days": 5000.00,
      "over_90": 10000.00,
      "total": 200000.00
    },
    "by_client": [
      {
        "client": "ABC Contracting",
        "current": 25000.00,
        "30_days": 15000.00,
        "60_days": 0.00,
        "90_days": 0.00,
        "over_90": 0.00,
        "total": 40000.00
      }
    ]
  }
}
```

---

## Background Jobs & Webhooks

### Background Jobs (Celery Beat)
1. **Daily at 00:00 UTC:**
   - Expire RFQs (`valid_until < today`)
   - Mark invoices as `OVERDUE` (`due_date < today AND balance_due > 0`)
   - Update credit status (aging calculation)
   - Check PDC clearing dates
   - Expire stock reservations (>7 days old)
   - Reorder level alerts

2. **Every 5 minutes:**
   - Process OCR jobs queue

### Webhook Events (Wave 27)
Workspace can configure webhook URL to receive events:

**Event Types:**
- `invoice.created`
- `invoice.paid`
- `invoice.overdue`
- `payment.received`
- `pdc.bounced`
- `stock.low_level`
- `spo.acknowledged`
- `grn.accepted`

**Payload Format:**
```json
{
  "event": "invoice.paid",
  "timestamp": "2026-08-26T14:30:00Z",
  "workspace_id": "uuid",
  "data": {
    "invoice_id": "uuid",
    "invoice_number": "INV-2026-0045",
    "client": "ABC Contracting",
    "amount": 7875.00
  }
}
```

---

## Error Codes

### Standard HTTP Status Codes
- `200` OK
- `201` Created
- `400` Bad Request (validation error)
- `401` Unauthorized (invalid/missing token)
- `403` Forbidden (insufficient permissions or cross-workspace access)
- `404` Not Found
- `405` Method Not Allowed (e.g., UPDATE on Payment)
- `409` Conflict (e.g., duplicate SKU)
- `422` Unprocessable Entity (business logic violation)
- `500` Internal Server Error

### Custom Error Codes
```
INSUFFICIENT_STOCK
CREDIT_LIMIT_EXCEEDED
CREDIT_HOLD_ACTIVE
DUPLICATE_SKU
DUPLICATE_INVOICE
INVALID_STATE_TRANSITION
MATCH_FAILED_QTY
MATCH_FAILED_PRICE
MATCH_FAILED_TAX
OVERPAYMENT_NOT_ALLOWED
NEGATIVE_STOCK_NOT_ALLOWED
INVOICE_NOT_EDITABLE
RESERVATION_REQUIRED
UNRECEIVED_ITEMS
WORKSPACE_MISMATCH
```

---

**End of API Contracts Specification**
