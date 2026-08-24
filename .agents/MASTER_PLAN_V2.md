# InvoiceSaaS — V2 Enterprise Master Plan
*Full B2B Trade Finance Platform · UAE-First · Two-Sided Market*
*Document Version: 2.0 | Date: Aug 2026 | Status: Awaiting Approval*

---

## ⚠️ One Open Decision Before Execution Begins

> [!CAUTION]
> **Inventory Scope — Your answer locks the architecture. Choose ONE:**
>
> **Option A — Full Inventory Management** *(Recommended)*
> Tracks stock by warehouse, movements, reservations, receipts, deliveries, returns, adjustments, reorder alerts, valuation. Does NOT include bin locations or barcode scanning.
>
> **Option B — Procurement + Basic Stock**
> Tracks supplier PO + GRN + basic stock quantity + delivery. No stock ledger or warehouse splits.
>
> **Option C — Full Inventory + Advanced Warehouse** *(Ambitious)*
> Everything in A plus bin locations, barcode scanning, batch/lot/serial tracking, pick/pack/dispatch, cycle counting.
>
> **My recommendation for a trading company: Option A.** Design the schema to be C-ready later without rebuilding.

---

## Section 1: Platform Architecture (Two-Sided B2B)

```
                         PLATFORM
                            │
             ┌──────────────┴──────────────┐
             │                             │
       CUSTOMER SIDE                 SUPPLIER SIDE
       (Accounts Receivable)         (Accounts Payable)
             │                             │
          Enquiry                      Procurement
             ↓                             ↓
         Quotation                    RFQ (to suppliers)
             ↓                             ↓
     Quotation Revision             Supplier Quotes
             ↓                             ↓
   Negotiation / Approval           Supplier Comparison
             ↓                             ↓
      Customer PO                     Supplier PO
             ↓                             ↓
   Sales Order Confirm               Supplier Acknowledges
             ↓                             ↓
          Invoice                    Goods Receipt (GRN)
             ↓                             ↓
     Delivery Order(s)              Supplier Invoice
             ↓                             ↓
   Customer Payments                  3-Way Match
             ↓                             ↓
    PDC / Cheque / Cash             Accounts Payable
             ↓                             ↓
       AR Ledger                     Supplier Payment
             ↓                             ↓
   Customer Statement             Supplier Ledger
             ↓
     Credit Control

                      PRODUCT MASTER
                           │
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
       Customer          Supplier        Inventory
       Documents         Documents        / Stock
   (Prices/Codes)    (Prices/Codes)    (Warehouses)
```

---

## Section 2: Domain Architecture (11 Domains)

### Domain A — Platform Foundation
Multi-tenancy, Workspace, Users, RBAC, Settings, Audit Trail, Security

### Domain B — Product & Catalog
Product Master, Item Codes, Multiple Identifiers, Categories, Brands, UOM, UOM Conversions, Pricing Rules, Customer Pricing, Supplier Pricing

### Domain C — Customer CRM
Customer Master, Contacts, Credit Profile, Credit Limit, Payment Terms, Account History, Credit Hold Rules

### Domain D — Sales (Customer Side)
Enquiry → Quotation → Revision/Negotiation → Customer PO → Invoice → Delivery Order → Customer Return → Credit Note

### Domain E — Credit & Receivables (AR)
AR Ledger, Aging, Overdue Detection, Credit Warnings, Credit Holds, PDC Management, Cheque Collections, Payment Allocation, Customer Statements

### Domain F — Supplier / Procurement (AP)
Supplier Master, Supplier Products, RFQ, Supplier Quotes, Supplier PO, GRN, Supplier Invoice, 3-Way Matching, Supplier Returns, Debit Notes, AP Ledger, Supplier Payments

### Domain G — Inventory
Warehouses, Stock Ledger (movement-based), Stock Reservations, Transfers, Stock Adjustments, Reorder Alerts, Inventory Valuation

### Domain H — Communication
WhatsApp (inbound + outbound), Email (Resend), PDF Generation, Templates, Document Sending, Message History

### Domain I — AI & OCR
Customer PO OCR, Invoice OCR, Supplier Invoice OCR, Gemini Vision extraction, confidence scoring, human verification queue

### Domain J — Documents & PDF
Quotation PDF, Customer PO (acknowledgement), Sales Invoice, Delivery Order, Supplier PO, GRN, Supplier Invoice, Statements, Credit Note, Debit Note

