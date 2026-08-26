# Domain Model Specification

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## 1. Workspace Domain

### Workspace (EXTEND existing)

**Purpose:** Multi-tenant workspace configuration with market-specific settings.

**Fields:**
- `market`: Enum [UAE, INDIA] — default UAE
- `currency`: str — default AED
- `trn`: str — UAE Tax Registration Number
- `company_whatsapp`: str — WhatsApp Business number
- `company_email`: str
- `company_logo_url`: str
- `company_address`: str
- `vat_rate`: Decimal(5,2) — default 5.00
- `price_tolerance_percent`: Decimal(5,2) — default 2.00 (3-way matching tolerance)
- `credit_warning_days`: int — default 60
- `credit_hold_days`: int — default 90
- `block_po_on_hold`: bool — default True
- `block_do_on_hold`: bool — default True
- `block_invoice_on_hold`: bool — default False
- `require_po_approval`: bool — default False
- `allow_negative_stock`: bool — default False
- `auto_reserve_on_invoice`: bool — default True

**Constraints:**
- `workspace_id` is the multi-tenancy key for ALL entities
- VAT rate must be non-negative
- Credit warning days < credit hold days

---

## 2. Product Domain

### Category

**Purpose:** Product categorization with support for subcategories.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID (FK → workspaces)
- `name`: str
- `parent_id`: UUID (FK → categories, nullable) — supports subcategories
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `name` UNIQUE per workspace
- Circular parent references disallowed

---

### Brand

**Purpose:** Product brand and manufacturer information.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `name`: str
- `manufacturer`: str
- `country_of_origin`: str
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `name` UNIQUE per workspace

---

### UnitOfMeasure

**Purpose:** Standard units of measure for inventory and sales.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `code`: str — (PCS, MTR, KG, BOX, DRUM, CARTON, ROLL, COIL, PACK, SET, PAIR, LTR, SQM, CBM, TON, BUNDLE)
- `name`: str
- `dimension`: Enum [COUNT, LENGTH, WEIGHT, AREA, VOLUME, TIME]
- `is_base`: bool
- `created_at`: datetime

**Constraints:**
- `code` UNIQUE per workspace
- Only one `is_base=true` UOM per dimension per workspace

---

### Product

**Purpose:** Core product master with inventory tracking configuration.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `internal_sku`: str — UNIQUE per workspace (e.g., ELE-CBL-DUC-4C10)
- `name`: str
- `short_description`: str
- `description`: Text
- `category_id`: UUID (FK → categories)
- `brand_id`: UUID (FK → brands, nullable)
- `hs_code`: str — FTA/customs compliance
- `is_active`: bool — default True
- `track_inventory`: bool — default True
- `min_stock_level`: Decimal(12,4)
- `reorder_level`: Decimal(12,4)
- `max_stock_level`: Decimal(12,4)
- `reorder_quantity`: Decimal(12,4)
- `base_uom_id`: UUID (FK → unit_of_measures)
- `purchase_uom_id`: UUID (FK → unit_of_measures)
- `sales_uom_id`: UUID (FK → unit_of_measures)
- `standard_sell_price`: Decimal(12,2)
- `standard_cost_price`: Decimal(12,2)
- `vat_category`: Enum [STANDARD, ZERO_RATED, EXEMPT]
- `created_at`: datetime
- `updated_at`: datetime
- `deleted_at`: datetime (nullable)

**Constraints:**
- `internal_sku` UNIQUE per workspace
- Soft delete only (never hard delete)
- Stock levels must be non-negative
- `base_uom_id`, `purchase_uom_id`, `sales_uom_id` all required if `track_inventory=true`

---

### ProductIdentifier

**Purpose:** Multiple identifier codes per product (MPN, barcode, supplier codes, customer codes).

**Fields:**
- `id`: UUID
- `product_id`: UUID (FK → products, ON DELETE CASCADE)
- `identifier_type`: Enum [INTERNAL_SKU, MANUFACTURER_PART_NUMBER, SUPPLIER_CODE, BARCODE, CUSTOMER_CODE, EAN, UPC]
- `identifier_value`: str
- `source`: str — who assigned it (e.g., "DUCAB", "Customer ABC")
- `is_primary`: bool
- `created_at`: datetime

**Constraints:**
- `(identifier_type, identifier_value, product_id)` UNIQUE
- Only one `is_primary=true` per `identifier_type` per product

---

### ProductUOMConversion

**Purpose:** Per-product unit of measure conversions (NOT global).

**Fields:**
- `id`: UUID
- `product_id`: UUID (FK → products, ON DELETE CASCADE)
- `from_uom_id`: UUID (FK → unit_of_measures)
- `to_uom_id`: UUID (FK → unit_of_measures)
- `conversion_factor`: Decimal(10,4)
- `created_at`: datetime

**Constraints:**
- `(product_id, from_uom_id, to_uom_id)` UNIQUE
- `conversion_factor` must be positive
- `from_uom_id ≠ to_uom_id`

