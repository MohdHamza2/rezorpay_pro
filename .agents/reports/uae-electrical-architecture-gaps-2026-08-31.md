# UAE Electrical Wholesale — Missing Architecture (MVP)

**Project:** InvoiceSaaS (rezorpay_pro)
**Audience:** Coordinator + Database Agent + Backend Agent + Frontend Agent
**Date:** 2026-08-31
**Status:** Architecture lock for a *real usable* UAE electrical-trade MVP
**Rule:** Extend existing modules. Do **not** invent parallel invoice/payment/product/inventory systems.

---

## 0. How to use this document

This is the execution-ready architecture for the **sales-and-compliance hole**. Procurement (PR → RFQ → SPO → GRN → 3-way match) is already built. A UAE electrical wholesaler cannot go live on procurement alone.

- **Sections 1–2:** current vs target (diagrams).
- **Section 3:** files to reuse (do not duplicate).
- **Section 4:** every missing bounded context — models, APIs, invariants.
- **Section 5:** sequential phases 1..n (no skipped dependencies).
- **Sections 6–7:** threat model and tests.
- **Section 8:** must-have vs NOT-in-scope.
- **Section 9:** 15-bullet ship-priority gap list.

Agents must not invent business rules. Ambiguous cases are listed in §10; stop and ask.

---

## 1. Market facts that drive the design

Sources: UAE FTA VAT Law (Federal Decree-Law 8/2017) Art. 59 tax invoices; Cabinet Decision 74/2023 (records language); MoF e-invoicing (Ministerial Decisions 243/244 of 2025, PINT-AE / Peppol 5-corner); Federal Decree-Law 6/2022 (commercial payment timings); UAE electrical wholesale practice (quote → LPO → DN + tax invoice → Net 30/45/60, PDC common).

| Fact | Product implication |
|---|---|
| Standard VAT **5%**. TRN is **exactly 15 digits**, typically starting `100`. | Default tax rate 5.00. Validate TRN format. Never float. |
| Document must be labelled **"Tax Invoice"** (quotes, LPOs, delivery notes, receipts are **not** tax invoices). | Separate document types + PDF titles. Quotation ≠ Invoice. |
| Full tax invoice: seller name/address/TRN, buyer name/address/TRN (if registered), sequential number, issue date, **date of supply** if different, line description/qty/unit price/VAT rate, **discounts**, net, VAT in **AED**, gross. Issue generally **within 14 days** of supply. | Extend `Invoice` + `InvoiceItem` + workspace legal address. |
| Simplified tax invoice allowed if buyer **not VAT-registered**, or registered and consideration **≤ AED 10,000**. | `invoice_kind`: STANDARD \| SIMPLIFIED. Auto-select; allow override with reason. |
| Corrections: **do not edit** a reported tax invoice. Issue a **Tax Credit Note** (own gapless series, references original invoice number/date, reason, VAT adjustment). Issue within **14 days** of the adjustment event. | New CreditNote context. Keep existing void-only-when-unpaid. |
| Records: 5 years (VAT); 7 years (corporate tax). English invoices are legal; FTA may demand **certified Arabic translation**. Market still expects bilingual PDFs. | Soft-delete forever. Store `*_ar` names. Bilingual PDF in MVP. |
| e-invoicing: B2B/B2G structured **PINT-AE XML** via Accredited Service Provider. Large (≥ AED 50M) go-live **1 Jan 2027**; SMEs **1 Jul 2027**. B2C later. | **Data-model ready now. No ASP/Peppol in MVP.** |
| Sales cycle: Enquiry (often WhatsApp) → **Quotation** → customer **LPO** → pick → **Delivery Note** + **Tax Invoice** → payment (cash / transfer / cheque / **PDC**) on **Net 30 / 45 / 60**. | Sales documents are the MVP spine. WhatsApp is later. |
| Credit: new buyers COD or 50% advance; SME Net 30; mid Net 45–60. **HOLD** stops new LPOs and deliveries, not collections. | Enforce existing workspace credit flags on **Client**, not just store them. |
| **Retention (5–10%)** is a **construction/MEP project** pattern, not counter wholesale. Most electrical **trade credit is retention-free**. | Optional `retention_percent` default **0**. No retention-release module in MVP. |
| Catalogue: SKU, MPN, brand (Ducab, ABB, Schneider, Legrand…), **amp**, **cable mm² / cores**, voltage, poles, UOM (MTR, DRUM, PCS, ROLL). Volume + customer prices. | Extend `Product` + use existing `ProductPrice`. |
| Currency: **AED** on the tax invoice VAT lines even if quote was USD. | Keep `currency` on docs; require VAT amounts in AED (or AED equivalent + rate). MVP: AED-only tax invoices. USD quotes allowed, convert at confirmed rate before invoicing. |
| Trade discount vs volume price: header/line % or AED discount **before VAT**. | Line `discount_percent` / `discount_amount`; VAT on net after discount. |

---

## 2. Current vs target architecture

### 2.1 What exists today (honest)

The running system is a **multi-tenant FastAPI monolith** with a **complete inbound procurement stack** and a **thin sales stack**.

**Sales today:** Client (contact card) → free-text Invoice → Payment (cash/bank/cheque/PDC). PDF titled `INVOICE`, English-only, no buyer TRN, no date of supply, no discounts, lines not tied to SKUs.

**Ops today:** Product/Category/Brand/UOM (+ unused identifier/price/conversion tables) → Supplier → PR → RFQ → SPO → GRN → Supplier Invoice (3-way match). Inventory snapshot + `POST /inventory/adjust` (violates locked Rule 1.1).

**Frontend today** (`frontend/`): Vite + React 18 + TanStack Query. Routes: Dashboard, Clients, Invoices, Products, Suppliers, Inventory, Procurement, RFQ, SPO, GRN, Supplier Invoices, Settings. **No** Quotations, LPO, Delivery Notes, Credit Notes, Statements, Arabic, product-on-invoice-line.

### 2.2 Target MVP (sales spine + reuse procurement)

```
                         ┌──────────────────────────┐
                         │   WORKSPACE (UAE VAT)    │
                         │  TRN, legal address, AED │
                         │  default VAT 5%, credit  │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
              ▼                       ▼                       ▼
        PRODUCT MASTER          CUSTOMER (AR)            SUPPLIER (AP)
        SKU + electrical        Client + credit          (EXISTS — reuse)
        specs + prices          terms 30/45/60
              │                       │                       │
              │                       ▼                       ▼
              │              QUOTATION (QUO-YYYY-XXXX)   PR / RFQ / SPO
              │                       │                  GRN / SI 3-way
              │                       ▼                       │
              │              LPO / CPO (CPO-YYYY-XXXX)        │
              │                       │                       │
              │         ┌─────────────┴─────────────┐         │
              │         ▼                           ▼         │
              │   TAX INVOICE                  DELIVERY NOTE  │
              │   INV-YYYY-XXXX                DN-YYYY-XXXX   │
              │         │                           │         │
              │         ▼                           ▼         │
              │   PAYMENT (immutable)         STOCK ISSUE     │
              │   CREDIT NOTE (CN-…)          (from DN, not   │
              │                               /inventory/adjust)
              └───────────────────────────────────────────────┘
```

