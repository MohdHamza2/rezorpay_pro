# Electrical Catalogue Spec Columns — Architecture Addendum

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**. Do **not** implement paper `architecture/domain-model.md` Product extras or gaps-doc JSONB `specs`.
**Extends:** live `Product` / `ProductService.list_products` / `ProductCreate` `extra="forbid"` / Products UI. Do **not** fork an Item table, add a second product table, or grow invoice/quote/LPO/CN/DN line snapshots.
**Depends on:** bilingual PDF A–C on master (`be2c1e5e35e632587a3b79d73d2a67b75d3c627f`), volume/customer pricing, PDC pending-until-clear, AR Account Statement, tax credit notes (`b8d5f0c3a216`), DN, credit HOLD, LPO, quotes, FTA tax invoices, Product Master.
**After this WP A–C:** debit notes. Not this slice: Peppol, WhatsApp, bilingual party `*_ar` names, PDC, volume pricing, bilingual PDF changes, `hs_code` / `vat_category` (e-invoice pack later), UOM conversion changes.

Copy split: **WP-A API+Alembic+pytest → WP-B UI → WP-C Playwright**. Do not start WP-B until WP-A pytest is green. **Alembic: YES.**

UAE electrical wholesale staff search the catalogue as **4C 10mm²** (cable) and **63A 3P** (breaker). Wave 3 Product Master **rejected** these columns (`architecture/wave-3-product-master-addendum.md` §7 / §2.4 — write bodies `extra="forbid"` so unknown keys 422). This WP is that allowed later extension: typed nullable columns on the live `products` table plus list filters.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `backend/app/models/product.py` `Product` | `internal_sku`, `name`, `description`, `category_id`, `brand_id`, `base_uom_id`, `is_active`, `tax_rate` Numeric(5,2), `reorder_level` Numeric(12,2), timestamps, `deleted_at`. **No** `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage`, `specs`, `hs_code`, `name_ar`. Unique `(workspace_id, internal_sku)`. |
| Alembic `d3e4c7fdb29f` | Created `products`. Indexes: `workspace_id`, `internal_sku`, `name`, `category_id`, `brand_id`, `base_uom_id`. **Ancestor of HEAD. Do not edit.** |
| Alembic HEAD | **`b8d5f0c3a216`** (`b8d5f0c3a216_add_credit_notes.py`). PDC, AR statement, volume pricing, bilingual PDF added **no** revision. This WP **adds one new file** with `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC/pricing/PDF history. |
| Wave 3 §2.4 / §7 | Create required: `internal_sku`, `name`, `base_uom_id`. Electrical identity lived in SKU + name + description. Spec keys on POST/PUT → **422**. |
| `schemas/products.py` | `ProductCreate` / `ProductUpdate` `extra="forbid"`. Live tests: `hs_code` on create/PUT → 422. |
| `routers/products.py` GET `""` | Query: `search`, `category_id`, `brand_id`, `is_active`, `page`, `per_page`. **No** spec filters. Auth: `get_current_workspace_id` (any active JWT: OWNER / ADMIN / **MEMBER**). |
| `ProductService.list_products` | `search` = ILIKE `internal_sku` **OR** `name` **OR** `description`. Other filters AND. `deleted_at IS NULL`. Default **no** `is_active` filter. |
| PUT product | `model_dump(exclude_unset=True)`. JSON `null` clears; omit leaves unchanged. Same as `tax_rate`. |
| `InvoiceService._resolve_line` | Catalog line copies `internal_sku` → `sku_snapshot`, `name` → description if omitted, `base_uom_id` → `uom_id`, product `tax_rate` if set. **Does not read spec columns.** `sku_snapshot` max 100; tests assert exact SKU. |
| Invoice / quote / LPO / CN / DN items | `product_id`, `uom_id`, `sku_snapshot`, description + money/qty. **No** amp/mm²/cores/poles/voltage columns. |
| Frontend `Products.tsx` | Create/edit form: SKU, name, description, UOM, category, brand, tax, reorder, active. **No** spec fields. List: SKU/name/category/brand/UOM/status. **No** search or filter toolbar (API already has search/category/brand). `ProductDetailPanel` = identifiers / conversions / prices only. |
| Invoice / quote / LPO pickers | `getProducts({ is_active: true, per_page: 100 })`. Must keep working when spec query params are **omitted**. |
| Isolation | Cross-workspace GET/PUT/DELETE product → **404**, never 403. `product-isolation.spec.ts` POSTs `{internal_sku, name, base_uom_id}` only. |
| T7 (gaps) | Customer A must not see Customer B **price**. Unrelated to spec columns (not `ProductPrice`). Do not change `/prices` or resolve. |
| Stack | Docker API **8000**, Postgres **5434**, Vite Playwright **5173**. **Never SQLite.** Wrapper `{success, data, error}`. Decimal never float. |

CLAUDE.md: Alembic-only schema; isolation 404; MEMBER+ same as GET product today; existing SKUs without specs must keep creating.

---

## 1. ASCII — catalogue columns + typed list filters

```
  POST/PUT /api/v1/products
    known keys include amp_rating, cable_size_mm2, cores, poles, voltage
    extra="forbid" still (hs_code, specs, name_ar → 422)
           │
           ▼
  products  (same table — no Item fork)
    nullable spec columns + partial indexes (workspace_id, col) WHERE col IS NOT NULL
           │
           ▼
  GET /api/v1/products?amp_rating=&cable_size_mm2=&cores=&poles=&voltage=
    AND with existing search / category_id / brand_id / is_active
    omitted spec param = no constraint
    equality only (NULL rows drop out of that filter)
           │
           ▼
  Invoice / quote / LPO / CN / DN lines
    UNCHANGED — sku_snapshot stays internal_sku; no spec snapshot columns
