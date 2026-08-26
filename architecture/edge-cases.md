# Edge Cases Specification

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## Overview

This document specifies all edge cases that the system must handle, categorized by domain. Each edge case includes the scenario, expected system behavior, and implementation notes.

---

## Procurement Edge Cases

### P1: Supplier Partially Accepts PO
**Scenario:** Supplier confirms only 800 of 1,000 units ordered in SPO.

**Expected Behavior:**
1. Supplier uses acknowledgment endpoint with partial quantity
2. `SPOItem.acknowledged_quantity = 800` (vs `quantity = 1000`)
3. SPO status remains `ACKNOWLEDGED`
4. System flags `acknowledged_quantity < quantity` as warning
5. Buyer receives notification of partial acceptance
6. Buyer can choose to:
   - Accept partial order
   - Cancel remaining 200 units
   - Create new SPO for remaining 200 units to different supplier

**Implementation:**
- `SPOItem.acknowledged_quantity: Decimal(12,4)` field (nullable)
- Validation allows `acknowledged_quantity <= quantity`
- Dashboard shows "Partial Acknowledgment" badge

---

### P2: Supplier Rejects PO Entirely
**Scenario:** Supplier declines entire SPO (out of stock, discontinued product, pricing error).

**Expected Behavior:**
1. Supplier uses rejection endpoint with reason
2. SPO status → `REJECTED_BY_SUPPLIER`
3. `spo.rejection_reason` populated
4. System sends alert to buyer
5. Linked PR status reverts to `APPROVED` (can create new RFQ)
6. Stock reservations (if any) released

**Implementation:**
- `POST /supplier-portal/spos/{token}/reject` endpoint
- `SPOStatus.REJECTED_BY_SUPPLIER` enum value
- Workflow: revert PR, trigger new RFQ flow

---

### P3: Supplier Delivers More Than Ordered
**Scenario:** SPO ordered 1,000 units, GRN receives 1,100 units.

**Expected Behavior:**
1. GRN allows `quantity_received > spo_item.quantity` (no hard block)
2. System logs warning:
   ```
   "GRN over-receipt: Expected 1000, received 1100 (10% over)"
   ```
3. `grn_item.over_receipt_flag = true`
4. Buyer notified to review
5. Buyer can choose to:
   - Accept all 1,100 units (common for bulk orders)
   - Accept 1,000, reject 100 excess
   - Accept all, create PO amendment for additional 100
6. 3-way match uses `min(invoice_qty, grn_accepted_qty)` for comparison

**Implementation:**
- No hard validation blocking over-receipt
- `GRNItem.over_receipt_flag: bool` field
- Dashboard filter for "Over-receipts requiring review"

---

### P4: Supplier Delivers Less Than Ordered
**Scenario:** SPO ordered 1,000 units, GRN receives 800 units.

**Expected Behavior:**
1. GRN records `quantity_received = 800`
2. `SPOItem.received_quantity = 800`
3. SPO status → `PARTIALLY_RECEIVED` (not `FULLY_RECEIVED`)
4. Buyer can:
   - Wait for second shipment (create another GRN against same SPO)
   - Cancel remaining 200 units (SPO amendment)
   - Claim shortage with supplier
5. 3-way match passes for 800 units

**Implementation:**
- SPO allows multiple GRNs (one-to-many relationship)
- `SPOItem.received_quantity` increments with each GRN
- SPO closes only when `received_quantity >= quantity` for all items

---

### P5: Supplier Changes Price After PO Sent
**Scenario:** SPO sent with unit price AED 10.00, supplier requests AED 10.50.

**Expected Behavior:**
1. Supplier contacts buyer (outside system)
2. Buyer creates SPO amendment with new price
3. Amendment sent to supplier for re-acknowledgment
4. Original SPO locked until amendment resolved
5. If amendment accepted → SPO updated, 3-way match uses new price
6. If amendment rejected → SPO cancelled, new RFQ issued

**Implementation (Wave 29):**
- `SPOAmendment` table with `amendment_type = PRICE_CHANGE`
- Amendment approval workflow
- Original SPO `has_pending_amendment = true` (blocks GRN until resolved)

---

### P6: Supplier Changes Delivery Date After Acknowledgment
**Scenario:** SPO expected delivery 2026-09-15, supplier delays to 2026-09-30.

