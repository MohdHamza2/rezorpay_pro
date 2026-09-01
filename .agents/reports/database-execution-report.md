# Database Execution Report

---

## 2026-09-01 — WP-A Tax Credit Notes schema (planned BEFORE code)

**Spec:** `architecture/wave-credit-notes-addendum.md` §7. Architect lock: Alembic YES, new revision only. `down_revision = "a7c4e9d2b105"`. NEVER rewrite DN (`a7c4e9d2b105`), credit HOLD, LPO, quotes, FTA, or Product Master.

### Locked

- Tables: `credit_note_counters`, `credit_notes`, `credit_note_items`, `credit_note_events`.
- `credit_note_counters` composite PK `(workspace_id, year)` — clone invoice counters. Do **not** reuse invoice/quotation/lpo/dn/spo counters. Numbers `CN-YYYY-XXXX` allocated at create. Soft-delete does not rewind.
- `invoices.amount_credited` Numeric(12,2) NOT NULL default 0.
- `clients.credit_balance` Numeric(12,2) NOT NULL default 0.
- PG enum value `CREDIT_NOTE_ISSUED` on `invoiceeventtype` via `ALTER TYPE ... ADD VALUE`.
- PostgreSQL ENUMs: `creditnotestatus` (DRAFT|ISSUED), `creditnotereason` (SALES_RETURN|INVOICE_ERROR|DISCOUNT|GOODWILL|OTHER), `creditnoteeventtype` (CN_CREATED|CN_UPDATED|CN_ISSUED).
- No debit notes. No payment mutations. No `/apply`.

### Verification (planned)

`alembic upgrade head` on DATABASE_URL and `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test`. Never SQLite.

---

## 2026-09-01 — WP-A Tax Credit Notes schema (implemented)

**Revision:** `b8d5f0c3a216` revises `a7c4e9d2b105`. File: `backend/alembic/versions/b8d5f0c3a216_add_credit_notes.py`.

Applied via test `alembic upgrade head` + `alembic check`: "No new upgrade operations detected". DN revision `a7c4e9d2b105` not rewritten.

Created: `credit_note_counters`, `credit_notes`, `credit_note_items`, `credit_note_events`. Added `invoices.amount_credited` Numeric(12,2) NOT NULL default 0 and `clients.credit_balance` Numeric(12,2) NOT NULL default 0. `ALTER TYPE invoiceeventtype ADD VALUE IF NOT EXISTS 'CREDIT_NOTE_ISSUED'`. ENUMs `creditnotestatus`, `creditnotereason`, `creditnoteeventtype`. No debit notes. No payment table changes.

---

## 2026-09-01 — WP-A Delivery Notes schema (planned BEFORE code)

**Spec:** `architecture/wave-delivery-notes-addendum.md` §10. Architect lock: Alembic YES, new revision only. `down_revision = "9f3a7c2e1d04"`. NEVER rewrite credit (`9f3a7c2e1d04`), LPO, quotes, FTA, or Product Master.

### Locked

- Tables: `dn_counters`, `delivery_notes`, `delivery_note_items`, `delivery_note_events`.
- `dn_counters` composite PK `(workspace_id, year)` — clone LPO counters. Do **not** reuse invoice/quotation/lpo/spo counters. Numbers `DN-YYYY-XXXX`. Soft-delete does not rewind.
- `delivery_notes` XOR parent check: `(customer_purchase_order_id IS NULL) <> (invoice_id IS NULL)`.
- `customer_purchase_order_items.quantity_delivered` Numeric(10,2) NOT NULL default 0; checks `>= 0` and `<= quantity`.
- `inventory_transactions.reason` String(30) nullable; `notes` Text nullable.
- PG enum value `DN_CONFIRM` on `crediteventreason` via `ALTER TYPE ... ADD VALUE`.
- PostgreSQL ENUMs: `deliverynotestatus` (DRAFT|CONFIRMED|CANCELLED), `deliverynoteeventtype` (DN_CREATED|DN_UPDATED|DN_CONFIRMED|DN_CANCELLED).
- No `stock_reservations`. No DeliveryOrder module. No invoice delivered column.

### Verification (planned)

`alembic upgrade head` on DATABASE_URL and `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test`. Never SQLite.

---

## 2026-09-01 — WP-A Delivery Notes schema (implemented)