Procurement remains as built. **Do not rebuild SPO/GRN/SI.** Sales must start consuming `Product` and `InventoryLevel`.

### 2.3 Data model (current → target)

```
CURRENT
Workspace 1──* User
          1──* Client 1──* Invoice 1──* InvoiceItem   (description only)
                           Invoice 1──* Payment
                           Invoice 1──* InvoiceEvent
          1──* Product (SKU, tax_rate, reorder)
          1──* Supplier 1──* SPO 1──* GRN 1──* SupplierInvoice

TARGET (MVP additions in CAPS; existing kept)
Workspace ──+ legal_name, address, name_ar, iban, invoice_footer, market=UAE
Client    ──+ trn, credit_limit, credit_terms_days, credit_status,
              legal_name, billing/shipping, name_ar, client_code, whatsapp
Product   ──+ specs JSONB, amp_rating, cable_size_mm2, voltage_v, poles,
              hs_code, vat_category, name_ar
Invoice   ──+ quotation_id, cpo_id, supply_date, invoice_kind,
              discount_amount, payment_terms_days, seller/buyer TRN snapshots,
              document_title=TAX_INVOICE, einvoice_status
InvoiceItem ──+ product_id, uom_id, sku_snapshot, discount_*, tax_amount,
                line_net, line_gross
NEW: Quotation, QuotationItem, QuotationCounter
NEW: CustomerPurchaseOrder (LPO), CpoItem, CpoCounter
NEW: DeliveryNote, DeliveryNoteItem, DnCounter
NEW: CreditNote, CreditNoteItem, CnCounter
NEW: CreditStatusEvent
NEW: StockReservation (ties DN to InventoryLevel.reserved)
REUSE: Payment, InvoiceCounter, IdempotencyKey, AuditService, Inventory*
```

### 2.4 Request flow (target sales)

```
Client UI / API
    │  JWT (workspace_id from token, never body)
    ▼
Router (HTTP only)  ── wrapper {success, data, error}  ── pagination on lists
    ▼
Service (invariants, state machine, Decimal money, SELECT FOR UPDATE)
    ▼
PostgreSQL 16 (Alembic-only schema)
```

Quote → LPO → Invoice / DN sequence:

```
POST /quotations                     DRAFT
POST /quotations/{id}/send           SENT  (PDF; email later)
POST /quotations/{id}/accept         ACCEPTED
POST /quotations/{id}/convert-to-cpo RECEIVED LPO (copy lines, prices frozen)
POST /customer-purchase-orders/{id}/confirm
        credit check → CONFIRMED; optional stock reserve
POST /invoices  { cpo_id }           DRAFT tax invoice (lines from CPO, VAT 5%)
POST /invoices/{id}/send             SENT  ("Tax Invoice" PDF)
POST /delivery-notes { cpo_id }      DRAFT DN
POST /delivery-notes/{id}/dispatch   stock ISSUE; credit check if block_do_on_hold
POST /invoices/{id}/payments         Idempotency-Key; FOR UPDATE; no overpay
POST /credit-notes                   if return/discount/error after SENT
```

Walk-in / counter (no LPO): `POST /invoices` without `cpo_id` still allowed. Cash sale: create invoice + immediate payment. DN optional.

### 2.5 Invoice state machine (keep CLAUDE.md; add OVERDUE job)

Existing enum already has OVERDUE. Wire the daily job. Do not add VOIDED.

```
                    ┌────────────┐
                    │   DRAFT    │  editable; soft-delete OK
                    └─────┬──────┘
              /send │     │ /void
                    ▼     ▼
              ┌──────────┐   CANCELLED (terminal)
              │   SENT   │
              └──┬───┬───┘
                 │   │ due_date < today AND balance > 0 (job)
                 │   ▼
                 │ OVERDUE
                 │   │
     payment     ▼   ▼
         PARTIALLY_PAID ──payment──► PAID
                 │                     │
                 └──── /void ──────────┘──► CANCELLED
                                            (reason required;
                                             if VAT already
                                             reported → use
                                             Credit Note, do
                                             not void)
```

**Locked rules (already in CLAUDE.md):**
- Edit only in DRAFT.
- Payments immutable (amount/method/date). PDC *status* is a lifecycle, not a financial rewrite.
- Overpayment → 400.
- Gapless `INV-YYYY-XXXX` via `SELECT FOR UPDATE` on `InvoiceCounter`.

**New rules:**
- SENT/PAID/OVERDUE financial correction → **Credit Note**, not PUT.
- Void of SENT unpaid: allowed (CANCELLED + watermark). If the invoice was included in a VAT period, agents must **not** invent auto-void; require Credit Note (flag if `vat_reported_at` is set — field added in Phase 1, default null).
- `OVERDUE` is cache; source of truth remains `balance_due` and `due_date`.

### 2.6 Payment flow (extend existing)

```
POST /invoices/{id}/payments
  Header: Idempotency-Key (48h, workspace-scoped)   [EXISTS]
  Lock invoice FOR UPDATE                           [EXISTS]
  amount <= balance_due                             [EXISTS]
  method: CASH | BANK_TRANSFER | CHEQUE | PDC | CREDIT_CARD  [EXISTS]

  CASH / BANK_TRANSFER / CREDIT_CARD → status SUCCESS immediately
  CHEQUE dated today or past → SUCCESS (cleared-on-receipt assumption for MVP)
  PDC (pdc_date > today) → status PENDING, pdc_status=RECEIVED
        does NOT reduce balance_due until CLEARED

PDC machine (replace PUT /payments with dedicated actions):
  RECEIVED → DEPOSITED  (on/after pdc_date)
  DEPOSITED → CLEARED   → Payment.status=SUCCESS; invoice balance updates
  DEPOSITED → BOUNCED   → Payment stays; no SUCCESS; credit HOLD candidate
  RECEIVED → RETURNED   → cancelled before deposit; no SUCCESS

No DELETE. No amount UPDATE.
```

---

## 3. What already exists — reuse these files

Do not create `SalesInvoice`, `TaxInvoice`, `CustomerPayment`, `Item`, or a second stock table.

### 3.1 Platform

| Concern | Reuse |
|---|---|
| Entrypoint / router mount | `backend/app/main.py` |
| Settings | `backend/app/config.py` |
| Async DB | `backend/app/database.py` |
| JSON logs | `backend/app/logging.py` |
| JWT | `backend/app/auth/router.py`, `auth/utils.py`, `auth/dependencies.py` (`get_current_workspace_id`) |
| Wrapper + pagination | `backend/app/schemas/common.py` (`SuccessResponse`, `PaginatedResponse`, `ErrorCode`) |
| Roles | `backend/app/models/user.py` (`OWNER`, `ADMIN`, `MEMBER`) |

### 3.2 Sales core (extend)