**Expected Behavior:**
1. Supplier updates delivery date via portal (or buyer updates manually)
2. `spo.expected_delivery_date` updated to 2026-09-30
3. System logs date change in audit trail
4. Buyer receives notification of delay
5. If delay impacts production/sales, buyer can choose to cancel SPO

**Implementation:**
- `POST /supplier-portal/spos/{token}/update-delivery-date` endpoint
- Audit log records original vs new date
- Notification sent to linked PR requester (if production-critical)

---

### P7: Supplier Sends Duplicate Invoice
**Scenario:** Supplier already submitted invoice #INV-001, sends it again (accidental resubmission or fraud attempt).

**Expected Behavior:**
1. 3-way match duplicate check runs: `(supplier_id, invoice_number)` uniqueness
2. Match status → `FAILED_DUPLICATE`
3. Invoice blocked from approval
4. Alert sent to accounts payable team
5. Human review required before proceeding

**Implementation:**
- Unique constraint on `(workspace_id, supplier_id, invoice_number)` in `SupplierInvoice` table
- Database enforces uniqueness (prevents duplicate insert)
- Friendly error message: "Invoice #INV-001 already exists for this supplier"

---

### P8: Supplier Invoice Differs from PO (Price or Qty)
**Scenario:** SPO unit price AED 10.00, supplier invoice shows AED 10.50.

**Expected Behavior:**
1. 3-way match price variance check runs
2. Variance = `abs(10.50 - 10.00) / 10.00 * 100 = 5%`
3. If `5% > workspace.price_tolerance_percent` (default 2%) → `FAILED_PRICE`
4. Invoice blocked from approval
5. Accounts payable reviews:
   - If legitimate (market price increase) → override with reason
   - If error → reject invoice, contact supplier for correction

**Implementation:**
- Configurable `workspace.price_tolerance_percent` (default 2.00%)
- Override requires `can_override_match_failures` permission
- Audit log records override with reason

---

### P9: Supplier Invoice Arrives BEFORE GRN
**Scenario:** Supplier emails invoice on 2026-09-10, goods arrive on 2026-09-15.

**Expected Behavior:**
1. Supplier invoice entered with `grn_id = NULL`
2. Invoice status → `PENDING_GOODS`
3. 3-way match returns `UNRECEIVED_ITEMS` status
4. Invoice cannot be approved for payment
5. When GRN created (2026-09-15):
   - System auto-links GRN to invoice via `spo_id`
   - 3-way match re-runs automatically
   - If match passes → invoice status → `PENDING_APPROVAL`
6. Payment unblocked after goods received and matched

**Implementation:**
- `SupplierInvoice.grn_id` nullable
- Background job or webhook re-runs match when new GRN created for linked SPO
- Dashboard filter: "Invoices awaiting goods receipt"

---

### P10: Multiple GRNs Against One SPO
**Scenario:** SPO for 1,000 units. Supplier ships in 3 batches: 400, 400, 200 units.

**Expected Behavior:**
1. Three separate GRNs created, all linked to same SPO
2. After GRN 1: `spo_item.received_quantity = 400`, status = `PARTIALLY_RECEIVED`
3. After GRN 2: `spo_item.received_quantity = 800`, status = `PARTIALLY_RECEIVED`
4. After GRN 3: `spo_item.received_quantity = 1000`, status = `FULLY_RECEIVED`
5. Each GRN triggers separate inventory increase
6. 3-way matching:
   - Supplier can invoice after each GRN (3 invoices)
   - Or send one invoice after final GRN (1 invoice for 1,000)
   - Match validates invoice qty ≤ cumulative GRN qty

**Implementation:**
- `GRN.spo_id` (many-to-one relationship)
- `SPOItem.received_quantity` cumulative field
- Dashboard shows "3 GRNs" badge on SPO detail page

---

### P11: Multiple Supplier Invoices Against One SPO
**Scenario:** Supplier invoices separately for each GRN batch (3 invoices for same SPO).

**Expected Behavior:**
1. Three invoices created, all linked to same SPO
2. Each invoice validated against its specific GRN
3. 3-way match ensures:
   - `sum(invoice_quantities) <= spo.quantity` (no overbilling)
   - Each invoice matches its linked GRN
4. Payments processed independently per invoice
5. SPO status tracks invoicing: `PARTIALLY_INVOICED` → `FULLY_INVOICED`

