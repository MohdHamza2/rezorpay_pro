# InvoiceSaaS — V3 Enterprise Master Plan
*Full B2B Electrical Trading ERP / Trade Operations Platform*
*UAE-First · Two-Sided Market · Production-Grade*
*Document Version: 3.0 | Aug 2026 | Status: Awaiting Approval*

---

## Governing Principle

> This is NOT an invoice application with some inventory bolted on.
> This is a **B2B Electrical Trading ERP / Trade Operations Platform** with four interconnected financial/operational domains:

```
                    ┌─────────────────────────┐
                    │       PRODUCT MASTER     │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
              ▼                  ▼                   ▼
         CUSTOMER             INVENTORY           SUPPLIER
              │                  │                   │
              ▼                  │                   ▼
           SALES ◄───────────────┼─────────── PROCUREMENT
              │                  │                   │
              ▼                  ▼                   ▼
             AR              WAREHOUSE              AP
```

---

## Non-Negotiable Rule (AI Governance)

> [!CAUTION]
> **No AI agent is allowed to invent business rules.**
> If any agent encounters an ambiguous scenario (e.g., "Should receiving 110 units against a PO for 100 be allowed?"), it MUST STOP, flag the question in its execution report, and wait for human approval before implementing anything. This is the single most important governance rule.

---

## Section 1: Technology Stack (Locked)

| Category | Choice | Detail |
|---|---|---|
| **Backend** | FastAPI + SQLModel + asyncpg | Python 3.11, async-first |
| **Database** | PostgreSQL 16 | Alembic migrations only |
| **Frontend** | Vite + React 18 + TypeScript | Strict mode, Vanilla CSS |
| **Data Fetching** | TanStack Query v5 | Server state, caching |
| **Forms** | React Hook Form + Zod | Schema parity with backend |
| **PDF** | @react-pdf/renderer | Client-side, downloadable + sendable |
| **Email** | Resend | 3,000 free/month |
| **OCR** | Gemini Flash Vision | Free tier, state-of-the-art accuracy |
| **WhatsApp** | Meta WhatsApp Business Cloud API | Official, two-way, PDF sending |
| **Auth** | JWT (access 30min + refresh 7d) | passlib/bcrypt |
| **Market** | UAE first | India schema-ready from day 1 |
| **Inventory Scope** | **Option A — Full Inventory** | No bin locations for MVP, but schema supports it |

### Query Optimization Guidelines (N+1 Prevention)

**All list endpoints MUST eager-load required relationships to prevent N+1 queries.**

- **1:N relationships** (one-to-many, e.g., `Invoice.items`) → Use `.options(selectinload(Invoice.items))`
- **1:1 relationships** (one-to-one or many-to-one, e.g., `Invoice.client`) → Use `.options(joinedload(Invoice.client))`
- **Nested relationships** → Chain: `.options(selectinload(Invoice.items).joinedload(InvoiceItem.product))`

**Verification:** Every list endpoint returning entities with relationships must include eager loading. P4 stabilization caught one N+1 (SupplierInvoice.items); this guideline prevents recurrence.

---

## Section 2: Three Procurement Scenarios (All Supported)

```
Scenario A — Stock Replenishment
Stock falls below reorder level → Procurement Request → RFQ → Supplier PO → GRN → Stock

Scenario B — Customer-Driven Procurement
Customer PO → Stock check fails → Procurement Request → Supplier PO → GRN → Reserve for Customer → Delivery

Scenario C — Direct / Project Procurement
Project/customer requirement → Procurement → Supplier PO → GRN → Direct allocation → Delivery
```

All three share the same procurement infrastructure but differ in **origin** and **stock allocation behavior**.

---

## Section 3: Complete Entity Relationship Map

```
WORKSPACE
   │
   ├── USERS (RBAC roles)
   │
   ├── ─── PRODUCT DOMAIN ──────────────────────────────────────────
   │   ├── Category
   │   ├── Brand
   │   ├── UnitOfMeasure
   │   ├── Product
   │   │     ├── ProductIdentifier (INTERNAL_SKU, MPN, BARCODE, SUPPLIER_CODE, CUSTOMER_CODE, EAN, UPC)
   │   │     ├── ProductUOMConversion (per-product, not global)
   │   │     └── ProductPrice (customer/standard/volume tiers)
   │   └── SupplierProduct (supplier ↔ product mapping)
   │
   ├── ─── SUPPLIER DOMAIN ─────────────────────────────────────────
   │   ├── Supplier
   │   │     ├── SupplierContact
   │   │     ├── SupplierBankAccount
   │   │     └── SupplierDocument
   │   └── SupplierProduct (shared with product domain)
   │
   ├── ─── PROCUREMENT DOMAIN ──────────────────────────────────────
   │   ├── ProcurementRequest
   │   │     └── ProcurementRequestItem
   │   ├── RFQ
   │   │     ├── RFQItem
   │   │     └── SupplierRFQResponse
   │   │           └── SupplierQuoteItem
   │   ├── SupplierPurchaseOrder
   │   │     └── SupplierPurchaseOrderItem
   │   ├── GoodsReceiptNote (GRN)
   │   │     └── GRNItem
   │   ├── SupplierInvoice
   │   │     └── SupplierInvoiceItem
   │   ├── SupplierPayment
   │   ├── PurchaseReturn
   │   │     └── PurchaseReturnItem
   │   └── DebitNote
   │
   ├── ─── CUSTOMER DOMAIN ─────────────────────────────────────────
   │   ├── Client (Customer)
   │   ├── Enquiry
   │   │     └── EnquiryItem
   │   ├── Quotation
   │   │     └── QuotationItem
   │   ├── CustomerPurchaseOrder
   │   │     └── CustomerPurchaseOrderItem
   │   ├── Invoice
   │   │     └── InvoiceItem
   │   ├── DeliveryOrder
   │   │     └── DeliveryOrderItem
   │   ├── Payment (customer)
   │   ├── SalesReturn
   │   │     └── SalesReturnItem
   │   └── CreditNote
   │
   ├── ─── INVENTORY DOMAIN ────────────────────────────────────────
   │   ├── Warehouse
   │   │     └── WarehouseLocation (Zone → Rack → Shelf → Bin — schema-ready, not enforced MVP)
   │   ├── WarehouseStock (current qty per product per warehouse)
   │   ├── StockTransaction (immutable ledger — never update/delete)
   │   ├── StockReservation
   │   ├── StockTransfer
   │   │     └── StockTransferItem
   │   ├── StockAdjustment
   │   └── StockCount
   │         └── StockCountItem
   │
   └── ─── COMMUNICATION DOMAIN ────────────────────────────────────
       ├── WhatsAppMessage
       ├── EmailLog
       └── OcrJob
```

