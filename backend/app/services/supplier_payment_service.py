"""
Supplier AP Payment Service — Wave 22 (Phase 4).

Mirrors `PaymentService.record_payment` (AR) step-for-step:
1. FOR UPDATE row lock on the supplier invoice inside the transaction
2. Workspace-scoped idempotency check inside the transaction (48h TTL)
3. Eligibility gate: only APPROVED / PARTIALLY_PAID invoices are payable
4. No overpayment (amount <= balance_due)
5. Insert immutable SUCCESS payment + idempotency key
6. Recompute amount_paid / balance_due and transition to PAID when settled

Only `status=SUCCESS` counts toward `amount_paid` (Successful Only rule).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from fastapi import status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.payment import PaymentMethod, PaymentStatus, PDCStatus
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from app.models.supplier_payment import (
    SupplierPayment,
    SupplierPaymentIdempotencyKey,
)
from app.schemas.common import ErrorCode
from app.services.credit_control_service import aging_buckets, utc_today
from app.services.customer_po_support import raise_error
from app.services.line_money import money

PAYABLE_STATUSES = (
    SupplierInvoiceStatus.APPROVED,
    SupplierInvoiceStatus.PARTIALLY_PAID,
)
OPEN_AP_STATUSES = (
    SupplierInvoiceStatus.APPROVED,
    SupplierInvoiceStatus.PARTIALLY_PAID,
)
ZERO = Decimal("0.00")


def _payment_datetime(payment_date: date) -> datetime:
    return datetime.combine(payment_date, dtime.min).replace(tzinfo=timezone.utc)


@dataclass
class _AgingRow:
    """Adapter so the live AR `aging_buckets` helper accepts SupplierInvoice rows.

    AR invoices store `due_date` as a Date; supplier invoices store a tz-aware
    DateTime. Convert once, then hand the live helper plain `balance_due` /
    `due_date` rows — bucket boundaries stay identical (no fork).
    """

    balance_due: Decimal
    due_date: date

    @classmethod
    def from_invoice(cls, inv: SupplierInvoice) -> "_AgingRow":
        due = inv.due_date
        if isinstance(due, datetime):
            due = due.date()
        return cls(balance_due=inv.balance_due, due_date=due)


def ap_aging_buckets(invoices: Sequence[SupplierInvoice], today: date) -> dict:
    """Reuse the live aging bucket function on supplier invoices."""
    return aging_buckets([_AgingRow.from_invoice(inv) for inv in invoices], today)


def due_date_of(inv: SupplierInvoice) -> date:
    due = inv.due_date
    if isinstance(due, datetime):
        return due.date()
    return due


class SupplierPaymentService:
    @classmethod
    async def record_payment(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_invoice_id: uuid.UUID,
        user_id: uuid.UUID,
        amount: Decimal,
        idempotency_key: str,
        payment_method,
        payment_date: Optional[date] = None,
        reference_number: Optional[str] = None,
        bank_name: Optional[str] = None,
        pdc_date: Optional[date] = None,
    ) -> SupplierPayment:
        """Record an AP payment for an approved supplier invoice.

        All steps happen in a single atomic transaction. No overpayments, no
        payment without a prior 3-way-match approval.
        """
        if payment_date is None:
            payment_date = utc_today()

        # Step 1: lock the supplier invoice row (FOR UPDATE)
        result = await session.execute(
            select(SupplierInvoice)
            .where(SupplierInvoice.id == supplier_invoice_id)
            .where(SupplierInvoice.workspace_id == workspace_id)
            .with_for_update()
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Supplier invoice not found or not in workspace",
            )

        # Step 2: workspace-scoped idempotency check (inside the transaction)
        existing_key_result = await session.execute(
            select(SupplierPaymentIdempotencyKey)
            .where(SupplierPaymentIdempotencyKey.workspace_id == workspace_id)
            .where(SupplierPaymentIdempotencyKey.key == idempotency_key)
        )
        existing_key = existing_key_result.scalar_one_or_none()
        if existing_key:
            if existing_key.expires_at.replace(tzinfo=timezone.utc) > datetime.now(
                timezone.utc
            ):
                payment_result = await session.execute(
                    select(SupplierPayment).where(
                        SupplierPayment.id == existing_key.supplier_payment_id
                    )
                )
                existing_payment = payment_result.scalar_one_or_none()
                if existing_payment:
                    return existing_payment
                raise ValueError("Idempotency key exists but payment not found")
            await session.delete(existing_key)
            await session.flush()

        # Step 3: eligibility gate (consumes the 3-way-match state machine)
        if invoice.status not in PAYABLE_STATUSES:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.INVALID_STATE,
                "Supplier invoice is not APPROVED; it cannot be paid",
            )

        # Step 4: balance cap — no overpayments
        balance_due = invoice.balance_due
        if amount > balance_due:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.PAYMENT_EXCEEDS_BALANCE,
                f"Payment amount ({amount}) exceeds balance due ({balance_due}). "
                "Overpayments are not allowed for MVP.",
            )

        # Step 4b: PDC requires a post-dated cheque date (mirrors AR)
        is_pdc = payment_method == PaymentMethod.PDC
        if is_pdc and pdc_date is None:
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "pdc_date is required for PDC payments",
                "pdc_date",
            )

        # Step 5: create the immutable payment (PDC starts PENDING up front)
        payment = SupplierPayment(
            workspace_id=workspace_id,
            supplier_id=invoice.supplier_id,
            supplier_invoice_id=invoice.id,
            amount=amount,
            payment_date=_payment_datetime(payment_date),
            payment_method=payment_method,
            status=PaymentStatus.PENDING if is_pdc else PaymentStatus.SUCCESS,
            pdc_status=PDCStatus.RECEIVED if is_pdc else None,
            pdc_date=pdc_date if is_pdc else None,
            reference_number=reference_number,
            bank_name=bank_name,
            created_by=user_id,
        )
        session.add(payment)
        await session.flush()  # get payment.id

        # Step 6: store the idempotency key (48h TTL)
        session.add(
            SupplierPaymentIdempotencyKey(
                workspace_id=workspace_id,
                key=idempotency_key,
                supplier_payment_id=payment.id,
            )
        )

        # Step 7: recompute the stored amount_paid / balance_due columns.
        # PDC stays PENDING until CLEARED — it does not touch the invoice.
        if not is_pdc:
            cls._settle_invoice(invoice, amount)

        return payment

    @staticmethod
    def _settle_invoice(invoice: SupplierInvoice, amount: Decimal) -> None:
        """Add to amount_paid, retire balance_due, transition PAID when 0."""
        invoice.amount_paid = money(invoice.amount_paid + amount)
        invoice.balance_due = money(max(ZERO, invoice.balance_due - amount))
        invoice.updated_at = datetime.now(timezone.utc)
        if invoice.balance_due == ZERO:
            invoice.status = SupplierInvoiceStatus.PAID
            if invoice.paid_at is None:
                invoice.paid_at = datetime.now(timezone.utc)
        elif invoice.status == SupplierInvoiceStatus.APPROVED:
            invoice.status = SupplierInvoiceStatus.PARTIALLY_PAID

    @staticmethod
    async def get_payment(
        session: AsyncSession, payment_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Optional[SupplierPayment]:
        result = await session.execute(
            select(SupplierPayment).where(
                SupplierPayment.id == payment_id,
                SupplierPayment.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_payments(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_id: Optional[uuid.UUID] = None,
        supplier_invoice_id: Optional[uuid.UUID] = None,
        status_value: Optional[PaymentStatus] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SupplierPayment], int]:
        stmt = select(SupplierPayment).where(
            SupplierPayment.workspace_id == workspace_id
        )
        if supplier_id is not None:
            stmt = stmt.where(SupplierPayment.supplier_id == supplier_id)
        if supplier_invoice_id is not None:
            stmt = stmt.where(
                SupplierPayment.supplier_invoice_id == supplier_invoice_id
            )
        if status_value is not None:
            stmt = stmt.where(SupplierPayment.status == status_value)
        if from_date is not None:
            stmt = stmt.where(func.date(SupplierPayment.payment_date) >= from_date)
        if to_date is not None:
            stmt = stmt.where(func.date(SupplierPayment.payment_date) <= to_date)

        count_result = await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        total = count_result.scalar()

        rows = (
            (
                await session.execute(
                    stmt.order_by(SupplierPayment.payment_date.desc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def open_ap_invoices(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        supplier_id: Optional[uuid.UUID] = None,
    ) -> list[SupplierInvoice]:
        """Open AP = approved/partially-paid supplier invoices with a balance."""
        stmt = select(SupplierInvoice).where(
            SupplierInvoice.workspace_id == workspace_id,
            SupplierInvoice.status.in_(OPEN_AP_STATUSES),
            SupplierInvoice.balance_due > ZERO,
        )
        if supplier_id is not None:
            stmt = stmt.where(SupplierInvoice.supplier_id == supplier_id)
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def _supplier_names(
        cls, session: AsyncSession, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Supplier]:
        if not ids:
            return {}
        result = await session.execute(
            select(Supplier).where(
                Supplier.workspace_id == workspace_id, Supplier.id.in_(ids)
            )
        )
        return {s.id: s for s in result.scalars().all()}

    @classmethod
    async def ap_aging(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        as_of: Optional[date] = None,
        supplier_id: Optional[uuid.UUID] = None,
        view: str = "summary",
    ) -> dict:
        """AP aging report: summary | detail | by_supplier."""
        resolved = as_of or utc_today()
        if resolved > utc_today():
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "as_of cannot be after today",
                "as_of",
            )

        if supplier_id is not None and view == "by_supplier":
            raise_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "supplier_id cannot be combined with view=by_supplier",
                "supplier_id",
            )

        invoices = await cls.open_ap_invoices(session, workspace_id, supplier_id)

        # Pre-aggregate PDC Outstanding per supplier invoice to avoid row multiplication
        supplier_invoice_ids = [inv.id for inv in invoices]
        pdc_by_invoice = await _pdc_outstanding_by_supplier_invoice(
            session, workspace_id, supplier_invoice_ids
        )

        buckets = ap_aging_buckets(invoices, resolved)
        outstanding = money(sum((inv.balance_due for inv in invoices), ZERO))

        # Compute PDC Outstanding aggregates
        total_pdc_count = 0
        total_pdc_amount = ZERO
        for inv in invoices:
            cnt, amt = pdc_by_invoice.get(inv.id, (0, ZERO))
            total_pdc_count += cnt
            total_pdc_amount = money(total_pdc_amount + amt)

        if view == "detail":
            suppliers = await cls._supplier_names(
                session, workspace_id, [inv.supplier_id for inv in invoices]
            )
            rows = [
                {
                    "supplier_id": inv.supplier_id,
                    "supplier_name": (
                        suppliers.get(inv.supplier_id).name
                        if suppliers.get(inv.supplier_id)
                        else ""
                    ),
                    "supplier_invoice_id": inv.id,
                    "supplier_invoice_number": inv.supplier_invoice_number,
                    "invoice_date": inv.invoice_date.date(),
                    "due_date": due_date_of(inv),
                    "days_overdue": max(0, (resolved - due_date_of(inv)).days),
                    "balance_due": inv.balance_due,
                    "bucket": _bucket_of(inv, resolved),
                    "pdc_outstanding_count": pdc_by_invoice.get(inv.id, (0, ZERO))[0],
                    "pdc_outstanding_amount": pdc_by_invoice.get(inv.id, (0, ZERO))[1],
                }
                for inv in invoices
            ]
            return {
                "as_of": resolved,
                "total_outstanding": outstanding,
                "buckets": buckets,
                "invoices": rows,
                "pdc_outstanding_count": total_pdc_count,
                "pdc_outstanding_amount": total_pdc_amount,
            }

        if view == "by_supplier":
            per_supplier: dict[uuid.UUID, list[SupplierInvoice]] = {}
            for inv in invoices:
                per_supplier.setdefault(inv.supplier_id, []).append(inv)
            suppliers = await cls._supplier_names(
                session, workspace_id, list(per_supplier.keys())
            )
            rows = []
            for sid, invs in per_supplier.items():
                sup = suppliers.get(sid)
                # Per-supplier PDC aggregate
                supplier_pdc_count = 0
                supplier_pdc_amount = ZERO
                for inv in invs:
                    cnt, amt = pdc_by_invoice.get(inv.id, (0, ZERO))
                    supplier_pdc_count += cnt
                    supplier_pdc_amount = money(supplier_pdc_amount + amt)
                rows.append(
                    {
                        "supplier": {
                            "id": sid,
                            "name": sup.name if sup else "",
                            "supplier_code": sup.supplier_code if sup else "",
                        },
                        "total_outstanding": money(
                            sum((i.balance_due for i in invs), ZERO)
                        ),
                        "buckets": ap_aging_buckets(invs, resolved),
                        "pdc_outstanding_count": supplier_pdc_count,
                        "pdc_outstanding_amount": supplier_pdc_amount,
                    }
                )
            rows.sort(key=lambda r: r["supplier"]["name"])
            return {
                "as_of": resolved,
                "total_outstanding": outstanding,
                "buckets": buckets,
                "suppliers": rows,
                "pdc_outstanding_count": total_pdc_count,
                "pdc_outstanding_amount": total_pdc_amount,
            }

        supplier_ids = {inv.supplier_id for inv in invoices}
        return {
            "as_of": resolved,
            "supplier_count": len(supplier_ids),
            "invoice_count": len(invoices),
            "total_outstanding": outstanding,
            "buckets": buckets,
            "pdc_outstanding_count": total_pdc_count,
            "pdc_outstanding_amount": total_pdc_amount,
        }


def _bucket_of(inv: SupplierInvoice, as_of: date) -> str:
    days_overdue = (as_of - due_date_of(inv)).days
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "days_1_30"
    if days_overdue <= 60:
        return "days_31_60"
    if days_overdue <= 90:
        return "days_61_90"
    return "days_90_plus"


async def _pdc_outstanding_by_supplier_invoice(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    supplier_invoice_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, Decimal]]:
    """Pre-aggregate AP PDC Outstanding (RECEIVED + DEPOSITED) per supplier invoice.

    Returns a mapping: supplier_invoice_id -> (count, amount) for PDC payments with
    pdc_status IN (RECEIVED, DEPOSITED). Invoices with no PDC payments are
    not present in the result; callers should default to (0, ZERO).

    This pre-aggregation avoids row multiplication when joining to invoices.
    """
    if not supplier_invoice_ids:
        return {}
    stmt = (
        select(
            SupplierPayment.supplier_invoice_id,
            func.count(SupplierPayment.id),
            func.coalesce(func.sum(SupplierPayment.amount), ZERO),
        )
        .where(
            SupplierPayment.supplier_invoice_id.in_(supplier_invoice_ids),
            SupplierPayment.payment_method == PaymentMethod.PDC,
            SupplierPayment.pdc_status.in_([PDCStatus.RECEIVED, PDCStatus.DEPOSITED]),
        )
        .group_by(SupplierPayment.supplier_invoice_id)
    )
    result = await session.execute(stmt)
    return {row[0]: (row[1], row[2]) for row in result.all()}


supplier_payment_service = SupplierPaymentService()