| Concern | Reuse |
|---|---|
| Workspace + VAT 5% + credit flags | `backend/app/models/workspace.py`, `schemas/workspaces.py`, `routers/workspaces.py` |
| Client | `backend/app/models/client.py`, `schemas/clients.py`, `routers/clients.py` |
| Invoice + status | `backend/app/models/invoice.py`, `schemas/invoices.py`, `routers/invoices.py`, `services/invoice_service.py` |
| Invoice lines | `backend/app/models/invoice_item.py` |
| Gapless INV | `backend/app/models/invoice_counter.py`, `services/invoice_number.py` |
| Audit | `backend/app/models/invoice_event.py`, `services/audit_service.py` |
| Payment + PDC enums | `backend/app/models/payment.py`, `schemas/payments.py`, `routers/payments.py`, `services/payment_service.py` |
| Idempotency | `backend/app/models/idempotency_key.py` (used inside payment transaction) |

### 3.3 Catalogue / inventory / procurement (consume, don’t fork)

| Concern | Reuse |
|---|---|
| Product, Category, Brand, UOM | `backend/app/models/product.py`, `schemas/products.py`, `routers/products.py` |
| Identifiers, UOM conversion, prices | same `product.py` (`ProductIdentifier`, `ProductUOMConversion`, `ProductPrice`) — **tables exist, routers/CRUD incomplete** |
| Warehouse, bin, levels, txn | `backend/app/models/inventory.py`, `routers/inventory.py` |
| Supplier master | `backend/app/models/supplier.py`, `routers/suppliers.py` |
| PR | `backend/app/models/procurement.py`, `routers/procurement.py` |
| RFQ | `backend/app/models/rfq.py`, `routers/rfq.py` |
| SPO + numbering | `backend/app/models/spo.py`, `spo_counter.py`, `services/spo_service.py`, `spo_number.py`, `routers/spo.py` |
| GRN | `backend/app/models/grn.py`, `services/grn_service.py`, `routers/grn.py` |
| AP invoice + 3-way | `backend/app/models/supplier_invoice.py`, `services/supplier_invoice_service.py`, `routers/supplier_invoices.py` |

### 3.4 Frontend (extend)

| Concern | Reuse |
|---|---|
| Shell / nav | `frontend/src/components/Layout.tsx` |
| Auth | `frontend/src/contexts/AuthContext.tsx`, `pages/Login.tsx`, `Register.tsx` |
| Invoice UI + pay modal | `frontend/src/pages/Invoices.tsx`, `api/invoices.ts` |
| PDF (must retitle) | `frontend/src/components/pdf/InvoicePDF.tsx` |
| Clients / Products / Settings | `pages/Clients.tsx`, `Products.tsx`, `Settings.tsx` |
| Types | `frontend/src/types/api.ts` |

### 3.5 Specs already written (align; do not rewrite ERP)

`architecture/domain-model.md`, `business-rules.md`, `state-machines.md`, `api-contracts.md`, `.agents/MASTER_PLAN_V3.md`.

This document **narrows** V3 to a shippable UAE electrical MVP. Waves 6, 7, 19–20, 22, 25–29 of V3 are deferred except where this file says otherwise.

### 3.6 Defects in existing code that Phase 1 must fix (not new products)

1. `InvoiceItem.total_price` is **gross** (`qty * price * (1 + tax/100)`). FTA lines need **net, VAT, gross**. Add `tax_amount`, `discount_*`, `line_net`; keep `total_price` as **gross** for backward compat, recompute consistently.
2. Invoice create defaults `tax_rate` to **0**, workspace default is **5.00**. Service must default line tax to `workspace.default_tax_rate` unless overridden.
3. PDF title is `INVOICE` — must be **Tax Invoice** / **فاتورة ضريبية**.
4. PDF omits seller address, buyer TRN, supply date, discounts, per-line VAT.
5. `PUT /invoices/{id}/payments/{id}` can change `Payment.status` — violates payment immutability. Replace with PDC transition POSTs.
6. `POST /inventory/adjust` directly mutates `on_hand` — violates Rule 1.1. Keep for **approved StockAdjustment only** after Phase 9; until then, restrict to OWNER/ADMIN + reason, and always write `InventoryTransaction`.
7. Product identifier/price/conversion models have **no list/update/delete routes**.
8. Client `tax_id` is the TRN field — keep column, expose as `trn` in API (alias) so FTA language is used.
9. `InvoiceResponse` has no `amount_paid` / `balance_due` (computed on model; PDF already expects them).

---

## 4. Missing bounded contexts

Shared conventions for every new module:

- `workspace_id` on every table; queries filter JWT workspace only.
- Money: `Numeric(12,2)` / `Decimal`. Qty: `Numeric(12,4)`.
- Soft delete `deleted_at` on business docs.
- Gapless numbers: clone `InvoiceCounter` + `InvoiceNumberService` per prefix (`SELECT FOR UPDATE`).
- List: `page`, `per_page`, `PaginationMeta`.
- Responses: `SuccessResponse` / `PaginatedResponse`.
- State changes: service layer + audit event (extend `InvoiceEvent` pattern; new tables `quotation_events`, etc., or a generic `document_events` — **prefer per-doc event tables** to avoid a second audit product; keep `InvoiceEvent` as-is).
- Alembic migrations; no `create_all`.

Roles for MVP (do not add new enum values unless a phase says so):

| Action | MEMBER | ADMIN/OWNER |
|---|---|---|
| Create quote/invoice/DN/LPO | yes | yes |
| Send documents | yes | yes |
| Confirm LPO / dispatch DN | yes if client not HOLD | yes |
| Credit HOLD override | no | yes + reason |
| Issue credit note / void SENT | no | yes |
| PDC bounce / credit status manual | no | yes |
| Workspace TRN / VAT settings | no | yes |

---

### 4.1 Context A — UAE Tax Invoice Compliance (EXTEND Invoice)

**Purpose:** Make the existing invoice a legal UAE tax invoice.

**Extend `workspaces`**

| Field | Type | Notes |
|---|---|---|
| `legal_name` | str | Trade licence name |
| `legal_name_ar` | str? | Arabic legal name |
| `address_line` | text? | English address (FTA) |
| `address_line_ar` | text? | |
| `emirate` | str? | DU/AD/SH/AJ/RK/FJ/UQ |
| `iban` | str? | Printed on invoice |
| `market` | enum UAE/INDIA | default UAE |
| `currency` | char(3) | default AED |
| `invoice_footer` | text? | Bank details / LPO note |

`trn` and `default_tax_rate` already exist.

**Extend `invoices`**

| Field | Type | Notes |
|---|---|---|
| `quotation_id` | UUID? | FK quotations |
| `cpo_id` | UUID? | FK customer_purchase_orders |
| `supply_date` | date | default = issue_date |
| `invoice_kind` | enum STANDARD/SIMPLIFIED | |
| `discount_amount` | Numeric(12,2) | header discount after lines, before VAT; default 0 |
| `payment_terms_days` | int | snapshot from client |
| `seller_trn_snapshot` | str? | frozen at send |
| `buyer_trn_snapshot` | str? | |
| `seller_name_snapshot` | str? | |
| `buyer_name_snapshot` | str? | |
| `vat_reported_at` | timestamptz? | null = not yet in a return |
| `einvoice_status` | enum NOT_READY/READY/QUEUED/ACCEPTED/REJECTED | default NOT_READY |
| `retention_percent` | Numeric(5,2) | default 0 |
| `retention_amount` | Numeric(12,2) | default 0; not in VAT base change — VAT on full supply; net payable = total − retention |