**Revision:** `a7c4e9d2b105` revises `9f3a7c2e1d04`. File: `backend/alembic/versions/a7c4e9d2b105_add_delivery_notes.py`.

Applied: `alembic upgrade head` on `invoicesaas` (was at `9f3a7c2e1d04`). `alembic check`: "No new upgrade operations detected".

Created: `dn_counters`, `delivery_notes` (XOR parent check `check_dn_parent_xor`), `delivery_note_items`, `delivery_note_events`. Added `customer_purchase_order_items.quantity_delivered` Numeric(10,2) NOT NULL default 0 with `>= 0` and `<= quantity` checks. Added `inventory_transactions.reason` String(30) and `notes` Text. `ALTER TYPE crediteventreason ADD VALUE IF NOT EXISTS 'DN_CONFIRM'`. ENUMs `deliverynotestatus`, `deliverynoteeventtype`. Credit revision `9f3a7c2e1d04` not rewritten. No `stock_reservations`.

---

## 2026-09-01 — WP-A Credit HOLD / overdue schema (planned BEFORE code)

**Spec:** `architecture/wave-credit-control-addendum.md` §2, §8. Architect lock: Alembic YES, new revision only. `down_revision = "59084165d346"`. NEVER rewrite LPO (`59084165d346`), quotes, FTA, or Product Master.

### Locked

- `clients`: `credit_limit` Numeric(12,2) nullable (NULL inherit workspace default; 0 COD; >0 cap; check `>= 0` when not null). `payment_terms_days` int NOT NULL default 0, allow-list `{0,30,45,60}`. `credit_status` ENUM ACTIVE|WARNING|HOLD NOT NULL default ACTIVE. `credit_status_changed_at` timestamptz nullable. `credit_status_changed_by` UUID FK `users.id` nullable.
- Table `credit_status_events`: id, client_id, workspace_id, previous_status, new_status, exposure, effective_limit, oldest_overdue_days nullable, reason (EVALUATE/PAYMENT/SEND_CHECK/RECEIVE_CHECK), changed_by FK users, timestamp, metadata_log JSONB.
- Reuse Workspace flags. No new Workspace columns. No invoice columns. No `SUSPENDED`, no `credit_unlimited`.
- Optional index `invoices (workspace_id, client_id, status)` for exposure SUM.

### Verification (planned)

`alembic upgrade head` on DATABASE_URL and `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test`. Never SQLite.

---

## 2026-09-01 — WP-A Credit HOLD / overdue schema (implemented)

**Revision:** `9f3a7c2e1d04` revises `59084165d346`. File: `backend/alembic/versions/9f3a7c2e1d04_add_client_credit_control.py`.

Applied: `alembic upgrade head` on `invoicesaas` (was at `59084165d346`). `alembic check`: "No new upgrade operations detected".

Added to `clients`: `credit_limit` Numeric(12,2) nullable, `payment_terms_days` int NOT NULL default 0 (check IN 0/30/45/60), `credit_status` ENUM ACTIVE|WARNING|HOLD default ACTIVE, `credit_status_changed_at`, `credit_status_changed_by` FK users. Table `credit_status_events` with exposure/effective_limit Decimal(12,2), reason ENUM EVALUATE/PAYMENT/SEND_CHECK/RECEIVE_CHECK, JSONB `metadata_log`. Index `ix_invoices_workspace_id_client_id_status`. No Workspace columns. No invoice columns. LPO revision `59084165d346` not rewritten.

---

## 2026-09-01 — WP-A Customer LPO schema (planned BEFORE code)

**Spec:** `architecture/wave-customer-lpo-addendum.md` §8. Architect lock: Alembic YES, new revision only. `down_revision = "cb01b6bef962"`. NEVER rewrite quotes (`cb01b6bef962`), FTA (`c8e1a4f2b6d0`), or Product Master.

### Locked

- Tables: `lpo_counters`, `customer_purchase_orders`, `customer_purchase_order_items`, `customer_purchase_order_events`.
- Columns: `invoices.customer_purchase_order_id` UUID nullable indexed **not unique**; `invoice_items.customer_purchase_order_item_id` UUID nullable FK indexed.
- Keep unique `invoices.quotation_id`. Unique `customer_purchase_orders.quotation_id`.
- Partial unique `(workspace_id, client_id, customer_po_number)` WHERE `customer_po_number IS NOT NULL`.
- Internal numbers `LPO-YYYY-XXXX` via **new** `lpo_counters` (composite PK workspace_id+year). Do **not** reuse invoice/quotation/spo counters.
- Soft-delete does not rewind the counter.
- PostgreSQL ENUMs: `customerpurchaseorderstatus`, `customerpurchaseordereventtype`.
- No SPO/GRN changes. No `delivered_quantity`, retention, OCR URL, credit confirm columns.

