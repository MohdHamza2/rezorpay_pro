# Graph Report - rezorpay_pro  (2026-09-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 5357 nodes · 19367 edges · 197 communities (138 shown, 11 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 2112 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7b962f6c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.tsx
- utc_today
- CreditNotePDF.tsx
- timedelta
- helpers.ts
- CreditNote
- test_email_comms.py
- ProductService
- lpos.ts
- test_invoices.py
- quotation_service.py
- models/__init__.py
- deliveryNoteHelpers.ts
- tax_debit_note_service.py
- raise_error
- InvoiceService
- test_rfq_awards.py
- Invoice
- HTTPException
- Workspace
- customer_po_support.py
- CustomerPurchaseOrderService
- client.ts
- Invoices.tsx
- _get
- routers/quotations.py
- routers/clients.py
- GRNService
- stock_transfer_service.py
- stock_count_service.py
- test_delivery_notes.py
- test_quotations.py
- routers/delivery_notes.py
- Payment
- SupplierInvoice
- product_service.py
- PaymentStatus
- ArStatement.tsx
- DocumentRenderer
- WhatsAppService
- whatsapp_service.py
- SuccessResponse
- test_customer_lpos.py
- test_products.py
- stock_reservation_service.py
- routers/products.py
- test_whatsapp_comms.py
- debitNoteHelpers.ts
- routers/procurement.py
- Products.tsx
- purchase_return_service.py
- test_credit_notes.py
- Reports.tsx
- enquiries.py
- Client
- PurchaseReturnService
- AwardService
- test_pricing.py
- money
- User
- test_spo_amendments.py
- test_vat_compliance.py
- test_tax_debit_notes.py
- award_service.py
- supplier_debit_note_service.py
- supplier_payment_service.py
- test_supplier_invoice_events.py
- test_supplier_payment_reversal.py
- test_supplier_pdc.py
- ProductDetailPanel.tsx
- get_current_user
- services/__init__.py
- test_stock_counts.py
- inventory_ledger.py
- test_analytics.py
- test_stock_reservations.py
- ProductCatalogTabs.tsx
- supplier_statement_service.py
- quotationHelpers.ts
- test_stock_transfers.py
- test_supplier_products.py
- clients.ts
- spo.ts
- pricing_service.py
- routers/rfq.py
- vat_compliance_service.py
- _settings
- products.ts
- test_concurrent_numbering.py
- test_supplier_payments.py
- test_enquiries.py
- test_purchase_returns.py
- analytics_service.py
- test_landed_cost.py
- test_supplier_debit_notes.py
- SupplierPayment
- services/ar_aging.py
- send_email
- routers/supplier_debit_notes.py
- models/spo.py
- _register
- test_product_electrical_specs.py
- get_vat_compliance
- analytics.ts
- enquiries.ts
- compilerOptions
- package.json
- CreditBuckets
- test_ap_aging.py
- compilerOptions
- InvoiceCounter
- supplier_payment_reversal_service.py
- schemas/inventory.py
- DnCounter
- LpoCounter
- QuotationCounter
- SPOCounter
- CreditNoteCounter
- GRNCounter
- RFQAwardCounter
- tax_debit_note.py
- routers/analytics.py
- get_cashflow
- normalize_phone_to_e164
- dependencies
- EnquiryCounter
- PurchaseReturnCounter
- routers/supplier_invoices.py
- routers/workspaces.py
- devDependencies
- ar_aging_by_customer
- supplier_statements.py
- global_exception_handler
- test_bilingual_pdf_assets.py
- test_grn.py
- run_async_migrations
- SupplierPaymentCreate
- .oxlintrc.json
- scripts
- .total_price
- setup_database
- setup_database
- setup_database
- setup_database
- tsconfig.json
- readiness_check
- utils/__init__.py
- migrate.sh
- run-tests.sh

## God Nodes (most connected - your core abstractions)
1. `User` - 243 edges
2. `SuccessResponse` - 192 edges
3. `raise_error()` - 173 edges
4. `ErrorCode` - 157 edges
5. `Invoice` - 145 edges
6. `ProductService` - 108 edges
7. `_get()` - 89 edges
8. `money()` - 89 edges
9. `SupplierInvoice` - 88 edges
10. `Client` - 80 edges

## Surprising Connections (you probably didn't know these)
- `copy_quote_item()` --uses--> `QuotationItem`  [INFERRED]
  backend/app/services/customer_po_support.py → backend/app/models/quotation_item.py
- `_load_and_expire()` --uses--> `Quotation`  [INFERRED]
  backend/app/routers/quotations.py → backend/app/models/quotation.py
- `_load_or_404()` --uses--> `Quotation`  [INFERRED]
  backend/app/routers/quotations.py → backend/app/models/quotation.py
- `_wrapped()` --uses--> `Quotation`  [INFERRED]
  backend/app/routers/quotations.py → backend/app/models/quotation.py
- `CustomerPurchaseOrderService` --uses--> `Quotation`  [INFERRED]
  backend/app/services/customer_po_service.py → backend/app/models/quotation.py

## Import Cycles
- None detected.

## Communities (197 total, 11 thin omitted)

### Community 0 - "App.tsx"
Cohesion: 0.05
Nodes (103): getClients(), createCreditNote(), createCreditNoteBody(), CreditNote, CreditNoteCreatePayload, CreditNoteItemWrite, CreditNoteListItem, CreditNoteListQuery (+95 more)

### Community 1 - "utc_today"
Cohesion: 0.06
Nodes (110): utc_today(), _by_type(), _cn_payload(), _create_client(), _create_cn(), _create_invoice(), _dec(), _headers() (+102 more)

### Community 2 - "CreditNotePDF.tsx"
Cohesion: 0.05
Nodes (88): Client, StatementDocType, CreditNoteItem, TaxDebitNoteItem, DeliveryNoteItem, InvoiceItem, InvoiceStatus, QuotationItem (+80 more)

### Community 3 - "timedelta"
Cohesion: 0.06
Nodes (95): create_client(), fixture, Wave 29 AR — aging report tests. Covers: bucket placement, totals/outstanding…, register_and_token(), seed_invoice(), insert(), seed_payment(), insert() (+87 more)