**Extend `invoice_items`**

| Field | Type | Notes |
|---|---|---|
| `product_id` | UUID? | FK products; nullable for ad-hoc lines |
| `uom_id` | UUID? | |
| `sku_snapshot` | str? | |
| `discount_percent` | Numeric(5,2) | default 0 |
| `discount_amount` | Numeric(12,2) | default 0 |
| `tax_amount` | Numeric(12,2) | VAT on (qty*unit_price − discount) |
| `line_net` | Numeric(12,2) | after discount, before VAT |

Line math (service, Decimal quantize 0.01):

```
gross_line = qty * unit_price
discount_amount = max(explicit, gross_line * discount_percent/100)
line_net = gross_line - discount_amount
tax_amount = line_net * tax_rate/100
total_price = line_net + tax_amount   # GROSS; keep column name
invoice.subtotal = sum(line_net) - header_discount
invoice.tax_amount = sum(tax_amount)  # recalc header discount VAT if used
invoice.total_amount = subtotal + tax_amount
payable = total_amount - retention_amount
```

Header discount in MVP: **allowed only if no line discounts** (avoid double-discount ambiguity). Flag if both sent.

**Invariants**

- Currency of tax invoice = AED for MVP (`400` if USD).
- STANDARD requires buyer name + address; buyer TRN required if `client.trn` present OR total > 10000 and client marked VAT-registered (`trn` not null).
- SIMPLIFIED: buyer TRN optional; still needs seller TRN and "Tax Invoice".
- Cannot SEND if workspace.trn is null or not 15 digits.
- TRN regex: `^100[0-9]{12}$` (15 digits starting 100). Soft-warn vs hard-fail: **hard-fail on send**, soft-validate on save.
- `supply_date` ≤ `issue_date` + 14 days warning (do not block; log).
- Snapshots written on `/send`, then immutable.

**API (extend `routers/invoices.py`)**

```
PUT  /invoices/{id}                 DRAFT only (existing)
POST /invoices/{id}/send            validate FTA fields; snapshot; PDF flag
GET  /invoices/{id}/pdf-model       payload the React PDF needs (no HTML)
```

Send request unchanged; service loads workspace + client.

**Frontend:** rewrite `InvoicePDF.tsx` bilingual; invoice form: product picker, tax 5% default, discount, supply date, LPO ref.

---

### 4.2 Context B — Customer Commercial Master (EXTEND Client)

**Extend `clients`**

| Field | Type | Notes |
|---|---|---|
| `client_code` | str | unique per workspace; `CL-YYYY-XXXX` or user-entered |
| `legal_name` | str? | |
| `legal_name_ar` | str? | |
| `trade_name` | str? | |
| `trn` | str? | API alias of `tax_id` **or** migrate `tax_id` → keep `tax_id` column, populate both in schema |
| `whatsapp` | str? | |
| `billing_address` | text? | |
| `shipping_address` | text? | |
| `credit_limit` | Numeric(12,2) | 0 = no credit (COD) for MVP? **Decision: 0 means use workspace.credit_limit_default; null means unlimited only if ADMIN sets `credit_unlimited=true`** |
| `credit_unlimited` | bool | default false |
| `credit_terms_days` | int | 0, 30, 45, 60 (allow 90) |
| `credit_status` | enum ACTIVE/WARNING/HOLD/SUSPENDED | default ACTIVE |
| `credit_status_changed_at` | timestamptz? | |
| `credit_status_changed_by` | UUID? | |
| `credit_status_reason` | text? | |
| `payment_terms` | str? | display string e.g. "Net 30, PDC accepted" |
| `retention_default_percent` | Numeric(5,2) | default 0 |
| `is_vat_registered` | bool | default false; true if trn set |
| `is_active` | bool | default true |

Keep `tax_id`; Pydantic `trn` reads/writes `tax_id` to avoid dual sources. Database agent: add `trn` as **computed alias in schema only** unless a real second column is required — **single column `tax_id` stays; API field name `trn`**.

**New `credit_status_events`**

`id, workspace_id, client_id, from_status, to_status, reason, outstanding_snapshot, overdue_days_snapshot, changed_by, created_at`

**Invariants**

- Outstanding = sum `balance_due` of invoices in SENT, PARTIALLY_PAID, OVERDUE (SUCCESS payments only; PDC PENDING excluded).
- HOLD if outstanding > credit_limit (and not unlimited) **OR** oldest overdue age > `workspace.credit_hold_days`.
- WARNING if oldest overdue > `workspace.credit_warning_days`.
- HOLD blocks CPO confirm if `block_po_on_hold`; blocks DN dispatch if `block_do_on_hold`. Does **not** block payments or credit notes.
- Manual SUSPENDED only ADMIN + reason.
- New client: `credit_terms_days=0` (COD) recommended default — **lock: default 0, not 30**, to match UAE "new buyer earns credit".

**API**

```
GET    /clients                      + filters credit_status, search
POST   /clients
PUT    /clients/{id}
GET    /clients/{id}/statement       Phase 8
GET    /clients/{id}/aging           Phase 8
POST   /clients/{id}/credit-status   ADMIN; body {status, reason}
```

**Service:** `credit_control_service.py` — `evaluate(client_id)`, `assert_can_confirm_cpo`, `assert_can_dispatch_dn`, `assert_can_create_invoice` (invoice create is **not** blocked by HOLD unless `workspace.block_invoice_on_hold` — field missing, add default **false**).

---

### 4.3 Context C — Electrical Product Catalogue (EXTEND Product)

Tables exist. Gap is **attributes + API completeness + use on sales lines**.

**Extend `products`**

| Field | Type | Notes |
|---|---|---|
| `name_ar` | str? | |
| `hs_code` | str? | FTA/customs; e-invoice later |
| `vat_category` | enum STANDARD/ZERO_RATED/EXEMPT | default STANDARD → tax 5 / 0 / 0 |
| `track_inventory` | bool | default true |
| `amp_rating` | Numeric(8,2)? | breakers, MCCB, cables ampacity |
| `cable_size_mm2` | Numeric(8,2)? | |
| `cores` | int? | |
| `voltage_v` | int? | 230/400/11000 |
| `poles` | int? | 1/2/3/4 |
| `specs` | JSONB | extra: IP rating, kA, colour temp, drum length |

**Complete product APIs** (Hermes wave-3 plan, still open):

```
GET/PUT/DELETE /products/{id}
GET/POST /products/{id}/identifiers
DELETE   /products/{id}/identifiers/{id}
GET/POST /products/{id}/conversions
GET/POST /products/{id}/prices
GET      /products?search=&category_id=&amp_rating=&cable_size_mm2=
```

**Pricing service** `pricing_service.py` (new, uses `ProductPrice`):

Order of precedence (first match wins):