```

Staff find **4C 10mm²** with `cores=4&cable_size_mm2=10`. Staff find **63A 3P** with `amp_rating=63&poles=3`. Search string `"10mm"` / `"63A"` is **not** parsed into those columns (§4.3).

---

## 2. Decisions (architect lock)

### 2.1 Columns on live `products` — **typed, all nullable**

Do **not** fork Item. Do **not** add a `product_type` / CABLE vs BREAKER discriminator. Absence of a spec **is** the type: cables fill mm² + cores; breakers fill amp + poles (+ voltage); glands/tape/accessories leave all null.

| Column | SQL | Python / Pydantic | Required | Example |
|---|---|---|---|---|
| `amp_rating` | `Numeric(8,2) NULL` | `Optional[Decimal]` `gt=0`, `max_digits=8`, `decimal_places=2` | **no** | `63` → 63.00 (63A MCB). `1.6` allowed (control fuse). |
| `cable_size_mm2` | `Numeric(8,2) NULL` | same Decimal constraints | **no** | `10` → 10.00 (10mm²). `1.5` / `2.5` **must** work (not Integer). |
| `cores` | `Integer NULL` | `Optional[int]` `ge=1`, `le=24` | **no** | `4` (4C). |
| `poles` | `Integer NULL` | `Optional[int]` `ge=1`, `le=4` | **no** | `3` (3P). 4P = 3P+N. |
| `voltage` | `String(32) NULL` | `Optional[str]` max 32; see §2.2 | **no** | `230/400` (dual-rate breaker). `11000` (11kV). |

**amp_rating is Numeric, not int.** Gaps paper already said Numeric(8,2). Integer would drop 1.6A fuses and force a later migration. List `?amp_rating=63` still matches 63.00 (Numeric equality). **Never `float`.**

These are **not** money. Do **not** use Numeric(12,2). Do **not** add DB CHECK constraints (Wave 3 products have none; Pydantic/service is the gate).

Existing POST `{internal_sku, name, base_uom_id}` stays 201; new columns default SQL NULL.

PUT: omit = unchanged; `"amp_rating": null` clears. Empty string on `voltage` after strip → treat as null (do not store `""`).

### 2.2 Voltage is a **string**, not `voltage_v` int

Paper (`voltage_v` int, notes 230/400/11000) **cannot** store the dominant UAE breaker marking **230/400V** in one integer without lying (230 XOR 400).

**Lock column name `voltage`** (not `voltage_v` — that suffix implies volts-as-int).

Canonical stored form: **digits, optional one slash, no unit suffix, no spaces.**

- Regex after strip: `^[0-9]+(/[0-9]+)?$`
- Store `230`, `400`, `230/400`, `11000` (11kV → 11000). Reject `230V`, `11kV`, `230 / 400` → **422**.
- List filter: **exact** string match (`?voltage=230/400`). No “contains 400”.
- Filter omitted = no constraint.

### 2.3 Reject JSONB `specs` blob

Paper §4.3 listed `specs JSONB` (IP, kA, colour temp, drum length) **plus** typed columns. **Reject the blob this WP.**

1. The user story is typed filters `amp_rating` / `cable_size_mm2` / `cores` / `poles`. Btree partial indexes serve equality. JSONB would need GIN + operators for the same GET.
2. Wave 3 `extra="forbid"` exists so unknown catalogue keys 422. A `specs` object is a back door for `hs_code` / `name_ar` / arbitrary junk.
3. IP / kA / drum length are not this search gap. If a later WP needs them, add **typed nullable columns**, not a bag.

POST/PUT key `specs` remains **422**. Do not add the column.

### 2.4 Invoice / document snapshots — **catalogue only (no)**

FTA send already copies **SKU / name / UOM / tax_rate**, not electrical specs (`_resolve_line`).

**Do not** add spec columns to `invoice_items` (or quote / LPO / CN / DN items). **Do not** stuff `"4C 10mm²"` into `sku_snapshot` (tests assert exact `internal_sku`; column max 100). **Do not** auto-append specs onto line `description` (would mutate Tax Invoice text and FTA Playwright).

SENT invoices do not grow columns. Staff who need specs on a PDF put them in the product **name** (already legal line description) or description override — out of this WP’s API.

Quote convert / LPO→invoice / CN copy / DN copy: untouched.

### 2.5 Search vs filters

**`search` stays ILIKE on `internal_sku`, `name`, `description` only.** Do **not** parse `"10mm"` / `"63A"` / `"4C"` into spec columns (false positives on SKUs like `ELE-63`; `amp_rating::text` would match 630).

Findability for WP-C is **query params**, not search:

```
GET /api/v1/products?cable_size_mm2=10&cores=4
GET /api/v1/products?amp_rating=63&poles=3
```

A product named `4-core 10mm XLPE` can still be found with `search=10mm` via existing ILIKE. A SKU whose **name omits** mm² but has `cable_size_mm2=10` is found **only** via the typed filter. Document that; do not “fix” search.

No range filters (`amp_rating_min`). Equality only. Multiple spec params **AND**. Combining cable filters with breaker filters typically returns empty (correct).

`category_id` / `brand_id` / `is_active` / `search` keep today’s AND semantics.

### 2.6 Roles and T7

Same as GET product: any active JWT (**MEMBER+**). No new RBAC. T7 is prices; spec list is workspace catalogue, not dealer book.

---

## 3. Alembic — **YES**

New revision file only. **`down_revision = "b8d5f0c3a216"`.** Never edit `b8d5f0c3a216_add_credit_notes.py` or any older file.

Suggested message: `add product electrical specs`. Autogenerate **after** the model change, then **edit** the file so:

1. Parent is exactly `"b8d5f0c3a216"` (HEAD today).
2. Five nullable columns as §2.1.
3. Partial indexes below (autogenerate will miss `postgresql_where` unless Indexes are on the model — put them on `Product.__table_args__` next to `uq_workspace_internal_sku` so `alembic check` stays clean).

**Do not** add `Field(index=True)` on spec columns (that creates full indexes that include NULL for every accessory).

| Index name | Columns | Predicate |
|---|---|---|
| `ix_products_workspace_amp_rating` | `workspace_id`, `amp_rating` | `amp_rating IS NOT NULL` |
| `ix_products_workspace_cable_size_mm2` | `workspace_id`, `cable_size_mm2` | `cable_size_mm2 IS NOT NULL` |
| `ix_products_workspace_cores` | `workspace_id`, `cores` | `cores IS NOT NULL` |
| `ix_products_workspace_poles` | `workspace_id`, `poles` | `poles IS NOT NULL` |
| `ix_products_workspace_voltage` | `workspace_id`, `voltage` | `voltage IS NOT NULL` |

No unique on specs (many 10mm² 4C cables). No rewrite of `d3e4c7fdb29f`. Downgrade: drop the five indexes, drop the five columns.

After merge, debit notes must `down_revision` = **this new revision id**, not `b8d5f0c3a216`.

---

## 4. API

Base `/api/v1`. Existing `/products` prefix. Wrapper + `PaginatedResponse`. Extra unknown keys **422**. Cross-tenant **404**. JWT workspace only (ignore query `workspace_id`).

No new routes.

### 4.1 Write bodies

`ProductCreate` / `ProductUpdate`: add the five fields as **optional**. `extra="forbid"` **stays**.

Still 422: `hs_code`, `vat_category`, `specs`, `name_ar`, `from_uom_id`, `track_inventory`, and any other unknown key.

Invalid spec (amp ≤ 0, cores 0, poles 5, voltage `230V`) → **422** (Pydantic). Do not 400 from the service for those.

Response `ProductResponse` / `ProductDetailResponse`: include the five fields (JSON `null` when unset). List rows use `ProductResponse` (already). Decimal JSON number or string OK; models stay Decimal.

Create still **201**. Nested identifier / conversion / price / resolved-price: **untouched**.

### 4.2 GET list query

Add optional params (omit = no filter):

| Param | Type | Match |
|---|---|---|
| `amp_rating` | Decimal | `Product.amp_rating == value` |
| `cable_size_mm2` | Decimal | equality |
| `cores` | int | equality |
| `poles` | int | equality |
| `voltage` | str | exact (strip; same regex if non-empty) |

Keep: `search`, `category_id`, `brand_id`, `is_active`, `page`, `per_page`.

Pass through `ProductService.list_products`. Invalid query types → 422.

### 4.3 Isolation

Workspace B GET/PUT/DELETE A’s product → 404. List is already scoped by JWT `workspace_id` (B’s `?amp_rating=63` cannot return A’s rows). Ignore `workspace_id` query param.

---

## 5. Module boundaries

| Layer | Owns |
|---|---|
| `models/product.py` | Five columns + five partial Indexes in `__table_args__`. Import `Integer` / `Index` / `text` as needed. |
| New Alembic revision | Columns + indexes; `down_revision = "b8d5f0c3a216"` |
| `schemas/products.py` | Optional fields + voltage validator; `extra="forbid"` |
| `routers/products.py` | List query params only (HTTP) |
| `product_service.py` | Persist + AND filters. No commit. No `print()`. |
| `InvoiceService` / quote / LPO / CN / DN / PDF / pricing | **Do not touch** |
| `Products.tsx` + `api/products.ts` | WP-B form + list filters |
| `ProductDetailPanel.tsx` | **Do not rebuild** identifiers / conversions / prices |

Files < 500 lines. All imports at top. `black` + `ruff` on Python.

---

## 6. Tests — WP-A `backend/tests/test_product_electrical_specs.py`

PostgreSQL only (`invoicesaas_test` / same as existing). Never SQLite. Reuse `_register` / `_create_uom` patterns from `test_products.py` (import helpers or duplicate the small register/uom/product helpers in the new file — do not refactor `test_products.py`).

Minimum cases:

1. Create **without** specs (Wave 3 payload) → 201; GET shows all five keys **null**. Existing `_create_product` contract unbroken.
2. Create cable `cable_size_mm2=10`, `cores=4`; breaker `amp_rating=63`, `poles=3`, `voltage="230/400"`. GET/list echo Decimal/int/str correctly. `1.5` mm² and `2.5` mm² accepted.
3. POST/PUT `hs_code` still 422; POST `specs: {}` 422; POST `amp_rating` as known key **not** 422.
4. `amp_rating=0` / negative / `cores=0` / `poles=5` / `voltage="230V"` → 422.
5. List `?cable_size_mm2=10&cores=4` returns the cable, **not** the breaker. `?amp_rating=63&poles=3` returns the breaker, **not** the cable. AND of all four spec filters on those two rows → empty `data`.
6. Accessory (all specs null) **excluded** from `?amp_rating=63`. Omitted spec params still list everyone (including nulls).
7. `search` still hits SKU; `search=10mm` does **not** find a row whose name/SKU/description lack `10mm` even if `cable_size_mm2=10`.
8. PUT `"amp_rating": null` clears; omit on PUT leaves value.
9. Isolation: workspace B GET/PUT A’s product 404 (not 403). B’s list `?amp_rating=63` does not include A’s breaker.
10. No `float` / `Float` on new schema or model fields (grep).
11. `alembic check` clean against the **new** HEAD. `backend/alembic/versions/` still contains `b8d5f0c3a216_add_credit_notes.py` **unmodified**. Exactly one new revision whose `down_revision == "b8d5f0c3a216"`.

Also keep `pytest tests/test_products.py tests/test_multi_tenant_isolation.py` green (create-without-specs, extra-key 422, pagination).

---

## 7. WP-B UI (after A green)

`frontend/src/pages/Products.tsx` + `frontend/src/api/products.ts` (+ CSS if needed).

**Form (create/edit modal):** optional inputs Amp, Cable mm², Cores, Poles, Voltage. Empty → omit on create; empty → JSON `null` on update (so staff can clear). Zod optional; do not require specs. Testids:

- `product-amp-input`
- `product-mm2-input`
- `product-cores-input`
- `product-poles-input`
- `product-voltage-input`

**List filters:** toolbar on the Products tab. Same five fields + Apply + Clear. Testids:

- `product-filter-amp`
- `product-filter-mm2`
- `product-filter-cores`
- `product-filter-poles`
- `product-filter-voltage` (optional to fill in WP-C)
- `product-filter-apply`
- `product-filter-clear`

Wire into `getProducts` query key so Apply refetches. Clear omits spec params.

**List column:** one **Specs** cell, compact, not five empty columns:

- cores + mm² → `{cores}C {mm2}mm²` (strip trailing zeros; use `mm²` in UI)
- amp + poles → `{amp}A {poles}P`
- voltage if set → append ` {voltage}V` only in the **display** string (stored value has no `V`)
- else `—`

**Do not** rebuild `ProductDetailPanel` pricing/identifiers/conversions. **Do not** add spec filters to invoice/quote/LPO product pickers. **Do not** rebuild category/brand/UOM tabs.

`Product` / `ProductWrite` / `ProductListQuery` types gain the five optional fields. `listParams` passes them when set.

`npm run build`.

---

## 8. WP-C Playwright

New `frontend/e2e/electrical-specs.spec.ts`. Reuse `registerViaUi`, `createUom`, `E2E_PASSWORD` (`Passw0rd1`, 8+). Unique SKUs via `suffix`.

1. Register workspace → UOM PCS (or MTR) → Products tab.
2. Create cable SKU `CBL-4C10-{suffix}`: cores `4`, mm² `10` (name may be anything).
3. Create breaker SKU `MCB-63-3P-{suffix}`: amp `63`, poles `3`. Voltage optional.
4. Filter mm² `10` + cores `4` → Apply → `product-row-CBL-4C10-…` visible; breaker row **not** visible.
5. Clear; filter amp `63` + poles `3` → breaker visible; cable **not** visible.
6. Existing `product-catalog.spec.ts` and `product-isolation.spec.ts` **unchanged** and still green (no spec fields required; isolation still 404 not 403).

`API_URL` `http://localhost:8000`. Postgres **5434**. Vite **5173**. Never SQLite. Do not cover debit notes, Peppol, WhatsApp, bilingual names, hs_code, pricing, PDF.