**Implementation:**
- `SupplierInvoice.spo_id` and `SupplierInvoice.grn_id` (many SPOs to one invoice, many invoices to one SPO)
- `SPOItem.invoiced_quantity` cumulative field
- Validation: `invoiced_quantity <= received_quantity`

---

### P12: One Supplier Invoice Covering Multiple SPOs
**Scenario:** Supplier sends consolidated monthly invoice covering SPO-2026-0001, SPO-2026-0002, SPO-2026-0003.

**Expected Behavior:**
1. System creates one `SupplierInvoice` with `spo_id = NULL` (consolidated)
2. Invoice items link to specific SPOs via `SupplierInvoiceItem.spo_item_id`
3. 3-way match runs per line item:
   - Item 1 validated against SPO-0001 + GRN-0001
   - Item 2 validated against SPO-0002 + GRN-0002
   - Item 3 validated against SPO-0003 + GRN-0003
4. If any item fails match → entire invoice blocked
5. Payment processed as one transaction (consolidated total)

**Implementation (Wave 29):**
- `SupplierInvoice.spo_id` nullable (for consolidated invoices)
- `SupplierInvoiceItem.spo_item_id` links to specific SPO line
- 3-way match iterates line items, validates each against linked SPO/GRN

---

## Inventory Edge Cases

### I1: Insufficient Available Stock for Reservation
**Scenario:** Product A has 50 units on hand, 40 reserved. New DO requests 20 units (available = 10).

**Expected Behavior:**
1. Reservation service calculates `available = on_hand (50) - reserved (40) - damaged (0) = 10`
2. Requested quantity (20) > available (10)
3. If `workspace.allow_negative_stock = false` → return 400 error:
   ```json
   {
     "success": false,
     "error": {
       "code": "INSUFFICIENT_STOCK",
       "message": "Insufficient stock available: 10 UNITS (requested: 20 UNITS)",
       "product_id": 123,
       "warehouse_id": 1,
       "available": 10,
       "requested": 20
     }
   }
   ```
4. If `workspace.allow_negative_stock = true` → allow reservation, flag for procurement alert

**Implementation:**
- Service layer checks `available_quantity` before creating reservation
- Error response includes actionable data (current availability)
- Dashboard shows "Negative stock products" alert

---

### I2: Stock Reserved But DO Delivery Fails
**Scenario:** DO created with 100-unit reservation. Delivery fails (customer rejects, logistics issue). Need to release reservation.

**Expected Behavior:**
1. DO status → `CANCELLED` or `FAILED`
2. Service releases reservation:
   - `StockReservation.status` → `CANCELLED`
   - `WarehouseStock.quantity_reserved` decreases by 100
   - Stock returns to `available` pool
3. Audit log records reservation cancellation with reason
4. Stock becomes available for other orders

**Implementation:**
- `DELETE /delivery-orders/{id}` or `POST /delivery-orders/{id}/cancel` endpoint
- Auto-releases linked reservations
- Transaction ensures atomic update (reservation + stock)

---

### I3: Damaged Goods Discovered After Acceptance
**Scenario:** GRN accepted 1,000 units. Week later, warehouse finds 50 units damaged.

**Expected Behavior:**
1. Warehouse creates damage report
2. Stock adjustment created:
   - `adjustment_type = DAMAGE_WRITE_OFF`
   - `quantity_change = -50`
   - Reason: "Water damage discovered in storage area"
3. On approval:
   - `WarehouseStock.quantity_on_hand` decreases by 50
   - `WarehouseStock.quantity_damaged` increases by 50
   - StockTransaction type `DAMAGE_WRITE_OFF` created
4. Damaged stock tracked separately (not available for sale)
5. If supplier responsible → create `PurchaseReturn` for supplier claim

**Implementation:**
- `StockAdjustment` with `adjustment_type` enum
- Separate `quantity_damaged` tracking on `WarehouseStock`
- Dashboard: "Damaged stock report" for insurance/supplier claims

---

### I4: Concurrent Reservation Race Condition
**Scenario:** Last 10 units available. Two DOs created simultaneously for 10 units each at 10:00:00.001 AM.

