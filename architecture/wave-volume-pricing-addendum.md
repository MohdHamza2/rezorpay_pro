# Volume / Customer Pricing — Architecture Addendum (Gap 8)

**Date:** 2026-09-01
**Status:** Coordinator lock. Coder implements **this file**.
**Extends:** live `ProductPrice` / `PriceType` / `InvoiceService._line_unit_price` / `_resolve_line` (already imported by quotations + LPO) / FTA `money()` / optional line `unit_price`. Do **not** invent `TIER_2`, a second price table, purchase/SPO prices, or a `price_source` column on document lines.
**Depends on:** PDC truth A–C on master (`ab5129928cbb5952d594f237671f664174e33555`), AR statement (no revision), tax credit notes (`b8d5f0c3a216`), DN, credit HOLD, LPO, quotes, FTA tax invoices, Product Master.
**After this WP A–C:** bilingual PDF (gap 13). Not this slice: electrical spec columns (amp/mm²), debit notes, WhatsApp, Peppol, PDC changes, re-pricing SENT invoices.

Copy the PDC/AR split: **WP-A API+pytest → WP-B UI → WP-C Playwright**. Do not start WP-B until WP-A pytest is green. **Alembic: no.**

UAE electrical wholesale sells the same SKU at **list**, **volume breaks**, and **dealer (customer) prices**. `ProductPrice` CRUD already exists. Documents still copy **DEFAULT_SALES only**. This WP wires `PricingService.resolve` so omitted `unit_price` on catalog lines becomes CUSTOMER_SPECIFIC / TIER_1 / DEFAULT_SALES by quantity + client.

---

## 0. Runtime truth (lock against live code)

| Source | Truth |
|---|---|
| `models/product.py` `ProductPrice` | Columns: `workspace_id`, `product_id`, `price_type` str, `currency` default AED, `price` Numeric(12,2), optional `client_id`, optional `min_quantity` Numeric(12,2). **No** `deleted_at`, date range, `TIER_2`, `max_quantity`. |
| Alembic `d3e4c7fdb29f` | Created `product_prices`. Already an ancestor of HEAD. **No new columns needed.** |
| Alembic HEAD | **`b8d5f0c3a216`** (`b8d5f0c3a216_add_credit_notes.py`). PDC + AR statement added **no** revision. This WP adds **none**. Later WPs `down_revision = "b8d5f0c3a216"`. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC history. |
| `schemas/products.py` `PriceType` | **DEFAULT_SALES**, **TIER_1**, **CUSTOMER_SPECIFIC** only. Volume = **multiple TIER_1 rows** with different `min_quantity`. Do **not** add `TIER_2`. |
| Wave 3 uniqueness (live `ProductService._assert_price_unique`) | DEFAULT_SALES: `client_id` null, at most one per product, `min_quantity` omitted. TIER_1: `client_id` null, `min_quantity` > 0, unique `(product_id, TIER_1, min_quantity)`. CUSTOMER_SPECIFIC: `client_id` required, unique `(product_id, client_id, min_quantity)` treating **null min as 0**. Currency **AED** only. |
| `InvoiceService._line_unit_price` | Explicit `unit_price` **wins**. Else `_default_sales_price` only. **Ignores** TIER_1 and CUSTOMER_SPECIFIC. **Does not receive `client_id`.** |
| `_resolve_line` | Shared. `quotation_support.add_items` and `customer_po_support.add_items` already call it (`line_owner` quotation/lpo). Hooking resolve here covers invoice **and** quote **and** LPO create/PUT. |
| Convert freeze | `quotation_support.frozen_invoice_items` and `customer_po_support.slice_invoice_items` pass **explicit** `unit_price`. `_line_unit_price` therefore must **not** re-price convert / LPO→invoice. |
| Credit notes | Copy invoice line `unit_price`. Do **not** call `_resolve_line`. |
| Delivery notes | **No** unit price. Untouched. |
| `ProductService.list_prices` + GET product `prices[]` | Returns **all** workspace rows including every CUSTOMER_SPECIFIC. Any JWT (`get_current_workspace_id`). **T7 leak if this were a customer portal.** It is B2B back-office. |
| Frontend | `ProductDetailPanel` already CRUDs list / volume / customer prices. Invoice / quote / LPO forms call `getProductPrices` and pick **DEFAULT_SALES only** (`Invoices.tsx` `handleProductPick`, same in `QuotationForm.tsx` / `LpoForm.tsx`). |
| `InvoiceItemCreate` | `unit_price` optional iff `product_id`. `QuotationItemCreate` / `CustomerPurchaseOrderItemCreate` **inherit** that. Response `unit_price` remains required (stored). |
| `ErrorCode.NO_LIST_PRICE` | Already exists. Reuse. |
| Isolation | Cross-workspace GET/PUT → **404**, never 403. |
| Roles | Product + sales GETs: OWNER / ADMIN / MEMBER (any active JWT). No product RBAC today. |
| Money | `line_money.money()` ROUND_HALF_UP fils. Never float. Never SQLite. Docker API **8000**, Postgres **5434**. |