Optional tiny isolation assertion in the new spec: second workspace GET A’s product id → 404. Do **not** rewrite `product-isolation.spec.ts`.

---

## 9. WP split

### WP-A — API + Alembic + pytest

Model + schemas + router query params + service filters + new Alembic revision + `test_product_electrical_specs.py`. **No frontend.**

**Acceptance:** §6 green; `test_products.py` extra-key + create-without-specs green; `alembic check` clean; HEAD **moves** to the new revision parented on `b8d5f0c3a216`.

### WP-B — UI (after A green)

Form + list filters + Specs column + types. Do not rebuild pricing/identifiers.

**Acceptance:** `npm run build`; staff can save 4C 10mm² and 63A 3P and filter the list.

### WP-C — Playwright

§8. Docker 8000 / Postgres 5434 / Vite 5173.

---

## 10. NOT in this WP

- Debit notes
- Peppol / PINT-AE / WhatsApp
- `name_ar` / party `*_ar` / bilingual PDF changes
- `hs_code` / `vat_category` (e-invoice pack later)
- JSONB `specs`, IP rating, kA, drum length
- Second product / Item table
- Invoice / quote / LPO / CN / DN line spec columns or `sku_snapshot` rewrite
- UOM conversion changes; seed UOM list
- Range search; parsing `search=63A`
- Product picker on invoices/quotes/LPOs
- `ProductDetailPanel` rebuild; volume pricing / PDC / credit HOLD / AR / FTA send gates
- RBAC beyond today’s MEMBER JWT
- SQLite, `create_all`, rewriting old Alembic files