---

## Section 4: Complete Database Schema

### 4.1 Workspace (EXTEND)
```
+ market: Enum [UAE, INDIA]                     default = UAE
+ currency: str                                  default = AED
+ trn: str                                       UAE Tax Registration Number
+ company_whatsapp: str                          WhatsApp Business number
+ company_email: str
+ company_logo_url: str
+ company_address: str
+ vat_rate: Decimal(5,2)                         default = 5.00
+ price_tolerance_percent: Decimal(5,2)          default = 2.00 (3-way matching tolerance)
+ credit_warning_days: int                       default = 60
+ credit_hold_days: int                          default = 90
+ block_po_on_hold: bool                         default = True
+ block_do_on_hold: bool                         default = True
+ block_invoice_on_hold: bool                    default = False
+ require_po_approval: bool                      default = False
+ allow_negative_stock: bool                     default = False
+ auto_reserve_on_invoice: bool                  default = True
```

---

### 4.2 Product Domain

#### Category
```
id, workspace_id
name: str
parent_id: UUID (FK → categories, nullable)     — supports subcategories
created_at, updated_at
```

#### Brand
```
id, workspace_id
name, manufacturer, country_of_origin: str
created_at, updated_at
```

#### UnitOfMeasure
```
id, workspace_id
code: str     (PCS, MTR, KG, BOX, DRUM, CARTON, ROLL, COIL, PACK, SET, PAIR, LTR, SQM, CBM, TON, BUNDLE)
name: str
dimension: Enum [COUNT, LENGTH, WEIGHT, AREA, VOLUME, TIME]
is_base: bool
created_at
```

#### Product
```
id, workspace_id
internal_sku: str                               UNIQUE per workspace (ELE-CBL-DUC-4C10)
name: str
short_description: str
description: Text
category_id: UUID
brand_id: UUID (nullable)
hs_code: str                                    FTA/customs compliance
is_active: bool                                 default = True
track_inventory: bool                           default = True
min_stock_level: Decimal(12,4)
reorder_level: Decimal(12,4)
max_stock_level: Decimal(12,4)
reorder_quantity: Decimal(12,4)
base_uom_id: UUID
purchase_uom_id: UUID
sales_uom_id: UUID
standard_sell_price: Decimal(12,2)
standard_cost_price: Decimal(12,2)
vat_category: Enum [STANDARD, ZERO_RATED, EXEMPT]
created_at, updated_at, deleted_at
```

#### ProductIdentifier
```
id, product_id
identifier_type: Enum [INTERNAL_SKU, MANUFACTURER_PART_NUMBER, SUPPLIER_CODE, BARCODE, CUSTOMER_CODE, EAN, UPC]
identifier_value: str
source: str                                     who assigned it (e.g. "DUCAB", "Customer ABC")
is_primary: bool
created_at
```

#### ProductUOMConversion
```
id, product_id
from_uom_id, to_uom_id: UUID
conversion_factor: Decimal(10,4)               PER PRODUCT — not global
                                                1 DRUM of Product X = 500 MTR
                                                1 DRUM of Product Y = 300 MTR
created_at
```
> ⚠️ Conversions are per-product. Same UOM, different factor. System must NEVER assume global UOM conversion.

#### ProductPrice
```
id, workspace_id, product_id
entity_type: Enum [CUSTOMER, CUSTOMER_GROUP, STANDARD]
entity_id: UUID (nullable)
min_quantity, max_quantity: Decimal             quantity break pricing
unit_price: Decimal(12,2)
currency: str
valid_from: date
valid_to: date (nullable)
created_at
```

---

### 4.3 Supplier Domain

#### Supplier
```
id, workspace_id
supplier_code: str                              UNIQUE per workspace (SUP-001)
legal_name: str
trade_name: str
contact_person: str
phone, whatsapp, email, website: str
address, country: str
trn: str                                        Supplier VAT/Tax Reg Number
currency: str                                   default = AED
payment_terms_days: int                         default = 30
credit_limit: Decimal(12,2)                     default = 0
bank_name, bank_account, bank_iban, bank_swift: str
status: Enum [ACTIVE, INACTIVE, ON_HOLD, BLOCKED, BLACKLISTED]
rating: int                                     1–5
is_preferred: bool
notes: Text
created_at, updated_at, deleted_at
```

#### SupplierContact
```
id, supplier_id
name, title, phone, whatsapp, email: str
is_primary: bool
created_at, updated_at
```

#### SupplierBankAccount
```
id, supplier_id
bank_name, account_name, account_number, iban, swift: str
currency: str
is_primary: bool
created_at, updated_at
```

#### SupplierDocument
```
id, supplier_id
document_type: Enum [TRADE_LICENSE, VAT_CERTIFICATE, ISO_CERTIFICATE, CONTRACT, OTHER]
file_url: str
expiry_date: date (nullable)
created_at
```

#### SupplierProduct
```
id, supplier_id, product_id
supplier_sku: str                               supplier's own code for this product
supplier_description: str
purchase_uom_id: UUID
conversion_to_base: Decimal(10,4)
last_purchase_price: Decimal(12,2)
current_purchase_price: Decimal(12,2)
currency: str
lead_time_days: int
moq: Decimal(12,4)                              minimum order quantity
is_preferred: bool
last_purchased_at: datetime
created_at, updated_at
```

---

### 4.4 Procurement Domain

#### ProcurementRequest
```
id, workspace_id
pr_number: str                                  gapless — PR-YYYY-XXXX
source: Enum [LOW_STOCK, CUSTOMER_ORDER, PROJECT, MANUAL, REORDER_LEVEL, BACKORDER, WAREHOUSE_REQUEST, TRANSFER_SHORTAGE]
source_reference_type: str                      (customer_po, invoice, etc.)
source_reference_id: UUID (nullable)
requested_by: UUID (FK → users)
approved_by: UUID (nullable)
warehouse_id: UUID
required_by_date: date
status: Enum [DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED, PARTIALLY_ORDERED, FULLY_ORDERED, FULFILLED, REJECTED, CANCELLED]
notes: Text
created_at, updated_at
→ items: List[ProcurementRequestItem]
```

