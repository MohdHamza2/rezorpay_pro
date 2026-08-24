# RFQ & Supplier Quotation Architecture
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification — Step 3 Detail*

## 1. Architectural Principle
**An RFQ is PRICE & AVAILABILITY DISCOVERY. It is not a commitment.**
- **INV-3.1**: An RFQ, a Quote, and an Award never touch `WarehouseStock`, `StockTransaction`, or any ledger.
- **INV-3.2**: An Award never increments `ProcurementRequestItem.ordered_quantity`. Only SPO creation does.
- **INV-3.3**: Quotes are snapshots. Later changes to `SupplierProduct` or `Supplier` defaults must never mutate a received quote (Master/Transaction Snapshot Rule).

## 2. Core Entities

### 2.1 RFQ (Header)
- `rfq_number`: Gapless, e.g., `RFQ-2026-000001` (6 digits). UNIQUE per workspace.
- `rfq_type`: `STANDARD`, `URGENT`, `MARKET_DISCOVERY`, `ANNUAL_CONTRACT`.
- `award_mode`: `SINGLE`, `SPLIT` (default SPLIT).
- `sealed_until`: (Optional) Hides quotes from comparison endpoint until this datetime.
- `evaluation_criteria`: `LOWEST_PRICE`, `LOWEST_LANDED_COST` (Default), `WEIGHTED_SCORE`.
- `currency`: Reference currency for landed cost normalization.

### 2.2 RFQItem & RFQItemSource (Consolidation)
- **`RFQItem`**: `product_id` (Required unless `MARKET_DISCOVERY`), `awarded_quantity` (derived), `is_mandatory`.
- **`RFQItemSource`**: Enables N PRs → 1 RFQ, or 1 PR → N RFQs.
  - Links `rfq_item_id` to `procurement_request_item_id`.
  - Constraint: `quantity_from_source` ≤ PR item's remaining qty (`approved` - `ordered` - `cancelled`).

### 2.3 SupplierRFQResponse (The Quote Envelope)
- Contains FX snapshots: `quote_currency`, `exchange_rate`, `rate_date`, `rate_source`.
- `completeness`: `FULL`, `PARTIAL`, `INCOMPLETE`.
- `normalized_total`: Workspace currency (The only comparable number).
- UNIQUE constraint on (`rfq_id`, `supplier_id`, `revision_number`).

### 2.4 SupplierQuoteItem
- `is_alternate` & `alternate_approval_status`.
- `quantity_available`: Supplier's stated availability.
- `normalized_unit_price`: Derived via exchange rate and UOM conversion.

### 2.5 RFQAward & RFQAwardLine (The Decision)
- **`RFQAward`**: `award_number` (`AWD-2026-000001`), `total_awarded_value`, `status`, `justification`, `spo_generation_status`.
- **`RFQAwardLine`**: `awarded_quantity`, `is_lowest_price` (derived), `deviation_reason` (Mandatory if `is_lowest_price` = false).

## 3. Comparison & Normalization Engine
All quotes are mathematically normalized to workspace currency and product base UOM before ranking.
1. **Normalize Unit Price**: `P_norm = (quoted_price * (1 - discount%) * FX_rate) / supplier_uom_conversion`.
2. **Landed Cost Allocation**: Header charges (freight, customs) apportioned pro-rata by extended value.
3. **VAT Excluded**: VAT is recoverable in UAE, thus excluded from comparative ranking.
4. **Ranking Guardrails**: Missing FX rates or missing UOM conversions instantly flag the quote as non-comparable.

## 4. State Machines (RFQ Domain)

### RFQ Lifecycle
`DRAFT` → `SENT` → `PARTIALLY_RESPONDED` → `FULLY_RESPONDED` → `UNDER_EVALUATION` → `PARTIALLY_AWARDED` → `AWARDED`.
- Background job transitions to `EXPIRED` if deadline passes with 0 quotes.
- `SENT` is item-immutable. Changes require `POST /revise`.

### SupplierRFQResponse Lifecycle
`PENDING` → `RECEIVED` → `SHORTLISTED` → `SELECTED` / `PARTIALLY_SELECTED` / `NOT_SELECTED`.
- Terminal: `DECLINED`, `NO_RESPONSE`, `WITHDRAWN`, `SUPERSEDED` (if RFQ is revised).

### RFQAward Lifecycle
`DRAFT` → `PENDING_APPROVAL` → `APPROVED` → `CONVERTED` (SPOs generated).

## 5. RFQ Business Rules (RFQ-001 to RFQ-036)
- **RFQ-007**: A PR-traced RFQ item must have ≥1 RFQItemSource row, summing exactly to item quantity.
- **RFQ-012**: BLOCKED/BLACKLISTED suppliers cannot be invited.
- **RFQ-016**: Quotes are immutable once RECEIVED. Corrections create `revision_number + 1`.
- **RFQ-021**: Quote values are immutable snapshots.
- **RFQ-024**: Non-lowest-price award requires `deviation_reason` (min 10 chars).
- **RFQ-025**: Award value above threshold requires Maker-Checker approval.
- **RFQ-028**: SPO generation from an award is idempotent (48h TTL).
- **RFQ-035**: Internal notes, target prices, and competitor quotes MUST NEVER appear on supplier-facing PDFs/APIs.

## 6. Implementation Workflow (Steps 3A - 3N)
Follows exact sequence from Schema Design (3A), Alembic (3B) through Comparison Engine (3I), Award Maker-Checker (3J) and E2E Tests (3N).

## 7. Decisions Locked In (User Approved)
- **Split Awards**: Allowed (Default `SPLIT`).
- **Award Entity**: Fully persisted entity (not just a flag).
- **Evaluation Criteria**: `LOWEST_LANDED_COST` is default.
- **VAT**: Excluded from comparison matrix.
- **Handoff**: `/rfq-awards/{id}/generate-spos` handles the bridge to Step 4.