**Critical Rule:** Conversions are per-product. System MUST NEVER assume global UOM conversion. 1 DRUM of Product X = 500 MTR, but 1 DRUM of Product Y = 300 MTR.

---

### ProductPrice

**Purpose:** Customer-specific, customer-group, and standard pricing with quantity breaks.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `product_id`: UUID (FK → products)
- `entity_type`: Enum [CUSTOMER, CUSTOMER_GROUP, STANDARD]
- `entity_id`: UUID (nullable) — customer_id or group_id
- `min_quantity`: Decimal
- `max_quantity`: Decimal
- `unit_price`: Decimal(12,2)
- `currency`: str
- `valid_from`: date
- `valid_to`: date (nullable)
- `created_at`: datetime

**Constraints:**
- `min_quantity` ≤ `max_quantity`
- No overlapping quantity ranges for same (product, entity_type, entity_id, date range)

---

## 3. Supplier Domain

### Supplier

**Purpose:** Supplier master with financial terms and status tracking.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `supplier_code`: str — UNIQUE per workspace (e.g., SUP-001)
- `legal_name`: str
- `trade_name`: str
- `contact_person`: str
- `phone`: str
- `whatsapp`: str
- `email`: str
- `website`: str
- `address`: str
- `country`: str
- `trn`: str — Supplier VAT/Tax Registration Number
- `currency`: str — default AED
- `payment_terms_days`: int — default 30
- `credit_limit`: Decimal(12,2) — default 0
- `bank_name`: str
- `bank_account`: str
- `bank_iban`: str
- `bank_swift`: str
- `status`: Enum [ACTIVE, INACTIVE, ON_HOLD, BLOCKED, BLACKLISTED]
- `rating`: int — 1–5
- `is_preferred`: bool
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime
- `deleted_at`: datetime (nullable)

**Constraints:**
- `supplier_code` UNIQUE per workspace
- Soft delete only
- `rating` between 1 and 5 (inclusive)

---

### SupplierContact

**Purpose:** Multiple contacts per supplier.

**Fields:**
- `id`: UUID
- `supplier_id`: UUID (FK → suppliers)
- `name`: str
- `title`: str
- `phone`: str
- `whatsapp`: str
- `email`: str
- `is_primary`: bool
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- Only one `is_primary=true` per supplier

---

### SupplierBankAccount

**Purpose:** Multiple bank accounts per supplier for payments.

**Fields:**
- `id`: UUID
- `supplier_id`: UUID (FK → suppliers)
- `bank_name`: str
- `account_name`: str
- `account_number`: str
- `iban`: str
- `swift`: str
- `currency`: str
- `is_primary`: bool
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- Only one `is_primary=true` per supplier

---

### SupplierDocument

**Purpose:** Document storage for supplier certificates, licenses, trade permits.

**Fields:**
- `id`: UUID
- `supplier_id`: UUID (FK → suppliers)
- `document_type`: Enum [TRADE_LICENSE, VAT_CERTIFICATE, ISO_CERT, INSURANCE, CONTRACT, OTHER]
- `file_url`: str
- `expiry_date`: date (nullable)
- `uploaded_at`: datetime
- `uploaded_by`: UUID (FK → users)

**Constraints:**
- Alert when `expiry_date` within 30 days

---

### SupplierProduct

**Purpose:** Supplier-specific product codes and lead times.

**Fields:**
- `id`: UUID
- `supplier_id`: UUID (FK → suppliers)
- `product_id`: UUID (FK → products)
- `supplier_product_code`: str
- `supplier_product_name`: str (nullable)
- `lead_time_days`: int
- `min_order_quantity`: Decimal(12,4)
- `last_purchase_price`: Decimal(12,2)
- `last_purchase_date`: date (nullable)
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `(supplier_id, product_id)` UNIQUE

---

## 4. Customer Domain

### Client (EXTEND existing)

**Purpose:** Customer master with credit control fields.

**Existing fields:** (from P0-P4)
- `id`, `workspace_id`, `name`, `email`, `phone`, `address`, `tax_id`, `created_at`, `updated_at`

**New fields:**
- `client_code`: str — UNIQUE per workspace (e.g., CL-001)
- `legal_name`: str
- `trade_name`: str
- `contact_person`: str
- `whatsapp`: str
- `trn`: str — Customer VAT/Tax Registration Number
- `billing_address`: Text
- `shipping_address`: Text
- `currency`: str — default AED
- `credit_limit`: Decimal(12,2) — default 0
- `credit_terms_days`: int — default 30
- `credit_status`: Enum [ACTIVE, WARNING, HOLD, SUSPENDED]
- `credit_status_changed_at`: datetime (nullable)
- `credit_status_changed_by`: UUID (FK → users, nullable)
- `credit_status_reason`: Text (nullable)
- `payment_terms`: str
- `is_active`: bool — default True
- `deleted_at`: datetime (nullable)

**Constraints:**
- `client_code` UNIQUE per workspace
- Soft delete only
- `credit_limit` must be non-negative

---

## 5. Procurement Domain

### ProcurementRequest