#### ProcurementRequestItem
```
id, pr_id
product_id: UUID
internal_sku: str
description: str
quantity_required: Decimal(12,4)
quantity_ordered: Decimal(12,4)               default = 0
uom_id: UUID
notes: str
```

#### RFQ — Request for Quotation
```
id, workspace_id
rfq_number: str                                 gapless — RFQ-YYYY-XXXX
procurement_request_id: UUID (nullable)
required_delivery_date: date
warehouse_id: UUID
currency: str
terms: Text
notes: Text
status: Enum [DRAFT, SENT, PARTIALLY_RESPONDED, FULLY_RESPONDED, EXPIRED, CLOSED, CANCELLED]
created_at, updated_at
→ items: List[RFQItem]
→ supplier_responses: List[SupplierRFQResponse]
```

#### RFQItem
```
id, rfq_id
product_id: UUID (nullable)
internal_sku, description: str
quantity: Decimal(12,4)
uom_id: UUID
target_price: Decimal(12,2) (nullable)
specifications: Text
required_date: date (nullable)
```

#### SupplierRFQResponse
```
id, rfq_id, supplier_id
sent_at: datetime
responded_at: datetime (nullable)
total_quoted_amount: Decimal(12,2)
lead_time_days: int
payment_terms_days: int
validity_days: int
notes: Text
status: Enum [PENDING, RECEIVED, DECLINED, EXPIRED, SELECTED, REJECTED]
selected_by: UUID (nullable)
selected_at: datetime (nullable)
selection_reason: Text (nullable)             AUDIT: why this supplier was chosen
→ quote_items: List[SupplierQuoteItem]
```

#### SupplierQuoteItem
```
id, response_id, rfq_item_id
product_id: UUID
supplier_sku: str
description: str
quantity_available: Decimal(12,4)
uom_id: UUID
unit_price: Decimal(12,2)
discount_percent: Decimal(5,2)
vat_rate: Decimal(5,2)
total_price: Decimal(12,2)
lead_time_days: int
notes: str
```

#### SupplierPurchaseOrder
```
id, workspace_id, supplier_id
rfq_id: UUID (nullable)
procurement_request_id: UUID (nullable)
spo_number: str                                 gapless — SPO-YYYY-XXXX
our_reference: str
supplier_reference: str                         supplier's own PO/order reference
status: Enum [DRAFT, PENDING_APPROVAL, APPROVED, SENT, ACKNOWLEDGED, PARTIALLY_RECEIVED, FULLY_RECEIVED, PARTIALLY_CANCELLED, CANCELLED, REJECTED, CLOSED]
po_date: date
expected_delivery_date: date
warehouse_id: UUID
currency: str
payment_terms_days: int
delivery_terms: str                             (DAP, EXW, FOB...)
subtotal, vat_amount, total_amount: Decimal(12,2)
quantity_ordered_total: Decimal(12,4)
quantity_confirmed_by_supplier: Decimal(12,4)  (on acknowledgement — may differ)
quantity_backordered: Decimal(12,4)
notes: Text
approved_by: UUID (nullable)
approved_at: datetime (nullable)
sent_at: datetime (nullable)
acknowledged_at: datetime (nullable)
created_at, updated_at
→ items: List[SupplierPurchaseOrderItem]
```

#### SupplierPurchaseOrderItem
```
id, spo_id
line_number: int
product_id: UUID (nullable)
internal_sku, supplier_sku, description: str
quantity_ordered: Decimal(12,4)
quantity_confirmed: Decimal(12,4)              (supplier's confirmed qty on acknowledgement)
quantity_backordered: Decimal(12,4)
quantity_received: Decimal(12,4)               default = 0
uom_id: UUID
unit_price: Decimal(12,2)
discount_percent: Decimal(5,2)
vat_rate: Decimal(5,2)
vat_amount, total_price: Decimal(12,2)
expected_delivery_date: date
```

#### GoodsReceiptNote (GRN)
```
id, workspace_id, supplier_id
spo_id: UUID
grn_number: str                                 gapless — GRN-YYYY-XXXX
warehouse_id: UUID
received_date: date
received_by: UUID (FK → users)
delivery_reference: str                         supplier's shipment/delivery note ref
status: Enum [DRAFT, RECEIVING, PENDING_INSPECTION, PARTIALLY_ACCEPTED, ACCEPTED, PARTIALLY_REJECTED, REJECTED, CANCELLED]
notes: Text
created_at, updated_at
→ items: List[GRNItem]
```

#### GRNItem
```
id, grn_id, spo_item_id
product_id: UUID
internal_sku, description: str
quantity_ordered: Decimal(12,4)
quantity_received: Decimal(12,4)
quantity_accepted: Decimal(12,4)
quantity_damaged: Decimal(12,4)
quantity_rejected: Decimal(12,4)
uom_id: UUID
batch_number: str (nullable)
notes: str
```
> ⚠️ Inventory increases only by `quantity_accepted`. Damaged/rejected stock goes to DAMAGED state separately.

#### SupplierInvoice
```
id, workspace_id, supplier_id
grn_id: UUID (nullable)
spo_id: UUID (nullable)
supplier_invoice_number: str                    THEIR invoice number
our_reference: str
status: Enum [RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PARTIALLY_PAID, PAID, CANCELLED]
invoice_date: date
due_date: date
currency: str
subtotal, vat_amount, total_amount: Decimal(12,2)
amount_paid: Decimal(12,2)                      cached
three_way_match_status: Enum [NOT_CHECKED, PASSED, FAILED_QTY, FAILED_PRICE, FAILED_TAX, MANUAL_REVIEW]
three_way_match_notes: Text
document_url: str
ocr_extracted: bool
created_at, updated_at
→ items: List[SupplierInvoiceItem]
```

#### SupplierInvoiceItem
```
id, supplier_invoice_id, spo_item_id (nullable), grn_item_id (nullable)
product_id: UUID
description: str
quantity: Decimal(12,4)
uom_id: UUID
unit_price: Decimal(12,2)
vat_rate: Decimal(5,2)
vat_amount, total_price: Decimal(12,2)
match_status: Enum [MATCHED, QTY_VARIANCE, PRICE_VARIANCE, TAX_VARIANCE, UNMATCHED]
variance_notes: str
```