---

## 11. Drift vs paper

| Paper / Wave 3 | This WP |
|---|---|
| Wave 3 §7 “do not invent spec columns” | **Superseded.** This is the later Alembic Wave 3 promised. Do **not** edit `wave-3-product-master-addendum.md`. |
| Wave 3 future `down_revision = "06c9b4b1dcda"` | **Stale.** Parent is **`b8d5f0c3a216`**. |
| Gaps §4.3 `specs` JSONB + `voltage_v` int | **No blob.** `voltage` string for 230/400. |
| Gaps GET `?amp_rating=&cable_size_mm2=` | **In**, plus `cores`, `poles`, `voltage`. |
| Gaps `name_ar` / `hs_code` / `vat_category` on Product | **Still out** (422). |
| Gaps “use on sales lines” | **Out.** Catalogue search only. Lines stay description/sku/uom. |
| T7 customer prices | **Unrelated.** Do not touch `ProductPrice`. |

---

## 12. Coder checklist (copy)

1. Report first: `.agents/reports/backend-execution-report.md` (schema → also note the new revision in that report).
2. Alembic **yes**, `down_revision = "b8d5f0c3a216"` only. Five nullable columns. Five partial `(workspace_id, col)` indexes. Never rewrite old revisions.
3. `extra="forbid"` stays; the five keys become **known**. `hs_code` / `specs` still 422.
4. List filters equality AND. `search` unchanged (name/SKU/description).
5. Invoice snapshots **no**. Do not edit `_resolve_line` or line models.
6. WP-A pytest green before WP-B.
7. Next after A–C: **debit notes** (parent = this WP’s new revision), not Peppol.

**Coder-ready lock**

- Alembic parent: **`b8d5f0c3a216`**
- Columns: `amp_rating Numeric(8,2) NULL`, `cable_size_mm2 Numeric(8,2) NULL`, `cores Integer NULL`, `poles Integer NULL`, `voltage String(32) NULL`
- List filters: `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage` (exact, AND, optional)
- Invoice snapshot: **no** (catalogue only)