### Verification (planned)

`alembic upgrade head` on DATABASE_URL and `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test`. Never SQLite.

---

## 2026-09-01 — WP-A Customer LPO schema (implemented)

**Revision:** `59084165d346` revises `cb01b6bef962`. File: `backend/alembic/versions/59084165d346_add_customer_lpos.py`.

Applied: `alembic upgrade head` on `invoicesaas` (was at `cb01b6bef962`). `alembic check`: "No new upgrade operations detected".

Created: `lpo_counters`, `customer_purchase_orders`, `customer_purchase_order_items`, `customer_purchase_order_events`. Added `invoices.customer_purchase_order_id` UUID nullable indexed **not unique** (`fk_invoices_customer_purchase_order_id`). Added `invoice_items.customer_purchase_order_item_id` UUID nullable FK indexed (`fk_invoice_items_cpo_item_id`). Unique index on `customer_purchase_orders.quotation_id`. Partial unique `uq_cpo_workspace_client_po_number`. PostgreSQL ENUMs `customerpurchaseorderstatus` and `customerpurchaseordereventtype`. Quotes revision `cb01b6bef962` not rewritten. No SPO/GRN changes.

---

## 2026-09-01 — WP-A Quotations schema (planned BEFORE code)

**Spec:** `architecture/wave-quotations-addendum.md` §9. Architect lock: Alembic YES, new revision only. `down_revision = "c8e1a4f2b6d0"`. NEVER rewrite FTA (`c8e1a4f2b6d0`) or Product Master (`d3e4c7fdb29f`).

### Locked