#### SupplierPayment
```
id, workspace_id, supplier_id, supplier_invoice_id
amount: Decimal(12,2)
method: Enum [CASH, CHEQUE, BANK_TRANSFER, CREDIT_CARD, ONLINE]
payment_date: date
reference_number: str
cheque_number, cheque_bank: str (nullable)
notes: str
paid_by: UUID (FK → users)
created_at
```

#### PurchaseReturn
```
id, workspace_id, supplier_id, grn_id
prn_number: str                                 gapless — PRN-YYYY-XXXX
status: Enum [DRAFT, REQUESTED, APPROVED, SENT, PARTIALLY_RETURNED, FULLY_RETURNED, CLOSED, CANCELLED]
reason: Text
created_at, updated_at
→ items: List[PurchaseReturnItem]
```

#### DebitNote (Supplier)
```
id, workspace_id, supplier_id
purchase_return_id: UUID (nullable)
dn_number: str                                  gapless — DN-YYYY-XXXX
amount, vat_amount, total_amount: Decimal(12,2)
status: Enum [DRAFT, ISSUED, APPLIED, CANCELLED]
notes: Text
created_at, updated_at
```

---

### 4.5 Customer Domain (EXTEND existing)

#### Client (EXTEND)
```
+ credit_limit: Decimal(12,2)                   default = 0 (0 = unlimited)
+ credit_terms_days: int                         default = 30
+ credit_status: Enum [ACTIVE, WARNING, HOLD, SUSPENDED]
+ trn: str
+ whatsapp_number: str
+ billing_address, shipping_address: str
+ contact_person: str
+ website: str
+ notes: Text
```

#### Invoice (EXTEND)
```
+ customer_po_id: UUID (nullable)
+ quotation_id: UUID (nullable)
+ amount_paid: Decimal(12,2)                    cached sum of SUCCESS payments
+ balance_due: Decimal(12,2)                    total_amount - amount_paid
+ payment_terms_days: int
+ discount_amount: Decimal(12,2)
```

#### InvoiceItem (EXTEND)
```
+ product_id: UUID (nullable)
+ internal_sku: str                              copied at invoicing time
+ uom_id: UUID (nullable)
+ discount_percent: Decimal(5,2)
+ vat_amount: Decimal(12,2)
```

#### Payment / Customer (EXTEND)
```
+ method: Enum [CASH, CHEQUE, BANK_TRANSFER, CREDIT_CARD, PDC, ONLINE]
+ cheque_number, cheque_bank: str
+ cheque_date: date                              PDC future date
+ pdc_status: Enum [PDC_PENDING, PRESENTED, CLEARED, BOUNCED]
+ reference_number: str
+ notes: str
+ received_by: UUID (FK → users)
```

---

### 4.6 Inventory Domain

#### Warehouse
```
id, workspace_id
code: str                                       MAIN, SHOP, WH2
name: str
address: str
type: Enum [MAIN_WAREHOUSE, SHOP, BRANCH, TRANSIT, DAMAGED, QUARANTINE]
is_default: bool
is_active: bool
created_at, updated_at
```

#### WarehouseLocation *(schema-ready; not enforced in MVP)*
```
id, warehouse_id
code: str                                       A1-R2-S3-B4 (Zone-Rack-Shelf-Bin)
zone, rack, shelf, bin: str (nullable)
is_active: bool
created_at
```

#### WarehouseStock *(cached summary — source of truth is StockTransaction)*
```
id, workspace_id, product_id, warehouse_id
quantity_on_hand: Decimal(12,4)
quantity_reserved: Decimal(12,4)
quantity_on_order: Decimal(12,4)               open SPO quantity
quantity_damaged: Decimal(12,4)
quantity_in_transit: Decimal(12,4)
UNIQUE: (product_id, warehouse_id)
last_updated_at: datetime
```

> **Available = on_hand − reserved − damaged − in_transit**

#### StockTransaction *(IMMUTABLE — never update or delete)*
```
id, workspace_id, product_id, warehouse_id
location_id: UUID (nullable)
transaction_type: Enum [
  PURCHASE_RECEIPT,       direction = IN    (from GRN accepted qty)
  PURCHASE_RETURN,        direction = OUT   (returned to supplier)
  SALES_DELIVERY,         direction = OUT   (from DO dispatch)
  SALES_RETURN,           direction = IN    (customer returned goods)
  STOCK_ADJUSTMENT_IN,    direction = IN    (manual correction)
  STOCK_ADJUSTMENT_OUT,   direction = OUT   (manual correction, write-off)
  TRANSFER_IN,            direction = IN    (received from other warehouse)
  TRANSFER_OUT,           direction = OUT   (sent to other warehouse)
  OPENING_STOCK,          direction = IN    (initial balance entry)
  DAMAGE_WRITE_OFF,       direction = OUT   (damaged goods removed)
  RECLASSIFICATION_IN,    direction = IN    (from damaged/quarantine to usable)
  RECLASSIFICATION_OUT    direction = OUT   (to damaged/quarantine)
]
direction: Enum [IN, OUT]
quantity: Decimal(12,4)                        always positive
unit_cost: Decimal(12,2)                       for inventory valuation
reference_type: str                            (grn, do, transfer, adjustment, etc.)
reference_id: UUID
notes: str
created_by: UUID (FK → users)
created_at: datetime                           IMMUTABLE
```

#### StockReservation
```
id, workspace_id, product_id, warehouse_id
delivery_order_id: UUID
customer_po_id: UUID (nullable)
invoice_id: UUID (nullable)
quantity_reserved: Decimal(12,4)
quantity_fulfilled: Decimal(12,4)             default = 0
status: Enum [PENDING, RESERVED, PARTIALLY_FULFILLED, FULFILLED, RELEASED, CANCELLED]
reserved_at: datetime
fulfilled_at: datetime (nullable)
```

#### StockTransfer
```
id, workspace_id
transfer_number: str                           gapless — TRF-YYYY-XXXX
from_warehouse_id: UUID
to_warehouse_id: UUID
status: Enum [DRAFT, REQUESTED, APPROVED, IN_TRANSIT, PARTIALLY_RECEIVED, RECEIVED, CANCELLED]
requested_by: UUID
approved_by: UUID (nullable)
transfer_date: date
received_date: date (nullable)
notes: Text
created_at, updated_at
→ items: List[StockTransferItem]
```