**Purpose:** Internal procurement requisition with approval workflow.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `pr_number`: str — gapless (PR-YYYY-XXXX)
- `requested_by`: UUID (FK → users)
- `requested_date`: date
- `required_by_date`: date
- `source_type`: Enum [STOCK_REPLENISHMENT, CUSTOMER_ORDER, PROJECT, MANUAL]
- `source_id`: UUID (nullable) — CPO ID if CUSTOMER_ORDER
- `status`: Enum [DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED, PARTIALLY_ORDERED, FULLY_ORDERED, FULFILLED, CANCELLED]
- `approved_by`: UUID (FK → users, nullable)
- `approved_at`: datetime (nullable)
- `rejection_reason`: Text (nullable)
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `pr_number` UNIQUE per workspace
- Gapless numbering enforced via `SELECT FOR UPDATE`

---

### ProcurementRequestItem

**Fields:**
- `id`: UUID
- `pr_id`: UUID (FK → procurement_requests)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `estimated_unit_price`: Decimal(12,2)
- `notes`: Text
- `created_at`: datetime

---

### RFQ (Request for Quotation)

**Purpose:** Multi-supplier quote request.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `rfq_number`: str — gapless (RFQ-YYYY-XXXX)
- `pr_id`: UUID (FK → procurement_requests, nullable)
- `created_by`: UUID (FK → users)
- `created_date`: date
- `due_date`: date
- `status`: Enum [DRAFT, SENT, PARTIALLY_RESPONDED, FULLY_RESPONDED, CLOSED, EXPIRED, CANCELLED]
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `rfq_number` UNIQUE per workspace

---

### RFQItem

**Fields:**
- `id`: UUID
- `rfq_id`: UUID (FK → rfqs)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `specifications`: Text
- `created_at`: datetime

---

### SupplierRFQResponse

**Purpose:** Supplier's quote in response to RFQ.

**Fields:**
- `id`: UUID
- `rfq_id`: UUID (FK → rfqs)
- `supplier_id`: UUID (FK → suppliers)
- `status`: Enum [PENDING, RECEIVED, SELECTED, REJECTED, DECLINED, EXPIRED]
- `quoted_date`: date (nullable)
- `valid_until`: date (nullable)
- `payment_terms`: str
- `delivery_lead_time`: int — days
- `total_amount`: Decimal(12,2)
- `currency`: str
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `(rfq_id, supplier_id)` UNIQUE

---

### SupplierRFQResponseItem

**Fields:**
- `id`: UUID
- `response_id`: UUID (FK → supplier_rfq_responses)
- `rfq_item_id`: UUID (FK → rfq_items)
- `unit_price`: Decimal(12,2)
- `tax_rate`: Decimal(5,2)
- `tax_amount`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `lead_time_days`: int
- `notes`: Text
- `created_at`: datetime

---

### SupplierPurchaseOrder (EXTEND existing)

**Purpose:** Supplier purchase order with approval workflow.

**Existing fields:** (from P0-P4)
- `id`, `workspace_id`, `spo_number`, `supplier_id`, `created_by`, `order_date`, `expected_delivery_date`, `status`, `created_at`, `updated_at`

**New fields:**
- `rfq_id`: UUID (FK → rfqs, nullable)
- `pr_id`: UUID (FK → procurement_requests, nullable)
- `status`: Enum [DRAFT, PENDING_APPROVAL, APPROVED, SENT, ACKNOWLEDGED, REJECTED, PARTIALLY_RECEIVED, FULLY_RECEIVED, PARTIALLY_CANCELLED, CANCELLED, CLOSED]
- `approved_by`: UUID (FK → users, nullable)
- `approved_at`: datetime (nullable)
- `sent_at`: datetime (nullable)
- `acknowledged_at`: datetime (nullable)
- `payment_terms_days`: int
- `shipping_address`: Text
- `subtotal`: Decimal(12,2)
- `tax_amount`: Decimal(12,2)
- `total_amount`: Decimal(12,2)
- `currency`: str
- `notes`: Text
- `deleted_at`: datetime (nullable)

**Constraints:**
- Soft delete only
- State transitions validated by StateMachineService

---

### SupplierPurchaseOrderItem (EXTEND existing)

**Existing fields:**
- `id`, `spo_id`, `product_id`, `quantity`, `unit_price`, `total_price`, `created_at`

**New fields:**
- `uom_id`: UUID (FK → unit_of_measures)
- `tax_rate`: Decimal(5,2)
- `tax_amount`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `received_quantity`: Decimal(12,4) — default 0
- `invoiced_quantity`: Decimal(12,4) — default 0

---

### GoodsReceiptNote (EXTEND existing)

**Purpose:** Goods receiving with per-item accept/reject.

**Existing fields:**
- `id`, `workspace_id`, `grn_number`, `spo_id`, `received_by`, `received_date`, `status`, `created_at`, `updated_at`