- Tables: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`.
- Column: `invoices.quotation_id` UUID nullable unique FK → `quotations.id` (indexed). No `quotations.converted_invoice_id` (avoid circular FK).
- No `enquiry_id`, `revision_number`, `revised_from_id`, LPO tables, `clients`/`products` column changes.
- Quote numbers: `QUO-YYYY-XXXX` via **new** `quotation_counters` (composite PK workspace_id+year). Do **not** reuse `invoice_counters`.
- Soft-delete does not rewind the counter.
- PostgreSQL ENUMs: `quotationstatus`, `quotationeventtype`.

### Columns

| Table | Notes |
|---|---|
| `quotation_counters` | Same shape as `invoice_counters`: PK `(workspace_id, year)`, `last_number` NOT NULL default 0, timestamps |
| `quotations` | UUID PK, workspace/client FKs, `quotation_number` unique per workspace, status ENUM default DRAFT, AED, dates, Decimal(12,2) totals ≥ 0, notes, rejection_reason, timestamps, `deleted_at` |
| `quotation_items` | Same shape as live `invoice_items` minus `invoice_id`; FK `quotation_id`; optional `product_id`/`uom_id`/`sku_snapshot`; XOR discounts; line_net / tax_amount / total_price (gross) |
| `quotation_events` | Clone `invoice_events`; types CREATED/UPDATED/SENT/ACCEPTED/REJECTED/EXPIRED/CONVERTED; JSONB `metadata_log`; `changed_by` FK users |
| `invoices.quotation_id` | UUID nullable unique FK, indexed |

### Verification (planned)

`alembic upgrade head` on DATABASE_URL (host 5434) and test DB. `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test`. Never SQLite.

---

## 2026-09-01 — WP-A Quotations schema (implemented)

**Revision:** `cb01b6bef962` revises `c8e1a4f2b6d0`. File: `backend/alembic/versions/cb01b6bef962_add_quotations.py`.

Applied: `alembic upgrade head` on `invoicesaas` (was at `c8e1a4f2b6d0`). `alembic check`: "No new upgrade operations detected".

Created: `quotation_counters`, `quotations`, `quotation_items`, `quotation_events`. Added `invoices.quotation_id` UUID nullable unique FK (`ix_invoices_quotation_id`, `fk_invoices_quotation_id`). PostgreSQL ENUMs `quotationstatus` and `quotationeventtype`. FTA revision `c8e1a4f2b6d0` not rewritten.

---


## 2026-08-31 — WP-A FTA Tax Invoice schema (planned BEFORE code)

**Spec:** `architecture/wave-fta-tax-invoice-addendum.md` §6. Architect lock: Alembic YES, new revision only.

### Locked

- `down_revision = "06c9b4b1dcda"` (current HEAD). NEVER rewrite `d3e4c7fdb29f` or any ancestor.
- No `clients.trn` (buyer TRN stays `clients.tax_id`). No IBAN. No header `discount_amount` column. No quotation/cpo/retention/einvoice columns.
- `invoice_kind` is `String(20)` nullable (not a PostgreSQL ENUM). Null on DRAFT; `STANDARD`/`SIMPLIFIED` at send.

### Columns

| Table | Column | Type | Notes |
|---|---|---|---|
| `workspaces` | `address` | Text nullable | Seller FTA address |
| `invoices` | `supply_date` | Date NOT NULL | Backfill = `issue_date` |
| `invoices` | `invoice_kind` | String(20) nullable | Set at send |
| `invoices` | `seller_trn_snapshot` | String(15) nullable | Frozen at send |
| `invoices` | `seller_name_snapshot` | String(255) nullable | |
| `invoices` | `seller_address_snapshot` | Text nullable | |
| `invoices` | `buyer_trn_snapshot` | String(15) nullable | |
| `invoices` | `buyer_name_snapshot` | String(255) nullable | |
| `invoices` | `buyer_address_snapshot` | Text nullable | |
| `invoice_items` | `product_id` | UUID FK `products.id` nullable, index | Catalog line |
| `invoice_items` | `uom_id` | UUID FK `units_of_measure.id` nullable | Snapshot only |
| `invoice_items` | `sku_snapshot` | String(100) nullable | |
| `invoice_items` | `discount_percent` | Numeric(5,2) NOT NULL default 0 | `>= 0` |
| `invoice_items` | `discount_amount` | Numeric(12,2) NOT NULL default 0 | `>= 0` |
| `invoice_items` | `line_net` | Numeric(12,2) NOT NULL default 0 | After discount, excl VAT |
| `invoice_items` | `tax_amount` | Numeric(12,2) NOT NULL default 0 | Line VAT |

Keep `invoice_items.total_price` as **gross**. Keep `quantity` Numeric(10,2).

### Backfill (same revision)

```
invoices.supply_date = issue_date
invoice_items.line_net = round(quantity * unit_price, 2)
invoice_items.tax_amount = round(line_net * tax_rate/100, 2)
invoice_items.total_price = line_net + tax_amount
```

Existing SENT rows: best-effort; snapshots stay null until a new send.

### Verification

`alembic upgrade head` on DATABASE_URL (host 5434) and test DB. `alembic check` clean. Tests use SQLModel `create_all` on `{DATABASE_URL}_test` plus this model shape.

---

## 2026-08-31 — WP-A FTA Tax Invoice schema (implemented)

**Revision:** `c8e1a4f2b6d0` revises `06c9b4b1dcda`. File: `backend/alembic/versions/c8e1a4f2b6d0_fta_tax_invoice_fields.py`.

Applied: `alembic upgrade head` on `invoicesaas` (was at `06c9b4b1dcda`) and full chain on `invoicesaas_test`. `alembic check`: "No new upgrade operations detected" on both.

Backfill in the same revision: `invoices.supply_date = issue_date`; line `line_net` / `tax_amount` / `total_price` from qty×price×rate. No `clients.trn`. No IBAN. `invoice_kind` is String(20), not a PG ENUM.

---

## Step 5: Goods Receipt Note (GRN) & Receiving
### Action: Creating GRN models
- Overwrote backend/app/models/grn.py to match Wave 14/15 Step 5 requirements.
- Generated alembic migration
- Fixed GoodsReceiptNote and GRNItem base inheritance
- Removed cascade_delete parameter from Relationship
- Reviewing generated migration for Enum safety
- Added custom SQL script to migration to handle GRNStatus ENUM values
- Fixed 'import sqlmodel' missing in generated alembic script and applied head
## Summary of Wave 14/15 Step 5
- Database schema updated with GoodsReceiptNote and GRNItem models matching architecture rules.
- Alembic migration generated, manually edited for ENUM safety, and applied to database successfully.
