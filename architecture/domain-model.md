# Domain Model Architecture
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification*

## 1. Platform Foundation Domain
- **Workspace**: Core tenant entity. Fields: market, currency, 	rn, at_rate, credit configuration booleans.
- **User**: System actors with RBAC roles.

## 2. Product & Catalog Domain
- **Category**: Hierarchical product grouping (supports parent_id).
- **Brand**: Manufacturer and origin details.
- **UnitOfMeasure**: Standard units (PCS, MTR, KG) with dimension tracking.
- **Product**: Core item master. internal_sku (UNIQUE), reorder levels, UOMs.
- **ProductIdentifier**: Alternate codes (Barcode, MPN, Supplier Code).
- **ProductUOMConversion**: Per-product conversion factors.
- **ProductPrice**: Customer-specific or volume-tiered pricing.

## 3. Supplier Domain
- **Supplier**: supplier_code (UNIQUE), payment terms, credit limit, rating, status.
- **SupplierContact**: Contact persons.
- **SupplierBankAccount**: Bank details for AP.
- **SupplierDocument**: Trade licenses, contracts.
- **SupplierProduct**: Product mapping, supplier SKU, lead time, MOQ.

## 4. Procurement Domain
- **ProcurementRequest** & **Item**: Internal demand signal.
- **RFQ** & **Item**: Request sent to multiple suppliers.
- **SupplierRFQResponse** & **QuoteItem**: Specific supplier's quote.
- **SupplierPurchaseOrder** & **Item**: SPO sent to supplier.
- **GoodsReceiptNote (GRN)** & **Item**: Tracks quantity_accepted, quantity_damaged.
- **SupplierInvoice** & **Item**: AP document. Triggers 3-Way Match.
- **SupplierPayment**: AP settlement.
- **PurchaseReturn** & **DebitNote**: Supplier returns.

## 5. Customer & Sales Domain
- **Client (Customer)**: CRM profile with credit_status (ACTIVE, WARNING, HOLD).
- **Enquiry**: Inbound lead.
- **Quotation**: Pre-sales doc.
- **CustomerPurchaseOrder (CPO)**: Customer's confirmed order.
- **Invoice**: Financial AR document.
- **DeliveryOrder (DO)**: Fulfillment document. Consumes Stock Reservations.
- **SalesReturn** & **CreditNote**: Returns and adjustments.
- **Payment**: AR settlement (PDC, Transfer, etc).

## 6. Inventory Domain
- **Warehouse**: Physical or logical storage.
- **WarehouseLocation**: Zone/Rack/Shelf/Bin.
- **WarehouseStock**: Cached status (on_hand, eserved, damaged, in_transit).
- **StockTransaction**: IMMUTABLE ledger of all movements.
- **StockReservation**: Hard allocation for CPO/DO.
- **StockTransfer**: Inter-warehouse movement.
- **StockAdjustment**: Manual corrections.
- **StockCount**: Physical auditing workflow.

## 7. Communication & AI Domain
- **WhatsAppMessage**: Inbound/Outbound Meta API tracking.
- **EmailLog**: Resend API tracking.
- **OcrJob**: Gemini Vision extraction tracking.