**New fields:**
- `warehouse_id`: UUID (FK → warehouses)
- `status`: Enum [DRAFT, RECEIVING, PENDING_INSPECTION, PARTIALLY_ACCEPTED, ACCEPTED, PARTIALLY_REJECTED, REJECTED, CANCELLED]
- `inspection_notes`: Text
- `inspected_by`: UUID (FK → users, nullable)
- `inspected_at`: datetime (nullable)
- `deleted_at`: datetime (nullable)

**Constraints:**
- Soft delete only

---

### GoodsReceiptNoteItem (EXTEND existing)

**Existing fields:**
- `id`, `grn_id`, `spo_item_id`, `product_id`, `quantity_received`, `created_at`

**New fields:**
- `quantity_ordered`: Decimal(12,4)
- `quantity_accepted`: Decimal(12,4) — default 0
- `quantity_rejected`: Decimal(12,4) — default 0
- `quantity_damaged`: Decimal(12,4) — default 0
- `uom_id`: UUID (FK → unit_of_measures)
- `rejection_reason`: Text (nullable)
- `inspection_notes`: Text

**Constraints:**
- `quantity_accepted + quantity_rejected + quantity_damaged = quantity_received`

---

### SupplierInvoice (EXTEND existing)

**Purpose:** Supplier invoice with 3-way matching.

**Existing fields:**
- `id`, `workspace_id`, `invoice_number`, `supplier_id`, `invoice_date`, `due_date`, `subtotal`, `tax_amount`, `total_amount`, `status`, `created_at`, `updated_at`

**New fields:**
- `spo_id`: UUID (FK → supplier_purchase_orders, nullable)
- `grn_id`: UUID (FK → goods_receipt_notes, nullable)
- `status`: Enum [RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID, CANCELLED]
- `three_way_match_status`: Enum [PENDING, MATCHED, FAILED_QTY, FAILED_PRICE, FAILED_TAX, DUPLICATE_INVOICE, UNRECEIVED_ITEMS]
- `match_checked_at`: datetime (nullable)
- `match_checked_by`: UUID (FK → users, nullable)
- `discrepancy_notes`: Text (nullable)
- `approved_by`: UUID (FK → users, nullable)
- `approved_at`: datetime (nullable)
- `amount_paid`: Decimal(12,2) — default 0
- `balance_due`: Decimal(12,2)
- `currency`: str
- `payment_terms_days`: int
- `deleted_at`: datetime (nullable)

**Constraints:**
- `invoice_number` UNIQUE per (workspace_id, supplier_id)
- Soft delete only

---

## 6. Inventory Domain

### Warehouse

**Purpose:** Physical warehouse locations.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `warehouse_code`: str — UNIQUE per workspace
- `name`: str
- `address`: Text
- `manager_id`: UUID (FK → users, nullable)
- `is_active`: bool — default True
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `warehouse_code` UNIQUE per workspace

---

### WarehouseLocation

**Purpose:** Bin locations within warehouses (schema only for MVP, not enforced).

**Fields:**
- `id`: UUID
- `warehouse_id`: UUID (FK → warehouses)
- `zone`: str (nullable)
- `rack`: str (nullable)
- `shelf`: str (nullable)
- `bin`: str (nullable)
- `location_code`: str — UNIQUE per warehouse
- `created_at`: datetime

**Constraints:**
- `location_code` UNIQUE per warehouse

---

### WarehouseStock

**Purpose:** Current stock levels per product per warehouse.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `warehouse_id`: UUID (FK → warehouses)
- `product_id`: UUID (FK → products)
- `quantity_on_hand`: Decimal(12,4) — default 0
- `quantity_reserved`: Decimal(12,4) — default 0
- `quantity_damaged`: Decimal(12,4) — default 0
- `quantity_in_transit`: Decimal(12,4) — default 0
- `last_updated_at`: datetime
- `created_at`: datetime

**Constraints:**
- `(warehouse_id, product_id)` UNIQUE
- All quantities must be non-negative (unless `workspace.allow_negative_stock=true`)
- Available quantity = `quantity_on_hand - quantity_reserved - quantity_damaged`

---

### StockTransaction

**Purpose:** Immutable audit trail of all stock movements.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `warehouse_id`: UUID (FK → warehouses)
- `product_id`: UUID (FK → products)
- `transaction_type`: Enum [GRN_RECEIPT, DO_DISPATCH, ADJUSTMENT, TRANSFER_OUT, TRANSFER_IN, DAMAGE, WRITE_OFF]
- `transaction_date`: datetime
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `reference_type`: str — e.g., "GRN", "DO", "StockAdjustment"
- `reference_id`: UUID
- `balance_after`: Decimal(12,4)
- `created_by`: UUID (FK → users)
- `created_at`: datetime

**Constraints:**
- **Immutable** — NO UPDATE or DELETE allowed (financial audit trail)
- Must create new record for every stock movement

---

### StockReservation

**Purpose:** Reserve stock for pending deliveries.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `warehouse_id`: UUID (FK → warehouses)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `reserved_for_type`: str — e.g., "DeliveryOrder", "Invoice"
- `reserved_for_id`: UUID
- `reserved_at`: datetime
- `reserved_by`: UUID (FK → users)
- `released_at`: datetime (nullable)
- `status`: Enum [ACTIVE, RELEASED, DISPATCHED]
- `created_at`: datetime

