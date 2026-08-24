# Edge Cases — InvoiceSaaS B2B Trading Platform

> Sourced from MASTER_PLAN_V3.md Section 10 and architecture documents.
> Status: Implemented / Partial / Not Yet Implemented (NYI)

---

## Procurement Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| C-1 | SPO item quantity > GRN accepted quantity | 3-Way Match fails with `FAILED_QTY`; invoice blocked | ✅ Implemented |
| C-2 | Invoice price > SPO unit price by >2% | 3-Way Match fails with `FAILED_PRICE`; variance recorded | ✅ Implemented |
| C-3 | Tax amount on invoice differs from SPO VAT rate computation | 3-Way Match fails with `FAILED_TAX`; variance recorded | ✅ Implemented |
| C-4 | Duplicate invoice number for same supplier | HTTP 409 CONFLICT; prevented by unique constraint | ✅ Implemented |
| C-5 | Invoice submitted before GRN is in ACCEPTED/PARTIALLY_ACCEPTED | Match returns `UNRECEIVED_ITEMS` | ✅ Implemented |
| C-6 | Invoice supplier ≠ SPO supplier | Match returns `FAILED_SUPPLIER` | ✅ Implemented |
| C-7 | Invoice currency ≠ SPO currency | Match returns `FAILED_CURRENCY` | ✅ Implemented |
| C-8 | Invoice product ≠ SPO product | Match returns `FAILED_PRODUCT` | ✅ Implemented |
| C-9 | SPO cancelled after GRN created | GRN remains valid (physical receipt already happened) | ✅ Implemented (GRN not blocked) |
| C-10 | GRN linked to SPO in DRAFT/PENDING state | SPO must be in SENT or ACKNOWLEDGED state to link GRN | NYI (validation missing) |
| C-11 | Multiple GRNs for same SPO (partial shipments) | All GRN accepted quantities aggregated for matching | ✅ Implemented (sum in `_match_item`) |
| C-12 | AP manager approves DISCREPANCY invoice directly | Blocked by INV-6.1 rule; must use `resolve-discrepancy` endpoint | ✅ Implemented |
| C-13 | Zero-quantity SPO item | Cannot create SPO item with qty=0 (Pydantic `ge=0`, service checks) | ✅ Implemented |
| C-14 | GRN disposition: accepted + damaged + rejected > received | Service must validate total ≤ received quantity | Partial (not explicitly validated) |

---

## Inventory Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| I-1 | Warehouse has no bins when GRN disposition runs | HTTP 400: "Warehouse must have at least one bin" | ✅ Implemented |
| I-2 | Manual stock adjustment results in negative on-hand | HTTP 400: "Cannot have negative on-hand stock" | ✅ Implemented |
| I-3 | Damaged/rejected GRN items posted to inventory | Only `quantity_accepted` posts to `on_hand`; damaged qty is not added | ✅ Implemented |
| I-4 | GRN cancelled after stock posted | Stock already posted is not reversed (manual adjustment required) | NYI — no reversal logic |
| I-5 | Two concurrent GRN dispositions for same bin | Race condition; no `SELECT FOR UPDATE` on inventory levels | NYI — needs SELECT FOR UPDATE |
| I-6 | Product deleted while inventory level exists | Soft-delete only; inventory level still queryable | ✅ Implemented (soft deletes) |
| I-7 | Reorder level breached | System detects breach on inventory adjustment | NYI — no reorder alerts yet |

---

## Product Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| P-1 | Duplicate `internal_sku` in same workspace | Database unique constraint prevents this | ✅ Implemented |
| P-2 | Product with no UoM assigned | Pydantic requires `base_uom_id` — blocked at API | ✅ Implemented |
| P-3 | UoM deleted while referenced by product | Soft delete UoM; product retains FK reference | NYI — no cascade protection |
| P-4 | Category with parent_id pointing to non-existent category | No FK enforcement at API level for parent_id | NYI |
| P-5 | Product tax_rate changes after invoice created | Invoice item `tax_rate` is snapshotted at creation time | ✅ Implemented |

---

## Customer Credit Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| CR-1 | Client invoice total exceeds credit limit | Credit check not yet implemented | NYI |
| CR-2 | Payment date in the future | Pydantic validator blocks future payment dates | ✅ Implemented |
| CR-3 | Invoice voided after partial payment received | VOID blocked on PARTIALLY_PAID invoices | NYI — need state guard |
| CR-4 | PDC (Post-Dated Cheque) bounces | `pdc_status` field exists; no auto-reversal | Partial (field only) |

---

## Financial / Document Number Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| F-1 | Two concurrent invoice creates get same number | `SELECT FOR UPDATE` on InvoiceCounter prevents gap/duplicate | ✅ Implemented |
| F-2 | Two concurrent SPO creates get same SPO number | SPO counter uses `SELECT FOR UPDATE` via `get_next_spo_number()` | ✅ Implemented |
| F-3 | Two concurrent GRN creates get same GRN number | GRN number generation uses atomic counter | ✅ Implemented |
| F-4 | Decimal arithmetic produces floating-point drift | All monetary fields use `Numeric(12,2)` in DB and `Decimal` in Python | ✅ Implemented |

---

## Security Edge Cases

| # | Edge Case | Expected Behavior | Status |
|---|-----------|-------------------|--------|
| S-1 | User accesses another workspace's data | All queries filter by `workspace_id` from JWT | ✅ Implemented |
| S-2 | Rate limiting on auth endpoints | `5 per minute` on `/auth/register` and `/auth/login` | ✅ Implemented (SlowAPI) |
| S-3 | Expired JWT used | 401 Unauthorized returned | ✅ Implemented |
| S-4 | Refresh token reuse after logout | No token blacklist yet | NYI |