FTA tax-invoice addendum: omit `unit_price` copies **DEFAULT_SALES only**; Wave 3 engine was **deferred**. This WP is that engine. Explicit override still wins (FTA lock).

CLAUDE.md: Decimal `Numeric(12,2)`; wrapper `{success, data, error}`; isolation **404 not 403**; never SQLite; `workspace_id` from JWT only.

---

## 1. ASCII — resolve then persist frozen unit_price

```
  DRAFT invoice / quotation / LPO
  line: product_id set, unit_price omitted
  header: client_id
           │
           ▼
  PricingService.resolve(workspace_id, product_id, client_id, quantity)
           │  filter workspace_id; AED; qty ≥ min (null min = 0)
           │  first match wins:
           │    1. CUSTOMER_SPECIFIC for THIS client_id, highest min_quantity
           │    2. TIER_1 with client_id IS NULL, highest min_quantity
           │    3. DEFAULT_SALES
           │    else 422 NO_LIST_PRICE
           ▼
  persist line.unit_price = money(resolved)
  (do NOT persist price_type — no new column)

  Explicit unit_price in body  →  skip resolve (FTA lock)
  product_id omitted           →  unit_price required (unchanged)
  quote convert / LPO→invoice  →  pass frozen unit_price (skip resolve)
  SEND / CN / DN               →  do not resolve
  SENT PUT                     →  403 INVALID_STATE (unchanged)

  Preview (staff form):
  GET /products/{id}/resolved-price?client_id=&quantity=
           → one row { unit_price, price_type, min_quantity }
           → never other clients' CUSTOMER_SPECIFIC
           → other workspace product/client → 404
```

---

## 2. Alembic — **NO**

**Decision: no new revision. HEAD stays `b8d5f0c3a216`.**

Justification (existing columns suffice):

| Need | Live column |
|---|---|
| List vs volume vs dealer | `price_type` (str allow-list, not a PG ENUM) |
| Dealer identity | `client_id` FK `clients.id` |
| Volume break | `min_quantity` (multiple TIER_1 rows) |
| Money | `price` Numeric(12,2) |
| Tenant | `workspace_id` |
| Currency | `currency` (AED only on write) |

Do **not** add: `TIER_2`, `valid_from`/`valid_to`, `max_quantity`, `price_source` on `invoice_items` / `quotation_items` / `customer_purchase_order_items`, purchase/cost price types.

If a later WP needs those, new file `down_revision = "b8d5f0c3a216"` (or then-HEAD). **Never** edit `d3e4c7fdb29f` or CN/DN/credit/LPO/FTA revisions.

`alembic check` must stay clean.

---

## 3. `PricingService.resolve` — lock

**New** `backend/app/services/pricing_service.py`. Service does not commit. Router commits only for writes (preview is read-only).