**Expected Behavior:**
1. Both requests hit reservation service at same millisecond
2. Service uses `SELECT FOR NO KEY UPDATE` lock on `WarehouseStock` row
3. First transaction (T1) acquires lock:
   - Reads `available = 10`
   - Creates reservation for 10 units
   - Updates `quantity_reserved = 10`
   - Commits
4. Second transaction (T2) waits for lock:
   - Reads `available = 0` (after T1 commit)
   - Returns 400 "Insufficient stock"
5. Result: One DO succeeds, one fails (correct behavior)

**Implementation:**
- `SELECT FOR NO KEY UPDATE` lock in reservation service
- Pessimistic locking prevents race conditions
- Second request fails gracefully with clear error

---

### I5: Negative Stock Attempt
**Scenario:** Product has 5 units available. User tries to dispatch DO for 10 units.

**Expected Behavior:**
1. Validation at reservation time (before DO dispatch)
2. If `workspace.allow_negative_stock = false` → block with 400 error
3. If `workspace.allow_negative_stock = true`:
   - Allow reservation (available becomes -5)
   - Flag product as "Backorder"
   - Send alert to procurement: "Negative stock alert: Product XYZ, Available: -5"
   - DO status → `PENDING_STOCK` until inventory replenished

**Implementation:**
- Service layer enforces `allow_negative_stock` setting
- Backorder tracking (Wave 29)
- Procurement alert triggers auto-PR

---

### I6: Warehouse Transfer In Progress — Another DO Tries to Use That Stock
**Scenario:** Transfer dispatched from WH-A to WH-B (50 units in transit). New DO tries to reserve from WH-A.

**Expected Behavior:**
1. On transfer dispatch:
   - WH-A: `quantity_on_hand` decreased by 50
   - WH-A: `quantity_in_transit` increased by 50
   - Available at WH-A = `on_hand - reserved - damaged` (transfer already deducted)
2. New DO reservation request:
   - WH-A available stock already reflects transfer (stock deducted on dispatch)
   - If sufficient stock remains → reservation succeeds
   - If insufficient → fails with "Insufficient stock"
3. In-transit stock excluded from `available` calculation

**Implementation:**
- Transfer dispatch immediately decreases `quantity_on_hand` at source
- `quantity_in_transit` tracked separately (not part of `available`)
- No race condition (stock already gone from source)

---

### I7: Product Deactivated With Open Reservations
**Scenario:** Product discontinued. Admin marks `product.active = false`. Existing reservations still active.

**Expected Behavior:**
1. Product deactivation does NOT affect existing reservations
2. Existing DOs can still dispatch (honor commitments)
3. NEW reservations blocked:
   - `POST /stock-reservations` checks `product.active = true`
   - If false → return 400 "Product is inactive and cannot be reserved"
4. Dashboard shows "Products with open reservations to clear before archival"

**Implementation:**
- Product deactivation soft (not deletion)
- Service layer checks `product.active` before new reservations
- Existing reservations grandfathered (no retroactive cancellation)

---

### I8: UOM Conversion Needed During Receiving
**Scenario:** SPO ordered 1,500 MTR cable. Supplier ships 5 DRUMS (1 DRUM = 300 MTR for this product).

**Expected Behavior:**
1. GRN records `quantity_received = 5, uom_id = DRUM`
2. 3-way match runs UOM conversion:
   - Look up `ProductUOMConversion` for (product_id, DRUM → MTR)
   - Find conversion: `1 DRUM = 300 MTR`
   - Convert: `5 DRUMS * 300 = 1500 MTR`
   - Compare: `1500 MTR (converted) = 1500 MTR (ordered)` ✓ PASS
3. If no conversion found → match fails with "Cannot convert DRUM to MTR for Product XYZ"
4. Inventory increases by converted quantity: `quantity_on_hand += 1500 MTR`

**Implementation:**
- UOM conversion service (Wave 5)
- 3-way match normalizes all quantities to SPO UOM before comparison
- Inventory stored in product's `base_uom` (MTR in this case)

---

## Product Edge Cases

### PR1: Same Product Has Multiple Supplier Codes
**Scenario:** Product "ABC Cable" has internal SKU "CAB-001". Supplier A calls it "A-CAB-123", Supplier B calls it "B-WIRE-456".

**Expected Behavior:**
1. `ProductIdentifier` table stores supplier-specific codes:
   - (product_id=1, identifier_type=SUPPLIER_SKU, supplier_id=A, value="A-CAB-123")
   - (product_id=1, identifier_type=SUPPLIER_SKU, supplier_id=B, value="B-WIRE-456")
