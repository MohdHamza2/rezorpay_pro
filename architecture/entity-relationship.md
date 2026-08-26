# Entity Relationship Diagram

**Project:** InvoiceSaaS (rezorpay_pro)
**Version:** 3.0
**Date:** August 2026
**Status:** Wave 0 — Architecture Lock

---

## Overview

This document presents the complete entity-relationship diagram for all 50+ entities across all 27 waves, showing relationships, cardinality, and multi-tenant scoping.

---

## Mermaid ER Diagram

```mermaid
erDiagram
    %% ============================================================
    %% WORKSPACE & AUTH DOMAIN
    %% ============================================================

    Workspace ||--o{ User : "has_users"
    Workspace {
        uuid id PK
        string name
        enum market_type "UAE_MAINLAND|UAE_FREEZONE|INDIA|SAUDI"
        decimal credit_warning_days
        decimal credit_hold_days
        bool block_po_on_hold
        bool block_do_on_hold
        decimal price_tolerance_percent
        bool allow_negative_stock
        uuid default_warehouse_id FK
    }

    User {
        uuid id PK
        uuid workspace_id FK
        string email UK
        string hashed_password
        string full_name
        enum role "ADMIN|MANAGER|SALES|PURCHASE|WAREHOUSE|ACCOUNTANT"
        bool is_active
        datetime last_login_at
    }

    %% ============================================================
    %% PRODUCT DOMAIN
    %% ============================================================

    Workspace ||--o{ ProductCategory : "owns"
    Workspace ||--o{ Brand : "owns"
    Workspace ||--o{ UnitOfMeasure : "owns"
    Workspace ||--o{ Product : "owns"

    ProductCategory ||--o{ ProductCategory : "parent_child"
    ProductCategory ||--o{ Product : "categorizes"
    Brand ||--o{ Product : "brands"
    UnitOfMeasure ||--o{ Product : "base_uom"
    UnitOfMeasure ||--o{ Product : "purchase_uom"
    UnitOfMeasure ||--o{ Product : "sales_uom"

    Product ||--o{ ProductIdentifier : "has_identifiers"
    Product ||--o{ ProductUOMConversion : "has_conversions"
    Product ||--o{ ProductPrice : "has_price_tiers"
    Product ||--o| Product : "replacement"

    ProductCategory {
        uuid id PK
        uuid workspace_id FK
        string name
        string code UK
        uuid parent_category_id FK
        int level
    }

    Brand {
        uuid id PK
        uuid workspace_id FK
        string name
        string manufacturer
        string country_of_origin
    }

    UnitOfMeasure {
        uuid id PK
        uuid workspace_id FK
        string code "PCS|MTR|KG|BOX|DRUM|etc"
        string name
        enum dimension "COUNT|LENGTH|WEIGHT|VOLUME"
        bool is_base
    }

    Product {
        uuid id PK
        uuid workspace_id FK
        string internal_sku UK
        string name
        text description
        uuid category_id FK
        uuid brand_id FK
        string hs_code
        bool is_active
        bool track_inventory
        decimal min_stock_level
        decimal reorder_level
        decimal max_stock_level
        decimal reorder_quantity
        uuid base_uom_id FK
        uuid purchase_uom_id FK
        uuid sales_uom_id FK
        decimal standard_sell_price
        decimal standard_cost_price
        enum vat_category "STANDARD|ZERO_RATED|EXEMPT"
        uuid replacement_product_id FK
        datetime deleted_at
    }

    ProductIdentifier {
        uuid id PK
        uuid product_id FK
        enum identifier_type "INTERNAL_SKU|MANUFACTURER_PART_NUMBER|SUPPLIER_CODE|BARCODE|etc"
        string identifier_value
        string source
        bool is_primary
        bool active
        date start_date
        date end_date
    }

    ProductUOMConversion {
        uuid id PK
        uuid product_id FK
        uuid from_uom_id FK
        uuid to_uom_id FK
        decimal conversion_factor
    }

    ProductPrice {
        uuid id PK
        uuid product_id FK
        uuid client_id FK
        decimal unit_price
        uuid uom_id FK
        date valid_from
        date valid_until
    }

    %% ============================================================
    %% SUPPLIER DOMAIN
    %% ============================================================

    Workspace ||--o{ Supplier : "owns"
    Supplier ||--o{ SupplierContact : "has_contacts"
    Supplier ||--o{ SupplierBankAccount : "has_bank_accounts"
    Supplier ||--o{ SupplierDocument : "has_documents"
    Supplier ||--o{ SupplierProduct : "supplies_products"
    Product ||--o{ SupplierProduct : "supplied_by"
    UnitOfMeasure ||--o{ SupplierProduct : "supplier_uom"

    Supplier {
        uuid id PK
        uuid workspace_id FK
        string name
        string code UK
        string tax_registration_number
        string contact_person
        string email
        string phone
        text address
        string country
        string payment_terms "NET_30|NET_60|etc"
        string currency "AED|USD|EUR|INR|SAR"
        decimal credit_limit
        int lead_time_days
        enum status "ACTIVE|SUSPENDED|BLOCKED"
        decimal rating
        datetime deleted_at
    }

    SupplierContact {
        uuid id PK
        uuid supplier_id FK
        string name
        string designation
        string email
        string phone
        string mobile
        bool is_primary
    }

    SupplierBankAccount {
        uuid id PK
        uuid supplier_id FK
        string bank_name
        string account_number
        string iban
        string swift_code
        string branch
        string currency
        bool is_primary
    }

    SupplierDocument {
        uuid id PK
        uuid supplier_id FK
        enum document_type "TRADE_LICENSE|VAT_CERTIFICATE|ISO_CERT|CATALOG|CONTRACT"
        string file_path
        date expiry_date
        datetime uploaded_at
    }

    SupplierProduct {
        uuid id PK
        uuid supplier_id FK
        uuid product_id FK
        string supplier_sku
        decimal unit_price
        uuid uom_id FK
        int lead_time_days
        decimal min_order_quantity
        bool is_preferred
    }

    %% ============================================================
    %% CUSTOMER DOMAIN
    %% ============================================================

    Workspace ||--o{ Client : "owns"

    Client {
        uuid id PK
        uuid workspace_id FK
        string name
        string code UK
        string email
        string phone
        string tax_id
        text billing_address
        text shipping_address
        string country
        string payment_terms "NET_30|COD|ADVANCE|etc"
        decimal credit_limit
        enum credit_status "ACTIVE|WARNING|HOLD|SUSPENDED"
        datetime credit_status_changed_at
        uuid credit_status_changed_by FK
        string credit_status_reason
        datetime deleted_at
    }

    %% ============================================================
    %% PROCUREMENT DOMAIN
    %% ============================================================

    Workspace ||--o{ ProcurementRequest : "owns"
    Workspace ||--o{ RFQ : "owns"
    Workspace ||--o{ SupplierRFQResponse : "owns"
    Workspace ||--o{ SupplierPurchaseOrder : "owns"
    Workspace ||--o{ GoodsReceiptNote : "owns"
    Workspace ||--o{ SupplierInvoice : "owns"

    Product ||--o{ ProcurementRequest : "requested"
    User ||--o{ ProcurementRequest : "requested_by"
    ProcurementRequest ||--o{ RFQ : "generates"

    RFQ ||--o{ RFQItem : "has_items"
    RFQ ||--o{ SupplierRFQResponse : "receives_responses"
    Product ||--o{ RFQItem : "item_product"

    Supplier ||--o{ SupplierRFQResponse : "responds"
    RFQ ||--o{ SupplierRFQResponse : "response_to"
    SupplierRFQResponse ||--o{ SupplierRFQResponseItem : "has_items"
    Product ||--o{ SupplierRFQResponseItem : "item_product"

    Supplier ||--o{ SupplierPurchaseOrder : "receives"
    RFQ ||--o{ SupplierPurchaseOrder : "converts_to"
    SupplierRFQResponse ||--o{ SupplierPurchaseOrder : "selected_response"
    SupplierPurchaseOrder ||--o{ SPOItem : "has_items"
    Product ||--o{ SPOItem : "item_product"

    SupplierPurchaseOrder ||--o{ GoodsReceiptNote : "receives_goods"
    Warehouse ||--o{ GoodsReceiptNote : "receives_at"
    GoodsReceiptNote ||--o{ GRNItem : "has_items"
    Product ||--o{ GRNItem : "item_product"

    SupplierPurchaseOrder ||--o{ SupplierInvoice : "invoiced"
    GoodsReceiptNote ||--o{ SupplierInvoice : "invoice_for"
    Supplier ||--o{ SupplierInvoice : "invoices"
    SupplierInvoice ||--o{ SupplierInvoiceItem : "has_items"
    Product ||--o{ SupplierInvoiceItem : "item_product"

    ProcurementRequest {
        uuid id PK
        uuid workspace_id FK
        string pr_number UK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        uuid requested_by FK
        text reason
        enum status "DRAFT|PENDING_APPROVAL|APPROVED|REJECTED|CONVERTED"
        date required_by
        datetime deleted_at
    }

    RFQ {
        uuid id PK
        uuid workspace_id FK
        string rfq_number UK
        uuid pr_id FK
        date valid_until
        enum status "DRAFT|SENT|EXPIRED|COMPLETED"
        text notes
        datetime deleted_at
    }

    RFQItem {
        uuid id PK
        uuid rfq_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        text specifications
    }

    SupplierRFQResponse {
        uuid id PK
        uuid workspace_id FK
        uuid rfq_id FK
        uuid supplier_id FK
        date response_date
        enum status "PENDING|SUBMITTED|ACCEPTED|REJECTED|EXPIRED"
        int lead_time_days
        string payment_terms
        text notes
    }

    SupplierRFQResponseItem {
        uuid id PK
        uuid response_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        text notes
    }

    SupplierPurchaseOrder {
        uuid id PK
        uuid workspace_id FK
        string spo_number UK
        uuid supplier_id FK
        uuid rfq_id FK
        uuid supplier_rfq_response_id FK
        date order_date
        date expected_delivery_date
        enum status "DRAFT|PENDING_APPROVAL|APPROVED|SENT|ACKNOWLEDGED|PARTIALLY_RECEIVED|FULLY_RECEIVED|CLOSED|CANCELLED"
        string payment_terms
        string delivery_terms
        decimal subtotal
        decimal tax_amount
        decimal total_amount
        text notes
        datetime sent_at
        datetime acknowledged_at
        datetime deleted_at
    }

    SPOItem {
        uuid id PK
        uuid spo_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        decimal line_total
        decimal received_quantity
        decimal invoiced_quantity
        bool fully_received
    }

    GoodsReceiptNote {
        uuid id PK
        uuid workspace_id FK
        string grn_number UK
        uuid spo_id FK
        uuid warehouse_id FK
        date received_date
        enum status "DRAFT|RECEIVING|PENDING_INSPECTION|ACCEPTED|PARTIALLY_ACCEPTED|REJECTED"
        uuid received_by FK
        uuid inspected_by FK
        text notes
        datetime deleted_at
    }

    GRNItem {
        uuid id PK
        uuid grn_id FK
        uuid product_id FK
        decimal quantity_ordered
        decimal quantity_received
        decimal quantity_accepted
        decimal quantity_rejected
        decimal quantity_damaged
        uuid uom_id FK
        text rejection_reason
        bool over_receipt_flag
    }

    SupplierInvoice {
        uuid id PK
        uuid workspace_id FK
        string invoice_number UK
        uuid supplier_id FK
        uuid spo_id FK
        uuid grn_id FK
        date invoice_date
        date due_date
        decimal subtotal
        decimal tax_amount
        decimal total_amount
        decimal amount_paid
        decimal balance_due
        enum three_way_match_status "PENDING|PASSED|FAILED_QTY|FAILED_PRICE|FAILED_TAX|FAILED_DUPLICATE|UNRECEIVED_ITEMS"
        uuid match_override_by FK
        datetime match_override_at
        text match_override_reason
        enum approval_status "PENDING|APPROVED|REJECTED"
        datetime approved_at
        datetime deleted_at
    }

    SupplierInvoiceItem {
        uuid id PK
        uuid supplier_invoice_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        decimal tax_amount
        decimal line_total
    }

    %% ============================================================
    %% INVENTORY DOMAIN
    %% ============================================================

    Workspace ||--o{ Warehouse : "owns"
    Workspace ||--o{ StockTransaction : "tracks"
    Workspace ||--o{ StockReservation : "tracks"
    Workspace ||--o{ StockTransfer : "tracks"
    Workspace ||--o{ StockAdjustment : "tracks"
    Workspace ||--o{ StockCount : "tracks"

    Warehouse ||--o{ WarehouseStock : "stores"
    Product ||--o{ WarehouseStock : "stored_in"

    Warehouse ||--o{ StockTransaction : "transactions_at"
    Product ||--o{ StockTransaction : "transaction_for"

    Warehouse ||--o{ StockReservation : "reserves_from"
    Product ||--o{ StockReservation : "reserves_product"

    Warehouse ||--o{ StockTransfer : "source"
    Warehouse ||--o{ StockTransfer : "destination"
    Product ||--o{ StockTransfer : "transfers_product"

    Warehouse ||--o{ StockAdjustment : "adjusts_at"
    Product ||--o{ StockAdjustment : "adjusts_product"

    Warehouse ||--o{ StockCount : "counts_at"
    StockCount ||--o{ StockCountItem : "has_items"
    Product ||--o{ StockCountItem : "counted_product"

    Warehouse {
        uuid id PK
        uuid workspace_id FK
        string name
        string code UK
        text address
        string city
        string country
        bool is_active
        datetime deleted_at
    }

    WarehouseStock {
        uuid id PK
        uuid workspace_id FK
        uuid warehouse_id FK
        uuid product_id FK
        decimal quantity_on_hand
        decimal quantity_reserved
        decimal quantity_available "computed"
        decimal quantity_damaged
        decimal quantity_in_transit
        decimal reorder_level
        decimal reorder_quantity
        decimal average_unit_cost
        datetime last_restocked_at
    }

    StockTransaction {
        uuid id PK
        uuid workspace_id FK
        uuid warehouse_id FK
        uuid product_id FK
        enum transaction_type "GRN_RECEIPT|DELIVERY_DISPATCH|TRANSFER_OUT|TRANSFER_IN|ADJUSTMENT_IN|ADJUSTMENT_OUT|RETURN_IN|RETURN_OUT|DAMAGE_WRITE_OFF"
        decimal quantity_change
        decimal quantity_after
        uuid uom_id FK
        decimal unit_cost
        uuid grn_id FK
        uuid delivery_order_id FK
        uuid stock_transfer_id FK
        uuid stock_adjustment_id FK
        uuid sales_return_id FK
        uuid purchase_return_id FK
        text notes
        datetime transaction_date
    }

    StockReservation {
        uuid id PK
        uuid workspace_id FK
        uuid warehouse_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        uuid cpo_id FK
        enum status "ACTIVE|DISPATCHED|CANCELLED|EXPIRED"
        datetime dispatched_at
        datetime cancelled_at
        text cancellation_reason
        datetime created_at
    }

    StockTransfer {
        uuid id PK
        uuid workspace_id FK
        string transfer_number UK
        uuid source_warehouse_id FK
        uuid destination_warehouse_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        enum status "DRAFT|APPROVED|IN_TRANSIT|RECEIVED|CANCELLED"
        date expected_arrival_date
        datetime dispatched_at
        datetime received_at
        decimal received_quantity
        uuid requested_by FK
        uuid approved_by FK
        text notes
        datetime deleted_at
    }

    StockAdjustment {
        uuid id PK
        uuid workspace_id FK
        string adjustment_number UK
        uuid warehouse_id FK
        uuid product_id FK
        decimal quantity_change
        uuid uom_id FK
        enum adjustment_type "DAMAGE_WRITE_OFF|STOCK_COUNT|DATA_CORRECTION|TRANSFER_DISCREPANCY|QUALITY_REJECTION"
        text reason
        enum status "DRAFT|APPROVED|REJECTED"
        uuid created_by FK
        uuid approved_by FK
        datetime approved_at
        datetime deleted_at
    }

    StockCount {
        uuid id PK
        uuid workspace_id FK
        string count_number UK
        uuid warehouse_id FK
        enum count_type "FULL|PARTIAL|CYCLE"
        date scheduled_date
        enum status "SCHEDULED|IN_PROGRESS|COMPLETED|RECONCILED"
        uuid created_by FK
        datetime deleted_at
    }

    StockCountItem {
        uuid id PK
        uuid stock_count_id FK
        uuid product_id FK
        decimal expected_quantity
        decimal counted_quantity
        decimal variance
        uuid uom_id FK
        text notes
        bool requires_approval
        bool auto_approved
    }

    %% ============================================================
    %% CUSTOMER SALES DOMAIN
    %% ============================================================

    Workspace ||--o{ Enquiry : "owns"
    Workspace ||--o{ Quotation : "owns"
    Workspace ||--o{ CustomerPurchaseOrder : "owns"
    Workspace ||--o{ Invoice : "owns"
    Workspace ||--o{ DeliveryOrder : "owns"
    Workspace ||--o{ Payment : "tracks"

    Client ||--o{ Enquiry : "enquires"
    Enquiry ||--o{ EnquiryItem : "has_items"
    Product ||--o{ EnquiryItem : "enquiry_product"

    Client ||--o{ Quotation : "quotes_to"
    Enquiry ||--o{ Quotation : "converts_to"
    Quotation ||--o{ QuotationItem : "has_items"
    Product ||--o{ QuotationItem : "quoted_product"

    Client ||--o{ CustomerPurchaseOrder : "places_order"
    Quotation ||--o{ CustomerPurchaseOrder : "converts_to"
    CustomerPurchaseOrder ||--o{ CPOItem : "has_items"
    Product ||--o{ CPOItem : "ordered_product"

    Client ||--o{ Invoice : "invoiced_to"
    CustomerPurchaseOrder ||--o{ Invoice : "invoiced"
    Quotation ||--o{ Invoice : "direct_invoice"
    Invoice ||--o{ InvoiceItem : "has_items"
    Product ||--o{ InvoiceItem : "invoiced_product"

    Client ||--o{ DeliveryOrder : "delivers_to"
    CustomerPurchaseOrder ||--o{ DeliveryOrder : "fulfills"
    Warehouse ||--o{ DeliveryOrder : "dispatches_from"
    DeliveryOrder ||--o{ DOItem : "has_items"
    Product ||--o{ DOItem : "delivered_product"

    Client ||--o{ Payment : "pays"
    Invoice ||--o{ Payment : "payment_for"

    Enquiry {
        uuid id PK
        uuid workspace_id FK
        string enquiry_number UK
        uuid client_id FK
        date enquiry_date
        enum status "NEW|IN_PROGRESS|QUOTED|CONVERTED|LOST"
        enum source "PHONE|EMAIL|WEBSITE|WHATSAPP|WALK_IN"
        text notes
        datetime deleted_at
    }

    EnquiryItem {
        uuid id PK
        uuid enquiry_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        text specifications
    }

    Quotation {
        uuid id PK
        uuid workspace_id FK
        string quotation_number UK
        uuid client_id FK
        uuid enquiry_id FK
        date quotation_date
        date valid_until
        enum status "DRAFT|SENT|ACCEPTED|REJECTED|EXPIRED|REVISED|CONVERTED"
        decimal subtotal
        decimal tax_amount
        decimal total_amount
        text terms_and_conditions
        text notes
        datetime deleted_at
    }

    QuotationItem {
        uuid id PK
        uuid quotation_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        decimal line_total
        text description
    }

    CustomerPurchaseOrder {
        uuid id PK
        uuid workspace_id FK
        string cpo_number UK
        uuid client_id FK
        uuid quotation_id FK
        string customer_po_number
        date order_date
        date expected_delivery_date
        enum status "RECEIVED|CONFIRMED|PARTIALLY_INVOICED|FULLY_INVOICED|PARTIALLY_DELIVERED|FULLY_DELIVERED|CLOSED|CANCELLED"
        decimal subtotal
        decimal tax_amount
        decimal total_amount
        text delivery_address
        text notes
        datetime deleted_at
    }

    CPOItem {
        uuid id PK
        uuid cpo_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        decimal line_total
        decimal invoiced_quantity
        decimal delivered_quantity
    }

    Invoice {
        uuid id PK
        uuid workspace_id FK
        string invoice_number UK
        uuid client_id FK
        uuid cpo_id FK
        uuid quotation_id FK
        date invoice_date
        date due_date
        enum status "DRAFT|SENT|PARTIALLY_PAID|PAID|OVERDUE|CANCELLED"
        decimal subtotal
        decimal tax_amount
        decimal total_amount
        decimal amount_paid
        decimal balance_due
        text notes
        datetime sent_at
        datetime deleted_at
    }

    InvoiceItem {
        uuid id PK
        uuid invoice_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal tax_rate
        decimal line_total
        text description
    }

    DeliveryOrder {
        uuid id PK
        uuid workspace_id FK
        string do_number UK
        uuid client_id FK
        uuid cpo_id FK
        uuid warehouse_id FK
        date delivery_date
        enum status "DRAFT|CONFIRMED|PACKED|DISPATCHED|DELIVERED|CANCELLED"
        text delivery_address
        text notes
        datetime dispatched_at
        datetime deleted_at
    }

    DOItem {
        uuid id PK
        uuid delivery_order_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
    }

    Payment {
        uuid id PK
        uuid workspace_id FK
        string payment_number UK
        uuid client_id FK
        uuid invoice_id FK
        date payment_date
        decimal amount
        enum payment_method "CASH|BANK_TRANSFER|CHEQUE|PDC|CREDIT_CARD|ONLINE"
        string reference_number
        enum pdc_status "PDC_PENDING|PRESENTED|CLEARED|BOUNCED"
        date pdc_clearing_date
        text notes
        datetime created_at
    }

    %% ============================================================
    %% RETURNS DOMAIN
    %% ============================================================

    Workspace ||--o{ SalesReturn : "owns"
    Workspace ||--o{ PurchaseReturn : "owns"
    Workspace ||--o{ CreditNote : "issues"
    Workspace ||--o{ DebitNote : "issues"

    Client ||--o{ SalesReturn : "returns_from"
    Invoice ||--o{ SalesReturn : "return_for"
    DeliveryOrder ||--o{ SalesReturn : "returned_delivery"
    SalesReturn ||--o{ SalesReturnItem : "has_items"
    Product ||--o{ SalesReturnItem : "returned_product"

    Supplier ||--o{ PurchaseReturn : "returns_to"
    GoodsReceiptNote ||--o{ PurchaseReturn : "return_for"
    PurchaseReturn ||--o{ PurchaseReturnItem : "has_items"
    Product ||--o{ PurchaseReturnItem : "returned_product"

    Client ||--o{ CreditNote : "issued_to"
    Invoice ||--o{ CreditNote : "credit_for"
    SalesReturn ||--o{ CreditNote : "generates"

    Supplier ||--o{ DebitNote : "issued_to"
    SupplierInvoice ||--o{ DebitNote : "debit_for"
    PurchaseReturn ||--o{ DebitNote : "generates"

    SalesReturn {
        uuid id PK
        uuid workspace_id FK
        string return_number UK
        uuid client_id FK
        uuid invoice_id FK
        uuid delivery_order_id FK
        date return_date
        enum status "DRAFT|PENDING_APPROVAL|APPROVED|RECEIVED|COMPLETED|REJECTED"
        decimal total_amount
        text reason
        datetime deleted_at
    }

    SalesReturnItem {
        uuid id PK
        uuid sales_return_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal line_total
        enum return_type "QUALITY_ISSUE|DAMAGE|WRONG_ITEM|EXCESS|CUSTOMER_REQUEST"
        text notes
    }

    PurchaseReturn {
        uuid id PK
        uuid workspace_id FK
        string return_number UK
        uuid supplier_id FK
        uuid grn_id FK
        date return_date
        enum status "DRAFT|PENDING_SUPPLIER|APPROVED|DISPATCHED|COMPLETED|REJECTED"
        decimal total_amount
        text reason
        datetime deleted_at
    }

    PurchaseReturnItem {
        uuid id PK
        uuid purchase_return_id FK
        uuid product_id FK
        decimal quantity
        uuid uom_id FK
        decimal unit_price
        decimal line_total
        enum return_type "QUALITY_ISSUE|DAMAGE|WRONG_ITEM|EXCESS"
        text notes
    }

    CreditNote {
        uuid id PK
        uuid workspace_id FK
        string credit_note_number UK
        uuid client_id FK
        uuid invoice_id FK
        uuid sales_return_id FK
        date issue_date
        decimal amount
        enum status "DRAFT|ISSUED|APPLIED|VOID"
        text reason
        datetime deleted_at
    }

    DebitNote {
        uuid id PK
        uuid workspace_id FK
        string debit_note_number UK
        uuid supplier_id FK
        uuid supplier_invoice_id FK
        uuid purchase_return_id FK
        date issue_date
        decimal amount
        enum status "DRAFT|ISSUED|APPLIED|VOID"
        text reason
        datetime deleted_at
    }

    %% ============================================================
    %% COMMUNICATION DOMAIN
    %% ============================================================

    Workspace ||--o{ WhatsAppMessage : "sends"
    Workspace ||--o{ EmailLog : "sends"
    Workspace ||--o{ OcrJob : "processes"

    Client ||--o{ WhatsAppMessage : "customer_messages"
    Supplier ||--o{ WhatsAppMessage : "supplier_messages"

    Client ||--o{ EmailLog : "customer_emails"
    Supplier ||--o{ EmailLog : "supplier_emails"

    WhatsAppMessage {
        uuid id PK
        uuid workspace_id FK
        uuid client_id FK
        uuid supplier_id FK
        enum direction "INBOUND|OUTBOUND"
        string phone_number
        text message_body
        enum message_type "TEXT|IMAGE|PDF|LOCATION"
        string media_url
        enum status "SENT|DELIVERED|READ|FAILED"
        datetime sent_at
    }

    EmailLog {
        uuid id PK
        uuid workspace_id FK
        uuid client_id FK
        uuid supplier_id FK
        string from_email
        string to_email
        string subject
        text body_html
        json attachments
        enum status "QUEUED|SENT|DELIVERED|FAILED|BOUNCED"
        datetime sent_at
    }

    OcrJob {
        uuid id PK
        uuid workspace_id FK
        enum document_type "INVOICE|PO|QUOTATION|DELIVERY_NOTE"
        string file_path
        enum status "PENDING|PROCESSING|COMPLETED|FAILED"
        json extracted_data
        float confidence_score
        datetime processed_at
    }

    %% ============================================================
    %% DOCUMENT COUNTERS
    %% ============================================================

    Workspace ||--o{ EnquiryCounter : "owns"
    Workspace ||--o{ QuotationCounter : "owns"
    Workspace ||--o{ CPOCounter : "owns"
    Workspace ||--o{ InvoiceCounter : "owns"
    Workspace ||--o{ DOCounter : "owns"
    Workspace ||--o{ CreditNoteCounter : "owns"
    Workspace ||--o{ PRCounter : "owns"
    Workspace ||--o{ RFQCounter : "owns"
    Workspace ||--o{ SPOCounter : "owns"
    Workspace ||--o{ GRNCounter : "owns"
    Workspace ||--o{ StockTransferCounter : "owns"
    Workspace ||--o{ StockAdjustmentCounter : "owns"
    Workspace ||--o{ StockCountCounter : "owns"
    Workspace ||--o{ DebitNoteCounter : "owns"
    Workspace ||--o{ SalesReturnCounter : "owns"
    Workspace ||--o{ PurchaseReturnCounter : "owns"

    EnquiryCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    QuotationCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    CPOCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    InvoiceCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    DOCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    CreditNoteCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    PRCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    RFQCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    SPOCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    GRNCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    StockTransferCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    StockAdjustmentCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    StockCountCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    DebitNoteCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    SalesReturnCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }

    PurchaseReturnCounter {
        uuid id PK
        uuid workspace_id FK
        int year
        int current_value
    }
```