### Community 4 - "helpers.ts"
Cohesion: 0.08
Nodes (53): applyStatementRange(), createElectricalProduct(), isGoogleFontUrl(), watchGoogleFontRequests(), API_URL, applyCreditSettings(), authJson(), createAdhocInvoiceViaUi() (+45 more)

### Community 5 - "CreditNote"
Cohesion: 0.07
Nodes (65): CreditNote, CreditNoteReason, CreditNoteStatus, CreditNoteEvent, CreditNoteEventType, Enum, SQLModel, str (+57 more)

### Community 6 - "test_email_comms.py"
Cohesion: 0.06
Nodes (48): EmailIdempotencyKey, EmailLog, EmailStatus, _now(), datetime, Enum, SQLModel, str (+40 more)

### Community 7 - "ProductService"
Cohesion: 0.10
Nodes (28): Brand, Category, Product, ProductIdentifier, ProductUOMConversion, SQLModel, UnitOfMeasure, _bad_request() (+20 more)

### Community 8 - "lpos.ts"
Cohesion: 0.05
Nodes (72): CreditNoteListResult, TaxDebitNoteListResult, DeliveryNoteListResult, cancelLpo(), createLpo(), createLpoInvoice(), CustomerPurchaseOrder, deleteLpo() (+64 more)

### Community 9 - "test_invoices.py"
Cohesion: 0.07
Nodes (57): fixture, setup_database(), fixture, setup_database(), fixture, setup_database(), fixture, Create all tables before tests run, drop them after. (+49 more)

### Community 10 - "quotation_service.py"
Cohesion: 0.09
Nodes (56): Enum, SQLModel, str, QuotationEvent, QuotationEventType, SQLModel, QuotationItem, Enum (+48 more)

### Community 11 - "models/__init__.py"
Cohesion: 0.06
Nodes (36): Run migrations in 'offline' mode., run_migrations_offline(), get_current_workspace_id(), UUID, get_settings(), model_validator, Settings, get_session() (+28 more)

### Community 12 - "deliveryNoteHelpers.ts"
Cohesion: 0.06
Nodes (64): cancelDeliveryNote(), confirmDeliveryNote(), createDeliveryNote(), createDeliveryNoteBody(), deleteDeliveryNote(), DeliveryNote, DeliveryNoteCreatePayload, DeliveryNoteItemWrite (+56 more)

### Community 13 - "tax_debit_note_service.py"
Cohesion: 0.08
Nodes (59): InvoiceItem, SQLModel, Enum, str, TaxDebitNote, TaxDebitNoteItem, TaxDebitNoteReason, TaxDebitNoteStatus (+51 more)

### Community 14 - "raise_error"
Cohesion: 0.10
Nodes (51): DeliveryNote, DeliveryNoteEvent, DeliveryNoteEventType, Enum, SQLModel, str, DeliveryNoteItem, SQLModel (+43 more)

### Community 15 - "InvoiceService"
Cohesion: 0.06
Nodes (58): InvoiceStatus, Enum, str, create_invoice(), delete_invoice(), get_invoice(), list_invoices(), AsyncSession (+50 more)

### Community 16 - "test_rfq_awards.py"
Cohesion: 0.09
Nodes (53): SQLModel, Supplier, SupplierBankAccount, SupplierContact, SupplierDocument, SupplierProduct, create_supplier(), create_supplier_product() (+45 more)

### Community 17 - "Invoice"
Cohesion: 0.08
Nodes (52): Invoice, Decimal, _balance_payload(), Cash and credits are separate; due is max(0, total − paid − credited)., should_mark_overdue(), _add_items(), _apply_header_patch(), _apply_send_snapshots() (+44 more)

### Community 18 - "HTTPException"
Cohesion: 0.11
Nodes (41): SQLModel, SPOAmendment, SPOAmendmentLine, SPOStatusHistory, SupplierPurchaseOrder, SupplierPurchaseOrderItem, acknowledge_spo(), apply_amendment() (+33 more)

### Community 19 - "Workspace"
Cohesion: 0.07
Nodes (53): SQLModel, SQLModel, SQLModel, Workspace, Enum, str, StatementDocType, activity_sort_key() (+45 more)

### Community 20 - "customer_po_support.py"
Cohesion: 0.12
Nodes (45): CustomerPurchaseOrder, CustomerPurchaseOrderEvent, CustomerPurchaseOrderEventType, Enum, SQLModel, str, CustomerPurchaseOrderItem, Decimal (+37 more)

### Community 21 - "CustomerPurchaseOrderService"
Cohesion: 0.08
Nodes (53): CustomerPurchaseOrderStatus, str, cancel_customer_purchase_order(), create_customer_purchase_order(), delete_customer_purchase_order(), get_customer_purchase_order(), invoice_customer_purchase_order(), list_customer_purchase_orders() (+45 more)

### Community 22 - "client.ts"
Cohesion: 0.06
Nodes (45): apiClient, DashboardStats, getDashboardStats(), formatErrorToast(), skipInterceptorToast(), ProcurementRequest, ProcurementRequestItem, RFQ (+37 more)

### Community 23 - "Invoices.tsx"
Cohesion: 0.07
Nodes (56): createInvoice(), Invoice, InvoiceCreatePayload, InvoiceCurrency, InvoiceItemWrite, InvoiceKind, InvoiceListItem, InvoiceUpdatePayload (+48 more)

### Community 24 - "_get"
Cohesion: 0.09
Nodes (57): root(), health_check(), ap_aging_by_supplier(), ap_aging_detail(), ap_aging_summary(), bounce_supplier_pdc(), clear_supplier_pdc(), create_supplier_payment() (+49 more)

### Community 25 - "routers/quotations.py"
Cohesion: 0.08
Nodes (53): accept_quotation(), convert_quotation_to_invoice(), convert_quotation_to_lpo(), create_quotation(), delete_quotation(), get_quotation(), _load_and_expire(), _load_or_404() (+45 more)

### Community 26 - "routers/clients.py"
Cohesion: 0.08
Nodes (51): CreditStatus, Enum, create_client(), delete_client(), export_client_statement(), get_client(), get_client_ar_statement(), get_client_credit() (+43 more)

