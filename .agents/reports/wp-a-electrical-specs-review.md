# WP-A Electrical Catalogue Spec Columns — Code Review

**Date:** 2026-09-01
**Reviewer:** reviewer subagent
**Scope:** API + Alembic + pytest only. No git commit. No UI. No code changes (no P0).
**Spec:** `architecture/wave-electrical-specs-addendum.md`, `.agents/reports/architect-electrical-specs-note.md`, `.claude/CLAUDE.md`

## Verdict

**APPROVE_WITH_NITS**

WP-B UI **may start**. No P0.

Debit notes (next after A–C) must set `down_revision = "1a30af047312"`, not `b8d5f0c3a216`.

---

## P0 gate (do not start WP-B if any fail)

| Gate | Result |
|---|---|
| Float money / spec columns | **PASS.** `amp_rating` / `cable_size_mm2` are `Optional[Decimal]` + `Numeric(8, 2)`. Cores/poles `Integer`. No `float` / `Float` on the new fields. Not money; not `Numeric(12, 2)`. |
| Isolation 403 | **PASS.** Cross-workspace GET/PUT/DELETE still 404 via `_get_live`. New spec test asserts GET/PUT 404 and `!= 403`. Existing product isolation tests assert DELETE 404. List is JWT `workspace_id` only. |
| Rewritten Alembic history | **PASS.** Credit-notes file hash matches `HEAD` (`8b63842449c06ec02a63591cda923d59bd34d8fc`). `git status` shows no edits under `backend/alembic/versions/` except the new untracked file. Only child of `b8d5f0c3a216` is `1a30af047312`. |
| JSONB `specs` blob | **PASS.** No `specs` column. POST `specs: {}` still 422 (`extra="forbid"`). |
| Invoice / quote / LPO / CN / DN line snapshot columns | **PASS.** Line models unchanged (no spec columns). `_resolve_line` still copies `internal_sku` → `sku_snapshot` only. `git status` does not touch invoice/quote/LPO/CN/DN services or models. |

---

## Checklist

| # | Item | Result |
|---|---|---|
| 1 | Parent exactly `b8d5f0c3a216`; credit-notes file unmodified; no rewrite of older revs | **PASS.** `1a30af047312_add_product_electrical_specs.py` `down_revision = "b8d5f0c3a216"`. Credit-notes blob identical to `HEAD`. `d3e4c7fdb29f` and other older files not in the WP-A diff. Reviewer `alembic heads` → `1a30af047312 (head)`. |
| 2 | `amp_rating` / `cable_size_mm2` Numeric(8,2) not int; cores 1–24; poles 1–4; voltage string regex | **PASS.** Migration and model use `Numeric(8, 2)` / `Integer` / `String(32)`. Pydantic `gt=0`, `max_digits=8`, `decimal_places=2`; `cores` `ge=1, le=24`; `poles` `ge=1, le=4`. Voltage `^[0-9]+(/[0-9]+)?$` after strip; blank → null. Tests: `1.5` / `2.5` mm², `230/400`, `230V` / `11kV` / `230 / 400` → 422. No DB CHECK (addendum lock). |
| 3 | Partial indexes `WHERE col IS NOT NULL`; not `Field(index=True)` | **PASS.** Five `Index(..., postgresql_where=text("… IS NOT NULL"))` on `Product.__table_args__`. Spec columns use `sa_column=Column(...)` with no `index=True`. Migration `create_index(..., postgresql_where=sa.text(...))`. Downgrade drops the five indexes then the five columns. |
| 4 | `extra=forbid`; unknown keys 422; five keys accepted | **PASS.** `ProductCreate` / `ProductUpdate` inherit `StrictModel` (`extra="forbid"`) via `ProductElectricalSpecs`. `hs_code` / `specs` 422 on POST/PUT; `amp_rating` create 201. Live `test_products.py` extra-key tests still green. |
| 5 | List equality AND; omitted param lists nulls; accessory excluded from amp filter | **PASS.** `_apply_spec_filters` ANDs equality. `?cable_size_mm2=10&cores=4` returns cable not breaker; `?amp_rating=63&poles=3` returns breaker not cable; all four together → empty `data`. Accessory (all null) excluded from `?amp_rating=63`. Omitted spec params list everyone. |
| 6 | `search` does not parse `10mm` / `63A` | **PASS.** Search remains ILIKE on `internal_sku` / `name` / `description` only. `search=10mm` does not hit a row whose name/SKU/description lack `10mm` even with `cable_size_mm2=10`. SKU search still works. |
| 7 | Isolation 404 not 403 | **PASS.** Workspace B GET/PUT A’s product 404 (not 403) with spoof `?workspace_id=`. B’s `?amp_rating=63` does not include A’s breaker. DELETE 404 covered by `test_products.py` + `test_multi_tenant_isolation.py` (unchanged). |
| 8 | No `float` / `Float` on new fields | **PASS.** Model `Numeric` / `Integer` / `String`. Schema `Decimal` / `int` / `str`. AST grep test on model + schema files. Reviewer grep: no `Float` in `product.py`. |
| 9 | Invoice/quote/LPO/CN/DN models and `_resolve_line` untouched | **PASS.** Only model change is `backend/app/models/product.py`. `_resolve_line` still `sku_snapshot = product.internal_sku`; description from name; no spec append. Line tables have `sku_snapshot` max 100 only. Frontend has no `amp_rating` / `cable_size_mm2` (WP-B). |
| 10 | Tests hit PostgreSQL and §6 assertions | **PASS.** `TEST_DATABASE_URL` is `DATABASE_URL` if it already ends with `_test`, else `DATABASE_URL + "_test"`. Never SQLite. 11 functions map to addendum §6. Reviewer re-ran: **45 passed** (`test_product_electrical_specs.py` 11 + `test_products.py` 29 + `test_multi_tenant_isolation.py` 5) in 49.61s. |
| 11 | `alembic check` clean; HEAD is `1a30af047312` | **PASS.** Reviewer: `alembic heads` = `1a30af047312 (head)`; `alembic check` = `No new upgrade operations detected` (`PostgresqlImpl`). |