```
async def resolve(
    session,
    workspace_id: UUID,
    product_id: UUID,
    client_id: Optional[UUID],
    quantity: Decimal,
) -> ResolvedPrice
```

`ResolvedPrice` (dataclass or Pydantic, not a table): `unit_price`, `currency="AED"`, `price_type`, `min_quantity` (optional), `price_id` (winning `ProductPrice.id`).

`unit_price = money(row.price)` from `app.services.line_money`. Quantity is Decimal; compare as Decimal. Never float.

### 3.1 Load / isolation (before matching)

1. Product: `id == product_id`, `workspace_id == JWT`, `deleted_at IS NULL` else **404** `"Product not found"`.
2. Inactive product: **do not** 400 inside `resolve` itself — document add already 400s in `_load_invoice_product`. Preview GET **does** 400 `VALIDATION_ERROR` `field=product_id` with the same “cannot add inactive product” idea so the form does not fill a dead SKU. Deleted / other-workspace stays **404**.
3. If `client_id` is not None: client must exist, same workspace, `deleted_at IS NULL` else **404** `"Client not found"`. Cross-tenant client is 404, **not** silent skip (skipping would look like “no dealer price”).
4. `quantity` must be `> 0` else **422** `VALIDATION_ERROR` `field=quantity`.

### 3.2 Qualifying a row

- `ProductPrice.workspace_id == workspace_id`
- `ProductPrice.product_id == product_id`
- `currency == "AED"` (ignore any non-AED debris)
- `qty >= min_qty` where `min_qty = min_quantity if min_quantity is not None else 0`

**Highest `min_quantity` wins** inside a bucket: treat null as 0, then pick the qualifying row with the greatest min. Unique constraints make ties impossible; if debris ties, pick a stable order (`id` ASC) and do not return two rows.

### 3.3 Precedence (first bucket that has a qualifying row)

1. **CUSTOMER_SPECIFIC** where `client_id == resolve.client_id` (and `resolve.client_id` is not None). If `resolve.client_id` is None, **skip this bucket entirely**.
2. **TIER_1** where `client_id IS NULL`.
3. **DEFAULT_SALES** (`client_id` must be null; `min_quantity` null/0 — Wave 3 forbids min on list).
4. Else **422** `NO_LIST_PRICE` `field=product_id`. Message: product has no matching sales price for this quantity/client. Keep the error **code**.

**Never** use CUSTOMER_SPECIFIC for a different client. Customer A’s 80 AED row must not apply to B even if it is cheaper. TIER_1 is workspace-wide, not per client.

Do **not** walk TIER_2. Do **not** invent DEALER as a fourth type (Wave 3: CUSTOMER_SPECIFIC is the dealer row).

### 3.4 Worked example (WP-C / pytest fixture)

Product P:

| price_type | client | min_quantity | price |
|---|---|---|---|
| DEFAULT_SALES | — | — | 100.00 |
| TIER_1 | — | 10 | 90.00 |
| CUSTOMER_SPECIFIC | A | 1 | 80.00 |

| Call | Result |
|---|---|
| client A, qty 1 | 80 CUSTOMER_SPECIFIC |
| client A, qty 10 | **80 CUSTOMER_SPECIFIC** (customer beats tier) |
| client B, qty 10 | 90 TIER_1 |
| client B, qty 1 | 100 DEFAULT_SALES |
| client None, qty 10 | 90 TIER_1 (preview before client pick) |
| no rows at all, unit_price omitted | 422 NO_LIST_PRICE |

If A also has CUSTOMER_SPECIFIC min 50 → 70, then A qty 10 stays 80; A qty 50 → 70 (highest qualifying customer min).

---

## 4. Explicit `unit_price` always wins

FTA lock. Resolve **only** when:

- `unit_price` is **omitted** (JSON null / key absent), **and**
- `product_id` is set.

Ad-hoc lines (no `product_id`): `unit_price` still required (existing 422). Do not resolve.