#### StockTransferItem
```
id, transfer_id, product_id
internal_sku, description: str
quantity_requested: Decimal(12,4)
quantity_sent: Decimal(12,4)
quantity_received: Decimal(12,4)
uom_id: UUID
notes: str
```

#### StockAdjustment
```
id, workspace_id, product_id, warehouse_id
adjustment_number: str                          gapless — ADJ-YYYY-XXXX
adjustment_type: Enum [INCREASE, DECREASE, WRITE_OFF, RECLASSIFICATION]
quantity_before: Decimal(12,4)
quantity_adjusted: Decimal(12,4)
quantity_after: Decimal(12,4)
reason: Text
approved_by: UUID
status: Enum [PENDING_APPROVAL, APPROVED, REJECTED]
created_by: UUID
created_at, updated_at
```
> ⚠️ No direct quantity edits ever. Every change creates a StockTransaction + StockAdjustment.

#### StockCount
```
id, workspace_id, warehouse_id
count_number: str                               gapless — CNT-YYYY-XXXX
status: Enum [DRAFT, COUNTING, VARIANCE_REVIEW, APPROVED, ADJUSTMENT_POSTED, CLOSED]
count_date: date
counted_by: UUID
approved_by: UUID (nullable)
notes: Text
created_at, updated_at
→ items: List[StockCountItem]
```

#### StockCountItem
```
id, count_id, product_id
internal_sku, description: str
system_quantity: Decimal(12,4)
counted_quantity: Decimal(12,4)
variance: Decimal(12,4)                        counted - system
variance_reason: str
uom_id: UUID
```

---

### 4.7 Communication Domain

#### WhatsAppMessage
```
id, workspace_id
client_id: UUID (nullable)
supplier_id: UUID (nullable)
direction: Enum [INBOUND, OUTBOUND]
wa_message_id: str                             UNIQUE — Meta's ID, for deduplication
from_number, to_number: str
message_type: Enum [TEXT, DOCUMENT, IMAGE, TEMPLATE]
body: Text
document_url: str
template_name: str (nullable)
linked_entity_type: str
linked_entity_id: UUID
status: Enum [PENDING, SENT, DELIVERED, READ, FAILED]
error_message: str
created_at: datetime
```

#### EmailLog
```
id, workspace_id
resend_message_id: str
to_email, from_email, subject: str
linked_entity_type, linked_entity_id
status: Enum [QUEUED, SENT, DELIVERED, BOUNCED, FAILED]
sent_at: datetime
```

#### OcrJob
```
id, workspace_id
file_url: str
document_type: Enum [CUSTOMER_PO, SUPPLIER_INVOICE, SUPPLIER_QUOTATION, DELIVERY_NOTE, GENERAL]
status: Enum [PENDING, PROCESSING, COMPLETED, FAILED, REQUIRES_REVIEW]
extracted_data: JSON
confidence_score: Decimal(3,2)                 0.00 – 1.00
reviewed_by: UUID (nullable)
linked_entity_type: str
linked_entity_id: UUID (nullable)
gemini_model: str
processing_ms: int
created_at: datetime
```

---

## Section 5: Complete State Machines

### Invoice (Customer)
```
DRAFT → SENT → PARTIALLY_PAID → PAID
      ↘ OVERDUE (auto background job — due_date < today AND balance > 0)
      ↘ CANCELLED (any non-PAID state, with reason)
```

### Quotation
```
DRAFT → SENT → ACCEPTED → CONVERTED
             ↘ REJECTED
             ↘ EXPIRED (auto — valid_until < today)
DRAFT/SENT → REVISED (creates new Quotation with revision_number++)
```

### Customer PO
```
RECEIVED → CONFIRMED (after credit check) → PARTIALLY_INVOICED → FULLY_INVOICED → CLOSED
Any → CANCELLED
```

### Supplier PO
```
DRAFT → PENDING_APPROVAL → APPROVED → SENT → ACKNOWLEDGED → PARTIALLY_RECEIVED → FULLY_RECEIVED → CLOSED
                                            ↘ REJECTED (supplier rejects)
                        Any non-CLOSED → PARTIALLY_CANCELLED / CANCELLED
```

### RFQ
```
DRAFT → SENT → PARTIALLY_RESPONDED → FULLY_RESPONDED → CLOSED
                                                       ↘ EXPIRED
Any → CANCELLED
```

### Supplier RFQ Response
```
PENDING → RECEIVED → SELECTED (one supplier chosen — others REJECTED)
        ↘ DECLINED (supplier declines to quote)
        ↘ EXPIRED
```

### GRN
```
DRAFT → RECEIVING → PENDING_INSPECTION → PARTIALLY_ACCEPTED / ACCEPTED / PARTIALLY_REJECTED / REJECTED
Any → CANCELLED
```

### Supplier Invoice
```
RECEIVED → PENDING_MATCHING → MATCHED → APPROVED → PARTIALLY_PAID → PAID
                             ↘ DISCREPANCY → (resolve) → APPROVED
Any → CANCELLED
```

### Delivery Order
```
PENDING → PARTIAL → DELIVERED
DELIVERED → RETURNED (customer return)
```

### Customer Credit Status
```
ACTIVE → WARNING (overdue > credit_warning_days)
       ↘ HOLD (overdue > credit_hold_days OR overdue > credit_limit)
HOLD → ACTIVE (overdue cleared + manual release by authorized user)
HOLD → SUSPENDED (management decision, manual only)
SUSPENDED → ACTIVE (manual release only)
```

### PDC Lifecycle
```
PDC_PENDING → PRESENTED → CLEARED (success — invoice balance updated)
                         ↘ BOUNCED (fail — alert raised, ledger reversed, customer flagged)
```

### Stock Transfer
```
DRAFT → REQUESTED → APPROVED → IN_TRANSIT → PARTIALLY_RECEIVED → RECEIVED
Any → CANCELLED
```

### Stock Adjustment
```
PENDING_APPROVAL → APPROVED → (StockTransaction created, WarehouseStock updated)
               ↘ REJECTED
```

### Stock Count
```
DRAFT → COUNTING → VARIANCE_REVIEW → APPROVED → ADJUSTMENT_POSTED → CLOSED
```

