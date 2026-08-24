# InvoiceSaaS — Enterprise Platform Master Plan
*UAE-First B2B Trade Finance & Automation Platform*
*Document Version: 1.0 | Date: Aug 2026*

---

## Section 1: Technology Decisions (Finalized)

| Category | Choice | Reason |
|---|---|---|
| **Email** | **Resend** | 3,000 free emails/month, modern API, excellent deliverability |
| **OCR / Document AI** | **Gemini Flash Vision** | Free tier (1M tokens/day), state-of-the-art accuracy, already in Google ecosystem |
| **WhatsApp** | **Meta WhatsApp Business Cloud API** | Official API, send PDFs, templates, two-way messaging |
| **PDF Generation** | **`@react-pdf/renderer`** (client-side) | Zero server cost, renders same as UI, downloadable & sendable via WhatsApp |
| **Market** | UAE first, India schema-ready from day 1 | Market flag in Workspace model now |

---

## Section 2: Complete Business Logic & Workflow Pipelines

### 2.1 — The Core Business Reality (UAE B2B Credit System)

> Businesses in the UAE operate primarily on **trade credit**. A customer (buyer) receives goods or services and pays later — after 30, 60, or 90 days based on their agreed terms. Payments come via **cheque (PDC), bank transfer, cash, or credit card**. The seller (your user) must track every transaction against each customer's running account.

This is NOT a simple invoicing system. This is a **full ledger system with a complete document pipeline**:

```
ENQUIRY → QUOTATION → PURCHASE ORDER → INVOICE → DELIVERY ORDER → PAYMENT
```

### 2.2 — Full Pipeline Logic (Step by Step)

#### Step 1: ENQUIRY
- A customer contacts via **WhatsApp (company number), email, phone, or walk-in**
- Inbound WhatsApp messages auto-create an Enquiry in the system
- System logs: `customer ref`, `items description`, `quantity`, `urgency`, `source`
- Sales team reviews and converts to Quotation
- **Status flow**: `NEW → IN_PROGRESS → QUOTED → CLOSED`

#### Step 2: QUOTATION
- Created from an Enquiry (one-click convert) or manually
- Contains: line items, prices, validity date, terms, VAT breakdown (5% UAE)
- Generated as **PDF** client-side
- Sent to customer via: **WhatsApp PDF attachment** OR **Email** OR both
- Customer accepts → one-click convert to Purchase Order
- **Status flow**: `DRAFT → SENT → ACCEPTED → REJECTED → EXPIRED → CONVERTED`

#### Step 3: PURCHASE ORDER (PO)
- Either: converted from Quotation, OR manually entered when customer sends their PO document
- If customer sends a scanned PO → **Gemini Vision OCR** extracts PO number, items, quantities
- PO is linked to one or many Invoices (partial invoicing supported)
- **Status flow**: `RECEIVED → CONFIRMED → PARTIALLY_INVOICED → FULLY_INVOICED → CLOSED`

#### Step 4: INVOICE
- Created from a PO or Quotation (one-click convert) or manually
- **Gapless invoice numbering** (`INV-YYYY-XXXX`, enforced with row locks)
- UAE VAT (5%) computed per line item + total
- TRN (Tax Registration Number) printed on invoice
- Generated as PDF → Sent via WhatsApp / Email
- **Status flow (extended)**:
  ```
  DRAFT → SENT → PARTIALLY_PAID → PAID
        ↘ OVERDUE (auto-set when due_date passes, balance > 0)
        ↘ CANCELLED
  ```

#### Step 5: DELIVERY ORDER (DO)
- Created from Invoice (after invoice is SENT)
- Tracks physical delivery per line item: quantity ordered vs. delivered
- Recipient signs/confirms; signature URL stored
- PDF generated → sent with goods or via WhatsApp to customer
- **Status flow**: `PENDING → PARTIAL → DELIVERED → RETURNED`

#### Step 6: PAYMENT COLLECTION
- Payments recorded against the invoice with method-specific fields:
  - **Cash**: amount, date, reference
  - **Cheque / PDC**: cheque number, bank name, cheque date (future = PDC), face amount
  - **Bank Transfer**: transaction reference number, bank
  - **Credit Card**: last 4 digits, approval code