**Constraints:**
- Row-level lock (`SELECT FOR NO KEY UPDATE`) when creating reservation to prevent race conditions

---

### StockTransfer

**Purpose:** Inter-warehouse stock transfers.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `transfer_number`: str — gapless (TRF-YYYY-XXXX)
- `from_warehouse_id`: UUID (FK → warehouses)
- `to_warehouse_id`: UUID (FK → warehouses)
- `transfer_date`: date
- `requested_by`: UUID (FK → users)
- `approved_by`: UUID (FK → users, nullable)
- `approved_at`: datetime (nullable)
- `status`: Enum [DRAFT, REQUESTED, APPROVED, IN_TRANSIT, PARTIALLY_RECEIVED, RECEIVED, CANCELLED]
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `transfer_number` UNIQUE per workspace
- `from_warehouse_id ≠ to_warehouse_id`

---

### StockTransferItem

**Fields:**
- `id`: UUID
- `transfer_id`: UUID (FK → stock_transfers)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `quantity_received`: Decimal(12,4) — default 0
- `created_at`: datetime

---

### StockAdjustment

**Purpose:** Manual stock adjustments with approval.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `adjustment_number`: str — gapless (ADJ-YYYY-XXXX)
- `warehouse_id`: UUID (FK → warehouses)
- `product_id`: UUID (FK → products)
- `adjustment_date`: date
- `current_quantity`: Decimal(12,4)
- `adjusted_quantity`: Decimal(12,4)
- `variance`: Decimal(12,4) — adjusted_quantity - current_quantity
- `uom_id`: UUID (FK → unit_of_measures)
- `reason`: Enum [DAMAGE, LOSS, THEFT, COUNT_CORRECTION, EXPIRY, OTHER]
- `reason_notes`: Text
- `requested_by`: UUID (FK → users)
- `approved_by`: UUID (FK → users, nullable)
- `status`: Enum [PENDING_APPROVAL, APPROVED, REJECTED]
- `approved_at`: datetime (nullable)
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `adjustment_number` UNIQUE per workspace
- Cannot approve own adjustment

---

### StockCount

**Purpose:** Physical stock count workflow.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `count_number`: str — gapless (CNT-YYYY-XXXX)
- `warehouse_id`: UUID (FK → warehouses)
- `count_date`: date
- `counted_by`: UUID (FK → users)
- `approved_by`: UUID (FK → users, nullable)
- `status`: Enum [DRAFT, COUNTING, VARIANCE_REVIEW, APPROVED, ADJUSTMENT_POSTED, CLOSED]
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `count_number` UNIQUE per workspace

---

### StockCountItem

**Fields:**
- `id`: UUID
- `count_id`: UUID (FK → stock_counts)
- `product_id`: UUID (FK → products)
- `system_quantity`: Decimal(12,4) — from WarehouseStock
- `counted_quantity`: Decimal(12,4)
- `variance`: Decimal(12,4) — counted_quantity - system_quantity
- `uom_id`: UUID (FK → unit_of_measures)
- `notes`: Text
- `created_at`: datetime

---

## 7. Customer Sales Domain

### Enquiry

**Purpose:** Customer enquiry tracking with WhatsApp integration.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `enquiry_number`: str — gapless (ENQ-YYYY-XXXX)
- `client_id`: UUID (FK → clients, nullable)
- `contact_name`: str
- `contact_phone`: str
- `contact_email`: str (nullable)
- `enquiry_date`: date
- `source`: Enum [PHONE, EMAIL, WHATSAPP, WALK_IN, WEBSITE, OTHER]
- `status`: Enum [NEW, CONTACTED, QUOTED, WON, LOST, CANCELLED]
- `assigned_to`: UUID (FK → users, nullable)
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `enquiry_number` UNIQUE per workspace

---

### EnquiryItem

**Fields:**
- `id`: UUID
- `enquiry_id`: UUID (FK → enquiries)
- `product_id`: UUID (FK → products, nullable)
- `product_description`: str
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures, nullable)
- `created_at`: datetime

---

### Quotation

**Purpose:** Customer quotation with revision support.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `quotation_number`: str — gapless (QUO-YYYY-XXXX)
- `enquiry_id`: UUID (FK → enquiries, nullable)
- `client_id`: UUID (FK → clients)
- `quotation_date`: date
- `valid_until`: date
- `revision_number`: int — default 0
- `revised_from_id`: UUID (FK → quotations, nullable)
- `status`: Enum [DRAFT, SENT, ACCEPTED, REJECTED, EXPIRED, REVISED, CONVERTED]
- `subtotal`: Decimal(12,2)
- `tax_amount`: Decimal(12,2)
- `total_amount`: Decimal(12,2)
- `currency`: str
- `payment_terms`: str
- `delivery_terms`: str
- `notes`: Text
- `created_by`: UUID (FK → users)
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `quotation_number` UNIQUE per workspace
- Revision increments on copy (QUO-2026-0001 Rev 1, Rev 2, etc.)