2. Search endpoint accepts any identifier:
   - Search "A-CAB-123" → returns Product "ABC Cable"
   - Search "B-WIRE-456" → returns same Product "ABC Cable"
   - Search internal SKU "CAB-001" → returns Product "ABC Cable"
3. SPO creation allows selection by any identifier
4. Product display shows all identifiers: "SKU: CAB-001, Supplier A: A-CAB-123, Supplier B: B-WIRE-456"

**Implementation:**
- `ProductIdentifier` with `identifier_type` enum (INTERNAL_SKU, SUPPLIER_SKU, BARCODE, etc.)
- Search indexes all identifier types
- Dashboard: "Product cross-reference" report

---

### PR2: Same Physical Product With Different UOMs From Different Suppliers
**Scenario:** Supplier A sells cable by MTR, Supplier B sells same cable by DRUM.

**Expected Behavior:**
1. Single Product entity (one SKU)
2. `SupplierProduct` records supplier-specific UOM:
   - (supplier_id=A, product_id=1, unit_price=5.00, uom_id=MTR)
   - (supplier_id=B, product_id=1, unit_price=1200.00, uom_id=DRUM)
3. `ProductUOMConversion` defines conversion:
   - (product_id=1, from_uom=DRUM, to_uom=MTR, conversion_factor=300)
4. RFQ sent to both suppliers shows their preferred UOM
5. 3-way match converts to base UOM for comparison
6. Inventory stored in base UOM (MTR)

**Implementation:**
- `SupplierProduct.uom_id` field
- Conversion service handles multi-supplier UOM differences
- Price comparison normalizes to base UOM unit price

---

### PR3: Supplier Changes Their Product Code
**Scenario:** Supplier A previously used "A-CAB-123", now uses "A-CAB-123-V2" for same product.

**Expected Behavior:**
1. Admin updates `ProductIdentifier`:
   - Old: `value = "A-CAB-123"`, `active = false`, `end_date = 2026-08-01`
   - New: `value = "A-CAB-123-V2"`, `active = true`, `start_date = 2026-08-01`
2. Both identifiers searchable (historical reference)
3. Active identifier used for new SPOs
4. Old SPOs still show original identifier (audit trail)
5. Search for either code returns same product

**Implementation:**
- `ProductIdentifier` has `active` flag and `start_date`/`end_date`
- Historical identifiers retained (not deleted)
- Dashboard: "Identifier change log"

---

### PR4: Product Replaced by New SKU (Discontinuation Flow)
**Scenario:** Product "CAB-001" discontinued, replaced by improved "CAB-001-V2".

**Expected Behavior:**
1. Admin marks `CAB-001.active = false`, sets `replacement_product_id = CAB-001-V2.id`
2. Existing stock of CAB-001 remains saleable (clear inventory)
3. New purchases blocked for CAB-001:
   - SPO creation suggests replacement: "CAB-001 discontinued. Use CAB-001-V2 instead?"
4. Customer orders for CAB-001 prompt substitution approval:
   - "Customer ordered CAB-001 (discontinued). Substitute with CAB-001-V2? [Yes/No]"
5. Reports show "Products pending discontinuation" (active stock > 0, product inactive)

**Implementation (Wave 29):**
- `Product.replacement_product_id` (self-referential FK)
- Service layer suggests replacement on SPO/DO creation
- Dashboard: "Discontinued products with stock"

---

### PR5: Duplicate Internal SKU Attempt
**Scenario:** User tries to create new product with SKU "CAB-001" (already exists).

**Expected Behavior:**
1. Database unique constraint on `(workspace_id, sku)` rejects insert
2. API returns 400 error:
   ```json
   {
     "success": false,
     "error": {
       "code": "DUPLICATE_SKU",
       "message": "Product with SKU 'CAB-001' already exists in this workspace",
       "existing_product_id": 123
     }
   }
   ```
3. Frontend shows error with link to existing product

**Implementation:**
- Unique constraint: `CREATE UNIQUE INDEX idx_product_sku ON product (workspace_id, sku) WHERE deleted_at IS NULL`
- Soft-deleted products excluded from uniqueness check (SKU can be reused after deletion)

---

## Customer Credit Edge Cases