1. `price_type=CUSTOMER_SPECIFIC` + `client_id` + qty ≥ `min_quantity` (highest min_quantity)
2. `price_type` in TIER_* / volume with `client_id` null + qty ≥ min_quantity
3. `price_type=DEFAULT_SALES`
4. Fallback: require explicit `unit_price` on the line (quotes/invoices may override)

Invariants: prices AED; never float; inactive products cannot be added to new quotes/invoices (existing drafts keep snapshot description/sku/price).

**Seed UOMs** (workspace onboarding, not global): PCS, MTR, DRUM, ROLL, COIL, BOX, CARTON, SET, PAIR.

---

### 4.4 Context D — Quotation

**Why MVP:** Electrical wholesale prices from quotes. LPO comes after. A tax invoice is not a quote.

**Models**

`quotations`: `id, workspace_id, quotation_number, client_id, enquiry_id null, quotation_date, valid_until, revision_number default 0, revised_from_id, status, currency default AED, subtotal, discount_amount, tax_amount, total_amount, payment_terms_days, delivery_terms, notes, created_by, created_at, updated_at, deleted_at`

Status: `DRAFT | SENT | ACCEPTED | REJECTED | EXPIRED | REVISED | CONVERTED`

`quotation_items`: `product_id, description, sku_snapshot, quantity, uom_id, unit_price, discount_percent, discount_amount, tax_rate, tax_amount, line_net, total_price (gross)`

`quotation_counters`: like `InvoiceCounter` (workspace_id, year, last_number) prefix `QUO`.

**State**

```
DRAFT → SENT | (revise creates new row, old → REVISED)
SENT → ACCEPTED | REJECTED | EXPIRED | REVISED
ACCEPTED → CONVERTED (to CPO and/or Invoice)
EXPIRED → REVISED (new dates)
REJECTED, CONVERTED terminal
```

**Invariants**

- Edit only DRAFT.
- Quote is **not** a tax invoice; PDF title "Quotation" / "عرض سعر". No TRN obligation, but print seller TRN anyway (market).
- `valid_until` required; job sets EXPIRED.
- Convert copies prices; does not re-price unless `reprice=true`.
- Gapless QUO-YYYY-XXXX.
- USD quotes allowed; convert-to-invoice blocked until currency AED or explicit `exchange_rate` + AED totals (MVP: **block non-AED convert** with 400).

**API**

```
POST /quotations
GET  /quotations?status&client_id&page
GET  /quotations/{id}
PUT  /quotations/{id}                    DRAFT
DELETE /quotations/{id}                  DRAFT soft
POST /quotations/{id}/send
POST /quotations/{id}/accept
POST /quotations/{id}/reject             {reason}
POST /quotations/{id}/revise             copies to new number+revision
POST /quotations/{id}/convert-to-cpo
POST /quotations/{id}/convert-to-invoice
```

---

### 4.5 Context E — Customer LPO (CustomerPurchaseOrder)

UAE name: **LPO**. Code name: `CustomerPurchaseOrder` / routes `/customer-purchase-orders`. UI label: LPO.

**Models**

`customer_purchase_orders`: `id, workspace_id, cpo_number (CPO-YYYY-XXXX), client_id, quotation_id?, customer_lpo_number (theirs), lpo_date, delivery_date?, status, confirmed_by?, confirmed_at?, subtotal, tax_amount, total_amount, currency, payment_terms_days, retention_percent default 0, notes, document_url?, created_at, updated_at, deleted_at`

Status: `RECEIVED | CONFIRMED | PARTIALLY_INVOICED | FULLY_INVOICED | CLOSED | CANCELLED`

`customer_purchase_order_items`: `product_id, description, quantity, uom_id, unit_price, discount_*, tax_*, line_net, total_price, invoiced_quantity, delivered_quantity`

**State**

```
RECEIVED → CONFIRMED (credit check) | CANCELLED
CONFIRMED → PARTIALLY_INVOICED | FULLY_INVOICED | CANCELLED
PARTIALLY_INVOICED → FULLY_INVOICED | CLOSED | CANCELLED
FULLY_INVOICED → CLOSED
```

Invoice and DN are **independent children of CPO** (Rule 4.2). Optional `invoice_id` on DN when they ship together — convenience, not required.

**Invariants**

- Confirm blocked on HOLD if `block_po_on_hold` (403 `CREDIT_HOLD`) unless ADMIN `override_reason`.
- Cannot invoice qty > ordered (sum of invoice lines linked to cpo item).
- Cannot deliver qty > ordered.
- `customer_lpo_number` unique per (workspace, client) recommended but **not unique globally** (two clients may use PO-001). Unique `(workspace_id, client_id, customer_lpo_number)` where lpo_number not null.
- OCR of scanned LPO is **out of MVP**.

**API**

```
POST /customer-purchase-orders
GET  /customer-purchase-orders
GET  /customer-purchase-orders/{id}
PUT  /customer-purchase-orders/{id}          RECEIVED only
POST /customer-purchase-orders/{id}/confirm  {override_reason?}
POST /customer-purchase-orders/{id}/cancel   {reason}
POST /customer-purchase-orders/{id}/invoices  convenience: create DRAFT invoice from remaining qty
POST /customer-purchase-orders/{id}/delivery-notes
```

---

### 4.6 Context F — Credit Control (service + job, not a new ERP)

Workspace flags already exist (`credit_warning_days`, `credit_hold_days`, `block_po_on_hold`, `block_do_on_hold`, `credit_limit_default`). They are **inert**.

**Add** `workspaces.block_invoice_on_hold` bool default false.

**Job:** daily UTC `jobs/credit_and_overdue.py` (or FastAPI lifespan + APScheduler/Celery — **lock: start with a POST `/internal/jobs/nightly` protected by settings token**, then wire scheduler in deploy phase).

Nightly:

1. Invoice SENT/PARTIALLY_PAID where `due_date < today` and balance > 0 → OVERDUE.
2. Recompute each client credit_status; write `credit_status_events` on change.
3. Quotation SENT where `valid_until < today` → EXPIRED.

**PDC bounce:** on BOUNCED, re-run `evaluate(client)`; typically HOLD.

**Invoice due_date:** on create, default `issue_date + client.credit_terms_days`.

---

### 4.7 Context G — Delivery Note (DeliveryOrder)

Architecture docs say DeliveryOrder / DO-YYYY-XXXX. UAE electrical counter uses **Delivery Note (DN)**. Code: table `delivery_notes`, number `DN-YYYY-XXXX`, UI "Delivery Note". Do not create a second "DO" module.

**Models**

`delivery_notes`: `id, workspace_id, dn_number, cpo_id?, invoice_id?, client_id, warehouse_id, delivery_date, status, shipping_address, vehicle_number?, driver_name?, dispatched_by?, dispatched_at?, notes, created_at, updated_at, deleted_at`

Status: `DRAFT | DISPATCHED | PARTIAL | DELIVERED | RETURNED | CANCELLED`

Simplify vs V3: MVP uses `DRAFT → DISPATCHED (all lines) | CANCELLED`. PARTIAL only if some lines qty < ordered remaining. RETURNED is a status flag; **goods return qty in Phase later** — MVP: RETURNED blocks further dispatch; stock reverse via Credit Note + manual StockAdjustment (ADMIN).