---

### QuotationItem

**Fields:**
- `id`: UUID
- `quotation_id`: UUID (FK → quotations)
- `product_id`: UUID (FK → products)
- `description`: str
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `unit_price`: Decimal(12,2)
- `discount_percent`: Decimal(5,2) — default 0
- `discount_amount`: Decimal(12,2) — default 0
- `tax_rate`: Decimal(5,2)
- `tax_amount`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `created_at`: datetime

---

### CustomerPurchaseOrder

**Purpose:** Customer PO received (our reference).

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `cpo_number`: str — gapless (CPO-YYYY-XXXX)
- `quotation_id`: UUID (FK → quotations, nullable)
- `client_id`: UUID (FK → clients)
- `customer_po_number`: str — customer's PO reference
- `po_date`: date
- `delivery_date`: date (nullable)
- `status`: Enum [RECEIVED, CONFIRMED, PARTIALLY_INVOICED, FULLY_INVOICED, CLOSED, CANCELLED]
- `confirmed_by`: UUID (FK → users, nullable)
- `confirmed_at`: datetime (nullable)
- `subtotal`: Decimal(12,2)
- `tax_amount`: Decimal(12,2)
- `total_amount`: Decimal(12,2)
- `currency`: str
- `payment_terms`: str
- `notes`: Text
- `ocr_job_id`: UUID (FK → ocr_jobs, nullable)
- `created_at`: datetime
- `updated_at`: datetime
- `deleted_at`: datetime (nullable)

**Constraints:**
- `cpo_number` UNIQUE per workspace
- Credit check enforced on confirmation if client credit_status = HOLD
- Soft delete only

---

### CustomerPurchaseOrderItem

**Fields:**
- `id`: UUID
- `cpo_id`: UUID (FK → customer_purchase_orders)
- `product_id`: UUID (FK → products)
- `description`: str
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `unit_price`: Decimal(12,2)
- `discount_amount`: Decimal(12,2) — default 0
- `tax_rate`: Decimal(5,2)
- `tax_amount`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `invoiced_quantity`: Decimal(12,4) — default 0
- `delivered_quantity`: Decimal(12,4) — default 0
- `created_at`: datetime

---

### Invoice (EXTEND existing)

**Purpose:** Customer invoice with payment tracking.

**Existing fields:** (from P0-P4)
- `id`, `workspace_id`, `invoice_number`, `client_id`, `issue_date`, `due_date`, `subtotal`, `tax_amount`, `total_amount`, `status`, `created_at`, `updated_at`

**New fields:**
- `cpo_id`: UUID (FK → customer_purchase_orders, nullable)
- `quotation_id`: UUID (FK → quotations, nullable)
- `status`: Enum [DRAFT, SENT, PARTIALLY_PAID, PAID, OVERDUE, CANCELLED]
- `amount_paid`: Decimal(12,2) — default 0
- `balance_due`: Decimal(12,2)
- `payment_terms_days`: int
- `discount_amount`: Decimal(12,2) — default 0
- `currency`: str
- `notes`: Text
- `deleted_at`: datetime (nullable)

**Constraints:**
- Soft delete only
- State transitions validated by StateMachineService

---

### InvoiceItem (EXTEND existing)

**Existing fields:**
- `id`, `invoice_id`, `product_id`, `quantity`, `unit_price`, `total_price`, `created_at`

**New fields:**
- `description`: str
- `uom_id`: UUID (FK → unit_of_measures)
- `discount_amount`: Decimal(12,2) — default 0
- `tax_rate`: Decimal(5,2)
- `tax_amount`: Decimal(12,2)
- `line_total`: Decimal(12,2)

---

### DeliveryOrder

**Purpose:** Goods dispatch to customer with stock reservation.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `do_number`: str — gapless (DO-YYYY-XXXX)
- `cpo_id`: UUID (FK → customer_purchase_orders)
- `invoice_id`: UUID (FK → invoices, nullable)
- `warehouse_id`: UUID (FK → warehouses)
- `client_id`: UUID (FK → clients)
- `delivery_date`: date
- `status`: Enum [PENDING, PARTIAL, DELIVERED, RETURNED]
- `shipping_address`: Text
- `driver_name`: str (nullable)
- `vehicle_number`: str (nullable)
- `dispatched_by`: UUID (FK → users, nullable)
- `dispatched_at`: datetime (nullable)
- `notes`: Text
- `created_at`: datetime
- `updated_at`: datetime
- `deleted_at`: datetime (nullable)

**Constraints:**
- `do_number` UNIQUE per workspace
- Must have active StockReservation before dispatch
- Soft delete only

---

### DeliveryOrderItem

**Fields:**
- `id`: UUID
- `do_id`: UUID (FK → delivery_orders)
- `cpo_item_id`: UUID (FK → customer_purchase_order_items, nullable)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `delivered_quantity`: Decimal(12,4) — default 0
- `stock_reservation_id`: UUID (FK → stock_reservations, nullable)
- `created_at`: datetime