- PDC (Post Dated Cheque) lifecycle: `PDC_PENDING → CLEARED → BOUNCED`
- When `amount_paid ≥ total_amount` → invoice auto-transitions to `PAID`

#### Step 7: CUSTOMER CREDIT ACCOUNT / STATEMENT
- Every client has a **running credit ledger**: invoices debit, payments credit
- Credit limit enforced: system warns if new invoice would breach limit
- Statement generated as PDF for any date range
- Statement sent via WhatsApp / Email on demand or scheduled (monthly)

---

## Section 3: Complete Database Schema Changes

### 3.1 — Workspace (EXTEND existing)
```
+ market: Enum [UAE, INDIA]           default = UAE
+ currency: str                        default = AED
+ trn: str                            (Tax Registration Number, UAE FTA)
+ company_whatsapp: str               (Company's WhatsApp business number)
+ company_email: str
+ company_logo_url: str
+ company_address: str
+ vat_rate: Decimal(5,2)              default = 5.00 for UAE
```

### 3.2 — Client (EXTEND existing)
```
+ credit_limit: Decimal(12,2)         default = 0 (0 = no limit)
+ credit_terms_days: int              default = 30 (30 / 60 / 90)
+ trn: str                            (Customer's Tax Reg Number)
+ whatsapp_number: str
+ billing_address: str
+ shipping_address: str
```

### 3.3 — Invoice (EXTEND existing)
```
+ po_id: UUID (FK → purchase_orders, nullable)
+ quotation_id: UUID (FK → quotations, nullable)
+ amount_paid: Decimal(12,2)          (cached from SUM of payments)
+ balance_due: Decimal(12,2)          (total_amount - amount_paid)
+ payment_terms_days: int             (30/60/90, from client default)
```

### 3.4 — InvoiceItem (EXTEND existing)
```
+ vat_amount: Decimal(12,2)           (computed: qty * unit_price * vat_rate/100)
(existing tax_rate field is the VAT rate — clarify naming in code)
```

### 3.5 — Payment (EXTEND existing)
```
+ method: Enum [CASH, CHEQUE, BANK_TRANSFER, CREDIT_CARD, PDC]
+ cheque_number: str
+ cheque_bank: str
+ cheque_date: date                   (for PDC — the future date on cheque)
+ pdc_status: Enum [PDC_PENDING, CLEARED, BOUNCED]
+ reference_number: str
+ notes: str
```

### 3.6 — Enquiry (NEW)
```
id, workspace_id, client_id (nullable)
contact_name, contact_phone, contact_whatsapp, contact_email
items_description: Text
source: Enum [WHATSAPP, EMAIL, PHONE, WALK_IN, MANUAL]
whatsapp_message_id: str              (Meta's WA message ID, for deduplication)
status: Enum [NEW, IN_PROGRESS, QUOTED, CLOSED]
notes: Text
created_at, updated_at
```

### 3.7 — Quotation + QuotationItem (NEW)
```
Quotation:
  id, workspace_id, client_id, enquiry_id (nullable)
  quotation_number: str (gapless — QUO-YYYY-XXXX)
  status: Enum [DRAFT, SENT, ACCEPTED, REJECTED, EXPIRED, CONVERTED]
  valid_until: date
  currency: str
  subtotal, vat_amount, total_amount: Decimal(12,2)
  notes, terms: Text
  sent_via: Enum [WHATSAPP, EMAIL, BOTH, NONE]
  sent_at: datetime
  created_at, updated_at, deleted_at

QuotationItem:
  id, quotation_id
  description, quantity, unit_price: Decimal
  vat_rate: Decimal                   (default 5.00)
  vat_amount, total_price: Decimal
```

### 3.8 — PurchaseOrder + PurchaseOrderItem (NEW)
```
PurchaseOrder:
  id, workspace_id, client_id, quotation_id (nullable)
  po_number: str                      (customer's PO number)
  our_reference: str
  status: Enum [RECEIVED, CONFIRMED, PARTIALLY_INVOICED, FULLY_INVOICED, CLOSED]
  po_date, expected_delivery_date: date
  document_url: str                   (customer's uploaded PO PDF)
  ocr_extracted: bool
  subtotal, total_amount: Decimal(12,2)
  notes: Text
  created_at, updated_at

PurchaseOrderItem:
  id, po_id
  description, quantity, unit_price: Decimal
  invoiced_quantity: Decimal          (tracks partial invoicing)
```