### Procurement Request
```
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED → PARTIALLY_ORDERED → FULLY_ORDERED → FULFILLED
                                 ↘ REJECTED
Any → CANCELLED
```

---

## Section 6: Critical Business Rules

### Inventory Rules
1. **Never manipulate stock directly.** Frontend cannot PUT a stock quantity. Only business events (GRN, DO, Adjustment, Transfer) create StockTransactions.
2. **Accepted qty only.** Inventory increases by `quantity_accepted` from GRN, NOT quantity received.
3. **Available = on_hand − reserved − damaged.** System must check available (not on_hand) before allowing reservations.
4. **No negative stock** unless `workspace.allow_negative_stock = true`. Blocked at service layer with meaningful error.
5. **Reservation before delivery.** DO must have an active reservation before dispatch. Stock movements happen on dispatch, not on reservation.
6. **Transfers use IN_TRANSIT state.** Stock removed from source warehouse immediately on approval. Added to destination on receipt. IN_TRANSIT is tracked separately.
7. **Concurrent reservation protection.** Row-level `SELECT FOR NO KEY UPDATE` lock on WarehouseStock row when creating reservations to prevent race conditions while allowing concurrent audit log writes.

### UOM Conversion Resolution Algorithm

**When GRN/SPO quantities use different UOMs:**

```
Problem: SPO orders 1500 MTR, GRN receives 5 DRUMS. How to match?

Algorithm:
1. Look up ProductUOMConversion for (product_id, from_uom=DRUMS, to_uom=MTR)
2. If direct conversion exists → convert and compare
3. If no direct conversion:
   a. Find all conversions FROM the source UOM
   b. Find all conversions TO the target UOM
   c. Find a chain through a common intermediate UOM (usually base_uom)
   d. If chain found → apply multi-hop conversion
   e. If no chain found → FAIL with error "Cannot match DRUMS to MTR for Product X"
4. Apply converted quantity to 3-way matching logic

Circular prevention: Track visited UOMs during chain resolution; abort if loop detected.

Example conversions:
- Product A: 1 DRUM = 500 MTR (direct)
- Product B: 1 CARTON = 50 PCS, 1 ROLL = 100 PCS (chain via PCS)
- Product C: No conversion defined → manual entry required

Edge case: If GRN uses base_uom and SPO uses purchase_uom, conversion is mandatory.
```

**Implementation:** `services/uom_conversion_service.py` with `resolve_conversion(product_id, from_uom_id, to_uom_id, quantity)` method.

### Financial Rules (from existing — extended)
8. All money uses `Decimal(12,2)` — NEVER float.
9. Payments are immutable — no update/delete of payment records.
10. Soft deletes only for all business entities.
11. Idempotency keys (48h TTL) for all payment endpoints, both customer and supplier.
12. No supplier payment when three_way_match_status = FAILED (unless authorized override).

### Credit Control Rules
13. Credit check runs on: CPO confirmation, Invoice creation, DO release.
14. Overdue = any invoice where `due_date < today AND balance_due > 0`.
15. Outstanding = TOTAL balance_due across all active invoices (not only overdue).
16. HOLD blocks CPO confirmation and DO release. Does NOT block payments, statements, or enquiries.
17. Credit status changes are audited with `changed_by`, `changed_at`, `reason`.

### Document Rules
18. All document numbers are gapless — `SELECT FOR UPDATE` on sequence counter.
19. Invoice ≠ Delivery. One invoice can have many DOs. One CPO can have many invoices.
20. Quantity reconciliation: system must track invoiced_qty and delivered_qty per CPO line item.
21. PDF watermarks: CANCELLED documents show diagonal "CANCELLED" watermark.

### Agent Rules (Governance)
22. **Agents cannot invent business rules.** Flag → wait for approval.
23. Every agent must report in `.agents/reports/[role]-execution-report.md`.
24. Schema changes: Database Agent first, Backend Agent second, Frontend Agent third.
25. Tests must pass before next wave begins.

---

## Section 7: 3-Way Matching Logic

```
When Supplier Invoice is received, system checks per line item:

1. Quantity Check:
   invoice_qty vs grn_accepted_qty vs spo_qty
   IF invoice_qty > grn_accepted_qty → FAILED_QTY

2. Price Check:
   invoice_unit_price vs spo_unit_price
   tolerance = workspace.price_tolerance_percent (default 2.00%)
   IF variance > tolerance → FAILED_PRICE

3. Tax Check:
   invoice_vat vs expected_vat (from SPO tax rate)
   IF mismatch → FAILED_TAX

4. Other Checks:
   - Correct supplier? (invoice supplier = PO supplier)
   - Correct currency?
   - Duplicate invoice number check

Outcomes:
  All pass → MATCHED → eligible for payment approval
  Any fail → DISCREPANCY → requires authorized user review before approval
  No GRN yet → UNRECEIVED_ITEMS (invoice arrived before goods)
  Same invoice number already exists → DUPLICATE_INVOICE → reject
```

**Note:** Tolerance is configurable per workspace. Default is 2% to handle minor rounding/price adjustments. Authorized users can adjust via Workspace settings.

---

## Section 8: Credit Control Decision Tree

```
On CPO confirmation / Invoice creation / DO release:

1. Fetch client.credit_status
2. Compute:
   - total_outstanding = SUM(balance_due) WHERE status ∈ [SENT, PARTIALLY_PAID, OVERDUE]
   - overdue_outstanding = SUM(balance_due) WHERE due_date < today
   - oldest_overdue_age = MAX(today − due_date) WHERE balance_due > 0
   - pdc_coverage = SUM(PDC payments WHERE pdc_status = PDC_PENDING)

3. Determine new status:
   IF oldest_overdue_age > workspace.credit_hold_days → HOLD
   ELIF oldest_overdue_age > workspace.credit_warning_days → WARNING
   ELSE → ACTIVE

4. On HOLD:
   IF workspace.block_po_on_hold AND action = CPO_CONFIRM → REJECT (raise error)
   IF workspace.block_do_on_hold AND action = DO_RELEASE → REJECT (raise error)
   IF workspace.block_invoice_on_hold AND action = INVOICE_CREATE → REJECT

5. Log to audit: credit_status_changed event

Customer on HOLD can always:
   ✅ View account, invoices, statements
   ✅ Make payments, provide PDC
   ✅ Send/receive WhatsApp messages
   ❌ New CPO confirmation (unless override)
   ❌ New DO release (unless override)
```