### Domain K — Reporting & Analytics
Sales Report, Purchase Report, AR Aging, AP Aging, PDC Report, Inventory Report, Stock Valuation, Customer Profitability, Supplier Performance, VAT Summary, Cash Flow Forecast

---

## Section 3: Complete Database Schema

### Foundation Models

#### Workspace (EXTEND existing)
```
+ market: Enum [UAE, INDIA]                default = UAE
+ currency: str                            default = AED
+ trn: str                                 Tax Registration Number (UAE FTA)
+ company_whatsapp: str                    Company's WhatsApp Business number
+ company_email: str
+ company_logo_url: str
+ company_address: str
+ vat_rate: Decimal(5,2)                   default = 5.00
+ credit_warning_days: int                 default = 60
+ credit_hold_days: int                    default = 90
+ block_po_on_hold: bool                   default = True
+ block_do_on_hold: bool                   default = True
+ block_invoice_on_hold: bool              default = False
```

#### User (existing — no change needed)

---

### Domain B — Product & Catalog

#### Category
```
id, workspace_id
name: str
parent_id: UUID (FK → categories, nullable)   [for subcategories]
created_at, updated_at
```

#### Brand
```
id, workspace_id
name: str
manufacturer: str
country_of_origin: str
created_at, updated_at
```

#### UnitOfMeasure
```
id, workspace_id
code: str        (PCS, MTR, KG, BOX, DRUM, CARTON, ROLL, COIL, PACK, SET, PAIR, LTR, SQM, CBM, TON, BUNDLE)
name: str        (Pieces, Meter, Kilogram...)
dimension: Enum [COUNT, LENGTH, WEIGHT, AREA, VOLUME, TIME]
is_base: bool    (whether this is a base unit)
created_at
```

#### Product
```
id, workspace_id
internal_sku: str          (ELE-CBL-DUC-4C10) — unique per workspace
name: str
short_description: str
description: Text
category_id: UUID (FK → categories)
brand_id: UUID (FK → brands, nullable)
hs_code: str               (for customs/FTA)
is_active: bool            default = True
track_inventory: bool      default = True
min_stock_level: Decimal
reorder_level: Decimal
max_stock_level: Decimal
base_uom_id: UUID (FK → unit_of_measures)
purchase_uom_id: UUID (FK → unit_of_measures)
sales_uom_id: UUID (FK → unit_of_measures)
standard_sell_price: Decimal(12,2)
standard_cost_price: Decimal(12,2)
vat_category: Enum [STANDARD, ZERO_RATED, EXEMPT]    UAE VAT classification
created_at, updated_at, deleted_at
```

#### ProductIdentifier
```
id, product_id
identifier_type: Enum [INTERNAL_SKU, MANUFACTURER_PART_NUMBER, SUPPLIER_CODE, BARCODE, CUSTOMER_CODE, EAN, UPC]
identifier_value: str
source: str                (who assigned this code — e.g. "DUCAB", "Customer ABC")
is_primary: bool
created_at
```

#### ProductUOMConversion
```
id, product_id
from_uom_id: UUID (FK → unit_of_measures)
to_uom_id: UUID (FK → unit_of_measures)
conversion_factor: Decimal(10,4)      (1 DRUM = 500 MTR → factor = 500)
created_at
```
> ⚠️ Conversions are per-product, NOT global. 1 BOX of MCB-20A = 12 PCS but 1 BOX of MCB-32A = 10 PCS.

#### ProductPrice (Customer-specific pricing)
```
id, workspace_id, product_id
entity_type: Enum [CUSTOMER, CUSTOMER_GROUP, STANDARD]
entity_id: UUID (nullable — FK to client or group)
min_quantity: Decimal      (for quantity breaks)
max_quantity: Decimal
unit_price: Decimal(12,2)
currency: str
valid_from: date
valid_to: date (nullable — open-ended)
created_at
```

#### SupplierProduct (Supplier ↔ Product mapping)
```
id, supplier_id, product_id
supplier_sku: str            (supplier's code for this product)
supplier_description: str
purchase_uom_id: UUID
last_purchase_price: Decimal(12,2)
current_purchase_price: Decimal(12,2)
currency: str
lead_time_days: int
moq: Decimal                 (minimum order quantity)
is_preferred: bool
last_purchased_at: datetime
created_at, updated_at
```

---

### Domain C — Customer CRM