### Community 27 - "GRNService"
Cohesion: 0.13
Nodes (44): GoodsReceiptNote, GRNItem, GRNStatus, SQLModel, str, AllocationBasis, LandedCostAllocation, LandedCostStatus (+36 more)

### Community 28 - "stock_transfer_service.py"
Cohesion: 0.10
Nodes (44): Enum, SQLModel, str, Workspace-scoped stock transfer number counter (ST-YYYY-0001)., Warehouse → warehouse stock movement with an immutable ledger trail. Dispatch…, StockTransfer, StockTransferCounter, StockTransferItem (+36 more)

### Community 29 - "stock_count_service.py"
Cohesion: 0.11
Nodes (44): Enum, SQLModel, str, Workspace-scoped stock count number counter (SC-YYYY-0001)., Physical stock count vs system expected quantity. Expected quantities are…, StockCount, StockCountCounter, StockCountItem (+36 more)

### Community 30 - "test_delivery_notes.py"
Cohesion: 0.15
Nodes (46): _adhoc_item(), _adjust(), _cancel_dn(), _confirm(), _create_client(), _create_dn(), _create_invoice(), _create_lpo() (+38 more)

### Community 31 - "test_quotations.py"
Cohesion: 0.16
Nodes (46): _accept(), _adhoc_item(), _convert(), _convert_lpo(), _create_catalog_product(), _create_client(), _create_quote(), _create_uom() (+38 more)

### Community 32 - "routers/delivery_notes.py"
Cohesion: 0.09
Nodes (43): DeliveryNoteStatus, Enum, SQLModel, str, cancel_delivery_note(), confirm_delivery_note(), create_delivery_note(), delete_delivery_note() (+35 more)

### Community 33 - "Payment"
Cohesion: 0.12
Nodes (38): Payment, bounce_pdc(), clear_pdc(), create_payment(), deposit_pdc(), get_balance_due(), list_payments(), _pdc_response() (+30 more)

### Community 34 - "SupplierInvoice"
Cohesion: 0.10
Nodes (37): Enum, SQLModel, str, Lifecycle event types for supplier (AP) invoices. Mirrors the implemented…, Immutable audit row for one supplier-invoice lifecycle transition. Append-only…, SupplierInvoiceEvent, SupplierInvoiceEventType, MatchResult (+29 more)

### Community 35 - "product_service.py"
Cohesion: 0.08
Nodes (43): _list_voltage(), BrandCreate, BrandUpdate, CategoryCreate, CategoryUpdate, IdentifierType, normalize_voltage(), PriceType (+35 more)

### Community 36 - "PaymentStatus"
Cohesion: 0.09
Nodes (35): IdempotencyKey, SQLModel, PaymentMethod, PaymentStatus, PDCStatus, Enum, SQLModel, str (+27 more)

### Community 37 - "ArStatement.tsx"
Cohesion: 0.10
Nodes (39): ArStatement, ArStatementLine, ArStatementParty, CreditBuckets, getArStatement(), agingBucketAr(), statementTypeAr(), registerPdfFonts() (+31 more)

### Community 38 - "DocumentRenderer"
Cohesion: 0.09
Nodes (35): DocumentRenderer, _iso(), _money(), PDF DocumentRenderer — Wave 27 (Phase 5) WhatsApp PDF delivery. An internal,…, Render `data` to PDF bytes. Unsupported document -> 400., Existing 2-dp Decimal -> '1234.50' string. Never recomputes anything., Date/datetime -> ISO date string; passthrough for existing strings., One deterministic block of a rendered document. ``kind`` selects the page… (+27 more)