---

## Section 9: Document Number Sequences

| Document | Prefix | Example |
|---|---|---|
| Enquiry | ENQ-YYYY-XXXX | ENQ-2026-0001 |
| Quotation | QUO-YYYY-XXXX | QUO-2026-0001 |
| Customer PO (our ref) | CPO-YYYY-XXXX | CPO-2026-0012 |
| Invoice | INV-YYYY-XXXX | INV-2026-0045 |
| Delivery Order | DO-YYYY-XXXX | DO-2026-0003 |
| Credit Note | CN-YYYY-XXXX | CN-2026-0001 |
| Procurement Request | PR-YYYY-XXXX | PR-2026-0001 |
| RFQ | RFQ-YYYY-XXXX | RFQ-2026-0001 |
| Supplier PO | SPO-YYYY-XXXX | SPO-2026-0008 |
| GRN | GRN-YYYY-XXXX | GRN-2026-0002 |
| Stock Transfer | TRF-YYYY-XXXX | TRF-2026-0001 |
| Stock Adjustment | ADJ-YYYY-XXXX | ADJ-2026-0001 |
| Stock Count | CNT-YYYY-XXXX | CNT-2026-0001 |
| Debit Note | DN-YYYY-XXXX | DN-2026-0001 |
| Sales Return | RTN-YYYY-XXXX | RTN-2026-0001 |
| Purchase Return | PRN-YYYY-XXXX | PRN-2026-0001 |

---

## Section 10: Edge Cases (Must Handle Before Coding)

### Procurement Edge Cases
- Supplier partially accepts PO (confirms 800 of 1,000 ordered)
- Supplier rejects PO entirely
- Supplier delivers more than ordered
- Supplier delivers less than ordered
- Supplier changes price after PO is sent
- Supplier changes delivery date after acknowledgement
- Supplier sends duplicate invoice
- Supplier invoice differs from PO (price or qty)
- Supplier invoice arrives BEFORE GRN
- Multiple GRNs against one SPO (partial shipments)
- Multiple supplier invoices against one SPO
- One supplier invoice covering multiple SPOs

### Inventory Edge Cases
- Insufficient available stock for reservation
- Stock reserved but DO delivery fails (need to release reservation)
- Damaged goods discovered after acceptance (reclassification needed)
- Concurrent reservation race condition (two DOs for same product simultaneously)
- Negative stock attempt (blocked by service layer)
- Warehouse transfer in progress — another DO tries to use that stock
- Product deactivated with open reservations
- UOM conversion needed during receiving (ordered in DRUM, received in MTR)

### Product Edge Cases
- Same product has multiple supplier codes (must search by any)
- Same physical product with different UOMs from different suppliers
- Supplier changes their product code
- Product replaced by a new SKU (discontinuation flow)
- Duplicate internal SKU attempt

### Customer Credit Edge Cases
- Invoice balance cleared partially by PDC — credit calculation must use NET outstanding
- PDC bounces after credit was calculated as covered — immediate re-evaluation
- Customer provides new PDC while existing invoice is overdue — does it count toward hold threshold?
- Authorized override of HOLD for a specific transaction

### Financial Edge Cases
- Currency mismatch between SPO and supplier invoice
- VAT mismatch between PO tax rate and invoice tax rate
- Rounding differences in Decimal calculations
- Partial payment leaving AED 0.01 remaining

---

## Section 11: Wave 0 — Architecture Lock (First Step)

> [!IMPORTANT]
> **Wave 0 produces specification documents only. No feature implementation.**
> Agents produce documents into `architecture/` folder. Human reviews and approves each before Wave 1 begins.

Documents to produce:
- `architecture/domain-model.md` — all entities, fields, types, constraints
- `architecture/entity-relationship.md` — ER diagram in Mermaid
- `architecture/state-machines.md` — all state machines with valid/invalid transitions
- `architecture/business-rules.md` — all business rules numbered and categorized
- `architecture/inventory-rules.md` — inventory-specific rules
- `architecture/procurement-rules.md` — procurement-specific rules
- `architecture/api-contracts.md` — all endpoint signatures with request/response schemas
- `architecture/edge-cases.md` — all edge cases with expected system behavior

---

## Section 12: Complete 27-Wave Execution Plan

> [!NOTE]
> **Definition of Done per Wave — A wave is NOT finished until ALL of these are checked:**
> - ☑ Database schema + Alembic migration + constraints + indexes
> - ☑ Backend schemas (Pydantic) + services (business logic) + routers (HTTP)
> - ☑ Authorization (workspace_id scoping, role checks)
> - ☑ Audit events logged
> - ☑ State machine transitions validated
> - ☑ Error handling (400/422/403/404 with proper codes)
> - ☑ Concurrency handling (row locks where needed)
> - ☑ Unit tests + integration tests + API tests
> - ☑ Frontend pages + components + Vanilla CSS
> - ☑ Empty states + Loading skeletons + Error toasts
> - ☑ Execution report updated in `.agents/reports/`
> - ☑ **ALL TESTS PASS**

---