`unit_price: 12.50` with `product_id` → persist 12.50 even if list is 100. Convert and LPO→invoice **must** keep passing explicit frozen prices so a later DEFAULT_SALES change cannot move a SENT-bound commercial number on a new DRAFT child.

Do **not** re-price:

| Path | Why |
|---|---|
| `POST /quotations/{id}/convert-to-invoice` | `frozen_invoice_items` already sets `unit_price` |
| `POST /quotations/{id}/convert-to-lpo` | `copy_quote_item` copies `unit_price` |
| `POST /customer-purchase-orders/{id}/invoices` | `slice_invoice_items` sets `unit_price` |
| `POST /invoices/{id}/send` | status + FTA snapshots only |
| Credit note create | copies invoice line money |
| Delivery note | no price |
| PUT non-DRAFT invoice / non-DRAFT quote / non-DRAFT LPO | already 403 |
| PUT LPO-linked invoice | already 403 (delete DRAFT + re-post remaining) |

**Re-pricing SENT invoices: out of this WP.**

---

## 5. Where it runs (hook)

**Single hook:** extend `_line_unit_price` / `_resolve_line` to take document `client_id` and line `quantity`, then call `PricingService.resolve` when `unit_price` is omitted.

| Caller | Pass `client_id` from |
|---|---|
| `invoice_service._add_items` (create + `update_draft` item replace) | `invoice.client_id` |
| `quotation_support.add_items` (create + DRAFT PUT) | `quotation.client_id` |
| `customer_po_support.add_items` (create + DRAFT PUT) | `lpo.client_id` |

`update_draft` applies header patch **before** replacing items — a same-request client change uses the **new** client for resolve. PUT client without `items` does **not** rewrite stored line prices (already persisted). WP-B re-resolves dirty-undirty lines in the form before save.

Replace `_default_sales_price` as the omit-price path. It may remain a private helper used only as bucket 3 inside `PricingService`.

Do **not** duplicate resolve in three document services.

AED-only documents stay as today (422 if not AED).

---

## 6. T7 isolation — lock

Gaps T7: *Customer A must never see Customer B’s price.*

This product is a **staff back-office**, not a customer portal. MEMBER already `GET /clients` for the whole workspace. `ProductDetailPanel` must list every dealer card to CRUD them.

### 6.1 GET `/products/{id}/prices` and GET product `prices[]`

**Keep today’s behaviour for OWNER, ADMIN, and MEMBER:** return **all** workspace prices for that product (DEFAULT_SALES + TIER_1 + every CUSTOMER_SPECIFIC).

**Reason:**

1. Inventing MEMBER-vs-ADMIN price RBAC would break live Product Master CRUD (no product-role gate exists; PDC/CN already use OWNER/ADMIN only where money/status is dangerous).
2. Filtering MEMBER would hide dealer prices they need to enter quotes for those clients.
3. T7 is **not** “staff cannot see the dealer book.” It is “never **apply** or **preview-leak** client B’s row while working as client A, and never cross workspace.”

Do **not** filter `list_prices` this WP.

### 6.2 Resolve (must)

- `WHERE workspace_id = JWT`.
- CUSTOMER_SPECIFIC **only** if `ProductPrice.client_id ==` the document/preview client.
- Never fall back to “any customer’s best price.”
- Cross-tenant product or client → **404**.

### 6.3 Preview GET (must)

Response is **one** winning price + `price_type` used. **No** array of other CUSTOMER_SPECIFIC rows. No `alternates`. No other `client_id` in the payload.

Workspace B token + workspace A `product_id` → **404** (same as GET product).

---

## 7. Preview API — **in WP-A** (required, not a later extra)

WP-B must not client-side `prices.find(DEFAULT_SALES)` or scan all CUSTOMER_SPECIFIC rows (easy to apply the wrong dealer). Server owns precedence.

```
GET /api/v1/products/{product_id}/resolved-price?client_id={uuid?}&quantity={decimal}
```

Auth: Bearer. JWT workspace only. Register next to `GET /{product_id}/prices` (nested path **before** is already how `/prices` is mounted).

