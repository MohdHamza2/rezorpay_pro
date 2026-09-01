# Architect note — Electrical catalogue spec columns

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-electrical-specs-addendum.md`

## Alembic

**YES.** Live `Product` has no amp/mm²/cores/poles/voltage (`product.py`; Wave 3 §7 deferred them; write bodies still 422 on those keys). New revision only: **`down_revision = "b8d5f0c3a216"`**. Never rewrite CN/DN/credit/LPO/FTA/AR/PDC/pricing/PDF history. After this WP, debit notes parent the **new** revision id. PDC/AR/volume/bilingual added no migration; HEAD is still credit notes.

## Columns (live `products`, all nullable)

| Column | Type | Why |
|---|---|---|
| `amp_rating` | Numeric(8,2) | Not int — 1.6A fuses; `?amp_rating=63` still matches 63.00 |
| `cable_size_mm2` | Numeric(8,2) | 1.5 / 2.5 mm² cannot be int |
| `cores` | Integer 1–24 | 4C → 4 |
| `poles` | Integer 1–4 | 3P → 3; 4P = 3P+N |
| `voltage` | String(32) | **Not** `voltage_v` int — UAE breakers are 230/400 dual-rate. Canonical `230/400`, `11000` for 11kV. Regex `^[0-9]+(/[0-9]+)?$` |

No second table. No `product_type`. Null specs = accessories / unset.

## Reject JSONB `specs`

Typed filters need btree equality. A blob reopens Wave 3 `extra="forbid"` (hs_code / junk). IP/kA/drum later as typed columns if ever.

## API

Create/update accept the five keys; `extra="forbid"` stays (`hs_code` / `specs` still 422). GET list adds exact AND query params. **`search` stays ILIKE sku/name/description** — do not parse `10mm` / `63A`. MEMBER+ same as GET product. Isolation 404.

## Invoice snapshot

**No.** `_resolve_line` copies SKU → `sku_snapshot`, name, UOM, tax only. Do not grow SENT line columns or stuff specs into `sku_snapshot`. Catalogue search only.

## WP split (A not skipped)

- **A** Model + Alembic + schemas + list filters + `test_product_electrical_specs.py`. No frontend until pytest green.
- **B** Product form + list filter toolbar + one Specs column. Do not rebuild `ProductDetailPanel` pricing/identifiers.
- **C** Playwright: create 4C 10mm² cable and 63A 3P breaker; filters find them. `product-isolation.spec.ts` unchanged. Docker 8000 / Postgres 5434 / Vite 5173. Never SQLite.

Out: debit notes (next), Peppol, WhatsApp, `*_ar` names, hs_code/vat_category, UOM conversion, PDF, PDC, volume pricing.