`delivery_note_items`: `cpo_item_id?, product_id, quantity, uom_id, stock_reservation_id?`

`stock_reservations`: `id, workspace_id, warehouse_id, product_id, quantity, uom_id, reserved_for_type (CPO|DN), reserved_for_id, status ACTIVE|RELEASED|DISPATCHED, created_by, created_at, released_at?`

On dispatch: `InventoryLevel.reserved -= qty`, `on_hand -= qty`, `InventoryTransaction` type **ISSUE** (enum exists), `reference_type=DN`.

**Invariants**

- Dispatch requires `track_inventory` products: available ≥ qty unless `allow_negative_stock` (add workspace flag default **false**).
- HOLD + `block_do_on_hold` → 403.
- PDF title "Delivery Note" / "إذن تسليم" — **not** Tax Invoice.
- Gapless DN numbers.
- Idempotent dispatch: `Idempotency-Key` on `/dispatch`.

**API**

```
POST /delivery-notes
GET  /delivery-notes
GET  /delivery-notes/{id}
PUT  /delivery-notes/{id}                 DRAFT
POST /delivery-notes/{id}/reserve         optional; auto on confirm CPO if stock
POST /delivery-notes/{id}/dispatch        Idempotency-Key
POST /delivery-notes/{id}/cancel          DRAFT or reserved-not-dispatched
```

Extend `TransactionType` with `RESERVE` and `RELEASE` **or** only adjust `reserved` without extra types. **Lock: add RESERVE, RELEASE to TransactionType** so the ledger explains reserved changes.

---

### 4.8 Context H — Tax Credit Note

FTA-mandatory for post-send corrections. Separate from invoice void.

**Models**

`credit_notes`: `id, workspace_id, credit_note_number (CN-YYYY-XXXX), invoice_id, client_id, issue_date, reason enum SALES_RETURN|INVOICE_ERROR|DISCOUNT|GOODWILL|OTHER, reason_notes, subtotal, tax_amount, total_amount, currency AED, status DRAFT|ISSUED|APPLIED|CANCELLED, created_by, created_at, updated_at, deleted_at`

`credit_note_items`: product_id?, description, quantity, uom_id?, unit_price, tax_rate, tax_amount, line_net, total_price

**State:** DRAFT → ISSUED (gapless number allocated **at issue**, like invoice send vs create — **lock: allocate number at create** to match invoices, only DRAFT editable). ISSUED → APPLIED (reduces invoice `amount_credited`; `balance_due = total - paid - credited`). CANCELLED from DRAFT/ISSUED if not applied and not vat_reported.

**Invariants**

- Must reference original `invoice_number` + `issue_date` (store snapshots).
- PDF title **"Tax Credit Note" / "إشعار دائن ضريبي"**.
- Total CN cannot exceed invoice `total_amount - already_credited`.
- Applying CN is financial; require `Idempotency-Key`.
- Does not delete payments.
- If invoice PAID and CN issued, `balance_due` goes negative? **Lock: reject apply if it would make balance_due < 0 unless `issue_refund=true`** (refund recorded as new Payment negative? Payments amount ≥ 0 constraint exists). **Lock: do not create negative payments.** Over-credit → 400. Refunds out of MVP (manual). So CN apply only up to `balance_due` (unpaid portion). If invoice already PAID, CN ISSUED for VAT but **does not auto-refund**; status ISSUED not APPLIED until a later refund module. Document this in UI.

Wait — FTA credit notes still reduce output VAT even if cash already collected. So we need:

- `vat_adjustment` always on ISSUED.
- `ar_applied` optional: reduces AR if unpaid.
- If paid: ISSUED for tax; AR shows "credit owing to customer" as `client_credit_balance` (new Numeric on client, default 0). Increase on paid-invoice CN; decrease when used against a later invoice.

**Lock:** `clients.credit_balance` (Decimal) = unapplied CN on paid invoices. Next invoice payable = total − min(credit_balance, total). Apply FIFO. Simple, shippable.

**API**

```
POST /credit-notes                  {invoice_id, items, reason}
GET  /credit-notes
GET  /credit-notes/{id}
PUT  /credit-notes/{id}             DRAFT
POST /credit-notes/{id}/issue
POST /credit-notes/{id}/apply       Idempotency-Key
```

---

### 4.9 Context I — AR Aging + Customer Statement

No new documents except PDF.

**API**

```
GET /reports/ar-aging?as_of=
    buckets: current, 1-30, 31-45, 46-60, 61-90, 90+
    per client + workspace totals
GET /clients/{id}/statement?from=&to=
    opening balance, invoices, payments, credit notes, closing
GET /dashboard/stats                 EXTEND existing: overdue_aed, dso, pdc_outstanding
```

Reuse `routers/dashboard.py`.

PDF: `StatementPDF.tsx`. Send via email **out of MVP** (download only).

---

### 4.10 Context J — Document PDF + bilingual

Client-side `@react-pdf/renderer` already chosen.

Templates:

| Doc | Title EN | Title AR | File |
|---|---|---|---|
| Tax Invoice | Tax Invoice | فاتورة ضريبية | extend `InvoicePDF.tsx` |
| Quotation | Quotation | عرض سعر | new |
| LPO ack | Purchase Order Acknowledgement | إشعار أمر شراء | new |
| Delivery Note | Delivery Note | إذن تسليم | new |
| Tax Credit Note | Tax Credit Note | إشعار دائن ضريبي | new |
| Statement | Account Statement | كشف حساب | new |

CANCELLED watermark (Rule 4.4). RTL: Arabic block on the right; English left. Font: must embed an Arabic-capable font (e.g. Noto Naskh Arabic) in the PDF renderer — Helvetica cannot render Arabic.

---

### 4.11 Context K — e-Invoicing readiness (fields only)

**Not in MVP:** Peppol, ASP, PINT-AE XML generation, 5-corner.

**Must store now** so 2027 is not a rewrite:

- Legal names, structured address, TRN both parties (snapshots on send).
- `invoice.einvoice_status`, `einvoice_uuid` nullable, `einvoice_error` text nullable.
- Line: SKU, UOM code, HS code, VAT category code (`S`/`Z`/`E`).
- Document type: invoice vs credit note.

Workspace setting `einvoicing_enabled` default false.

---

### 4.12 Context L — Inventory connection to sales (extend, fix)

Today GRN accept should post stock (verify in `grn_service` — already intended). Sales never issues stock.

**MVP lock:**

- DN dispatch is the **only** sales stock issue.
- Invoice send does **not** move stock (invoice ≠ delivery).
- Optional: CPO confirm creates `StockReservation` if `workspace.auto_reserve_on_invoice` — that flag name is wrong; **add `auto_reserve_on_cpo_confirm` default true**. Do not reserve on invoice create.
- Tighten `/inventory/adjust`: require `reason` enum DAMAGE|COUNT_CORRECTION|LOSS|OTHER, ADMIN only, always ledger.