#### Client (EXTEND existing)
```
+ credit_limit: Decimal(12,2)          default = 0 (0 = unlimited)
+ credit_terms_days: int               default = 30
+ credit_status: Enum [ACTIVE, WARNING, HOLD, SUSPENDED]   default = ACTIVE
+ trn: str                             Customer Tax Reg Number
+ whatsapp_number: str
+ billing_address: str
+ shipping_address: str
+ contact_person: str
+ website: str
+ notes: Text
```

---

### Domain D — Sales

#### Enquiry (NEW)
```
id, workspace_id
client_id: UUID (nullable — may be unknown at enquiry stage)
contact_name, contact_phone, contact_whatsapp, contact_email: str
source: Enum [WHATSAPP, EMAIL, PHONE, WALK_IN, MANUAL]
whatsapp_message_id: str               (Meta WA ID — for deduplication)
items_description: Text                (raw text from customer)
status: Enum [NEW, IN_PROGRESS, QUOTED, CLOSED]
assigned_to: UUID (FK → users, nullable)
notes: Text
created_at, updated_at
```

#### EnquiryItem (NEW — if items are structured)
```
id, enquiry_id
product_id: UUID (nullable — may not be identified yet)
description: str
quantity: Decimal
uom_id: UUID (nullable)
notes: str
```

#### Quotation (NEW)
```
id, workspace_id, client_id
enquiry_id: UUID (nullable)
quotation_number: str                  gapless — QUO-YYYY-XXXX
revision_number: int                   default = 1 (supports Q revisions)
parent_quotation_id: UUID (nullable)   if this is a revised version
status: Enum [DRAFT, SENT, ACCEPTED, REJECTED, EXPIRED, CONVERTED]
valid_until: date
currency: str                          default = AED
subtotal, vat_amount, total_amount: Decimal(12,2)
discount_amount: Decimal(12,2)
terms_conditions: Text
notes: Text
sent_via: Enum [WHATSAPP, EMAIL, BOTH, NONE]
sent_at: datetime
converted_to_invoice_id: UUID (nullable)
created_at, updated_at, deleted_at
```

#### QuotationItem (NEW)
```
id, quotation_id
line_number: int
product_id: UUID (nullable)
internal_sku: str                      (copied at time of quoting)
description: str
quantity: Decimal
uom_id: UUID
unit_price: Decimal(12,2)
discount_percent: Decimal(5,2)         default = 0
vat_rate: Decimal(5,2)                 default = 5.00
vat_amount: Decimal(12,2)
total_price: Decimal(12,2)
notes: str
```

#### CustomerPurchaseOrder (NEW — customer sends PO to us)
```
id, workspace_id, client_id
quotation_id: UUID (nullable)
customer_po_number: str                customer's own PO number
our_reference: str                     our internal SO/order reference
status: Enum [RECEIVED, CONFIRMED, PARTIALLY_INVOICED, FULLY_INVOICED, CLOSED, CANCELLED]
po_date: date
requested_delivery_date: date
document_url: str                      uploaded PDF of customer's PO
ocr_extracted: bool
subtotal, total_amount: Decimal(12,2)
notes: Text
credit_check_passed: bool
created_at, updated_at
```

#### CustomerPurchaseOrderItem (NEW)
```
id, customer_po_id
line_number: int
product_id: UUID (nullable)
internal_sku: str
description: str
quantity: Decimal
uom_id: UUID
unit_price: Decimal(12,2)
vat_rate: Decimal(5,2)
total_price: Decimal(12,2)
invoiced_quantity: Decimal             default = 0 (tracks partial invoicing)
delivered_quantity: Decimal            default = 0
```

#### Invoice (EXTEND existing)
```
+ customer_po_id: UUID (nullable, FK → customer_purchase_orders)
+ quotation_id: UUID (nullable, FK → quotations)
+ amount_paid: Decimal(12,2)           cached sum of SUCCESS payments
+ balance_due: Decimal(12,2)           total_amount - amount_paid
+ payment_terms_days: int              copied from client at creation
+ discount_amount: Decimal(12,2)
+ vat_amount: Decimal(12,2)           (currently as tax_amount — keep, clarify naming)
```

#### InvoiceItem (EXTEND existing)
```
+ product_id: UUID (nullable)
+ internal_sku: str                    (copied at invoicing time)
+ uom_id: UUID (nullable)
+ discount_percent: Decimal(5,2)
+ vat_amount: Decimal(12,2)           (computed from tax_rate)
(existing tax_rate = vat_rate — keep field, rename in display only)
```

