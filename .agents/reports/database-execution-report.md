# Database Execution Report

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