---

## Key Relationship Patterns

### Multi-Tenancy
**Every entity** (except UnitOfMeasure in some designs) includes `workspace_id` for data isolation:
- All queries filter by `workspace_id`
- Foreign keys validated within workspace boundary
- Cross-workspace access is a security violation

### Soft Deletes
Business entities use `deleted_at` timestamp instead of hard deletes:
- `deleted_at IS NULL` for active records
- `deleted_at IS NOT NULL` for soft-deleted records
- Maintains referential integrity and audit trail

### Gapless Numbering
Document counters ensure sequential numbering:
- One counter table per document type
- `SELECT FOR UPDATE` lock on counter row
- Format: `PREFIX-YYYY-XXXX` (e.g., `INV-2026-0045`)

### Immutable Audit Trails
Financial and stock records are immutable:
- `Payment` — no UPDATE/DELETE endpoints
- `StockTransaction` — no UPDATE/DELETE endpoints
- Corrections require offsetting entries

### State Machines
Documents follow defined state transitions:
- See [state-machines.md](state-machines.md) for all valid transitions
- Invalid transitions blocked at service layer
- State changes logged in audit trail

---

## Cardinality Notation

- `||--o{` : One-to-many (1:N)
- `||--||` : One-to-one (1:1)
- `}o--o{` : Many-to-many (N:M)
- `||--o|` : One-to-zero-or-one (1:0..1)

---

**End of Entity Relationship Diagram**