#### DeliveryOrder (NEW)
```
id, workspace_id, invoice_id, client_id
customer_po_id: UUID (nullable)
do_number: str                         gapless — DO-YYYY-XXXX
warehouse_id: UUID (FK → warehouses)
status: Enum [PENDING, PARTIAL, DELIVERED, RETURNED]
delivery_date: date
delivered_by: str
recipient_name, recipient_signature_url: str
vehicle_number: str
notes: Text
created_at, updated_at
```

#### DeliveryOrderItem (NEW)
```
id, do_id
invoice_item_id: UUID
product_id: UUID (nullable)
internal_sku: str
description: str
quantity_ordered: Decimal
quantity_delivered: Decimal
uom_id: UUID
```

#### SalesReturn (NEW)
```
id, workspace_id, client_id, invoice_id
return_number: str                     gapless — RTN-YYYY-XXXX
status: Enum [REQUESTED, APPROVED, RECEIVED, REJECTED]
reason: Text
received_date: date
notes: Text
created_at, updated_at
```

#### CreditNote (NEW)
```
id, workspace_id, client_id
sales_return_id: UUID (nullable)
credit_note_number: str                gapless — CN-YYYY-XXXX
amount: Decimal(12,2)
vat_amount: Decimal(12,2)
total_amount: Decimal(12,2)
status: Enum [DRAFT, ISSUED, APPLIED, CANCELLED]
notes: Text
applied_to_invoice_id: UUID (nullable)
created_at, updated_at
```

---

### Domain E — Credit & Receivables

#### Payment (EXTEND existing)
```
+ method: Enum [CASH, CHEQUE, BANK_TRANSFER, CREDIT_CARD, PDC, ONLINE]
+ cheque_number: str
+ cheque_bank: str
+ cheque_date: date                    (for PDC — future date on cheque)
+ pdc_status: Enum [PDC_PENDING, PRESENTED, CLEARED, BOUNCED]   (nullable)
+ reference_number: str                bank ref / transaction ID
+ notes: str
+ received_by: UUID (FK → users)
```

#### CustomerStatement (NEW)
```
id, workspace_id, client_id
period_from, period_to: date
opening_balance, closing_balance: Decimal(12,2)
total_invoiced, total_paid, total_outstanding: Decimal(12,2)
current_due, overdue_30, overdue_60, overdue_90, overdue_120_plus: Decimal(12,2)
generated_at: datetime
sent_via_whatsapp: bool
sent_via_email: bool
```

---

### Domain F — Supplier / Procurement

#### Supplier (NEW — first-class entity like Client)
```
id, workspace_id
supplier_code: str                     internal code — SUP-001
legal_name: str
trading_name: str
contact_person: str
phone, whatsapp: str
email: str
address: str
country: str                           default = UAE
trn: str                               Supplier Tax Reg Number
currency: str                          default = AED
payment_terms_days: int                default = 30
credit_limit: Decimal(12,2)
bank_name, bank_account, bank_iban: str
status: Enum [ACTIVE, INACTIVE, BLACKLISTED]
is_preferred: bool
rating: int                            1-5 star rating
notes: Text
created_at, updated_at, deleted_at
```

#### RFQ — Request for Quotation (NEW)
```
id, workspace_id
rfq_number: str                        gapless — RFQ-YYYY-XXXX
status: Enum [DRAFT, SENT, RESPONSES_RECEIVED, AWARDED, CANCELLED]
required_delivery_date: date
notes: Text
created_at, updated_at
→ rfq_suppliers: List[RFQSupplier]
→ rfq_items: List[RFQItem]
```

#### RFQSupplier (NEW)
```
id, rfq_id, supplier_id
sent_at: datetime
response_received_at: datetime (nullable)
quoted_amount: Decimal(12,2)
lead_time_days: int
notes: str
status: Enum [SENT, RESPONDED, SELECTED, REJECTED]
```

#### RFQItem (NEW)
```
id, rfq_id
product_id: UUID (nullable)
internal_sku, description: str
quantity: Decimal
uom_id: UUID
target_price: Decimal(12,2)  (nullable)
```

#### SupplierPurchaseOrder (NEW — we send PO to supplier)
```
id, workspace_id, supplier_id
rfq_id: UUID (nullable)
po_number: str                         gapless — SPO-YYYY-XXXX
status: Enum [DRAFT, SENT, ACKNOWLEDGED, PARTIALLY_RECEIVED, FULLY_RECEIVED, CLOSED, CANCELLED, REJECTED]
po_date: date
expected_delivery_date: date
currency: str                          default = AED
subtotal, vat_amount, total_amount: Decimal(12,2)
payment_terms_days: int
shipping_address: str
notes: Text
acknowledged_at: datetime
created_at, updated_at
```

