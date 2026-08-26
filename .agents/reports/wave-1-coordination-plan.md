# Wave 1 Coordination Plan
*Created: 2026-08-26 | Coordinator: Wave 1 Agent*

## Objective
Execute engineering review tasks T1-T4, T11-T12 for Wave 1: Bug Fix + Core Sync

## Task Status

### ✅ Completed (from previous execution)
- **T11**: Frontend .toFixed() null safety (18 instances fixed across 6 files)
- **Bonus**: TestClient API compatibility (httpx 0.26.0 → 0.27.0)
- **Bonus**: Payment modal verification (already functional)

### 🔄 In Progress (this session)
- **T1**: Multi-tenant isolation test suite
- **T2**: Fix N+1 queries (add selectinload/joinedload)
- **T3**: Verify locking strategy (SELECT FOR NO KEY UPDATE)
- **T4**: Credit control integration check
- **T12**: Document number collision test

## Analysis Phase Results

### T2: N+1 Query Analysis
**Routers WITH eager loading (✅):**
- `dashboard.py`: selectinload(Invoice.payments)
- `grn.py`: selectinload(GoodsReceiptNote.items) - 10 instances
- `invoices.py`: selectinload(Invoice.items), selectinload(Invoice.payments)
- `spo.py`: selectinload(SupplierPurchaseOrder.items) - 2 instances
- `supplier_invoices.py`: selectinload(SupplierInvoice.items)

**Routers MISSING eager loading (⚠️):**
- `clients.py`: No relationships loaded (Client has Invoice relationship)
- `products.py`: Need to verify if ProductVariant relationship needs loading
- `suppliers.py`: Need to verify if relationships exist
- `workspaces.py`: Need to verify workspace relationships

**Action:** Audit clients.py list endpoint for potential N+1 on invoice counts

### T3: Locking Strategy Analysis
**Current implementation:** Uses `FOR UPDATE` (exclusive lock)
```python
# invoice_number.py line 58
.with_for_update()  # <-- CRITICAL: Row-level lock
```

**PostgreSQL lock types:**
- `FOR UPDATE`: Exclusive lock - blocks ALL access (reads + writes)
- `FOR NO KEY UPDATE`: Less restrictive - allows reads, blocks only key-updating writes

**Consideration:** Since we're only incrementing `last_number` (not updating primary key), `FOR NO KEY UPDATE` would allow concurrent reads while maintaining counter safety.

**Action:** Test and potentially migrate to FOR NO KEY UPDATE for better concurrency

### T1: Multi-tenant Test Coverage
**Existing tests:**
- `test_spo.py::test_spo_is_workspace_isolated` ✅
- `test_spo.py::test_spo_numbers_are_gapless_within_a_workspace` ✅

**Missing coverage:**
- Invoice cross-tenant isolation
- Payment cross-tenant isolation
- Client cross-tenant isolation
- GRN cross-tenant isolation
- Product cross-tenant isolation
- Supplier cross-tenant isolation

**Action:** Create comprehensive multi-tenant test suite

### T12: Document Number Collision Test
**Existing:**
- `test_spo.py::test_spo_numbers_are_gapless_within_a_workspace` - basic uniqueness

**Missing:**
- Concurrent collision test (race condition simulation)
- Cross-year boundary test
- Rollback scenario test

**Action:** Add concurrent stress test for invoice/SPO number generation

### T4: Credit Control Integration
**Status:** Need to search codebase for credit control implementation

**Action:** Verify if credit control exists, check integration points

## Execution Strategy

### Phase 1: Analysis & Planning (✅ DONE)
- Audit all routers for N+1 queries
- Review locking implementation
- Identify test gaps
- Search for credit control code

### Phase 2: Backend Fixes
1. Add eager loading to clients.py (if N+1 detected)
2. Test FOR NO KEY UPDATE migration
3. Add multi-tenant isolation tests
4. Add concurrent collision tests

### Phase 3: Verification
1. Run full test suite
2. Verify no performance regressions
3. Confirm all tests pass
4. Update wave-1-execution-report.md

## Risk Assessment

**Low Risk:**
- Adding selectinload (non-breaking, performance improvement only)
- Adding new tests (no production code change)

**Medium Risk:**
- Changing lock type (requires thorough testing, rollback plan needed)

**Mitigation:**
- Test lock change in isolation first
- Keep FOR UPDATE as fallback if issues arise
- All changes behind test coverage