### 3.9 — DeliveryOrder + DeliveryOrderItem (NEW)
```
DeliveryOrder:
  id, workspace_id, invoice_id, client_id
  do_number: str (gapless — DO-YYYY-XXXX)
  status: Enum [PENDING, PARTIAL, DELIVERED, RETURNED]
  delivery_date: date
  delivered_by, recipient_name: str
  notes: Text
  created_at, updated_at

DeliveryOrderItem:
  id, do_id, invoice_item_id
  quantity_ordered, quantity_delivered: Decimal
```

### 3.10 — WhatsAppMessage (NEW)
```
id, workspace_id, client_id (nullable)
direction: Enum [INBOUND, OUTBOUND]
wa_message_id: str                    (Meta's ID, unique constraint)
from_number, to_number: str
message_type: Enum [TEXT, DOCUMENT, IMAGE, TEMPLATE]
body: Text
document_url: str
linked_entity_type: str               (enquiry/quotation/invoice/do/statement)
linked_entity_id: UUID
status: Enum [SENT, DELIVERED, READ, FAILED]
created_at: datetime
```

### 3.11 — EmailLog (NEW)
```
id, workspace_id
resend_message_id: str
to_email, from_email: str
subject: str
linked_entity_type, linked_entity_id
status: Enum [SENT, DELIVERED, BOUNCED, FAILED]
sent_at: datetime
```

### 3.12 — OcrJob (NEW)
```
id, workspace_id
file_url: str
document_type: Enum [INVOICE, PO, QUOTATION, DELIVERY_NOTE]
status: Enum [PENDING, PROCESSING, COMPLETED, FAILED]
extracted_data: JSON
linked_entity_id: UUID (nullable — set after entity created from extracted data)
created_at: datetime
```

---

## Section 4: Complete API Endpoint Master List

### Existing (Fix + Sync)
```
POST   /auth/register, /auth/login, /auth/refresh
GET    /auth/me
CRUD   /api/v1/clients
CRUD   /api/v1/invoices
POST   /api/v1/invoices/{id}/send
POST   /api/v1/invoices/{id}/void     (add reason field to frontend)
POST   /api/v1/invoices/{id}/payments (add full payment method fields)
GET    /api/v1/invoices/{id}/payments
GET    /api/v1/invoices/{id}/balance
GET    /api/v1/dashboard/metrics
```

### New Endpoints
```
--- WORKSPACE ---
GET/PUT /api/v1/workspace
POST    /api/v1/workspace/logo

--- ENQUIRIES ---
POST/GET /api/v1/enquiries
GET/PUT  /api/v1/enquiries/{id}
POST     /api/v1/enquiries/{id}/convert-to-quotation

--- QUOTATIONS ---
POST/GET /api/v1/quotations
GET/PUT  /api/v1/quotations/{id}
POST     /api/v1/quotations/{id}/send
POST     /api/v1/quotations/{id}/accept
POST     /api/v1/quotations/{id}/reject
POST     /api/v1/quotations/{id}/convert-to-invoice

--- PURCHASE ORDERS ---
POST/GET /api/v1/purchase-orders
GET/PUT  /api/v1/purchase-orders/{id}
POST     /api/v1/purchase-orders/{id}/confirm
POST     /api/v1/purchase-orders/{id}/convert-to-invoice
POST     /api/v1/purchase-orders/ocr-extract

--- DELIVERY ORDERS ---
POST/GET /api/v1/delivery-orders
GET/PUT  /api/v1/delivery-orders/{id}
POST     /api/v1/delivery-orders/{id}/mark-delivered
POST     /api/v1/delivery-orders/{id}/send

--- PAYMENTS ---
PUT      /api/v1/payments/{id}/pdc-status

--- CLIENT ACCOUNT ---
GET      /api/v1/clients/{id}/account
GET      /api/v1/clients/{id}/statement
POST     /api/v1/clients/{id}/statement/send

--- WHATSAPP ---
POST     /api/v1/whatsapp/webhook     (Meta sends inbound messages here)
POST     /api/v1/whatsapp/send
GET      /api/v1/whatsapp/messages

--- EMAIL ---
POST     /api/v1/email/send

--- OCR ---
POST     /api/v1/ocr/extract

--- REPORTS ---
GET      /api/v1/reports/aging
GET      /api/v1/reports/vat-summary
```