#### SupplierPurchaseOrderItem (NEW)
```
id, supplier_po_id
line_number: int
product_id: UUID (nullable)
internal_sku, description: str
quantity: Decimal
uom_id: UUID
unit_price: Decimal(12,2)
discount_percent: Decimal(5,2)
vat_rate: Decimal(5,2)
vat_amount, total_price: Decimal(12,2)
received_quantity: Decimal             default = 0
```

#### GoodsReceiptNote — GRN (NEW)
```
id, workspace_id, supplier_id
supplier_po_id: UUID
grn_number: str                        gapless — GRN-YYYY-XXXX
warehouse_id: UUID (FK → warehouses)
received_date: date
received_by: UUID (FK → users)
status: Enum [DRAFT, CONFIRMED, DISCREPANCY_FLAGGED]
notes: Text
created_at, updated_at
```

#### GRNItem (NEW)
```
id, grn_id
supplier_po_item_id: UUID
product_id: UUID
internal_sku, description: str
quantity_ordered: Decimal
quantity_received: Decimal
quantity_accepted: Decimal
quantity_damaged: Decimal
quantity_rejected: Decimal
uom_id: UUID
batch_number: str  (nullable)
notes: str
```

#### SupplierInvoice (NEW)
```
id, workspace_id, supplier_id
grn_id: UUID (nullable)
supplier_po_id: UUID (nullable)
supplier_invoice_number: str           THEIR invoice number
our_reference: str
status: Enum [RECEIVED, PENDING_MATCHING, MATCHED, DISCREPANCY, APPROVED, PAID, CANCELLED]
invoice_date: date
due_date: date
currency: str
subtotal, vat_amount, total_amount: Decimal(12,2)
amount_paid: Decimal(12,2)
three_way_match_status: Enum [NOT_CHECKED, PASSED, FAILED]
three_way_match_notes: Text
document_url: str                      uploaded PDF of supplier's invoice
ocr_extracted: bool
created_at, updated_at
```

#### PurchaseReturn (NEW)
```
id, workspace_id, supplier_id, grn_id
return_number: str                     gapless — PRN-YYYY-XXXX
status: Enum [REQUESTED, APPROVED, RETURNED, CANCELLED]
reason: Text
created_at, updated_at
```

#### DebitNote (NEW)
```
id, workspace_id, supplier_id
purchase_return_id: UUID (nullable)
debit_note_number: str                 gapless — DN-YYYY-XXXX
amount, vat_amount, total_amount: Decimal(12,2)
status: Enum [DRAFT, ISSUED, APPLIED, CANCELLED]
notes: Text
created_at, updated_at
```

#### SupplierPayment (NEW)
```
id, workspace_id, supplier_id, supplier_invoice_id
amount: Decimal(12,2)
method: Enum [CASH, CHEQUE, BANK_TRANSFER, CREDIT_CARD, ONLINE]
payment_date: date
reference_number: str
cheque_number, cheque_bank: str
notes: str
paid_by: UUID (FK → users)
created_at
```

---

### Domain G — Inventory

#### Warehouse (NEW)
```
id, workspace_id
name: str
code: str               (MAIN, SHOP, WH2...)
address: str
is_default: bool
is_active: bool
created_at, updated_at
```

#### WarehouseStock (NEW — current stock level per product per warehouse)
```
id, workspace_id, product_id, warehouse_id
quantity_on_hand: Decimal(12,4)        (current usable stock)
quantity_reserved: Decimal(12,4)       (reserved for DO pending dispatch)
quantity_on_order: Decimal(12,4)       (on open Supplier POs)
last_updated_at: datetime
UNIQUE: (product_id, warehouse_id)
```

#### StockTransaction (NEW — immutable ledger of every movement)
```
id, workspace_id, product_id, warehouse_id
transaction_type: Enum [
  PURCHASE_RECEIPT,     + (GRN accepted qty)
  PURCHASE_RETURN,      - (returned to supplier)
  SALES_DELIVERY,       - (DO dispatched)
  SALES_RETURN,         + (customer returned)
  STOCK_ADJUSTMENT_IN,  + (manual)
  STOCK_ADJUSTMENT_OUT, - (manual)
  TRANSFER_IN,          + (from another warehouse)
  TRANSFER_OUT,         - (to another warehouse)
  OPENING_STOCK         + (initial balance)
]
quantity: Decimal(12,4)               (always positive — direction in type)
direction: Enum [IN, OUT]
reference_type: str                   (GRN, DO, SPO, MANUAL...)
reference_id: UUID
notes: str
created_by: UUID (FK → users)
created_at: datetime                  (IMMUTABLE — no updates ever)
```

