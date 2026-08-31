# Wave 3 Product Master — Architecture Addendum (WP-1 lock)

**Date:** 2026-08-31
**Status:** Coordinator lock. Coder implements **this file**, not `architecture/api-contracts.md` Product blobs and not `architecture/domain-model.md` Product/UOM sections.
**Scope:** WP-1 Product Master **API** only (backend).
**Not this WP:** frontend (WP-2), browser E2E (WP-3), FTA tax invoice, quotations, LPO, invoice `product_id`, payment/PDC PUT.

Copy WP-1 acceptance criteria from `.agents/reports/mvp-execution-sequence-2026-08-31.md` §5. This addendum **resolves** the ambiguities that document told the coder not to pick.

Ship-order for **later** waves remains `.agents/reports/uae-electrical-architecture-gaps-2026-08-31.md`. After WP-1–3: FTA tax invoice / quotes / LPO — **not** in this addendum.

---

## 0. Runtime truth vs paper specs

| Source | Role in WP-1 |
|---|---|
| `backend/app/models/product.py` + Alembic `d3e4c7fdb29f` | **Schema truth.** Do not add columns. |
| `backend/app/schemas/common.py` `PaginatedResponse` | **List JSON truth** (`data` = array, `pagination` sibling). |
| `backend/app/routers/products.py` | Incomplete (list/create only). Replace logic with service; keep prefix `/products` mounted at `/api/v1`. |
| `architecture/domain-model.md` Product / ProductUOMConversion / ProductPrice | **Drift.** Documented in §15. Do not implement those extra fields in WP-1. |
| `architecture/api-contracts.md` GET `/products/{id}` | **Cut.** No `hs_code`, `vat_category`, `warehouse_stock`, `standard_sell_price`, `from_uom`. |
| `.hermes/plans/2026-08-27_153000-wave3-product-master.md` | **Stale.** Must **not** rewrite `d3e4c7fdb29f` `down_revision`. |
| Alembic HEAD | `06c9b4b1dcda`. `d3e4c7fdb29f` is already an **ancestor** of HEAD. Product tables already exist on a fully upgraded DB. |

---

## 1. ASCII — product aggregate + request flow

### 1.1 Aggregate (live tables — WP-1 does not add tables)

```
Workspace
    │
    ├── Category          (soft delete deleted_at)
    ├── Brand             (soft delete)
    ├── UnitOfMeasure     (soft delete; unique (workspace_id, code))
    └── Product           (soft delete + is_active)
            │  unique (workspace_id, internal_sku)
            │  FK base_uom_id → UnitOfMeasure  [REQUIRED]
            │  FK category_id, brand_id        [OPTIONAL]
            │
            ├── ProductIdentifier     (no deleted_at → hard DELETE)
            │     unique (workspace_id, type, value)
            ├── ProductUOMConversion  (no deleted_at → hard DELETE)
            │     unique (product_id, to_uom_id)
            │     implied FROM = Product.base_uom_id
            └── ProductPrice          (no deleted_at → hard DELETE)
                  currency default AED; price Numeric(12,2)
```

**There is no `from_uom_id` column.** Conversion meaning is locked in §3.

### 1.2 API request flow

```
Client  →  JWT  →  get_current_workspace_id()   [never body/query workspace_id]
              ↓
       routers/products.py     HTTP only: parse, status, wrapper
              ↓
       services/product_service.py     rules, uniqueness, 404 isolation
              ↓
       PostgreSQL 16 (existing tables; no WP-1 migration)
              ↓
       SuccessResponse | PaginatedResponse
         { "success": true, "data": ..., "error": omitted on success }
       errors via HTTPException → { "success": false, "error": { code, message } }
```

---

## 2. Exact endpoint list

Base: `/api/v1`. Router prefix already `/products`. Auth: `Authorization: Bearer` on all.

**Route order:** static paths (`/categories`, `/brands`, `/uom`) **before** `/{product_id}`. Path IDs are UUID.

List endpoints: query `page` (default 1, ge 1), `per_page` (default 20, ge 1, le 100). Response **must** be `PaginatedResponse` from `app.schemas.common`:

```json
{
  "success": true,
  "data": [ /* items */ ],
  "pagination": {
    "total": 0,
    "page": 1,
    "per_page": 20,
    "pages": 0,
    "has_next": false,
    "has_prev": false
  }
}
```

Do **not** nest `{ "items": [], "pagination": {} }` inside `data` (that shape in `api-contracts.md` is wrong vs live `PaginatedResponse` / `clients.py`).