---

## Section 5: Implementation Wave Plan

> [!IMPORTANT]
> **Governance per wave (NON-NEGOTIABLE)**:
> 1. Database Agent → schema + Alembic migration → report in `database-execution-report.md`
> 2. Backend Agent → router + service + schema → report in `backend-execution-report.md`
> 3. Frontend Agent → pages + components + CSS → report in `frontend-execution-report.md`
> 4. Full Pytest suite must pass after every wave before moving to the next.

| Wave | Focus | Delivers |
|---|---|---|
| **Wave 1** | Bug Fixes + Schema Sync | App stops crashing, field names aligned |
| **Wave 2** | Payment Methods Expansion | Cheque, PDC, Bank Transfer, Cash |
| **Wave 3** | Workspace Settings + Company Profile | Logo, TRN, WhatsApp number on all docs |
| **Wave 4** | PDF Generation (`@react-pdf/renderer`) | Downloadable Invoice, Quotation, DO PDFs |
| **Wave 5** | Email Integration (Resend) | Send documents via email |
| **Wave 6** | WhatsApp Integration (Meta API) | Send PDFs via WhatsApp, receive enquiries |
| **Wave 7** | Enquiry Module | Top of the business pipeline |
| **Wave 8** | Quotation Module | Pre-sale document with VAT + send via WA/Email |
| **Wave 9** | Purchase Order Module + Gemini OCR | Auto-extract customer PO fields |
| **Wave 10** | Delivery Order Module | Physical goods tracking, DO PDF |
| **Wave 11** | Customer Statement + Aging Report | Credit management |
| **Wave 12** | VAT Report (UAE FTA) | Tax compliance |
| **Wave 13** | Dashboard Enhancement | Real-time overdue alerts, cash flow |
| **Wave 14** | India Market (CGST/SGST/IGST) | Multi-market support |
| **Wave 15** | Production Deployment | Live launch |

---

## Section 6: PDF Template Standard (All Documents)

Every PDF must include:
1. **Header**: Company Logo + Name + TRN + Address + WhatsApp + Email
2. **Document type + Number** (`TAX INVOICE — INV-2026-0012`)
3. **Bill To / Ship To**: Client name, TRN, address, WhatsApp
4. **Dates**: Issue, Due (or Delivery/Valid Until depending on doc type)
5. **Line Items Table**: Description | Qty | Unit Price | VAT % | VAT Amount | Total
6. **Totals**: Subtotal | VAT Total | **Grand Total (AED)**
7. **Payment Terms** and **Bank Details** (for invoices)
8. **Footer**: "Thank you for your business. Contact: [WhatsApp]"

---

## Section 7: WhatsApp Business Flow

**Inbound (Customer → System)**:
1. Customer sends a message to company's WhatsApp number
2. Meta sends a webhook `POST /api/v1/whatsapp/webhook`
3. System extracts: sender number, message text/document
4. If document → triggers OCR job (Gemini)
5. System auto-creates an `Enquiry` record linked to the client (or anonymous)
6. Reply sent: "We received your enquiry. Reference: ENQ-2026-0001"

**Outbound (System → Customer)**:
1. User clicks "Send via WhatsApp" on Quotation / Invoice / DO / Statement
2. Frontend generates PDF using `@react-pdf/renderer`
3. PDF uploaded to server as temp file
4. Backend calls Meta API: `POST messages` with `type: document`, file URL
5. Message logged in `WhatsAppMessage` table
6. Status updated as Meta delivers confirmation webhooks

---

All reports will be saved in `.agents/reports/` following the mandatory reporting rules in `AGENTS.md`.