#### StockReservation (NEW)
```
id, workspace_id, product_id, warehouse_id
delivery_order_id: UUID
quantity_reserved: Decimal(12,4)
status: Enum [ACTIVE, FULFILLED, CANCELLED]
reserved_at: datetime
```

---

### Domain H — Communication

#### WhatsAppMessage (NEW)
```
id, workspace_id, client_id (nullable), supplier_id (nullable)
direction: Enum [INBOUND, OUTBOUND]
wa_message_id: str                     Meta's ID — UNIQUE for deduplication
from_number, to_number: str
message_type: Enum [TEXT, DOCUMENT, IMAGE, TEMPLATE]
body: Text
document_url: str
template_name: str
linked_entity_type: str               (enquiry/quotation/invoice/do/statement...)
linked_entity_id: UUID
status: Enum [PENDING, SENT, DELIVERED, READ, FAILED]
error_message: str
created_at: datetime
```

#### EmailLog (NEW)
```
id, workspace_id
resend_message_id: str
to_email, from_email: str
subject: str
linked_entity_type, linked_entity_id
status: Enum [QUEUED, SENT, DELIVERED, BOUNCED, FAILED]
sent_at: datetime
```

---

### Domain I — AI & OCR

#### OcrJob (NEW)
```
id, workspace_id
file_url: str
document_type: Enum [CUSTOMER_PO, SUPPLIER_INVOICE, QUOTATION, DELIVERY_NOTE, GENERAL]
status: Enum [PENDING, PROCESSING, COMPLETED, FAILED, REQUIRES_REVIEW]
extracted_data: JSON                   (Gemini Flash Vision output)
confidence_score: Decimal(3,2)         (0.00 to 1.00)
reviewed_by: UUID (nullable)
linked_entity_type: str
linked_entity_id: UUID (nullable)      (created after extraction)
gemini_model: str                      (e.g. gemini-2.0-flash)
processing_duration_ms: int
created_at: datetime
```

---

## Section 4: Complete State Machines

### Invoice (Customer)
```
DRAFT → SENT (via /send)
DRAFT → CANCELLED (via /void + reason)
DRAFT → [soft-deleted]
SENT → PARTIALLY_PAID (auto on partial payment)
SENT → PAID (auto on full payment)
SENT → OVERDUE (auto — background job, when due_date < today AND balance > 0)
SENT/PARTIALLY_PAID/OVERDUE → CANCELLED (via /void + reason)
PAID/CANCELLED → terminal
```

### Quotation
```
DRAFT → SENT (via /send — triggers WhatsApp/Email)
SENT → ACCEPTED (customer accepts)
SENT → REJECTED (customer rejects)
SENT → EXPIRED (auto — when valid_until < today)
ACCEPTED → CONVERTED (when converted to invoice/CPO)
DRAFT/SENT → DRAFT (revision — creates new Quotation with revision_number++)
```

### Customer PO
```
RECEIVED → CONFIRMED (credit check passes, we confirm)
CONFIRMED → PARTIALLY_INVOICED (auto when some qty invoiced)
PARTIALLY_INVOICED → FULLY_INVOICED (auto when all qty invoiced)
FULLY_INVOICED → CLOSED (after all DOs completed)
Any → CANCELLED
```

### Supplier PO
```
DRAFT → SENT (to supplier)
SENT → ACKNOWLEDGED (supplier confirms)
ACKNOWLEDGED → PARTIALLY_RECEIVED (first GRN created)
PARTIALLY_RECEIVED → FULLY_RECEIVED (all items received)
FULLY_RECEIVED → CLOSED
Any non-CLOSED → CANCELLED / REJECTED
```

### Delivery Order
```
PENDING → PARTIAL (partial delivery made)
PENDING/PARTIAL → DELIVERED (all items delivered)
DELIVERED → RETURNED (customer returns goods)
```

### Credit Status (Customer)
```
ACTIVE → WARNING (oldest overdue > workspace.credit_warning_days)
WARNING → HOLD (oldest overdue > workspace.credit_hold_days OR overdue > credit_limit)
HOLD → ACTIVE (overdue cleared, manually released by authorized user)
HOLD → SUSPENDED (management decision — manual only)
SUSPENDED → ACTIVE (manual release only)
```