| Query | Rule |
|---|---|
| `quantity` | **Required**, Decimal `> 0`. Missing/≤0 → 422. |
| `client_id` | Optional. Omitted → skip CUSTOMER_SPECIFIC (volume then list). Present → live same-workspace client or **404**. |

Success `SuccessResponse`:

```json
{
  "success": true,
  "data": {
    "product_id": "<uuid>",
    "client_id": "<uuid or null>",
    "quantity": "10.00",
    "unit_price": "90.00",
    "currency": "AED",
    "price_type": "TIER_1",
    "min_quantity": "10.00",
    "price_id": "<uuid>"
  }
}
```

`price_type` is the **winning** enum value. `min_quantity` null for DEFAULT_SALES. Extra keys on query ignored; extra body N/A (GET).

Errors: 404 product/client isolation; 400 inactive; 422 NO_LIST_PRICE / bad qty. Do not 403 for isolation.

---

## 8. Module boundaries

| Layer | Owns |
|---|---|
| `routers/products.py` | Preview GET only (HTTP, wrapper). Price CRUD unchanged. |
| `services/pricing_service.py` | Resolve + isolation + precedence. |
| `invoice_service._line_unit_price` | Explicit win; else `resolve`. Pass `client_id`. |
| `quotation_support` / `customer_po_support` | Pass `quotation.client_id` / `lpo.client_id` into `_resolve_line`. |
| `ProductService.list_prices` | **Unchanged** (staff dealer book). |
| Models | **Do not edit** `product.py`. |

Files < 500 lines. No mid-file imports. No `print()`. JSON logs: `product_id`, `price_type`, `workspace_id` — **not** full client/user objects, not tokens.

Schemas: `ResolvedPriceResponse` in `schemas/products.py`. `extra="forbid"` on any new write body (preview has none).

---

## 9. Tests — `backend/tests/test_pricing.py` (+ isolation)

PostgreSQL only (`invoicesaas_test` / existing derivation). **Never SQLite.**

Minimum cases:

1. Fixture product: DEFAULT_SALES 100, TIER_1 min 10 → 90, CUSTOMER_SPECIFIC client A min 1 → 80.
2. Invoice DRAFT create for **A**, omit `unit_price`, qty 1 → stored **80**. Qty 10 omit price → **80** (customer beats tier).
3. Invoice for **B**, omit price, qty 10 → **90** (not 80). Qty 1 → **100**.
4. Explicit `unit_price` 12.50 + product_id for A qty 10 → **12.50** stored.
5. Omit `unit_price` and no price rows → **422** `NO_LIST_PRICE`. Ad-hoc line without price still 422.
6. Other-workspace `product_id` on invoice → **404**. Other-workspace `client_id` on preview → **404**.
7. Inactive product on invoice/quote/LPO add → **400** (unchanged). Preview inactive → **400**.
8. Quotation DRAFT create/PUT omit price uses the same precedence as invoices. LPO DRAFT create/PUT same.
9. Quote convert-to-invoice / LPO `/invoices`: stored child `unit_price` **equals** parent even if DEFAULT_SALES is changed to 1.00 **after** the parent was saved (pass explicit; do not re-resolve).
10. Preview GET: A qty 10 → `{unit_price: 80, price_type: CUSTOMER_SPECIFIC}` and **no** other client ids in `data`. B qty 10 → 90 / TIER_1.
11. Workspace B GET `/products/{A_product}/resolved-price` → **404**. Extend `test_multi_tenant_isolation.py`.
12. MEMBER JWT: GET `/prices` still lists A and B dealer rows (documents the T7 staff-book decision). MEMBER invoice for B still 90 not 80.
13. No `Float` on new schema fields. `alembic check` clean (**no new revision**).

Keep `test_invoices.py` / `test_quotations.py` / `test_customer_purchase_orders.py` green (they already seed DEFAULT_SALES and often send explicit prices).

---

## 10. WP split

### WP-A — API + pytest

