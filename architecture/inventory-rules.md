# Inventory Rules
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification*

## 1. Core Principles
- **Rule 1.1**: NEVER manipulate stock directly. Frontend cannot PUT a stock quantity.
- **Rule 1.2**: StockTransaction is an IMMUTABLE ledger. All changes flow through business events.
- **Rule 1.3 (Locked per C-04)**: Available Stock = on_hand - reserved - damaged.
  - in_transit is EXCLUDED from this formula at the source because the Transfer rule already removes it from on_hand. It acts only as a destination-side informational bucket.

## 2. Receiving & Allocation
- **Rule 2.1**: Inventory increases by quantity_accepted from GRN, NOT quantity_received.
- **Rule 2.2**: No negative stock unless workspace.allow_negative_stock = true.

## 3. Movement & Concurrency
- **Rule 3.1**: Transfers use IN_TRANSIT state.
- **Rule 3.2**: Concurrent reservation protection via row-level SELECT FOR UPDATE locks on WarehouseStock.

## 4. Customer-Driven Procurement Allocation (Option A)
- **Rule 4.1 (Immediate Partial Reservation)**: When a Customer PO requests more quantity than is available, the system MUST immediately reserve the existing available stock.
- **Rule 4.2**: StockReservation updates (Locked per C-05):
  - delivery_order_id is now NULLABLE (because Option A reserves at CPO confirmation before DO exists).
  - Added eservation_source: CPO / INVOICE / DO / PR_INBOUND.
  - Added procurement_request_item_id (Nullable) to link inbound stock.
- **Rule 4.3**: When the GRN for the shortage arrives, it is instantly reserved for the target CPO.