---

### Payment (EXTEND existing)

**Purpose:** Customer payment with method-specific fields.

**Existing fields:**
- `id`, `workspace_id`, `invoice_id`, `amount`, `payment_date`, `created_at`

**New fields:**
- `payment_number`: str — internal reference
- `method`: Enum [CASH, BANK_TRANSFER, CHEQUE, PDC, CREDIT_CARD, ONLINE]
- `reference_number`: str (nullable) — bank transaction ref
- `cheque_number`: str (nullable)
- `cheque_date`: date (nullable)
- `cheque_bank`: str (nullable)
- `pdc_status`: Enum [PDC_PENDING, PRESENTED, CLEARED, BOUNCED] (nullable)
- `pdc_clearing_date`: date (nullable)
- `received_by`: UUID (FK → users)
- `notes`: Text
- `deleted_at`: datetime (nullable)

**Constraints:**
- **Immutable** — NO UPDATE or DELETE allowed (financial audit trail)
- Cheque fields required if method = CHEQUE or PDC
- Soft delete at record level, but never modify amount/date/method once created

---

## 8. Returns and Adjustments Domain

### SalesReturn

**Purpose:** Customer returns with credit note generation.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `return_number`: str — gapless (RTN-YYYY-XXXX)
- `invoice_id`: UUID (FK → invoices)
- `do_id`: UUID (FK → delivery_orders, nullable)
- `client_id`: UUID (FK → clients)
- `return_date`: date
- `reason`: Enum [DAMAGED, DEFECTIVE, WRONG_ITEM, EXCESS_DELIVERY, CUSTOMER_REQUEST, OTHER]
- `reason_notes`: Text
- `status`: Enum [PENDING, RECEIVED, INSPECTED, APPROVED, REJECTED]
- `received_by`: UUID (FK → users, nullable)
- `approved_by`: UUID (FK → users, nullable)
- `total_amount`: Decimal(12,2)
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `return_number` UNIQUE per workspace

---

### SalesReturnItem

**Fields:**
- `id`: UUID
- `return_id`: UUID (FK → sales_returns)
- `do_item_id`: UUID (FK → delivery_order_items, nullable)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `unit_price`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `condition`: Enum [GOOD, DAMAGED, DEFECTIVE]
- `created_at`: datetime

---

### PurchaseReturn

**Purpose:** Return goods to supplier with debit note generation.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `return_number`: str — gapless (PRN-YYYY-XXXX)
- `grn_id`: UUID (FK → goods_receipt_notes)
- `supplier_id`: UUID (FK → suppliers)
- `return_date`: date
- `reason`: Enum [DAMAGED, DEFECTIVE, WRONG_ITEM, EXCESS_DELIVERY, QUALITY_ISSUE, OTHER]
- `reason_notes`: Text
- `status`: Enum [PENDING, DISPATCHED, ACKNOWLEDGED, APPROVED, REJECTED]
- `approved_by`: UUID (FK → users, nullable)
- `total_amount`: Decimal(12,2)
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `return_number` UNIQUE per workspace

---

### PurchaseReturnItem

**Fields:**
- `id`: UUID
- `return_id`: UUID (FK → purchase_returns)
- `grn_item_id`: UUID (FK → goods_receipt_note_items, nullable)
- `product_id`: UUID (FK → products)
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures)
- `unit_price`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `created_at`: datetime

---

### CreditNote

**Purpose:** Credit memo issued to customer for returns/adjustments.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `credit_note_number`: str — gapless (CN-YYYY-XXXX)
- `invoice_id`: UUID (FK → invoices)
- `sales_return_id`: UUID (FK → sales_returns, nullable)
- `client_id`: UUID (FK → clients)
- `issue_date`: date
- `reason`: Enum [SALES_RETURN, INVOICE_ERROR, DISCOUNT, GOODWILL, OTHER]
- `reason_notes`: Text
- `subtotal`: Decimal(12,2)
- `tax_amount`: Decimal(12,2)
- `total_amount`: Decimal(12,2)
- `currency`: str
- `status`: Enum [DRAFT, ISSUED, APPLIED, CANCELLED]
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `credit_note_number` UNIQUE per workspace

---

### CreditNoteItem

**Fields:**
- `id`: UUID
- `credit_note_id`: UUID (FK → credit_notes)
- `product_id`: UUID (FK → products, nullable)
- `description`: str
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures, nullable)
- `unit_price`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `created_at`: datetime

---

### DebitNote

**Purpose:** Debit memo issued to supplier for returns/adjustments.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `debit_note_number`: str — gapless (DN-YYYY-XXXX)
- `supplier_invoice_id`: UUID (FK → supplier_invoices)
- `purchase_return_id`: UUID (FK → purchase_returns, nullable)
- `supplier_id`: UUID (FK → suppliers)
- `issue_date`: date
- `reason`: Enum [PURCHASE_RETURN, INVOICE_ERROR, QUALITY_ISSUE, SHORT_DELIVERY, OTHER]
- `reason_notes`: Text
- `subtotal`: Decimal(12,2)
- `tax_amount`: Decimal(12,2)
- `total_amount`: Decimal(12,2)
- `currency`: str
- `status`: Enum [DRAFT, ISSUED, APPLIED, CANCELLED]
- `created_at`: datetime
- `updated_at`: datetime