Stock transfer / count / multi-bin picking: **not MVP**. One default warehouse + default bin per warehouse is enough. `InventoryLevel` is bin-scoped — on warehouse create, auto-create bin `DEFAULT`.

---

### 4.13 Explicitly NOT a new context (do not build)

| Idea | Why not |
|---|---|
| Second invoice table | Extend `invoices` |
| WhatsApp inbox / Enquiry | Phase later; quote can be created without enquiry |
| OCR LPO | Later |
| Supplier payments / AP cheques | SI exists; paying suppliers is not required to sell cables |
| Retention release / DLP calendar | Optional % only |
| India GST | market=UAE |
| Reverse charge / exports zero-rate UI | vat_category on product is enough; no extra docs |
| Bin picking / barcode WMS | schema already has bins |
| Multi-entity holding company | one workspace = one TRN |

---

## 5. Sequential implementation order

Each phase: Alembic → models/schemas → service/router → tests (Postgres) → frontend. Do not start N+1 until N tests pass. Database agent then backend then frontend.

### Phase 1 — UAE Tax Invoice on existing Invoice (P0)

**Depends:** none.
**Does:** workspace legal address/AR; invoice supply_date, kind, snapshots, discount, line tax_amount/line_net/product_id/uom_id; default VAT 5%; TRN validate on send; PDF Tax Invoice bilingual; expose amount_paid/balance_due; due_date from terms if client has them (terms added Phase 2 — until then due_date as entered).
**Fix:** line math; PDF title; InvoiceResponse balances.
**Exit:** create+send invoice with workspace TRN, client tax_id, 5% VAT, AED, "Tax Invoice" PDF.

### Phase 2 — Client credit fields + Product sales-readiness (P0)

**Depends:** Phase 1 (invoice lines can take product_id).
**Does:** client commercial columns + API `trn`; product specs + identifier/price/conversion CRUD; pricing_service; invoice/quote forms pick SKU; default tax from product.vat_category / workspace.
**Exit:** invoice line from SKU pulls price + 5% VAT; client has Net 30 and TRN.

### Phase 3 — Quotations (P0)

**Depends:** Phase 2 (products + clients).
**Does:** quotation module, counter, PDF, convert-to-invoice (no CPO yet).
**Exit:** DRAFT→SENT→ACCEPTED→invoice with frozen prices.

### Phase 4 — Customer LPO (P0)

**Depends:** Phase 3.
**Does:** CPO module; convert quote→CPO; invoice from CPO remaining qty; unique LPO number per client.
**Exit:** quote → LPO confirm → partial invoice.

### Phase 5 — Credit control enforcement + overdue job (P0)

**Depends:** Phase 4 (confirm hook) + Phase 2 (client fields).
**Does:** credit_control_service; nightly overdue+HOLD; block confirm/dispatch; ADMIN override; credit_status_events; due_date default from terms.
**Exit:** client over limit cannot confirm LPO; overdue invoices show OVERDUE.

### Phase 6 — Delivery notes + stock issue (P0)

**Depends:** Phase 4 + Phase 5 (HOLD on dispatch) + existing inventory.
**Does:** DN module; reserve; dispatch ISSUE; auto DEFAULT bin; restrict /inventory/adjust.
**Exit:** confirm LPO → DN dispatch reduces on_hand; HOLD blocks dispatch.

### Phase 7 — Tax Credit Notes (P0)

**Depends:** Phase 1 invoices.
**Does:** CN module, PDF, apply to AR / credit_balance.
**Exit:** SENT invoice overcharge corrected with CN referencing original number; VAT amounts consistent.

### Phase 8 — AR aging + statement PDF (P1)

**Depends:** Phase 5, 7 (CN on statement).
**Does:** aging API, statement PDF, dashboard overdue AED + PDC outstanding.
**Exit:** owner can print a client statement for a date range.

### Phase 9 — Payment/PDC hygiene (P1)

**Depends:** existing payments.
**Does:** remove generic PUT; `POST .../pdc/deposit|clear|bounce|return`; bounced → credit evaluate; PDC not in balance until CLEARED (verify current code — if PDC SUCCESS immediately, **fix here**).
**Exit:** PDC future cheque does not mark invoice PAID; bounce puts client WARNING/HOLD.

### Phase 10 — e-invoice field pack + RBAC polish (P2)

**Depends:** Phase 1, 7.
**Does:** einvoice_status, hs_code on lines snapshot, workspace.einvoicing_enabled; send-path validation that PINT-AE mandatory business fields are non-null. No XML.
**Exit:** checklist endpoint `GET /invoices/{id}/einvoice-readiness` → missing fields array.

### Phase 11 — Frontend sales IA (parallel from Phase 3, complete after 8)

Nav group **Sales:** Clients, Quotations, LPOs, Delivery Notes, Tax Invoices, Credit Notes, Statements.
Keep Purchasing group as-is.
Empty/error/skeleton states required.

### Stop line (MVP ship)

Phases **1–8 + 9 (PDC truth) + 11**. Phase 10 can ship as “ready” without blocking first paying tenant.

**Do not start** WhatsApp, OCR, stock count/transfer, AP payments, India, Peppol until a tenant is live on 1–9.

---

## 6. Threat model (new surfaces)

| ID | Surface | Threat | Mitigation |
|---|---|---|---|
| T1 | All new GETs | Cross-workspace IDOR | `workspace_id` from JWT only; tests copy `test_multi_tenant_isolation.py` |
| T2 | Invoice/CN PDF | TRN/address leak via guessable UUID | auth on GET; no public PDF URL without token |
| T3 | `/send` | Spam / data exfil email | Phase 1 send = status change only (already). No SMTP until Resend wave. |
| T4 | Credit override | Sales clerk bypasses HOLD | ADMIN/OWNER + reason + audit event |
| T5 | CN apply | Double-apply AR reduction | Idempotency-Key; row lock invoice |
| T6 | DN dispatch | Double stock issue | Idempotency-Key; FOR UPDATE on InventoryLevel |
| T7 | Pricing | Customer A sees Customer B price | price query filtered workspace+client_id; never return other clients’ ProductPrice |
| T8 | TRN | Invalid TRN → FTA penalty | hard-fail send; don’t log full bank IBAN in JSON logs |
| T9 | PDC bounce | Silent PAID then bounce | PDC not SUCCESS until CLEARED; bounce re-evaluates credit |
| T10 | `/inventory/adjust` | Theft via qty write | ADMIN + reason; immutable InventoryTransaction |
| T11 | Gapless counters | Number skip / collision | SELECT FOR UPDATE; tests like `test_concurrent_numbering.py` for QUO/CPO/DN/CN |
| T12 | Soft delete | FTA 5-year records destroyed | no hard delete; `include_deleted` admin-only |
| T13 | Snapshot tampering | Change buyer TRN after send | snapshots immutable; PUT blocked non-DRAFT |
| T14 | Internal job | Nightly endpoint abused | shared secret header; not in public OpenAPI if possible |
| T15 | Arabic PDF fonts | XSS N/A; supply-chain font files | vendor from repo; no user-uploaded fonts |
| T16 | e-invoice later | XML injection / ASP secrets | no ASP keys in MVP; when added, vault + redact logs |
| T17 | Roles | MEMBER voids tax invoices | void SENT + issue CN = ADMIN |
| T18 | LPO unique | Invoice wrong client by spoofed client_id | client must belong to workspace (existing pattern in invoices.py) |

