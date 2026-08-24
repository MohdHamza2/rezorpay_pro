# Procurement Request Architecture
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification — Step 2 Detail*

## 1. Architectural Principle
**A Procurement Request (PR) is INTERNAL DEMAND.** It is the formal declaration that the company needs products. It is NOT a supplier quotation, a supplier PO, or an inventory transaction. This enforces strict separation of duties: demand generation vs. purchasing execution.

## 2. PR Sources & Destinations
The system supports three major procurement scenarios natively via combinations of Source and Destination.

**source_type Enum (C-01):**
- STOCK_REPLENISHMENT
- CUSTOMER_ORDER
- PROJECT
- MANUAL
- BACKORDER
- INTERNAL_REQUIREMENT

**destination_type Enum:**
- WAREHOUSE
- CUSTOMER
- PROJECT
- INTERNAL
- UNALLOCATED

## 3. Core Entities

### 3.1 ProcurementRequest (Header)
- **equest_number**: Gapless internal sequence (e.g., PR-2026-000001 - 6 digits locked per C-09). UNIQUE per workspace.
- **Source Links (C-03)**: customer_id, project_id, warehouse_id.
- **priority**: LOW, NORMAL, HIGH, URGENT.
- **procurement_method**: RFQ, DIRECT, CONTRACT, EMERGENCY.
- **equired_by_date**: When the *business* needs it (Different from Supplier PO delivery date).
- **status**: Derived from item states.

### 3.2 ProcurementRequestItem
Every item must carry a strict system product_id. NEVER rely on text descriptions alone.
- **product_id**: Reference to internal product master.
- **uom_id**: Strict UOM declaration. Must be convertible to the product's base UOM.
- **Traceability (C-03)**: customer_po_item_id (Mandatory for auto-reservation logic).
- **Quantity Tracking (Crucial Separation - C-02)**:
  - equested_quantity: What was asked for.
  - pproved_quantity: What the manager authorized.
  - ordered_quantity: What has been committed to a Supplier PO.
  - cancelled_quantity: Portion cancelled post-approval.
  - eceived_quantity: Tracked for fulfillment.
  - *Remaining Quantity* = pproved_quantity - ordered_quantity - cancelled_quantity.

## 4. PR State Machine & Lifecycle
**Valid States**: DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED, PARTIALLY_ORDERED, FULLY_ORDERED, FULFILLED, CANCELLED.

**Flow:**
DRAFT → SUBMITTED → UNDER_REVIEW (If approval required by workspace setting) → APPROVED.
APPROVED → PARTIALLY_ORDERED → FULLY_ORDERED → FULFILLED (When GRN completes receipt).

*Note: The Header Status is strictly derived from the states of its line items.*

## 5. Customer-Driven Allocation Logic (Option A - Locked In)
When a Customer PO exceeds available stock (e.g., CPO needs 1,000, Available is 300):
1. **Immediate Partial Reservation**: The system *instantly reserves* the 300 available units for the customer.
2. **Procure Shortage**: The system generates a PR for the 700 shortage.
3. **Fulfillment**: When the GRN for the 700 arrives, it leverages customer_po_item_id to immediately reserve it for that Customer PO.

## 6. Business Rules (PR Series)
- **Rule PR-001**: Every PR belongs to exactly one workspace.
- **Rule PR-002**: Every PR item references a product within the same workspace.
- **Rule PR-008**: pproved_quantity cannot exceed equested_quantity without explicit authorized amendment.
- **Rule PR-009**: ordered_quantity cannot exceed pproved_quantity unless an explicit over-ordering policy permits it.
- **Rule PR-011**: Header status MUST reflect item states.
- **Rule PR-016**: System must warn users if generating a PR for a product that already has open PRs/POs covering the shortage.