---

## Findings

### Critical (P0)

None.

### Warning

**W1 — Alembic pytest uses app `DATABASE_URL`, not `invoicesaas_test`**

`test_alembic_new_revision_parent_and_check` runs `alembic heads` / `upgrade head` / `check` with `cwd=backend`. `alembic/env.py` points at `settings.DATABASE_URL` (the app database). The rest of the module uses `{DATABASE_URL}_test` + `SQLModel.metadata.create_all`. Same pattern as credit-notes WP-A. Harmless when the app DB is already at this HEAD (this review’s `alembic check` was clean). It is not an isolated test-DB proof of the migration. Do not treat a green pytest as “upgrade head on `_test`”.

### Info / nits (do not block WP-B)

**I1 — List `?voltage=` has no dedicated pytest**

Service equality is implemented (`Product.voltage == voltage` after strip + regex). §6.5 tests mm²+cores and amp+poles AND, not `?voltage=230/400`. WP-B/C should still send the encoded query param; unencoded `/` in the query value is legal but worth encoding in `getProducts`.

**I2 — New isolation test does not DELETE**

Addendum §6.9 asks GET/PUT 404 (shipped). §4.3 also names DELETE. DELETE remains 404 via `_require_live_product`; covered by the existing 29+5 product isolation tests. No extra assertion needed for WP-B.

**I3 — Invalid list `voltage` 422 body is a string `detail`**

Write-body voltage failures go through Pydantic (error list). List uses `Depends(_list_voltage)` → `HTTPException(422, detail=str(exc))`. Status is still 422. WP-B must key off **HTTP 422**, not a specific `error.code`.

**I4 — `routers/products.py` is 556 lines**

Addendum “files &lt; 500” is exceeded by adding five query params to an already-large router. No new routes. Not a behaviour bug.

**I5 — `1.6` A and `search=63A` are untested**

`gt=0` + `Numeric(8, 2)` accept `1.6`. Search does not parse `63A` (same ILIKE path as `10mm`). Optional coverage later; not a WP-B blocker.

**I6 — Pytest schema is `create_all`, not Alembic, on `_test`**

Matches `test_products.py`. Indexes from `__table_args__` are created that way. Linear history is proven by the new revision file + reviewer `alembic check` on the app DB.

---

## What WP-B may rely on

- POST/PUT optional: `amp_rating`, `cable_size_mm2`, `cores`, `poles`, `voltage`. Omit on create → SQL NULL. PUT omit → unchanged; JSON `null` clears. Empty voltage string → null.
- GET `/api/v1/products` optional exact AND query params. Omit = no spec constraint (invoice/quote/LPO pickers keep working).
- `search` is still SKU/name/description ILIKE. Staff find **4C 10mm²** with `cores=4&cable_size_mm2=10`, **63A 3P** with `amp_rating=63&poles=3`.
- `hs_code` / `specs` / `name_ar` still 422.
- Cross-tenant product id → **404**.
- Response includes the five keys (`null` when unset). Decimals are `Decimal` in the API models.
- Do not rebuild `ProductDetailPanel` identifiers/conversions/prices. Do not add spec filters to invoice/quote/LPO pickers.

## Alembic for later WPs

| | |
|---|---|
| New HEAD | **`1a30af047312`** |
| Parent | **`b8d5f0c3a216`** (credit notes; unmodified) |
| Debit notes | `down_revision = "1a30af047312"` |

---

## Test evidence (this review)

```
pytest tests/test_product_electrical_specs.py tests/test_products.py tests/test_multi_tenant_isolation.py
45 passed, 1 warning in 49.61s
```

```
alembic heads  →  1a30af047312 (head)
alembic check  →  No new upgrade operations detected
```

Coder claim **11 + 29 = 40** plus isolation **5** matches this run.