STRIDE summary: **Spoofing** JWT; **Tampering** snapshots/stock; **Repudiation** audit events; **Info disclosure** IDOR/PDF; **DoS** pagination already; **Elevation** HOLD override / adjust.

---

## 7. Test strategy per module

Global (every phase): Postgres only; workspace isolation; Decimal; wrapper shape; no `create_all` in prod.

| Module | Must-have tests |
|---|---|
| Tax invoice (Ph1) | VAT 5% on net after discount; header+line consistency ±0.01 fils; send without TRN → 400; SIMPLIFIED vs STANDARD; edit SENT → 400; concurrent INV numbers; PDF-model has "Tax Invoice", both TRNs, AED |
| Client credit (Ph2/5) | default COD 0 days; HOLD blocks CPO confirm; payment still allowed on HOLD; outstanding includes PARTIALLY_PAID not DRAFT; 0.01 rounding |
| Product/pricing (Ph2) | volume break vs customer-specific precedence; inactive SKU blocked on new invoice; isolation of prices |
| Quotation (Ph3) | gapless QUO; revise increments; convert freezes price if product price later changes; EXPIRED job; USD convert-to-invoice 400 |
| LPO (Ph4) | cannot over-invoice qty; unique LPO per client; confirm credit path |
| DN/stock (Ph6) | dispatch decreases on_hand; concurrent last-10-units one fails; HOLD blocks dispatch; DN PDF not titled Tax Invoice; adjust negative blocked |
| Credit note (Ph7) | CN > invoice 400; apply idempotent; paid invoice CN → credit_balance not negative payment; references original number |
| Aging (Ph8) | buckets; cancelled invoices excluded; PDC pending excluded from paid |
| PDC (Ph9) | future PDC not SUCCESS; clear then PAID; bounce restores AR; PUT payment 405 |
| e-invoice ready (Ph10) | readiness endpoint lists missing HS/TRN/address |

Frontend: form VAT default 5; bilingual PDF smoke (download blob non-empty); HOLD shows error toast from `error.code`.

---

## 8. Must-have vs NOT-in-scope (usable MVP, not a toy)

### Must-have (cannot charge a Sharjah cable trader without these)

1. UAE **Tax Invoice** (title, TRNs, addresses, 5% VAT, AED, discounts, supply date, gapless INV).
2. **Clients** with TRN + **credit terms 0/30/45/60** + limit + HOLD.
3. **Product SKUs** on invoice lines (amp / mm² searchable).
4. **Quotations** with validity and convert.
5. **LPO** (customer PO number) and partial invoice.
6. **Delivery Note** independent of invoice; stock out on dispatch.
7. **Payments** cash/bank/cheque/**PDC truth**.
8. **Tax Credit Note**.
9. **AR aging + statement PDF**.
10. Bilingual PDF (EN+AR labels).
11. Multi-tenant, Decimal, soft delete, audit, existing procurement **kept**.

### NOT in MVP (explicit)

- WhatsApp Cloud API / inbound enquiry auto-create
- Resend/email send (download PDF is enough)
- Gemini OCR of LPO/supplier invoices
- Peppol ASP / PINT-AE XML submission
- Retention release, DLP, pay-when-paid clauses
- Progress billing / project WIP
- Supplier AP payment runs, AP PDC
- Purchase returns / debit notes / sales return warehouse workflow (CN + ADMIN adjust instead)
- Stock transfer, stock count, bin picking, barcode
- Negative-stock trading by default
- Multi-currency tax invoices
- Reverse charge, exports, free-zone special schemes UI
- India GST / HSN as a market
- Customer portal / invoice viewed tracking
- Credit insurance integrations
- Mobile native apps
- RBAC finer than OWNER/ADMIN/MEMBER (beyond the permission table in §4)

### Optional field, no workflow

- `retention_percent` on client/CPO/invoice (default 0) — display withheld; no release module.

---

## 9. Fifteen gaps, ship-priority order

1. **Tax Invoice compliance** — existing invoice/PDF is a commercial invoice, not FTA Art. 59.
2. **Line VAT math + default 5% + product_id** — wrong gross, tax 0, no SKU.
3. **Client TRN + Net 0/30/45/60 + credit limit** — `tax_id` unused for VAT; credit settings on workspace never enforced.
4. **Quotation bounded context** — missing; this is how electrical wholesale sells.
5. **Customer LPO (CPO)** — missing; every contractor/trader issues LPOs.
6. **Credit HOLD/WARNING engine + overdue job** — OVERDUE enum unused; no aging.
7. **Delivery Note + stock ISSUE** — sales never moves inventory; `/inventory/adjust` is a back door.
8. **Volume/customer pricing wired** — `ProductPrice` exists, unused.
9. **Electrical catalogue fields + product CRUD complete** — cannot search 4C 10mm² / 63A 3P.
10. **Tax Credit Note** — cannot legally correct a sent invoice.
11. **PDC does not count as cash until cleared; bounce path** — PUT payment is non-compliant.
12. **AR statement + aging report** — cannot collect Net 45 without a statement.
13. **Bilingual Tax Invoice/DN/Quote PDFs** — market expectation; Arabic font.
14. **Workspace legal address + IBAN + TRN hard-fail on send**.
15. **e-invoice field readiness** (non-blocking) — avoid 2027 rewrite.

---

## 10. Questions agents must NOT invent (stop and flag)

1. Should SIMPLIFIED vs STANDARD auto-switch at AED 10,000, or always STANDARD for B2B? **Recommendation: auto, allow ADMIN override.**
2. May MEMBER void a SENT unpaid invoice? **This doc: ADMIN only.**
3. If GRN already posts stock, is opening-balance via adjust allowed? **This doc: ADMIN adjust with reason only.**
4. Retention VAT: VAT on full certificate including retention (FTA construction practice). **If retention_percent > 0, VAT on full supply; payable net of retention.** Confirm with accountant before coding Phase 1 retention display.
5. PDC received: some traders treat as reducing exposure. **This doc: does not reduce `balance_due` until CLEARED.** Exposure for credit_limit may include PENDING PDC face value — **Recommendation: outstanding for HOLD uses invoiced AR minus SUCCESS only (PDC does not increase available credit).** Flag if product owner disagrees.

---

## 11. Coordinator checklist (first sprint)

1. Database: Phase 1 migration (workspace legal, invoice/item columns).
2. Backend: InvoiceService line math + send validation.
3. Frontend: InvoicePDF + invoice form VAT 5% + product dropdown (after Phase 2 product GET-by-id).
4. Do **not** open Quotation PR until Phase 1 send-validation is green.
5. Do **not** add WhatsApp/OCR tickets to the MVP board.

---

**End of architecture lock.** Path: `.agents/reports/uae-electrical-architecture-gaps-2026-08-31.md`
