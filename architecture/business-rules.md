# Business Rules
*InvoiceSaaS B2B Trading Platform*
*Wave 0 Specification*

## 1. Financial Rules
- **Rule 1.1**: All money uses Decimal(12,2). NEVER float. (DB & Pydantic).
- **Rule 1.2**: Payments are immutable. No update/delete of payment records. Reversals must be done via offsetting entries or specific bounce flows.
- **Rule 1.3**: Idempotency keys (48h TTL) for all payment endpoints.

## 2. Document & Operations Rules
- **Rule 2.1**: All document numbers are gapless (SELECT FOR UPDATE on sequence counter).
- **Rule 2.2**: Invoice ≠ Delivery. One CPO can have many invoices and many DOs.
- **Rule 2.3**: Quantity Reconciliation. System must track invoiced_qty and delivered_qty separately per CPO line item.
- **Rule 2.4**: Soft deletes only for all business entities.

## 3. Credit Control Rules
- **Rule 3.1**: Credit check runs on: CPO confirmation, Invoice creation, DO release.
- **Rule 3.2**: Overdue = any invoice where due_date < today AND balance_due > 0.
- **Rule 3.3**: HOLD blocks CPO confirmation and DO release. Does NOT block payments, statements, or enquiries.
- **Rule 3.4**: Credit status changes must be audited (changed_by, changed_at, eason).

## 4. Multi-tenancy Rules
- **Rule 4.1**: workspace_id must be on every core entity and checked on every query.
- **Rule 4.2**: API responses must wrap data in {success: true, data: ..., pagination: ...}.

## 5. Agent Governance Rules
- **Rule 5.1**: NO AI AGENT CAN INVENT BUSINESS RULES. Ambiguous scenarios must be flagged for human review.
