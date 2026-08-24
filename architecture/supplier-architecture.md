# Supplier Master & Foundation Architecture
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification — Supplier Domain Detail*

## 1. Architectural Principle
**Supplier Master ≠ Supplier Product ≠ Supplier Transaction**
Master vs Transaction Snapshot Rule applies.

## 2. Supplier Entity & Core
- **id**: Internal UUID.
- **workspace_id**: Tenant isolation boundary.
- **supplier_code**: Human-readable identifier. UNIQUE per workspace.
- **status (C-06)**: DRAFT, ACTIVE, INACTIVE, ON_HOLD, BLOCKED, BLACKLISTED. 

## 3. Sub-Entities (C-07)
*Note: Bank details, addresses, and TRNs are strictly kept in child tables. They are dropped from the inline Supplier root model to maintain proper source of truth.*

### 3.1 SupplierContact
- Fields: irst_name, last_name, email, phone, is_primary.

### 3.2 SupplierAddress (C-07)
- Fields: ddress_type, ddress_line_1, city, country, is_default.

### 3.3 SupplierTaxRegistration (C-07)
- Multi-market support. Fields: country_code, egistration_type, egistration_number.

### 3.4 SupplierBankAccount
- Security: Requires RBAC to view. Changes trigger audit records.

### 3.5 SupplierDocument
- Expiry triggers system warnings.

## 4. Supplier ↔ Product Mapping (SupplierProduct) (C-08 Locked)
Many-to-Many relationship mapping Suppliers to Products.
- **supplier_sku**: The supplier's SKU.
- **purchase_uom_id**: Supplier's UOM.
- **conversion_to_base**: Per-supplier UOM conversion factor.
- **moq**: Minimum order quantity.
- **lead_time_days**: Default delivery expectation.
- **current_purchase_price**: Snapshotted into POs. Evolving into history table later.

## 5. Supplier Status Definitions
- **DRAFT**: Awaiting approval (if configured).
- **ACTIVE**: Normal operations.
- **INACTIVE**: No new transactions. Historical reporting only.
- **ON_HOLD**: Temporary restriction.
- **BLOCKED**: No new procurement activity. Authorized override required.
- **BLACKLISTED**: Strongest restriction. No new transactions.