Item GET/POST/PUT: `SuccessResponse[T]` → `{ "success": true, "data": { ... } }`. POST create: **201**. DELETE: **200** `{ "success": true, "data": null }` (or empty object — pick `null` and use it consistently).

Cross-workspace or missing/deleted parent: **404** `"… not found"`, never 403. Ignore query `workspace_id` (tests still append it; JWT wins).

### 2.1 Category

| Method | Path | Body / query | Response `data` |
|---|---|---|---|
| GET | `/products/categories` | `page`, `per_page`, `search?` | array `CategoryResponse` |
| POST | `/products/categories` | `CategoryCreate` | `CategoryResponse` 201 |
| GET | `/products/categories/{id}` | — | `CategoryResponse` |
| PUT | `/products/categories/{id}` | `CategoryUpdate` (all optional) | `CategoryResponse` |
| DELETE | `/products/categories/{id}` | — | soft delete |

`CategoryCreate` / `CategoryResponse` (live + `deleted_at` on response optional):

- `name` str 1–255 **required** on create
- `description` str?
- `parent_id` UUID? (same workspace, not self, not deleted; circular parent → 400)
- Response adds: `id`, `workspace_id`, `created_at`, `updated_at`

`CategoryUpdate`: `name?`, `description?`, `parent_id?`.

List default: `deleted_at IS NULL`. Duplicate `name` among non-deleted rows in workspace → **409** `CONFLICT` (no DB unique today — enforce in service; **no Alembic unique**).

### 2.2 Brand

Same verbs as category at `/products/brands` and `/products/brands/{id}`.

Fields: `name` required, `description` optional. Duplicate name among non-deleted → 409.

### 2.3 Unit of measure

| Method | Path |
|---|---|
| GET | `/products/uom` paginated |
| POST | `/products/uom` |
| GET | `/products/uom/{id}` |
| PUT | `/products/uom/{id}` |
| DELETE | `/products/uom/{id}` soft |

Fields: `code` str 1–50 required, `name` str 1–255 required. `code` unique per workspace already (`uq_workspace_uom_code`). Duplicate → 409 from DB integrity or service pre-check.

**Do not** add `dimension` or `is_base` columns (domain-model drift).

Soft-delete UOM **blocked** (400) if any non-deleted `Product.base_uom_id` or `ProductUOMConversion.to_uom_id` references it.

### 2.4 Product

| Method | Path | Query / body |
|---|---|---|
| GET | `/products` | `page`, `per_page`, `search?` (ilike `internal_sku`, `name`, `description`), `category_id?`, `brand_id?`, `is_active?` (bool; **default omit = return both** unless you default true — **lock: default no `is_active` filter**, so existing SKUs still appear; WP-2 can pass `is_active=true`) |
| POST | `/products` | `ProductCreate` |
| GET | `/products/{id}` | detail includes child arrays |
| PUT | `/products/{id}` | `ProductUpdate` DRAFT-style: any field optional |
| DELETE | `/products/{id}` | soft `deleted_at` |

List and GET-by-id exclude `deleted_at IS NOT NULL` (404 on GET if deleted).

**ProductCreate required:** `internal_sku`, `name`, `base_uom_id`.
**ProductCreate optional:** `description`, `category_id`, `brand_id`, `is_active` (default true), `tax_rate`, `reorder_level`.