**Constraints:**
- `debit_note_number` UNIQUE per workspace

---

### DebitNoteItem

**Fields:**
- `id`: UUID
- `debit_note_id`: UUID (FK → debit_notes)
- `product_id`: UUID (FK → products, nullable)
- `description`: str
- `quantity`: Decimal(12,4)
- `uom_id`: UUID (FK → unit_of_measures, nullable)
- `unit_price`: Decimal(12,2)
- `line_total`: Decimal(12,2)
- `created_at`: datetime

---

## 9. Communication Domain

### WhatsAppMessage

**Purpose:** WhatsApp message history (inbound and outbound).

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `direction`: Enum [INBOUND, OUTBOUND]
- `from_number`: str
- `to_number`: str
- `message_body`: Text
- `media_url`: str (nullable)
- `linked_entity_type`: str (nullable) — "Enquiry", "Invoice", "Quotation"
- `linked_entity_id`: UUID (nullable)
- `status`: Enum [QUEUED, SENT, DELIVERED, READ, FAILED]
- `whatsapp_message_id`: str (nullable) — Meta's message ID
- `sent_at`: datetime (nullable)
- `delivered_at`: datetime (nullable)
- `read_at`: datetime (nullable)
- `created_at`: datetime

**Constraints:**
- Webhook integration with Meta WhatsApp Business Cloud API

---

### EmailLog

**Purpose:** Email history (all outbound emails).

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `resend_message_id`: str
- `to_email`: str
- `from_email`: str
- `subject`: str
- `linked_entity_type`: str (nullable) — "Invoice", "Quotation", "Statement"
- `linked_entity_id`: UUID (nullable)
- `status`: Enum [QUEUED, SENT, DELIVERED, BOUNCED, FAILED]
- `sent_at`: datetime (nullable)
- `created_at`: datetime

**Constraints:**
- Integration with Resend API

---

### OcrJob

**Purpose:** OCR processing jobs for scanned documents.

**Fields:**
- `id`: UUID
- `workspace_id`: UUID
- `file_url`: str
- `document_type`: Enum [CUSTOMER_PO, SUPPLIER_INVOICE, SUPPLIER_QUOTATION, DELIVERY_NOTE, GENERAL]
- `status`: Enum [PENDING, PROCESSING, COMPLETED, FAILED, REQUIRES_REVIEW]
- `extracted_data`: JSON
- `confidence_score`: Decimal(3,2) — 0.00–1.00
- `reviewed_by`: UUID (FK → users, nullable)
- `linked_entity_type`: str (nullable)
- `linked_entity_id`: UUID (nullable)
- `gemini_model`: str
- `processing_ms`: int
- `created_at`: datetime

**Constraints:**
- Integration with Gemini Flash Vision API

---

## 10. Audit and Events

### InvoiceEvent (existing from P0-P4)

**Purpose:** Audit trail for invoice state changes.

**Fields:**
- `id`, `invoice_id`, `event_type`, `metadata_log`, `created_by`, `created_at`

**Note:** Similar audit event tables needed for all 14 document types in production.

---

## Document Counters

**Purpose:** Gapless document numbering.

**Existing counters:** (from P0-P4)
- InvoiceCounter
- SPOCounter

**New counters needed:**
- EnquiryCounter (ENQ-YYYY-XXXX)
- QuotationCounter (QUO-YYYY-XXXX)
- CustomerPOCounter (CPO-YYYY-XXXX)
- DeliveryOrderCounter (DO-YYYY-XXXX)
- CreditNoteCounter (CN-YYYY-XXXX)
- DebitNoteCounter (DN-YYYY-XXXX)
- ProcurementRequestCounter (PR-YYYY-XXXX)
- RFQCounter (RFQ-YYYY-XXXX)
- GRNCounter (GRN-YYYY-XXXX)
- StockTransferCounter (TRF-YYYY-XXXX)
- StockAdjustmentCounter (ADJ-YYYY-XXXX)
- StockCountCounter (CNT-YYYY-XXXX)
- SalesReturnCounter (RTN-YYYY-XXXX)
- PurchaseReturnCounter (PRN-YYYY-XXXX)

**Constraints:**
- All use `SELECT FOR UPDATE` row lock to prevent race conditions
- Format: PREFIX-YYYY-XXXX (year-based reset)

---

## Data Type Standards

**Monetary values:** `Decimal(12,2)` — NEVER float
**Quantities:** `Decimal(12,4)` — supports fractional units
**Tax rates:** `Decimal(5,2)` — e.g., 5.00% VAT
**Percentages:** `Decimal(5,2)` — e.g., 2.50% discount
**Timestamps:** `datetime` with timezone
**Soft deletes:** `deleted_at` timestamp (nullable)

---

**End of Domain Model Specification**