`PricingService`, hook `_line_unit_price` + pass `client_id` from invoice/quote/LPO, preview GET, tests §9. **No frontend. No Alembic. No model column edits.**

**Acceptance:** pytest §9 green; existing sales suite green; `alembic check` (HEAD still `b8d5f0c3a216`); A qty 10 → 80; B qty 10 → 90; explicit 12.50 kept; convert frozen; cross-tenant preview 404; Decimal money.

### WP-B — UI (after A green)

- Invoice / quotation / LPO **line**: picking a product fills `unit_price` from **preview GET** (`client_id` + qty), not `getProductPrices` → DEFAULT_SALES.
- Changing **qty** or **header client** re-calls preview and fills price **until** the user dirty-overrides that line’s price.
- Product pick resets dirty and re-resolves.
- Show which rule matched: List (`DEFAULT_SALES`) / Volume (`TIER_1`) / Customer (`CUSTOMER_SPECIFIC`). Dirty override label **Override** (do not pretend it is still list).
- **Do not rebuild** `ProductDetailPanel` price CRUD.
- Types + `getResolvedPrice` in `frontend/src/api/products.ts`. Shared helper OK if it avoids copying the dirty/preview logic three times.

**Acceptance:** `npm run build`; catalog line with client A qty 10 shows 80 and “Customer”; switching client to B without dirty shows 90 “Volume”; typing 12.50 stays 12.50 when qty changes.

### WP-C — Playwright

Register workspace A → clients A and B → product with the §3.4 prices.

- Invoice (or quote) for **A** qty 1 → line 80; qty 10 still 80.
- Invoice for **B** qty 10 → 90.
- Explicit override 12.50 kept after qty change (dirty).
- Second workspace GET resolved-price (or open product URL) → **404**.

`API_URL` `http://localhost:8000`. Postgres **5434**. Never SQLite. Do not cover electrical specs, bilingual, debit notes, WhatsApp, Peppol, PDC, SENT re-price.

**Acceptance:** local API + Postgres. Isolation spec separate file OK (`volume-pricing-isolation.spec.ts`).

---

## 11. NOT in this WP

- Electrical spec columns (`amp_rating`, `cable_size_mm2`, cores, poles, `specs`)
- Bilingual / Arabic PDF (gap 13 — **next** after A–C)
- Debit notes, WhatsApp, Peppol, PINT-AE
- PDC record/clear/bounce changes
- Re-pricing SENT (or non-DRAFT) invoices
- `TIER_2` / changing `PriceType` enum (use multiple TIER_1)
- Purchase / SPO / cost prices
- Customer portal, public price list, hiding dealer book from MEMBER
- `price_source` snapshot column
- Header-level discount, USD tax invoices
- UOM conversion on the line (qty stays in base UOM as today)

---

## 12. Drift vs paper

| Paper | This WP |
|---|---|
| Gaps §4.3 `price_type in TIER_*` | **TIER_1 only**; multiple rows = volume |
| Gaps Phase 2 bundles specs + pricing_service | Specs **out**; pricing_service **in** |
| FTA addendum list price only | **Superseded for omit-price copy**; explicit override unchanged |
| Quotes/LPO “do not re-price on convert” | **Kept** — explicit frozen `unit_price` |
| T7 “never return other clients’ ProductPrice” | **Resolve + preview.** Staff GET `/prices` still returns the dealer book |
| `domain-model.md` `entity_type` / date range | **Out** — live `price_type` + `client_id` + `min_quantity` |

---

## 13. Coder checklist

1. Report first: `.agents/reports/backend-execution-report.md` (no database report — no migration).
2. Alembic **NO**. Do not touch `models/product.py`. HEAD `b8d5f0c3a216`.
3. One resolve function; hook `_line_unit_price`; convert paths keep explicit prices.
4. Preview GET returns one price + `price_type`. Isolation 404.
5. WP-A tests green before WP-B.
6. Next after A–C: **bilingual PDF (gap 13)**, not specs or debit notes.