### C1: Invoice Balance Cleared Partially by PDC
**Scenario:** Invoice AED 10,000. Customer provides PDC for AED 6,000 (clearing date: 2026-09-30). Credit limit check on 2026-09-01.

**Expected Behavior:**
1. Credit outstanding calculation:
   - Invoice balance_due = AED 10,000
   - PDC with status `PDC_PENDING` or `PRESENTED` does NOT reduce outstanding
   - Outstanding = AED 10,000 (until PDC clears)
2. On PDC clearing date (2026-09-30):
   - PDC status → `CLEARED`
   - Invoice `balance_due` → AED 4,000
   - Outstanding recalculated = AED 4,000
3. Rationale: PDC can bounce; credit exposure is real until bank confirms clearance

**Implementation:**
- Credit calculation uses `balance_due` (actual unpaid amount)
- PDC clearing date triggers invoice update + credit recalculation
- Background job runs daily to check PDC clearing dates

---

### C2: PDC Bounces After Credit Was Calculated as Covered
**Scenario:** PDC cleared on 2026-09-30, credit status updated to ACTIVE. PDC bounces on 2026-10-05 (bank notifies insufficient funds).

**Expected Behavior:**
1. Bank notifies PDC bounce (manual entry or API integration)
2. System updates:
   - PDC status → `BOUNCED`
   - Invoice `balance_due` increases by PDC amount (AED 6,000 restored)
   - Payment record reversed (or negative payment created)
3. Credit status re-evaluation:
   - Outstanding increases by AED 6,000
   - If now exceeds limit → status → `HOLD`
   - Customer receives "PDC bounced" notification
4. Bounced cheque fees applied (configurable per workspace)
5. Customer future PDCs may be declined (trust score decreased)

**Implementation:**
- `Payment.status` includes `BOUNCED` state
- Bounce triggers credit recalculation background job
- Audit log records bounce reason
- Dashboard: "Bounced cheques report"

---

### C3: Customer Provides New PDC While Existing Invoice Overdue
**Scenario:** Customer has overdue invoice from 2026-08-01 (AED 10,000). On 2026-09-01, places new order and provides PDC for new invoice (AED 5,000).

**Expected Behavior:**
1. Credit check on new order:
   - Outstanding = AED 10,000 (old invoice) + AED 5,000 (new order) = AED 15,000
   - PDC for new invoice does NOT reduce outstanding (not cleared yet)
   - If AED 15,000 > credit limit → order blocked or requires override
2. PDC clearing:
   - New PDC clears → reduces balance of NEW invoice only (not oldest invoice)
   - If workspace uses "oldest invoice first" policy:
     - PDC payment applied to oldest invoice first (AED 10,000)
     - Remaining AED 5,000 applied to new invoice
3. Credit aging calculation:
   - Uses oldest invoice date for aging (2026-08-01 invoice)
   - New PDC does NOT reset aging clock

**Implementation:**
- Payment allocation policy configurable: `oldest_first` or `match_invoice`
- Credit calculation includes ALL unpaid invoices
- PDC pending status does NOT reduce exposure

---

### C4: Authorized Override of HOLD for Specific Transaction
**Scenario:** Customer on HOLD (credit limit exceeded). Manager approves one-time CPO confirmation for strategic order.

**Expected Behavior:**
1. CPO confirmation blocked by credit check (status = HOLD)
2. Manager uses override:
   - `POST /customer-purchase-orders/{id}/confirm` with `override_credit_hold = true`
   - Requires `override_reason`: "Strategic customer, payment guaranteed by CEO"
   - User must have `can_override_credit_hold` permission
3. CPO confirmation succeeds
4. Credit status remains HOLD (override is transaction-specific, not customer-wide)
5. Audit log records override:
   ```json
   {
     "event": "CREDIT_HOLD_OVERRIDE",
     "cpo_id": 123,
     "override_by": "manager@company.com",
     "reason": "Strategic customer, payment guaranteed by CEO",
     "timestamp": "2026-09-01T10:30:00Z"
   }
   ```
6. Dashboard shows "Credit hold overrides" report for review

**Implementation:**
- Override flag on CPO/DO confirmation endpoints
- Authorization check for override permission
- Audit trail mandatory
- Override does NOT change `Client.credit_status` (remains HOLD)

---

## Financial Edge Cases

