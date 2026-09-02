# Wave 3: Product Master - Completion Plan

> **Goal:** Finish Wave 3 Product Master (models, schemas, migration, router, frontend) so all tests pass and CRUD works end-to-end.

**Current State:** Models (`product.py`), schemas (`products.py`), router (`products.py`), migration (`d3e4c7fdb29f`), and basic frontend (`Products.tsx`, `products.ts`) **exist but are incomplete**. No product tests. Migration not applied (alembic head at `06c9b4b1dcda`).

---

## Gaps Identified

| Component | Status | Missing |
|-----------|--------|---------|
| Models | ✅ Complete | — |
| Schemas | ⚠️ Partial | Missing: `ProductIdentifier`, `ProductUOMConversion`, `ProductPrice`, `CategoryUpdate`, `BrandUpdate`, `UOMUpdate`, `ProductUpdate` |
| Migration | ✅ Exists (`d3e4c7fdb29f`) | Not applied (down_rev mismatch: `96b45ccabfb7` vs current `06c9b4b1dcda`) |
| Router | ⚠️ Partial | Only GET/POST list; missing: detail, update, delete, search, pagination, identifiers, conversions, prices |
| Frontend | ⚠️ Partial | List only; missing: create/edit modals, category/brand/UOM management, identifiers, conversions, prices |
| Tests | ❌ None | Need: model, schema, router, isolation tests |

---

## Tasks (Bite-Sized)

### 1. Fix Migration & Apply
**Files:** `backend/alembic/versions/d3e4c7fdb29f_add_wave_3_product_master.py`
- Change `down_revision = '06c9b4b1dcda'`
- Run: `cd backend && .venv/Scripts/alembic.exe upgrade head`
- Verify: `cd backend && .venv/Scripts/alembic.exe current` → `d3e4c7fdb29f`

### 2. Complete Schemas (`backend/app/schemas/products.py`)
Add: `ProductIdentifier*`, `ProductUOMConversion*`, `ProductPrice*`, `CategoryUpdate`, `BrandUpdate`, `UOMUpdate`, `ProductUpdate`, `ProductDetailResponse` (with relations).

### 3. Complete Router (`backend/app/routers/products.py`)
Add endpoints:
- `GET /categories/{id}`, `PUT /categories/{id}`, `DELETE /categories/{id}`
- `GET /brands/{id}`, `PUT /brands/{id}`, `DELETE /brands/{id}`
- `GET /uom/{id}`, `PUT /uom/{id}`, `DELETE /uom/{id}`
- `GET /products?search=&page=&size=`, `GET /products/{id}`, `PUT /products/{id}`, `DELETE /products/{id}`
- `GET/POST /products/{id}/identifiers`, `DELETE /products/{id}/identifiers/{id}`
- `GET/POST /products/{id}/conversions`, `DELETE /products/{id}/conversions/{id}`
- `GET/POST /products/{id}/prices`, `DELETE /products/{id}/prices/{id}`

### 4. Backend Tests (`backend/tests/test_products.py`)
- Model CRUD (category, brand, uom, product)
- Workspace isolation (5 tests like `test_product_is_workspace_isolated`)
- Identifier/Conversion/Price CRUD
- Search/pagination
- Run: `cd backend && .venv/Scripts/pytest.exe tests/test_products.py -v`

### 5. Frontend - Category/Brand/UOM Management
**Files:** `frontend/src/pages/Products.tsx`, new `ProductMaster.tsx` or tabs
- Add tabs: Products / Categories / Brands / UOMs
- Create/Edit modals for each with react-hook-form + zod
- Connect to API (`createCategory`, `updateCategory`, `deleteCategory`, etc.)

### 6. Frontend - Product Detail with Identifiers/Conversions/Prices
- Product detail drawer/modal
- Add/remove identifiers (type: BARCODE, QR, SKU, etc.)
- Add/remove UOM conversions (to_uom + factor)
- Add/remove prices (price_type, currency, price, client_id, min_qty)

### 7. Frontend Build & Integration Test
- `cd frontend && npm run build` (must succeed, chunk < 500KB)
- Manual E2E: create category → brand → UOM → product → identifiers → conversions → prices

### 8. Full Test Suite
- `cd backend && .venv/Scripts/pytest.exe tests/ -v` (all pass)
- `cd frontend && npm run build` (success)

---

## Verification Commands

```bash
# Backend
cd backend && .venv/Scripts/alembic.exe upgrade head
cd backend && .venv/Scripts/pytest.exe tests/ -v

# Frontend
cd frontend && npm run build

# Git
git add backend/app/schemas/products.py backend/app/routers/products.py backend/tests/test_products.py frontend/src/pages/Products.tsx frontend/src/api/products.ts
git commit -m "feat(wave-3): complete Product Master CRUD + tests"
```

---

## Risks
- Migration down_rev mismatch — must fix before apply
- Frontend bundle size (currently 1.7MB) — use code-splitting for ProductMaster
- No service layer — router directly uses SQLAlchemy; acceptable for MVP