---

## Section 5: Credit Control Logic (Critical Business Rules)

```
On every CustomerPO confirmation / Invoice creation / DO release:

1. Fetch client credit profile
2. Compute:
   - total_outstanding = SUM(balance_due WHERE status NOT IN [DRAFT, CANCELLED, PAID])
   - overdue_outstanding = SUM(balance_due WHERE due_date < today)
   - oldest_overdue_age = MAX(today - due_date WHERE balance > 0)
3. Check:
   - IF oldest_overdue_age > credit_hold_days → status = HOLD
   - ELIF oldest_overdue_age > credit_warning_days → status = WARNING
   - ELSE → status = ACTIVE (or clear WARNING)
4. If HOLD:
   - IF workspace.block_po_on_hold → REJECT CPO confirmation
   - IF workspace.block_do_on_hold → BLOCK DO release
   - IF workspace.block_invoice_on_hold → BLOCK invoice creation
   - Log the block event in audit trail
   - Notify workspace admin
5. Customer on HOLD can still:
   - View their account / statement
   - Make payments / provide PDCs
   - Communicate via WhatsApp
```

### PDC Pipeline
```
PDC Received → Payment recorded (method=PDC, pdc_status=PDC_PENDING)
            → cheque_date arrives
            → Bank deposits cheque
            → CLEARED: pdc_status=CLEARED → invoice balance updated
            → BOUNCED: pdc_status=BOUNCED → create bounced cheque alert
                     → notify user → customer to be placed on review
                     → original payment amount reversed in ledger
```

---

## Section 6: 3-Way Matching (Supplier Invoice Validation)

```
When Supplier Invoice is received:
1. Fetch linked Supplier PO
2. Fetch linked GRN(s)
3. Compare per line item:
   - PO quantity vs GRN accepted quantity vs Invoice quantity
   - PO unit price vs Invoice unit price
4. Rules:
   - IF quantity_invoiced > quantity_accepted in GRN → DISCREPANCY (qty)
   - IF unit_price_invoiced > unit_price_PO (> 2% tolerance) → DISCREPANCY (price)
   - IF all matches within tolerance → status = MATCHED → proceed to payment
5. Discrepancies must be resolved by authorized user before payment
```

---

## Section 7: Document Number Sequences (All Gapless)

| Document | Format | Example |
|---|---|---|
| Quotation | QUO-YYYY-XXXX | QUO-2026-0001 |
| Customer PO Reference | CPO-YYYY-XXXX | CPO-2026-0012 |
| Invoice | INV-YYYY-XXXX | INV-2026-0045 (existing) |
| Delivery Order | DO-YYYY-XXXX | DO-2026-0003 |
| Supplier PO | SPO-YYYY-XXXX | SPO-2026-0008 |
| GRN | GRN-YYYY-XXXX | GRN-2026-0002 |
| RFQ | RFQ-YYYY-XXXX | RFQ-2026-0001 |
| Credit Note | CN-YYYY-XXXX | CN-2026-0001 |
| Debit Note | DN-YYYY-XXXX | DN-2026-0001 |
| Sales Return | RTN-YYYY-XXXX | RTN-2026-0001 |
| Purchase Return | PRN-YYYY-XXXX | PRN-2026-0001 |

All use `SELECT FOR UPDATE` row-lock on an `InvoiceCounter`-style sequence table.

---

## Section 8: PDF Standard Template

Every PDF must contain:
1. **Header**: Company logo (left) + Name, TRN, Address, WhatsApp, Email (right)
2. **Document type + number** in large bold: `TAX INVOICE — INV-2026-0012`
3. **Bill To / Ship To**: Client name, TRN, address, WhatsApp
4. **Dates**: Issue Date + Due Date (or delivery date, valid until, etc.)
5. **Line Items Table**: Code | Description | Qty | UOM | Unit Price | Disc% | VAT% | VAT Amt | Total
6. **Summary block**: Subtotal | Discount | VAT Total | **Grand Total (AED)**
7. **Payment Info** (for invoices): Bank name, IBAN, account number, payment terms
8. **Footer**: "Thank you for your business. Contact: [WhatsApp Number]"
9. **Watermark** (for CANCELLED / VOID documents): "CANCELLED" diagonally

---

## Section 9: WhatsApp Business Flow