### F1: Currency Mismatch Between SPO and Supplier Invoice
**Scenario:** SPO created in AED (unit price AED 10.00). Supplier invoice arrives in USD (unit price USD 2.72).

**Expected Behavior:**
1. 3-way match detects currency mismatch: `spo.currency != invoice.currency`
2. System converts invoice currency to SPO currency for comparison:
   - Fetch exchange rate for (USD → AED) on invoice date
   - Convert: USD 2.72 * 3.67 (exchange rate) = AED 9.98
   - Compare: `abs(9.98 - 10.00) / 10.00 * 100 = 0.2%` (within tolerance)
3. If conversion fails (no exchange rate available) → match status `FAILED_CURRENCY`
4. Invoice stored in original currency (USD), exchange rate recorded
5. Payment processed in invoice currency (USD) or converted based on workspace settings

**Implementation (Wave 29):**
- `ExchangeRate` table with daily rates
- 3-way match converts to SPO currency for comparison
- `SupplierInvoice.exchange_rate` field records rate used
- Multi-currency support (advanced)

---

### F2: VAT Mismatch Between PO Tax Rate and Invoice Tax Rate
**Scenario:** SPO created with 5% VAT (standard rate). Supplier invoice shows 0% VAT (claims exempt).

**Expected Behavior:**
1. 3-way match tax check:
   - Expected tax: `(10.00 * 100 * 0.05) = AED 50.00`
   - Actual tax: `AED 0.00`
   - Variance: `abs(0.00 - 50.00) = AED 50.00` (significant)
2. Match status → `FAILED_TAX`
3. Invoice blocked from approval
4. Accounts payable reviews:
   - If supplier is VAT-exempt (valid exemption certificate) → override with reason
   - If error → reject invoice, request corrected version

**Implementation:**
- Tax variance tolerance: absolute difference > AED 0.01 (1 fils)
- Override requires exemption documentation upload
- Audit log records override with reason

---

### F3: Rounding Differences in Decimal Calculations
**Scenario:** Invoice line: 3 units @ AED 10.333 each + 5% VAT.
- Frontend calculates: `3 * 10.333 * 1.05 = 32.5489 → AED 32.55` (rounded)
- Backend calculates: `(3 * 10.333).quantize(0.01) * 1.05 = 30.99 * 1.05 = 32.5395 → AED 32.54` (different rounding)

**Expected Behavior:**
1. System enforces consistent rounding strategy: **round at final total, not intermediate steps**
2. Calculation sequence:
   ```python
   subtotal = (quantity * unit_price).quantize(Decimal('0.01'))
   tax_amount = (subtotal * tax_rate / 100).quantize(Decimal('0.01'))
   total = subtotal + tax_amount
   ```
3. Rounding differences ≤ AED 0.01 per line tolerated
4. If total variance across all lines > AED 0.10 → validation fails

**Implementation:**
- Consistent rounding: `Decimal.quantize('0.01', rounding=ROUND_HALF_UP)`
- Schema validation includes total check: `sum(line_totals) = invoice_total`
- Frontend uses same rounding logic (JavaScript Decimal library)

---

### F4: Partial Payment Leaving AED 0.01 Remaining
**Scenario:** Invoice total AED 10,000.00. Customer pays AED 9,999.99 (bank transfer rounding).

**Expected Behavior:**
1. Payment recorded: `amount_paid = AED 9,999.99`
2. `balance_due = 10,000.00 - 9,999.99 = AED 0.01`
3. Invoice status remains `PARTIALLY_PAID` (not `PAID`)
4. System detects small remaining balance (< AED 0.10) → auto-flags for review:
   - Notification: "Invoice has trivial balance: AED 0.01"
   - Manager can approve write-off:
     ```python
     if balance_due < Decimal('0.10'):
         # Auto-write-off with approval
         invoice.balance_due = Decimal('0.00')
         invoice.status = InvoiceStatus.PAID
         audit_log("Trivial balance write-off: AED 0.01")
     ```
5. If workspace setting `auto_write_off_threshold = 0.10` enabled → auto-write-off

**Implementation:**
- `workspace.auto_write_off_threshold: Decimal(5,2)` (default 0.10)
- Service layer checks threshold on payment
- Audit log records write-offs
- Dashboard: "Trivial balance write-offs" report

---

**End of Edge Cases Specification**
