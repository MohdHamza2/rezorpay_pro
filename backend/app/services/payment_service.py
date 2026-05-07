"""
Payment Processing Service with Idempotency and Concurrency Control.

Critical Implementation Details:
1. Idempotency check happens INSIDE transaction with row locking
2. Only SUCCESS payments count toward invoice balance
3. Payment amount must not exceed balance due (no overpayments)
4. Row-level locking prevents race conditions on concurrent payments
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.idempotency_key import IdempotencyKey
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.services.invoice_service import InvoiceService
from app.services.audit_service import AuditService


class PaymentService:
    """
    Service for recording and managing payments.
    
    Implements the "Successful Only" Financial Rule:
    - Only payments with status=SUCCESS count toward invoice balance
    - FAILED/CANCELLED/REFUNDED payments are kept for audit but don't affect balance
    
    Implements Idempotency:
    - Duplicate requests with same key return existing payment
    - Keys are workspace-scoped (isolated between tenants)
    - Keys expire after 48 hours (TTL)
    """
    
    @classmethod
    async def record_payment(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        amount: Decimal,
        idempotency_key: str,
        gateway: Optional[PaymentGateway] = None,
        gateway_transaction_id: Optional[str] = None,
        payment_date: Optional[date] = None
    ) -> Payment:
        """
        Record a payment for an invoice with full concurrency safety.
        
        This is the CRITICAL path - handles:
        1. Row-level locking (FOR UPDATE)
        2. Idempotency check (inside transaction)
        3. Balance validation (no overpayments)
        4. Payment creation
        5. Idempotency key storage
        6. Invoice status update
        
        All operations happen in a single atomic transaction.
        
        Args:
            session: Database session (in transaction context)
            workspace_id: UUID of the workspace
            invoice_id: UUID of the invoice
            user_id: UUID of the user recording the payment
            amount: Payment amount (must be <= balance_due)
            idempotency_key: Unique key for deduplication (workspace-scoped)
            gateway: Payment gateway used
            gateway_transaction_id: Transaction ID from gateway
            payment_date: Date of payment (defaults to today)
            
        Returns:
            Payment: The created (or existing) payment
            
        Raises:
            ValueError: If payment exceeds balance due or idempotency conflict
        """
        if payment_date is None:
            payment_date = date.today()
        
        # Step 1: Lock invoice row (FOR UPDATE)
        # This prevents race conditions on concurrent payments
        result = await session.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .where(Invoice.workspace_id == workspace_id)
            .with_for_update()  # <-- CRITICAL: Row-level lock
        )
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise ValueError("Invoice not found or not in workspace")
        
        # Step 2: Check workspace-scoped idempotency key (inside transaction!)
        # This prevents double-spend window race conditions
        existing_key_result = await session.execute(
            select(IdempotencyKey)
            .where(IdempotencyKey.workspace_id == workspace_id)
            .where(IdempotencyKey.key == idempotency_key)
        )
        existing_key = existing_key_result.scalar_one_or_none()
        
        # Check expiration in python to avoid SQLite timezone issues
        if existing_key:
            if existing_key.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                # Valid existing key, return existing payment
                payment_result = await session.execute(
                    select(Payment).where(Payment.id == existing_key.payment_id)
                )
                existing_payment = payment_result.scalar_one_or_none()
                
                if existing_payment:
                    return existing_payment
                else:
                    # Shouldn't happen, but handle gracefully
                    raise ValueError("Idempotency key exists but payment not found")
            else:
                # Key expired, we should delete it or just ignore it because uniqueness constraint will still fail if we try to insert!
                # If we ignore it, the insertion later will fail. Let's delete it so we can re-insert!
                await session.delete(existing_key)
                await session.flush()
        
        # Step 3: Calculate balance due (eager load payments)
        result = await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.payments))
            .where(Invoice.id == invoice_id)
        )
        invoice_with_payments = result.scalar_one()
        
        balance_due = InvoiceService.calculate_balance_due(invoice_with_payments)
        
        # Step 4: Validate no overpayment
        if amount > balance_due:
            raise ValueError(
                f"Payment amount ({amount}) exceeds balance due ({balance_due}). "
                "Overpayments are not allowed for MVP."
            )
        
        # Step 5: Create payment
        payment = Payment(
            invoice_id=invoice_id,
            amount=amount,
            gateway=gateway,
            gateway_transaction_id=gateway_transaction_id,
            status=PaymentStatus.SUCCESS,
            payment_date=datetime.combine(payment_date, datetime.min.time()).replace(tzinfo=timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        session.add(payment)
        await session.flush()  # Get payment.id
        
        # Step 6: Store idempotency key (with TTL)
        idempotency = IdempotencyKey(
            workspace_id=workspace_id,
            key=idempotency_key,
            payment_id=payment.id
            # expires_at defaults to 48 hours from now
        )
        session.add(idempotency)
        
        # Step 7: Update invoice status (via InvoiceService)
        status_changed = await InvoiceService.update_status_from_payments(
            session, invoice, user_id
        )
        
        # Step 8: Log payment event
        await AuditService.log_payment_added(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            payment_amount=amount,
            payment_gateway=gateway.value if gateway else "manual",
            gateway_transaction_id=gateway_transaction_id,
            previous_status=invoice.status.value if not status_changed else "sent",
            new_status=invoice.status.value
        )
        
        return payment
    
    @staticmethod
    async def get_payments_for_invoice(
        session: AsyncSession,
        invoice_id: uuid.UUID,
        workspace_id: uuid.UUID
    ) -> list[Payment]:
        """
        Get all payments for an invoice.
        
        Note: Returns all payments regardless of status.
        For balance calculation, only SUCCESS payments are counted.
        """
        result = await session.execute(
            select(Payment)
            .join(Invoice)
            .where(Payment.invoice_id == invoice_id)
            .where(Invoice.workspace_id == workspace_id)
            .order_by(Payment.payment_date.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_successful_payments_total(
        session: AsyncSession,
        invoice_id: uuid.UUID
    ) -> Decimal:
        """Get sum of successful payments for an invoice."""
        result = await session.execute(
            select(Payment)
            .where(Payment.invoice_id == invoice_id)
            .where(Payment.status == PaymentStatus.SUCCESS)
        )
        payments = result.scalars().all()
        return sum(p.amount for p in payments)