**Inbound (Customer → System)**
```
Customer sends message to company WhatsApp number
       ↓
Meta sends webhook → POST /api/v1/whatsapp/webhook
       ↓
System extracts: sender number, message body/document
       ↓
If document attached → Create OcrJob → Gemini processes it
       ↓
System finds client by whatsapp_number OR creates anonymous
       ↓
Auto-creates Enquiry with source=WHATSAPP, message body as description
       ↓
Auto-reply: "Enquiry received. Reference: ENQ-2026-0041. We will respond shortly."
```

**Outbound (System → Customer)**
```
User clicks "Send via WhatsApp" on Quotation / Invoice / DO / Statement
       ↓
Frontend renders PDF using @react-pdf/renderer
       ↓
PDF blob uploaded to backend temp storage
       ↓
Backend calls Meta API: POST /messages → type: document → file URL
       ↓
WhatsAppMessage record created with linked_entity
       ↓
Status updates via Meta delivery webhooks (SENT → DELIVERED → READ)
```

---

## Section 10: Implementation Wave Plan

> [!IMPORTANT]
> **Governance per wave (NON-NEGOTIABLE)**
> - Database Agent runs migrations first → logs to `database-execution-report.md`
> - Backend Agent builds API/service → logs to `backend-execution-report.md`
> - Frontend Agent builds UI → logs to `frontend-execution-report.md`
> - Full Pytest suite must pass after every wave
> - All plans stored in `.agents/` folder

| Wave | Focus | Key Deliverables |
|---|---|---|
| **Wave 1** | Bug Fix + Core Sync | Fix `toFixed` crash, align all field names, real payment modal |
| **Wave 2** | Workspace Settings + Company Profile | TRN, logo, WhatsApp number, VAT config |
| **Wave 3** | Product Master | Product, Category, Brand, UOM, UOM Conversions, Identifiers |
| **Wave 4** | Payment Methods Expansion | Cheque, PDC, Bank Transfer, Cash with full fields |
| **Wave 5** | PDF Generation | All document PDFs using @react-pdf/renderer, download buttons |
| **Wave 6** | Email Integration (Resend) | Send documents via email, email logs |
| **Wave 7** | Enquiry Module | Enquiry CRUD, pipeline view, WhatsApp inbound auto-creation |
| **Wave 8** | Quotation Module | Quotation with VAT, revisions, send via WA/Email, convert to Invoice |
| **Wave 9** | Customer PO Module + OCR | CPO + Gemini Vision OCR for scanned POs |
| **Wave 10** | Delivery Order Module | DO, warehouse selection, stock reservation, delivery PDF |
| **Wave 11** | Supplier Master + Supplier Products | Supplier CRM, SupplierProduct mapping, pricing |
| **Wave 12** | RFQ Module | RFQ to multiple suppliers, comparison, award |
| **Wave 13** | Supplier PO Module | SPO full CRUD, send via WA/Email, acknowledge |
| **Wave 14** | GRN Module | Goods receipt, discrepancy tracking, stock update |
| **Wave 15** | Supplier Invoice + 3-Way Match | Supplier invoice validation, matching, approve |
| **Wave 16** | Supplier Payments + AP Ledger | Supplier payment recording, AP aging |
| **Wave 17** | WhatsApp Integration (Meta API) | Full inbound/outbound, message history per client |
| **Wave 18** | Inventory Module | Warehouse, stock ledger, movements, reservations |
| **Wave 19** | Credit Control System | Credit hold logic, aging, overdue alerts, dashboard |
| **Wave 20** | Customer Statement + AR Aging | Statement PDF, aging report, send via WA/Email |
| **Wave 21** | Sales Returns + Credit Notes | Return pipeline, credit note, ledger adjustment |
| **Wave 22** | Purchase Returns + Debit Notes | Purchase return pipeline, debit note |
| **Wave 23** | PDC Management | PDC lifecycle, bounce tracking, deposit schedule |
| **Wave 24** | VAT Report (UAE FTA) | VAT summary, FTA-compliant export |
| **Wave 25** | Dashboard V2 | Cash flow forecast, overdue alerts, AP/AR combined |
| **Wave 26** | India Market (CGST/SGST/IGST) | Multi-market tax handling |
| **Wave 27** | Production Deployment | Docker, CI/CD, SSL, domain, go-live |

---

## ⚠️ Awaiting Your Decision

> [!WARNING]
> Before Wave 1 begins, please confirm:
>
> **1. Inventory Scope**: Option A (recommended), B, or C?
>
> **2. Wave 1 Priority**: Confirm we start immediately with Wave 1 (Bug Fix + Core Sync)?
>
> Once you confirm both, execution begins immediately.