| Wave | Focus | Key Deliverables |
|---|---|---|
| **Wave 0** | Architecture Lock | Specification documents only. No code. |
| **Wave 1** | Bug Fix + Core Sync | Fix `toFixed` crash, align field names, real payment modal, pass all existing tests |
| **Wave 2** | Workspace Settings | TRN, logo, VAT config, WhatsApp number, credit control settings, price tolerance |
| **Wave 3** | Product Master | Product, Category, Brand, UOM, UOM Conversion, ProductIdentifier, ProductPrice |
| **Wave 4** | Supplier Master | Supplier, SupplierContact, SupplierBankAccount, SupplierDocument, SupplierProduct |
| **Wave 5** | Payment Methods | Cheque, PDC, Bank Transfer, Cash, method-specific fields, PDC lifecycle |
| **Wave 6** | Email Integration | Resend API, email templates, email logs, send buttons on all documents |
| **Wave 7** | Enquiry Module | Enquiry CRUD, WhatsApp inbound auto-creation, pipeline view |
| **Wave 8** | Quotation Module | Quotation + VAT + revisions, send via WA/Email PDF, accept/reject, convert to Invoice |
| **Wave 9** | Customer PO Module + OCR | CPO + Gemini Vision OCR for scanned POs, credit check on confirm |
| **Wave 10** | Credit Control System | Aging engine, HOLD/WARNING logic, DO/CPO blocking, PDC tracking |
| **Wave 11** | PDF Generation | `@react-pdf/renderer` templates for Invoice, Quotation, DO, Statement, SPO, GRN, CPO |
| **Wave 12** | Procurement Request | ProcurementRequest CRUD, sources, approval workflow |
| **Wave 13** | RFQ Module | RFQ, items, supplier responses, quote comparison, supplier selection + reason |
| **Wave 14** | Supplier PO Module | SPO full CRUD, approval, send, acknowledge, partial confirmation tracking |
| **Wave 15** | Warehouse Foundation | Warehouse CRUD, WarehouseLocation (schema only), WarehouseStock initialization |
| **Wave 16** | GRN Module | GRN creation, inspection, accept/reject per item, stock update on acceptance |
| **Wave 17** | Inventory Ledger | StockTransaction (immutable), WarehouseStock updates, stock query APIs |
| **Wave 18** | Stock Reservations | Reservation on CPO/Invoice, release on DO dispatch, concurrent locking |
| **Wave 19** | Stock Transfers + Adjustments | Transfer between warehouses, adjustment with approval, IN_TRANSIT state |
| **Wave 20** | Stock Count | Count workflow, variance review, approved adjustment posting |
| **Wave 21** | Supplier Invoice + 3-Way Match | Supplier invoice, 3-way matching engine (uses workspace tolerance), discrepancy resolution |
| **Wave 22** | Supplier AP + Payments | Supplier payment recording, AP ledger, supplier statement, AP aging |
| **Wave 23** | Delivery Order + Inventory Connect | DO linked to reservations, stock movement on dispatch, quantity reconciliation |
| **Wave 24** | Customer Statement + AR Aging | Statement PDF, aging report, send via WA/Email |
| **Wave 25** | Returns + Credit/Debit Notes | Sales return, purchase return, credit note, debit note, ledger adjustments |
| **Wave 26** | WhatsApp Full Integration | Meta webhook, inbound→Enquiry, outbound PDF sending, message history |
| **Wave 27** | Reports + Dashboard V2 | Inventory, procurement, AR, AP, PDC, VAT, cash flow forecast |
| **Wave 28** | India Market | CGST/SGST/IGST, GSTIN, HSN codes, multi-market workspace |
| **Wave 29** | Production Deployment | Docker hardening, CI/CD, SSL, domain, monitoring, go-live |

---

## Section 14: Cross-Cutting Test Requirements

**All waves must satisfy these test requirements in addition to feature-specific tests:**

### Multi-Tenant Isolation Suite
- ✅ Every GET endpoint returns only workspace-scoped data (no cross-tenant leaks)
- ✅ Every POST/PUT/DELETE enforces workspace_id from JWT token
- ✅ Attempt to access entity from different workspace → 403 Forbidden
- ✅ Test coverage: all routers with `workspace_id` filtering

### Concurrency Tests
- ✅ Gapless numbering: 2 parallel document creates → distinct sequential numbers
- ✅ Stock reservations: 2 parallel reservations for last 10 units → one succeeds, one fails with "Insufficient stock"
- ✅ Credit control: 2 parallel CPO confirmations for client at credit limit → one succeeds, one blocked
- ✅ Payment idempotency: same Idempotency-Key twice → second returns cached result, no duplicate Payment record

### State Machine Validator Tests
- ✅ All valid transitions succeed (e.g., DRAFT → SENT for Invoice)
- ✅ All invalid transitions fail with 400 + clear error (e.g., PAID → DRAFT blocked)
- ✅ State transition audit events logged to InvoiceEvent (or equivalent per entity)
- ✅ Terminal states block all transitions (e.g., CANCELLED → any fails)

### Immutability Regression Tests
- ✅ Payment UPDATE attempt → 405 Method Not Allowed (no PUT endpoint exists)
- ✅ Payment DELETE attempt → 405 Method Not Allowed (no DELETE endpoint exists)
- ✅ StockTransaction UPDATE attempt → 405 Method Not Allowed
- ✅ StockTransaction DELETE attempt → 405 Method Not Allowed
- ✅ Audit: Payment and StockTransaction records NEVER change after creation

### N+1 Query Prevention
- ✅ All list endpoints with relationships use eager loading (selectinload/joinedload)
- ✅ Verify via SQL logging: one query for parent + one per relationship type (not N queries for N items)
- ✅ Example: GET /invoices → one query for invoices, one for items (not 50 queries for 50 invoices)

### Authorization Tests
- ✅ Unauthenticated request → 401 Unauthorized
- ✅ JWT token expired → 401 with "Token expired" message
- ✅ Missing workspace_id in token → 403 Forbidden
- ✅ Role-based access control (if Wave requires): VIEWER cannot POST/PUT/DELETE

### Decimal Precision Tests
- ✅ All money calculations use Decimal(12,2), never float
- ✅ Rounding edge case: 0.005 rounds to 0.01, not 0.00
- ✅ VAT calculation: (amount * vat_rate) rounded to 2 decimals
- ✅ Partial payment leaves 0.00 balance, not 0.01 or -0.01

### Edge Case Coverage (per wave)
- ✅ Each wave's execution report lists which Section 10 edge cases are tested
- ✅ Untested edge cases documented in "Known Limitations" section of report
- ✅ Critical edge cases (inventory, financial, credit) MUST be tested before wave sign-off

---

## Section 15: Agent Governance Model

```
For every wave:

PLANNER (human reviews spec)
       ↓
Business Rules Review (verify logic is correct before building)
       ↓
Database Agent → schema + migration → database-execution-report.md
       ↓
Backend Agent → router + service + schema → backend-execution-report.md
       ↓
Frontend Agent → pages + components + CSS → frontend-execution-report.md
       ↓
All tests pass
       ↓
Wave sign-off → move to next wave
```

All reports stored in: `.agents/reports/`
Architecture documents stored in: `architecture/`
This master plan stored in: `.agents/MASTER_PLAN_V3.md`

---

## Status: Awaiting Your Approval to Begin Wave 0

> [!NOTE]
> Wave 0 does not write any application code.
> It produces the `architecture/` specification documents from this master plan.
> Once Wave 0 documents are reviewed and approved, Wave 1 (Bug Fix) begins immediately.