**Not accepted on create/update (no columns):** `hs_code`, `vat_category`, `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `specs`, `name_ar`, `track_inventory`, `purchase_uom_id`, `sales_uom_id`, `standard_sell_price`, `standard_cost_price`, `min_stock_level`, `max_stock_level`, `short_description`. Extra body keys → 422.

`base_uom_id` / `category_id` / `brand_id` must belong to JWT workspace and not be soft-deleted (400/404). `internal_sku` unique per workspace among non-deleted → 409.

PUT `base_uom_id` while conversions exist → **400** (conversions are defined vs current base; empty conversions first).

**ProductResponse (list and create):** live fields + `id`, `workspace_id`, `created_at`, `updated_at`. No stock. No nested warehouse.

```
id, workspace_id, internal_sku, name, description,
category_id, brand_id, base_uom_id,
is_active, tax_rate, reorder_level,
created_at, updated_at
```

`tax_rate` / `reorder_level` / money-like decimals: Pydantic `Decimal`, JSON number or string OK; **never `float` in models**.

**ProductDetailResponse (GET by id only):** `ProductResponse` plus:

```
identifiers: ProductIdentifierResponse[]
conversions: ProductUOMConversionResponse[]
prices: ProductPriceResponse[]
```

Eager-load children (`selectinload`). Do **not** embed `quantity_on_hand` / `warehouse_stock`.

### 2.5 Nested identifier / conversion / price

All scoped: parent product must be JWT workspace and `deleted_at IS NULL`. Child id must belong to that product. Else 404.

| Method | Path |
|---|---|
| GET | `/products/{product_id}/identifiers` → `SuccessResponse[list]` (no pagination required; typical small; **lock: unpaginated SuccessResponse list** to keep WP-1 small) |
| POST | `/products/{product_id}/identifiers` 201 |
| DELETE | `/products/{product_id}/identifiers/{identifier_id}` hard delete |
| GET | `/products/{product_id}/conversions` |
| POST | `/products/{product_id}/conversions` 201 |
| DELETE | `/products/{product_id}/conversions/{conversion_id}` |
| GET | `/products/{product_id}/prices` |
| POST | `/products/{product_id}/prices` 201 |
| DELETE | `/products/{product_id}/prices/{price_id}` |

No PUT on children (delete + create). No GET-by-child-id required.

---

## 3. UOM conversion shape — LIVE MODEL WINS

**Decision:** **No `from_uom_id` column. No Alembic.**

Live `ProductUOMConversion` (`product.py` + `d3e4c7fdb29f`):

- `to_uom_id` UUID FK `units_of_measure.id` **required**
- `conversion_factor` `Numeric(14, 6)` / `Decimal` **required**, must be **> 0**
- unique `(product_id, to_uom_id)`
- implied **from** UOM = `Product.base_uom_id`

**Semantic (coder must persist this in service docstring and 400 messages):**

> One (`1`) unit of `to_uom` equals `conversion_factor` units of the product’s **base UOM**.
> Example: base = MTR, `to_uom` = DRUM, `conversion_factor` = 500 → **1 DRUM = 500 MTR**.
> Matches the live comment `1 BOX = 10 PCS` when base is PCS and `to_uom` is BOX.

**Invariants**

- `to_uom_id` ≠ `product.base_uom_id` (400)
- `to_uom_id` in same workspace, not deleted
- Per-product only (Rule 1.8 “never global”) — already true
- Do **not** implement `uom_conversion_service.resolve_conversion` / multi-hop chains in WP-1 (Rule 1.8 remainder is **deferred** until GRN/SPO needs it). WP-1 is CRUD + validation only.

**Create body**

```json
{ "to_uom_id": "<uuid>", "conversion_factor": "500.000000" }
```

**Response**

```
id, workspace_id, product_id, to_uom_id, conversion_factor
```

Optionally echo `base_uom_id` (read-only, from parent) so WP-2 can label the conversion without a second product GET. **Do not** accept `from_uom_id` in the body (422).

`architecture/domain-model.md` lists `from_uom_id` + unique `(product_id, from_uom_id, to_uom_id)` and `Decimal(10,4)`. **Rejected for WP-1:** live unique is `(product_id, to_uom_id)` and `Numeric(14,6)`. A `from_uom_id` column is **not** required to express drum↔metre if from is always base.

---

## 4. Identifier types

**Decision:** DB column stays **`type: str(50)`** (live model). **Do not** create a PostgreSQL ENUM (would need Alembic).

Pydantic/service **allow-list** (Python `str, Enum` in schemas only):

| Value | WP-1 | Use |
|---|---|---|
| `MPN` | **in** | Manufacturer part number |
| `BARCODE` | **in** | Generic barcode |
| `SUPPLIER_CODE` | **in** | Supplier catalogue code |
| `EAN` | **in** | EAN-13 if distinct from BARCODE |
| `UPC` | **in** | UPC |
| `CUSTOMER_CODE` | **in** | Buyer’s own code (LPO lines later) |

Reject any other string with **422**. Do **not** use `INTERNAL_SKU` as an identifier type (`products.internal_sku` is the internal SKU).

**Create body:** `{ "type": "MPN", "value": "DUC-4C10" }`
`value` 1–255, stripped, non-empty.

**Not in live table — do not add:** `source`, `is_primary`, `created_at`, `identifier_type` rename. Unique already `(workspace_id, type, value)` → same MPN cannot exist on two products in one workspace (409).

---

## 5. Price tables (WP-1 vs deferred)

Live columns only: `price_type` str, `currency` str(3) default AED, `price` `Numeric(12,2)` **required**, `client_id` optional, `min_quantity` optional `Numeric(12,2)`.

**WP-1 allow-list `price_type` (Python enum, DB remains str):**

| `price_type` | Meaning | Rules |
|---|---|---|
| `DEFAULT_SALES` | List price | `client_id` must be null. At most **one** row per product (409). `min_quantity` null or omitted. |
| `TIER_1` | Volume break | `min_quantity` **required** `> 0`. `client_id` null. Unique `(product_id, TIER_1, min_quantity)` in service. |
| `CUSTOMER_SPECIFIC` | Customer / “dealer” price | `client_id` **required**, same workspace, not deleted. Unique `(product_id, client_id, min_quantity)` treating null min as 0. |

**Currency:** `AED` only. Omit → default AED. Anything else → 422.

**`price`:** `Decimal` `>= 0`, 2 decimal places. Never float.

**Deferred (do not invent columns or extra types):** `TIER_2`+, `DEALER` as a fourth type, `valid_from`/`valid_to`, `max_quantity`, `entity_type`/`entity_id`, customer groups, `standard_sell_price` / `standard_cost_price` on `Product`, pricing *resolution* engine for invoices.

---

## 6. VAT

| Field | Live | WP-1 |
|---|---|---|
| `Product.tax_rate` | `Numeric(5,2)` nullable | **Keep.** Optional on create. If set: `0 <= tax_rate <= 100`. UAE default for *invoices* is workspace `default_tax_rate` **5.00** — **do not copy 5.00 onto the product in WP-1**. Null means “inherit workspace at invoice time” (later wave). GET returns stored null. Do **not** add `effective_tax_rate`. |
| `Workspace.default_tax_rate` | 5.00 | Untouched. |
| `hs_code` | **not on model** | **Defer.** No Alembic. |
| `vat_category` | **not on model** | **Defer.** No Alembic. |

Invoice line VAT / FTA PDF is **after WP-1–3**.

---

## 7. Electrical catalogue fields

**Decision:** `product.py` has **none** of `amp_rating`, `cable_size_mm2`, `cores`, `voltage_v`, `poles`, `specs`. **Do not invent them in WP-1.**

Required on create: `internal_sku`, `name`, `base_uom_id` only.
Optional: `description`, `category_id`, `brand_id`, `is_active`, `tax_rate`, `reorder_level`.

Electrical identity for WP-1 lives in **SKU + name + description** (e.g. `ELE-CBL-4C10`, `"4-core 10mm² XLPE"`). Spec columns belong to a later Alembic from HEAD after WP-1–3 (gaps doc), not this slice.

---

## 8. Soft delete vs `is_active`; isolation

| Entity | Delete | `is_active` |
|---|---|---|
| Category, Brand, UOM, Product | **Soft:** set `deleted_at`, never `session.delete()` | Product only |
| Identifier, conversion, price | **Hard delete** (no `deleted_at` column; adding it would be Alembic — out of WP-1) | n/a |

List endpoints: `deleted_at IS NULL`.
GET deleted product/category/brand/uom: **404**.
`is_active=false`: still listed unless client filters; not the same as deleted.
Cross-workspace GET/PUT/DELETE product **and children**: **404**.

---

## 9. Stock embed on GET product

**Defer.** Inventory is `GET /api/v1/inventory/levels`. Product GET must not join `InventoryLevel`.

---

## 10. Category / Brand / UOM get-update-soft-delete

**In WP-1** (matches mvp-sequence §5). Paginated lists. See §2.1–2.3.

---

## 11. Nested CRUD paths

See §2.5. Service must load product with `Product.workspace_id == jwt` before any child write.

---

## 12. Service layer

**Required.** New `backend/app/services/product_service.py`.

- Router: auth, query params, `response_model`, `session.commit()` after service (same pattern as `invoices.py`).
- Service: all rules in this addendum, `HTTPException` 400/404/409, **no `print()`**, no mid-file imports.
- Service **does not commit** (invoice pattern).
- Do not leave business uniqueness in the router.

Files coder may edit: `schemas/products.py`, `routers/products.py`, `services/product_service.py`, `tests/test_products.py`, extend `tests/test_multi_tenant_isolation.py`. **Do not edit** `models/product.py` unless a later addendum says so. **Do not add Alembic.**

Existing `POST /products` and `POST /products/uom` must keep working for `test_spo.py` / `test_grn.py` / e2e (they POST `{name, internal_sku, base_uom_id}` and `{name, code}`). Prefer **201** (tests already allow 200 or 201). Changing list `GET /products` to `PaginatedResponse` is OK: `data` remains a JSON array.

---

## 13. Tests — `backend/tests/test_products.py`

PostgreSQL only (`invoicesaas_test` / same derivation as existing tests). No SQLite.

Minimum cases:

1. Category / brand / UOM create → get → update → soft-delete; list omits deleted; GET deleted 404.
2. Duplicate category name (non-deleted) 409; UOM duplicate code 409.
3. Product create missing `base_uom_id` 422; UOM from other workspace 404/400.
4. Product list pagination `page`/`per_page`/`pagination` keys; `search` hits SKU.
5. Product PUT; PUT after DELETE 404.
6. Product soft-delete; list excludes; SKU reusable after delete? **Lock: unique is on table without deleted filter** (`uq_workspace_internal_sku` is all rows). **Do not reuse SKU** of a soft-deleted product (409/integrity). Test that.
7. Identifier CRUD: MPN/BARCODE/SUPPLIER_CODE; reject `type=FOO` 422; duplicate type+value 409; other workspace 404.
8. Conversion: factor Decimal; `to_uom_id == base_uom_id` 400; factor `<= 0` 422; body `from_uom_id` 422; second conversion same `to_uom_id` 409.
9. Price: `DEFAULT_SALES` AED Decimal; second list price 409; `USD` 422; `TIER_1` without `min_quantity` 422; `CUSTOMER_SPECIFIC` without `client_id` 422; other workspace client 404.
10. Isolation: workspace B GET/PUT/DELETE A’s product, identifier, conversion, price → 404. Also extend `test_multi_tenant_isolation.py` for at least one child resource.
11. No `Float` in new schema fields (reviewer/grep).
12. UOM delete blocked while product references it (400).

Also keep: `pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` plus existing suite still green. `alembic check` clean (**no new revision**).

---

## 14. Explicit NOT in WP-1

- Frontend, Zod, Products.tsx (`alert` stub stays until WP-2).
- Quotations, LPO/CPO, FTA Tax Invoice PDF, invoice line `product_id`, credit notes, delivery notes.
- Rewriting Alembic `d3e4c7fdb29f` or any historical `down_revision`.
- SQLite, `create_all` in the app, GSD `init-project`.
- `hs_code`, `vat_category`, electrical spec columns, `from_uom_id`.
- Stock embed, `uom_conversion_service` multi-hop, invoice tax default copy.
- Seed UOM list (PCS/MTR/DRUM) — workspace creates UOMs via API.
- **Payment / PDC PUT:** **deferred, untouched.** CLAUDE.md / `business-rules.md` say payments immutable; live `PUT /invoices/{id}/payments/{id}` mutates `status` / `pdc_status`. WP-1 **must not** delete or “fix” that PUT. Log only (this section). Revisit in gaps-doc Phase 9.

---

## 15. Drift log (`domain-model.md` / `api-contracts.md` vs live)

Do **not** rewrite those files in WP-1. Future one-line domain-model note: ProductUOMConversion from-UOM is `Product.base_uom_id`, not a column.

| Paper | Live / WP-1 |
|---|---|
| `from_uom_id` on conversion | **Absent.** Implied base UOM. |
| Conversion `Decimal(10,4)` | `Numeric(14,6)` |
| Identifier Enum + `source` + `is_primary` | `type` str + allow-list; no source/primary |
| `hs_code`, `vat_category`, three UOMs, stock levels, sell/cost on Product | **Absent.** Defer. |
| Price `entity_type` / date range | `price_type` + `client_id` + `min_quantity` |
| GET product `warehouse_stock` | **Out.** Inventory router. |
| Paginated `data.items` | Live `data: []` + `pagination` |
| UOM `dimension` / `is_base` | **Absent.** |
| Category name UNIQUE in DB | Index only; **service 409** |

---

## 16. Alembic

**WP-1: no new revision.** Schema already matches `product.py` via `d3e4c7fdb29f` (in history under HEAD `06c9b4b1dcda`).

If a **future** WP needs `hs_code` / specs / `from_uom_id`: new file, `down_revision = "06c9b4b1dcda"` (or whatever HEAD is then). **NEVER** edit `d3e4c7fdb29f`.

---

## 17. Coder checklist (copy)

1. Report first: `.agents/reports/backend-execution-report.md` (and database report only if someone later adds columns — they should not).
2. Implement §2–§12 against live models.
3. `pytest tests/test_products.py tests/test_multi_tenant_isolation.py -v` on PostgreSQL.
4. Do not start WP-2 until this is green.

**Next after WP-1–3 (not now):** FTA tax invoice on existing invoices, then quotations, then LPO — `.agents/reports/uae-electrical-architecture-gaps-2026-08-31.md`.