### Community 39 - "WhatsAppService"
Cohesion: 0.12
Nodes (17): WhatsAppMessage, _now(), AsyncSession, datetime, UUID, Workspace, Single canonical-phone match only. Zero/multiple matches → NULL (never guess,…, Reserve key + insert QUEUED row (Txn 1), dispatch, mark Txn 2. (+9 more)

### Community 40 - "whatsapp_service.py"
Cohesion: 0.10
Nodes (37): _now(), datetime, Enum, SQLModel, str, WhatsApp Business API models — Wave 27 (Phase 5). Tracks every message sent…, Workspace-scoped send idempotency (48h TTL) with a request fingerprint. PK…, WhatsAppDirection (+29 more)

### Community 41 - "SuccessResponse"
Cohesion: 0.14
Nodes (43): adjust_stock(), approve_stock_count(), approve_stock_transfer(), cancel_stock_count(), cancel_stock_reservation(), cancel_stock_transfer(), complete_stock_count(), create_stock_count() (+35 more)

### Community 42 - "test_customer_lpos.py"
Cohesion: 0.18
Nodes (40): _accept_quote(), _adhoc_item(), _cancel(), _create_client(), _create_lpo(), _create_quote(), _dec(), _get_lpo() (+32 more)

### Community 43 - "test_products.py"
Cohesion: 0.15
Nodes (40): _assert_pagination(), _create_client(), _create_product(), _create_uom(), _dec(), _headers(), Any, Decimal (+32 more)

### Community 44 - "stock_reservation_service.py"
Cohesion: 0.14
Nodes (40): Enum, SQLModel, str, Committed stock against a received Customer PO. Lines hold per-(product,…, One reserved (product, warehouse, bin) quantity under a reservation., ReservationStatus, StockReservation, StockReservationItem (+32 more)

### Community 45 - "routers/products.py"
Cohesion: 0.17
Nodes (42): create_brand(), create_category(), create_conversion(), create_identifier(), create_price(), create_product(), create_uom(), delete_brand() (+34 more)

### Community 46 - "test_whatsapp_comms.py"
Cohesion: 0.17
Nodes (38): create_supplier(), _headers(), _provider(), Wave 27 — WhatsApp comms + webhook tests (addendum §6). Covers:…, Records every provider call; returns synthetic ids. Swapped into…, register_and_token(), seed_client(), _seed() (+30 more)

### Community 47 - "debitNoteHelpers.ts"
Cohesion: 0.11
Nodes (39): createTaxDebitNote(), createTaxDebitNoteBody(), getDebitNotes(), getTaxDebitNote(), itemBody(), listParams(), optionalText(), TaxDebitNote (+31 more)

### Community 48 - "routers/procurement.py"
Cohesion: 0.11
Nodes (34): PRCounter, SQLModel, Workspace-scoped Purchase Request (PR) counter for gapless sequences. Mirrors…, Generate formatted PR number: PR-2026-000001, PRDestinationType, PRMethod, ProcurementRequest, ProcurementRequestItem (+26 more)

### Community 49 - "Products.tsx"
Cohesion: 0.10
Nodes (35): createProduct(), deleteProduct(), ProductWrite, updateProduct(), buildProductCreate(), buildProductUpdate(), lookupCode(), lookupName() (+27 more)

### Community 50 - "purchase_return_service.py"
Cohesion: 0.14
Nodes (36): PurchaseReturnStatus, str, Purchase Return Models — Wave 23 (Phase 4). A purchase return ships…, ReturnType, approve_purchase_return(), cancel_purchase_return(), complete_purchase_return(), create_purchase_return() (+28 more)

### Community 51 - "test_credit_notes.py"
Cohesion: 0.22
Nodes (35): _cn_payload(), _create_client(), _create_cn(), _create_invoice(), _dec(), _get_balance(), _get_invoice(), _headers() (+27 more)

### Community 52 - "Reports.tsx"
Cohesion: 0.10
Nodes (37): getRecentInvoices(), ApAgingBySupplier, ApAgingDetail, ApAgingDetailRow, ApAgingSummary, ApAgingSupplierRow, ArAgingByCustomer, ArAgingCustomerRow (+29 more)

### Community 53 - "enquiries.py"
Cohesion: 0.16
Nodes (30): Enquiry, EnquiryItem, SQLModel, SQLModel, convert_enquiry_to_quotation(), create_enquiry(), get_enquiries(), get_enquiry() (+22 more)

### Community 54 - "Client"
Cohesion: 0.15
Nodes (23): Client, CreditEventReason, CreditStatusEvent, SQLModel, str, assert_warning_not_after_hold(), CreditControlService, CreditSnapshot (+15 more)

### Community 55 - "PurchaseReturnService"
Cohesion: 0.19
Nodes (16): PurchaseReturn, PurchaseReturnItem, _now(), PurchaseReturnService, AsyncSession, Decimal, UUID, Returned qty for a grn_item across non-CANCELLED returns. (+8 more)

### Community 56 - "AwardService"
Cohesion: 0.17
Nodes (18): SQLModel, RFQ, RFQAward, RFQAwardLine, RFQItem, SupplierQuoteItem, SupplierRFQResponse, AwardService (+10 more)

### Community 57 - "test_pricing.py"
Cohesion: 0.16
Nodes (32): _add_price(), _create_client(), _create_product(), _dec(), _headers(), _invoice_price(), _omit(), _post_doc() (+24 more)

### Community 58 - "money"
Cohesion: 0.17
Nodes (33): CreditNoteItem, SQLModel, add_lines(), apply_totals(), assert_cn_remaining(), assert_frozen(), assert_header_remaining(), assert_qty_remaining() (+25 more)

### Community 59 - "User"
Cohesion: 0.15
Nodes (34): hash_password(), Enum, SQLModel, str, User, UserRole, member_token(), _insert() (+26 more)

### Community 60 - "test_spo_amendments.py"
Cohesion: 0.22
Nodes (28): _landed_cost_rows(), _line(), _propose(), fixture, Wave 31 Item 2.2 — SPO amendments persistence tests. Covers: propose…, Run a full GRN receive+disposition accepting `qty` units., _receive_via_grn(), _register() (+20 more)

### Community 61 - "test_vat_compliance.py"
Cohesion: 0.24
Nodes (32): create_supplier_invoice(), _dec(), ensure_catalog(), _first_invoice_id(), get_csv(), get_json(), _headers(), _invoice_uuid() (+24 more)

### Community 62 - "test_tax_debit_notes.py"
Cohesion: 0.18
Nodes (28): _create_client(), _create_invoice(), _create_tdn(), _dec(), _get_balance(), _get_invoice(), _headers(), _issue() (+20 more)

### Community 63 - "award_service.py"
Cohesion: 0.18
Nodes (29): AwardStatus, Enum, str, QuoteCompleteness, QuoteStatus, RFQAwardMode, RFQEvalCriteria, RFQItemSource (+21 more)

### Community 64 - "supplier_debit_note_service.py"
Cohesion: 0.15
Nodes (19): SQLModel, str, Supplier Debit Note Models — Wave 23 (Phase 4). A supplier debit note (SDN)…, Generate formatted supplier debit note number: SDN-2026-0001, Workspace-scoped gapless counter for supplier debit notes (SDN-YYYY-XXXX)., SupplierDebitNote, SupplierDebitNoteCounter, SupplierDebitNoteStatus (+11 more)

### Community 65 - "supplier_payment_service.py"
Cohesion: 0.14
Nodes (22): SQLModel, SupplierPaymentIdempotencyKey, ap_aging_buckets(), _bucket_of(), due_date_of(), _landed_cost_outstanding_by_supplier_invoice(), _payment_datetime(), _pdc_outstanding_by_supplier_invoice() (+14 more)

### Community 66 - "test_supplier_invoice_events.py"
Cohesion: 0.18
Nodes (27): audit_log(), create_chain(), create_supplier(), _dt(), event_rows(), post_payment(), fixture, Wave 31 Item 2.6 — supplier-invoice event/history tests. Covers:… (+19 more)

### Community 67 - "test_supplier_payment_reversal.py"
Cohesion: 0.18
Nodes (26): ap_balance(), create_supplier(), get_statement(), _headers(), pdc_action(), post_payment(), post_pdc(), fixture (+18 more)

### Community 68 - "test_supplier_pdc.py"
Cohesion: 0.25
Nodes (28): ap_balance(), create_supplier(), _headers(), pdc_action(), post_payment(), fixture, Wave 24 — PDC-to-supplier (AP post-dated cheque issued) lifecycle tests.…, register_and_token() (+20 more)

### Community 69 - "ProductDetailPanel.tsx"
Cohesion: 0.10
Nodes (31): createProductConversion(), createProductIdentifier(), createProductPrice(), deleteProductConversion(), deleteProductIdentifier(), deleteProductPrice(), getProduct(), IdentifierType (+23 more)

### Community 70 - "get_current_user"
Cohesion: 0.16
Nodes (27): get_current_active_user(), get_current_user(), get_current_workspace(), AsyncSession, HTTPAuthorizationCredentials, User, Workspace, get_me() (+19 more)

### Community 71 - "services/__init__.py"
Cohesion: 0.14
Nodes (21): InvoiceEvent, InvoiceEventType, Enum, SQLModel, str, Comprehensive audit event types for invoice lifecycle. Reserved for Future Use:…, AuditService, Any (+13 more)

### Community 72 - "test_stock_counts.py"
Cohesion: 0.25
Nodes (27): _adjust(), _count_ledger(), _create_count(), _dec(), _deplete_source(), _headers(), _level_for(), _product() (+19 more)

### Community 73 - "inventory_ledger.py"
Cohesion: 0.20
Nodes (28): InventoryLevel, InventoryTransaction, Enum, SQLModel, str, Rule 1.2: StockTransaction is an IMMUTABLE ledger. All changes flow through…, Real-time snapshot of inventory at the Bin level. Rule 1.3: Available Stock =…, TransactionType (+20 more)

### Community 74 - "test_analytics.py"
Cohesion: 0.21
Nodes (26): _dec(), _headers(), _line(), Decimal, fixture, Wave 30 — BI analytics report tests. Covers: revenue buckets (day/week/month +…, Non-AED supplier payments must not be summed into the AED cashflow., register_and_token() (+18 more)

### Community 75 - "test_stock_reservations.py"
Cohesion: 0.24
Nodes (26): _adjust(), _confirm_dn(), _create_client(), _create_dn(), _dec(), _headers(), _level(), _product() (+18 more)

### Community 76 - "ProductCatalogTabs.tsx"
Cohesion: 0.11
Nodes (29): Brand, Category, createBrand(), createCategory(), createUOM(), deleteBrand(), deleteCategory(), deleteUOM() (+21 more)

### Community 77 - "supplier_statement_service.py"
Cohesion: 0.20
Nodes (23): str, SupplierStatementDocType, activity_sort_key(), assemble_lines(), collect_activity(), debit_note_activity(), debit_note_activity_date(), in_period() (+15 more)

### Community 78 - "quotationHelpers.ts"
Cohesion: 0.14
Nodes (26): ConvertToLpoPayload, createQuotation(), getQuotations(), listParams(), Quotation, QuotationCreatePayload, QuotationCurrency, QuotationItemWrite (+18 more)

### Community 79 - "test_stock_transfers.py"
Cohesion: 0.28
Nodes (24): _adjust(), _create_transfer(), _dec(), _headers(), _ledger_txns(), _level_for(), _product(), Any (+16 more)

### Community 80 - "test_supplier_products.py"
Cohesion: 0.21
Nodes (22): _link(), _product(), fixture, Wave 31 Item 2.4 — SupplierProduct link CRUD tests. Covers: create happy path +…, _register(), _set_supplier_status(), setup_database(), _soft_delete() (+14 more)

### Community 81 - "clients.ts"
Cohesion: 0.14
Nodes (24): ArStatementAging, ArStatementQuery, ArStatementTotals, ClientCredit, ClientWritePayload, createClient(), CreditStatus, deleteClient() (+16 more)

### Community 82 - "spo.ts"
Cohesion: 0.14
Nodes (22): addGRNItem(), getGRNReconciliation(), GRN, GRNDispositionRequest, GRNItem, GRNItemCreate, recordDisposition(), stageForInspection() (+14 more)

### Community 83 - "pricing_service.py"
Cohesion: 0.23
Nodes (17): ProductPrice, One winning sales price for staff invoice/quote/LPO forms., ResolvedPriceResponse, _best_row(), _dec(), _min_qty(), _no_list_price(), PricingService (+9 more)

### Community 84 - "routers/rfq.py"
Cohesion: 0.17
Nodes (22): SQLModel, Workspace-scoped Request for Quotation (RFQ) counter for gapless sequences.…, Generate formatted RFQ number: RFQ-2026-000001, RFQCounter, approve_award(), compare_quotes(), create_rfq(), draft_award() (+14 more)

### Community 85 - "vat_compliance_service.py"
Cohesion: 0.19
Nodes (26): _bucket(), build_report(), business_date(), buyer_name(), buyer_trn(), csv_text(), _csv_text(), _fmt_cell() (+18 more)

### Community 86 - "_settings"
Cohesion: 0.13
Nodes (23): _all_enquiries(), _count(), _inbound_body(), post_webhook(), _rows(), _settings(), _sign(), test_concurrent_duplicate_webhook_lands_once() (+15 more)

### Community 87 - "products.ts"
Cohesion: 0.11
Nodes (26): assignIfPresent(), BrandWrite, CategoryWrite, ConversionWrite, fallbackPagination(), getBrand(), getCategory(), getList() (+18 more)

### Community 88 - "test_concurrent_numbering.py"
Cohesion: 0.11
Nodes (19): Concurrent document number collision tests (T12). Tests gapless numbering under…, Create 10 SPOs concurrently and verify all numbers are unique and sequential., Seed supplier, warehouse, uom and product for procurement tests., Create 10 PRs concurrently and verify all numbers are unique and sequential., Create 10 RFQs concurrently and verify all numbers are unique and sequential., Create 10 draft GRNs concurrently and verify all numbers are unique and…, Verify that invoice counters are year-scoped (counter resets each year)., Verify that failed invoice creation does not consume a number (no gap). (+11 more)

### Community 89 - "test_supplier_payments.py"
Cohesion: 0.23
Nodes (22): balance_of(), create_supplier(), post_payment(), fixture, Wave 22 AP — supplier payment recording tests. Covers: happy-path partial +…, register_and_token(), seed_invoice(), _dt() (+14 more)

### Community 90 - "test_enquiries.py"
Cohesion: 0.18
Nodes (21): EnquirySource, EnquiryStatus, Enum, str, _create_catalog_product(), _create_client(), _create_uom(), _dec() (+13 more)

### Community 91 - "test_purchase_returns.py"
Cohesion: 0.18
Nodes (20): build_purchase_chain(), create_return(), _on_hand(), _prn_ledger_rows(), Decimal, fixture, Wave 23 — purchase return lifecycle tests. Covers: create → submit → approve →…, SPO → ack → GRN → disposition, returns id map. (+12 more)

### Community 92 - "analytics_service.py"
Cohesion: 0.22
Nodes (23): _ap_payments(), _ar_receipts(), _bucket_windows(), cashflow(), _period_floor(), AsyncSession, date, Decimal (+15 more)

### Community 93 - "test_landed_cost.py"
Cohesion: 0.17
Nodes (19): _allocations(), _auth(), _base_entities(), _disposition(), _grn_with_item(), fixture, Wave 31 Item 2.1 — D-22 landed cost allocation tests. Locked architecture:…, Create + approve + send + acknowledge an SPO. Returns (spo_id, spo_item_ids). (+11 more)

### Community 94 - "test_supplier_debit_notes.py"
Cohesion: 0.21
Nodes (20): apply_note(), _balance_due(), create_note(), create_supplier(), _invoice_status(), Decimal, fixture, Wave 23 — supplier debit note tests. Covers: manual create→issue→apply… (+12 more)

### Community 95 - "SupplierPayment"
Cohesion: 0.28
Nodes (14): SupplierPayment, RECEIVED → DEPOSITED → CLEARED | BOUNCED; RECEIVED → RETURNED., _cleared_already(), _invalid_state(), _now(), AsyncSession, datetime, NoReturn (+6 more)

### Community 96 - "services/ar_aging.py"
Cohesion: 0.18
Nodes (22): ar_aging(), _client_names(), _end_of_as_of(), _open_ar_invoices(), _payment_date_at_or_before(), _pdc_outstanding_by_invoice(), AsyncSession, date (+14 more)

### Community 97 - "send_email"
Cohesion: 0.16
Nodes (21): email_webhook(), get_email(), list_emails(), AsyncSession, datetime, HTTPAuthorizationCredentials, limit, post (+13 more)

### Community 98 - "routers/supplier_debit_notes.py"
Cohesion: 0.23
Nodes (21): apply_supplier_debit_note(), cancel_supplier_debit_note(), create_supplier_debit_note(), get_supplier_debit_note(), issue_supplier_debit_note(), list_supplier_debit_notes(), AsyncSession, post (+13 more)

### Community 99 - "models/spo.py"
Cohesion: 0.23
Nodes (19): ProcurementMethod, Enum, str, SPOAmendmentField, SPOAmendmentStatus, SPODeliverySchedule, SPODeliveryScheduleStatus, SPOStatus (+11 more)

### Community 100 - "_register"
Cohesion: 0.10
Nodes (21): Workspace B must not read, update, void, or send Workspace A's invoice., Workspace B must not record payment against Workspace A's invoice., Workspace B must not read or update Workspace A's product., Workspace B must not read or update Workspace A's supplier., Workspace B must not read or update Workspace A's client., _register(), test_client_is_workspace_isolated(), test_invoice_is_workspace_isolated() (+13 more)

### Community 101 - "test_product_electrical_specs.py"
Cohesion: 0.30
Nodes (18): _create_product(), _create_uom(), _dec(), _headers(), _ids(), Any, Decimal, WP-A electrical catalogue spec columns (addendum §6). Sync TestClient against… (+10 more)

### Community 102 - "get_vat_compliance"
Cohesion: 0.14
Nodes (19): get_vat_compliance(), AsyncSession, date, limit, Request, Export the workspace UAE VAT compliance pack for [from, to]., BaseModel, Wave 28 — UAE VAT Compliance Pack export response schemas. Read-only report.… (+11 more)

### Community 103 - "analytics.ts"
Cohesion: 0.14
Nodes (19): AnalyticsInterval, CashflowReport, CashflowRow, getCashflow(), getRevenue(), getSalesByCustomer(), getSalesByProduct(), RevenueReport (+11 more)

### Community 104 - "enquiries.ts"
Cohesion: 0.15
Nodes (15): convertEnquiryToQuotation(), EnquiryCreate, EnquiryItem, EnquiryItemWrite, EnquiryListQuery, EnquiryListResponse, EnquiryRead, EnquirySource (+7 more)

### Community 105 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 106 - "package.json"
Cohesion: 0.12
Nodes (16): name, private, type, version, @hookform/resolvers, oxlint, pg, react-dom (+8 more)

### Community 107 - "CreditBuckets"
Cohesion: 0.24
Nodes (15): ApAgingBySupplierResponse, ApAgingDetailResponse, ApAgingDetailRow, ApAgingSummaryResponse, ApAgingSupplierRow, BaseModel, AP aging report schemas — Wave 22 (Phase 4). Wave 30 item 1.5 adds PDC…, ArAgingByCustomerResponse (+7 more)

### Community 108 - "test_ap_aging.py"
Cohesion: 0.24
Nodes (13): create_supplier(), fixture, Wave 22 AP — aging report tests. Covers: bucket placement, totals/outstanding…, register_and_token(), seed_invoice(), insert(), setup_database(), test_aging_as_of_future_rejected() (+5 more)

### Community 109 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 110 - "InvoiceCounter"
Cohesion: 0.18
Nodes (11): InvoiceCounter, SQLModel, Workspace-scoped invoice number counter for gapless sequences. Uses composite…, Generate formatted invoice number: INV-2026-0001, InvoiceNumberService, AsyncSession, UUID, Gapless Invoice Number Generation Service. Ensures legally compliant invoice… (+3 more)

### Community 111 - "supplier_payment_reversal_service.py"
Cohesion: 0.24
Nodes (11): _invalid_state(), _now(), AsyncSession, datetime, Decimal, NoReturn, UUID, AP payment reversal — a SUCCESS CHEQUE/CASH/BANK payment that bounces at the… (+3 more)

### Community 112 - "schemas/inventory.py"
Cohesion: 0.20
Nodes (13): AdjustReason, BaseModel, Enum, model_validator, str, ADMIN/OWNER stock back door. Extra keys → 422., StockAdjustmentRequest, WarehouseBase (+5 more)

### Community 113 - "DnCounter"
Cohesion: 0.20
Nodes (10): DnCounter, SQLModel, Workspace-scoped delivery-note number counter (operational sequence). Composite…, Generate formatted delivery-note number: DN-2026-0001., DnNumberService, AsyncSession, UUID, Operational delivery-note number generation (DN-YYYY-XXXX). Clones LPO/quote… (+2 more)

### Community 114 - "LpoCounter"
Cohesion: 0.20
Nodes (10): LpoCounter, SQLModel, Workspace-scoped LPO number counter (operational sequence). Composite primary…, Generate formatted LPO number: LPO-2026-0001., LpoNumberService, AsyncSession, UUID, Operational LPO number generation (LPO-YYYY-XXXX). Clones quotation/invoice… (+2 more)

### Community 115 - "QuotationCounter"
Cohesion: 0.20
Nodes (10): SQLModel, QuotationCounter, Workspace-scoped quotation number counter (operational sequence). Composite…, Generate formatted quotation number: QUO-2026-0001., AsyncSession, UUID, QuotationNumberService, Operational quotation number generation (QUO-YYYY-XXXX). Clones… (+2 more)

### Community 116 - "SPOCounter"
Cohesion: 0.20
Nodes (10): SQLModel, Workspace-scoped Supplier Purchase Order (SPO) number counter for gapless…, Generate formatted SPO number: SPO-2026-000001, SPOCounter, AsyncSession, UUID, Gapless Supplier Purchase Order (SPO) number generation service. Mirrors…, Service for generating gapless, workspace-scoped SPO numbers. (+2 more)

### Community 117 - "CreditNoteCounter"
Cohesion: 0.22
Nodes (9): CreditNoteCounter, SQLModel, Workspace-scoped gapless CN-YYYY-XXXX counter. Soft-delete does not rewind., CreditNoteNumberService, AsyncSession, UUID, Gapless tax credit-note numbers (CN-YYYY-XXXX). FTA tax document sequence.…, SELECT FOR UPDATE counter for workspace/year CN numbers. (+1 more)

### Community 118 - "GRNCounter"
Cohesion: 0.22
Nodes (9): GRNCounter, SQLModel, Workspace-scoped Goods Receipt Note (GRN) counter for gapless sequences.…, Generate formatted GRN number: GRN-2026-000001, GRNNumberService, AsyncSession, UUID, Gapless Goods Receipt Note (GRN) number generation service. Mirrors… (+1 more)

### Community 119 - "RFQAwardCounter"
Cohesion: 0.22
Nodes (9): SQLModel, Workspace-scoped RFQ award counter for gapless sequences. Mirrors…, Generate formatted award number: AWD-2026-000001, RFQAwardCounter, AwardNumberService, AsyncSession, UUID, Gapless RFQ award number generation service. Mirrors… (+1 more)

### Community 120 - "tax_debit_note.py"
Cohesion: 0.24
Nodes (10): SQLModel, TaxDebitNoteBase, TaxDebitNoteCounter, TaxDebitNoteItemBase, AsyncSession, UUID, Gapless tax debit-note numbers (TDN-YYYY-XXXX). FTA tax document sequence.…, SELECT FOR UPDATE counter for workspace/year TDN numbers. (+2 more)

### Community 121 - "routers/analytics.py"
Cohesion: 0.29
Nodes (11): Wave 30 — BI analytics router. `GET /api/v1/reports/analytics/{revenue|sales-…, CashflowReport, CashflowRow, BaseModel, BI / analytics schemas — Wave 30 (Phase 6 continuation). Shared row shapes for…, RevenueReport, RevenueRow, SalesByCustomerReport (+3 more)

### Community 122 - "get_cashflow"
Cohesion: 0.31
Nodes (13): get_cashflow(), get_revenue(), get_sales_by_customer(), get_sales_by_product(), AsyncSession, date, limit, Request (+5 more)

### Community 123 - "normalize_phone_to_e164"
Cohesion: 0.26
Nodes (11): normalize_phone_to_e164(), Canonical phone normalization (Wave 27 — WhatsApp). `normalize_phone_to_e164`…, Normalize a phone string to canonical E.164 (``+<digits>``) or None. - Trims…, Wave 27 — canonical phone normalization tests. `normalize_phone_to_e164` is the…, test_bare_local_number_never_guessed(), test_bounds_min_and_max_digits(), test_edge_leading_zero_after_prefix_is_kept(), test_garbage_and_empty() (+3 more)

### Community 124 - "dependencies"
Cohesion: 0.15
Nodes (13): dependencies, axios, @hookform/resolvers, lucide-react, react, react-dom, react-hook-form, react-hot-toast (+5 more)

### Community 125 - "EnquiryCounter"
Cohesion: 0.27
Nodes (7): EnquiryCounter, SQLModel, Generate formatted enquiry number: ENQ-2026-0001, EnquiryNumberService, AsyncSession, UUID, Generate gapless enquiry number using FOR UPDATE locking.

### Community 126 - "PurchaseReturnCounter"
Cohesion: 0.24
Nodes (8): PurchaseReturnCounter, SQLModel, Workspace-scoped gapless counter for purchase returns (PRN-YYYY-XXXX)., Generate formatted purchase return number: PRN-2026-0001, PurchaseReturnNumberService, AsyncSession, UUID, Gapless Purchase Return (PRN) number generation service. Format: PRN-2026-0001…

### Community 127 - "routers/supplier_invoices.py"
Cohesion: 0.44
Nodes (10): approve_invoice(), create_supplier_invoice(), get_supplier_invoice(), get_supplier_invoice_audit_log(), list_supplier_invoices(), AsyncSession, post, UUID (+2 more)

### Community 128 - "routers/workspaces.py"
Cohesion: 0.36
Nodes (9): get_current_workspace(), AsyncSession, put, Request, UUID, update_current_workspace(), BaseModel, WorkspaceResponse (+1 more)

### Community 129 - "devDependencies"
Cohesion: 0.18
Nodes (11): devDependencies, oxlint, pg, @playwright/test, @types/node, @types/pg, @types/react, @types/react-dom (+3 more)

### Community 130 - "ar_aging_by_customer"
Cohesion: 0.33
Nodes (10): ar_aging_by_customer(), ar_aging_detail(), ar_aging_summary(), AsyncSession, date, Request, UUID, AR aging report (default view=summary). `historical=true` reconstructs balances… (+2 more)

### Community 131 - "supplier_statements.py"
Cohesion: 0.31
Nodes (9): BaseModel, Enum, Generated supplier AP statement JSON (the AP ledger). Wave 22 — query, no table., SupplierStatementAging, SupplierStatementLine, SupplierStatementResponse, SupplierStatementSupplier, SupplierStatementTotals (+1 more)

### Community 132 - "global_exception_handler"
Cohesion: 0.28
Nodes (9): global_exception_handler(), http_exception_handler(), Request, request_id_middleware(), validation_exception_handler(), Exception, exception_handler, middleware (+1 more)

### Community 134 - "test_grn.py"
Cohesion: 0.43
Nodes (6): get_auth_token(), get_workspace_id(), _init_module_auth(), Register once per module; subsequent calls reuse cached token., test_grn_cancellation(), test_grn_lifecycle()

### Community 136 - "run_async_migrations"
Cohesion: 0.33
Nodes (6): do_run_migrations(), In this scenario we need to create an Engine and associate a connection with…, Run migrations in 'online' mode., run_async_migrations(), run_migrations_online(), Connection

### Community 137 - "SupplierPaymentCreate"
Cohesion: 0.53
Nodes (3): date, field_validator, SupplierPaymentCreate

### Community 138 - ".oxlintrc.json"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 139 - "scripts"
Cohesion: 0.33
Nodes (6): scripts, build, dev, lint, preview, test:e2e

## Knowledge Gaps
- **236 isolated node(s):** `CreditNoteListQuery`, `SkeletonProps`, `CnLineForm`, `Props`, `CashflowRow` (+231 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1295 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `routers/workspaces.py`, `utc_today`, `CreditNote`, `test_email_comms.py`, `quotation_service.py`, `models/__init__.py`, `tax_debit_note_service.py`, `raise_error`, `InvoiceService`, `test_rfq_awards.py`, `HTTPException`, `Workspace`, `customer_po_support.py`, `CustomerPurchaseOrderService`, `_get`, `routers/quotations.py`, `routers/clients.py`, `GRNService`, `stock_count_service.py`, `test_delivery_notes.py`, `routers/delivery_notes.py`, `Payment`, `SupplierInvoice`, `WhatsAppService`, `whatsapp_service.py`, `SuccessResponse`, `test_whatsapp_comms.py`, `routers/procurement.py`, `purchase_return_service.py`, `enquiries.py`, `test_pricing.py`, `test_spo_amendments.py`, `test_vat_compliance.py`, `test_supplier_payment_reversal.py`, `test_supplier_pdc.py`, `services/__init__.py`, `test_stock_counts.py`, `inventory_ledger.py`, `test_analytics.py`, `test_stock_reservations.py`, `routers/rfq.py`, `test_purchase_returns.py`, `SupplierPayment`, `send_email`, `routers/supplier_debit_notes.py`, `get_vat_compliance`, `supplier_payment_reversal_service.py`, `routers/analytics.py`, `get_cashflow`, `routers/supplier_invoices.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `get_session()` connect `models/__init__.py` to `routers/workspaces.py`, `utc_today`, `timedelta`, `CreditNote`, `test_email_comms.py`, `test_grn.py`, `test_invoices.py`, `tax_debit_note_service.py`, `InvoiceService`, `test_rfq_awards.py`, `HTTPException`, `CustomerPurchaseOrderService`, `_get`, `routers/quotations.py`, `routers/clients.py`, `GRNService`, `test_delivery_notes.py`, `test_quotations.py`, `routers/delivery_notes.py`, `whatsapp_service.py`, `SuccessResponse`, `test_customer_lpos.py`, `test_products.py`, `routers/products.py`, `test_whatsapp_comms.py`, `routers/procurement.py`, `purchase_return_service.py`, `test_credit_notes.py`, `enquiries.py`, `test_pricing.py`, `test_spo_amendments.py`, `test_vat_compliance.py`, `test_tax_debit_notes.py`, `test_supplier_invoice_events.py`, `test_supplier_payment_reversal.py`, `test_supplier_pdc.py`, `get_current_user`, `test_stock_counts.py`, `test_analytics.py`, `test_stock_reservations.py`, `test_stock_transfers.py`, `test_supplier_products.py`, `routers/rfq.py`, `test_concurrent_numbering.py`, `test_supplier_payments.py`, `test_enquiries.py`, `test_purchase_returns.py`, `test_landed_cost.py`, `test_supplier_debit_notes.py`, `routers/supplier_debit_notes.py`, `test_product_electrical_specs.py`, `test_ap_aging.py`, `routers/analytics.py`, `routers/supplier_invoices.py`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `Invoice` connect `Invoice` to `utc_today`, `timedelta`, `CreditNote`, `quotation_service.py`, `models/__init__.py`, `tax_debit_note_service.py`, `raise_error`, `InvoiceService`, `Workspace`, `customer_po_support.py`, `CustomerPurchaseOrderService`, `routers/clients.py`, `Payment`, `PaymentStatus`, `test_whatsapp_comms.py`, `routers/procurement.py`, `Client`, `money`, `test_vat_compliance.py`, `services/__init__.py`, `test_analytics.py`, `vat_compliance_service.py`, `analytics_service.py`, `services/ar_aging.py`, `tax_debit_note.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 139 inferred relationships involving `User` (e.g. with `get_cashflow()` and `get_revenue()`) actually correct?**
  _`User` has 139 INFERRED edges - model-reasoned connections that need verification._
- **Are the 155 inferred relationships involving `SuccessResponse` (e.g. with `get_me()` and `login()`) actually correct?**
  _`SuccessResponse` has 155 INFERRED edges - model-reasoned connections that need verification._
- **Are the 115 inferred relationships involving `ErrorCode` (e.g. with `_require_owner_admin()` and `delete_debit_note()`) actually correct?**
  _`ErrorCode` has 115 INFERRED edges - model-reasoned connections that need verification._
- **Are the 64 inferred relationships involving `Invoice` (e.g. with `PaymentStatus` and `delete_client()`) actually correct?**
  _`Invoice` has 64 INFERRED edges - model-reasoned connections that need verification._