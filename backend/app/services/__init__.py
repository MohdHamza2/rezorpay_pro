"""
Business logic services for the Invoice SaaS backend.

Services handle complex business operations with proper transaction management,
ensuring data consistency and integrity.

Organization:
- invoice_number.py: Gapless invoice number generation
- invoice_service.py: Invoice lifecycle management
- payment_service.py: Payment processing with idempotency
- audit_service.py: Audit logging with minimal metadata
- spo_service.py: Supplier purchase order lifecycle
- spo_number.py: Gapless SPO number generation
- grn_service.py: Goods receipt note + 3-way match
- supplier_invoice_service.py: Supplier invoice matching/approval
"""

from app.services.invoice_number import InvoiceNumberService
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService
from app.services.audit_service import AuditService
from app.services.spo_service import SPOService
from app.services.spo_number import SPONumberService
from app.services.grn_service import GRNService
from app.services.supplier_invoice_service import (
    SupplierInvoiceService,
    supplier_invoice_service,
)

__all__ = [
    "InvoiceNumberService",
    "InvoiceService",
    "PaymentService",
    "AuditService",
    "SPOService",
    "SPONumberService",
    "GRNService",
    "SupplierInvoiceService",
    "supplier_invoice_service",
]
