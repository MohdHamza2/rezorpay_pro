"""
Invoice Lifecycle Management Service.

Status Integrity Rule:
- Invoice.status is a CACHED STATE, not source of truth
- Source of truth = total_amount - sum(successful_payments)
- Status is updated ONLY via this service (controlled updates)
- Never update status directly - always use service methods
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment, PaymentStatus
from app.services.invoice_number import InvoiceNumberService
from app.services.audit_service import AuditService


class InvoiceService:
    """
    Service for managing invoice lifecycle.
    
    All status updates go through this service to ensure:
    1. Status never drifts from actual payment totals
    2. Audit events are logged for all changes
    3. Transactions maintain data consistency
    """
    
    @staticmethod
    def serialize_invoice_list_item(invoice: Invoice):
        from app.schemas.invoices import InvoiceListItem
        return InvoiceListItem.model_validate(invoice)
        
    @staticmethod
    def serialize_invoice_response(invoice: Invoice):
        from app.schemas.invoices import InvoiceResponse
        return InvoiceResponse.model_validate(invoice)
    
    @staticmethod
    async def create_invoice(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        issue_date: date,
        due_date: date,
        currency: str = "AED",
        notes: Optional[str] = None,
        items: Optional[List[dict]] = None
    ) -> Invoice:
        """
        Create a new invoice with gapless numbering.
        
        Args:
            session: Database session (in transaction context)
            workspace_id: UUID of the workspace
            client_id: UUID of the client
            user_id: UUID of the user creating the invoice
            issue_date: Invoice issue date
            due_date: Invoice due date
            currency: Currency code (default AED)
            notes: Optional notes
            items: List of invoice items (dict with description, quantity, unit_price, tax_rate)
            
        Returns:
            Invoice: The created invoice
        """
        # Generate gapless invoice number (with row locking)
        invoice_number = await InvoiceNumberService.generate_invoice_number(
            session, workspace_id
        )
        
        # Create invoice
        invoice = Invoice(
            workspace_id=workspace_id,
            client_id=client_id,
            invoice_number=invoice_number,
            currency=currency,
            status=InvoiceStatus.DRAFT,
            issue_date=issue_date,
            due_date=due_date,
            notes=notes,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        session.add(invoice)
        await session.flush()  # Get invoice.id
        
        # Add items if provided
        if items:
            for item_data in items:
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=item_data["description"],
                    quantity=Decimal(str(item_data["quantity"])),
                    unit_price=Decimal(str(item_data["unit_price"])),
                    tax_rate=Decimal(str(item_data.get("tax_rate", 0))),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                # Calculate total for this item
                item.total_price = (
                    item.quantity * item.unit_price * 
                    (1 + item.tax_rate / 100)
                )
                session.add(item)
        
        await session.flush()  # Ensure items are in DB before querying them
        
        # Recalculate totals
        await InvoiceService._recalculate_totals(session, invoice)
        
        # Log creation event
        await AuditService.log_invoice_created(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            items_count=len(items) if items else 0,
            total=invoice.total_amount,
            invoice_number=invoice_number
        )
        
        return invoice
    
    @staticmethod
    async def _recalculate_totals(session: AsyncSession, invoice: Invoice) -> None:
        """
        Recalculate invoice totals from items.
        
        This is the ONLY place where invoice totals should be recalculated.
        """
        result = await session.execute(
            select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
        )
        items = result.scalars().all()
        
        subtotal = Decimal("0")
        tax_amount = Decimal("0")
        
        for item in items:
            item_subtotal = item.quantity * item.unit_price
            item_tax = item_subtotal * (item.tax_rate / 100)
            
            subtotal += item_subtotal
            tax_amount += item_tax
        
        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total_amount = subtotal + tax_amount
        invoice.updated_at = datetime.now(timezone.utc)
    
    @staticmethod
    def calculate_balance_due(invoice: Invoice) -> Decimal:
        """
        Calculate remaining balance on invoice.
        
        ⚠️ CRITICAL: Only counts successful payments.
        Failed payments are kept for audit trail but don't affect balance.
        """
        total_paid = sum(
            p.amount for p in invoice.payments
            if p.status == PaymentStatus.SUCCESS
        )
        return invoice.total_amount - total_paid
    
    @staticmethod
    def determine_status_from_balance(invoice: Invoice) -> InvoiceStatus:
        """
        Determine invoice status based on balance due.
        
        Source of truth calculation.
        """
        balance = InvoiceService.calculate_balance_due(invoice)
        
        if balance <= 0:
            return InvoiceStatus.PAID
        elif balance < invoice.total_amount:
            return InvoiceStatus.PARTIALLY_PAID
        else:
            # No payments or full balance remaining
            # Keep current status if draft/sent/overdue
            return invoice.status
    
    @classmethod
    async def update_status_from_payments(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID
    ) -> bool:
        """
        Recalculate and update invoice status from payments.
        
        This is the ONLY method that should update invoice status
        based on payment totals.
        
        Args:
            session: Database session
            invoice: Invoice to update
            user_id: User triggering the update
            
        Returns:
            bool: True if status changed, False otherwise
        """
        # Eager load payments for accurate calculation (force refresh)
        await session.refresh(invoice, ['payments'])
        
        # Calculate correct status from payments (source of truth)
        new_status = cls.determine_status_from_balance(invoice)
        
        # Only update if status changed
        if new_status != invoice.status:
            old_status = invoice.status
            invoice.status = new_status
            invoice.updated_at = datetime.now(timezone.utc)
            
            # Log status change
            await AuditService.log_status_changed(
                session=session,
                invoice_id=invoice.id,
                user_id=user_id,
                previous_status=old_status.value,
                new_status=new_status.value,
                reason="automatic_from_payment"
            )
            
            return True
        
        return False
    
    @classmethod
    async def mark_as_sent(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        sent_method: str = "email",
        recipient: Optional[str] = None
    ) -> None:
        """
        Mark invoice as sent.
        
        Only allowed for draft invoices.
        """
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError(f"Cannot mark as sent: invoice is {invoice.status.value}")
        
        old_status = invoice.status
        invoice.status = InvoiceStatus.SENT
        invoice.updated_at = datetime.now(timezone.utc)
        
        await AuditService.log_invoice_sent(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            sent_method=sent_method,
            recipient=recipient
        )
    
    @classmethod
    async def void_invoice(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        reason: str
    ) -> None:
        """
        Void (cancel) an invoice.
        
        Creates audit trail for accounting purposes.
        """
        if invoice.status in [InvoiceStatus.CANCELLED]:
            raise ValueError("Invoice is already voided")
        
        old_status = invoice.status
        invoice.status = InvoiceStatus.CANCELLED
        invoice.updated_at = datetime.now(timezone.utc)
        
        await AuditService.log_invoice_voided(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            reason=reason,
            previous_status=old_status.value
        )
    
    @staticmethod
    async def can_delete(invoice: Invoice) -> bool:
        """Check if invoice can be soft deleted (only drafts allowed)."""
        return invoice.status == InvoiceStatus.DRAFT
    
    @staticmethod
    async def can_edit(invoice: Invoice) -> bool:
        """Check if invoice can be edited (only drafts allowed)."""
        return invoice.status == InvoiceStatus.DRAFT
