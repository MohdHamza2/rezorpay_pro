"""
Invoice Lifecycle Management Service.

Status Integrity Rule:
- Invoice.status is a CACHED STATE, not source of truth
- Source of truth = total_amount - sum(successful_payments)
- Status is updated ONLY via this service (controlled updates)
- Never update status directly - always use service methods
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, NoReturn, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import PaymentStatus
from app.models.product import Product, ProductPrice
from app.models.workspace import Workspace
from app.schemas.common import ErrorCode, ErrorDetail
from app.services.audit_service import AuditService
from app.services.invoice_number import InvoiceNumberService
from app.services.line_money import apply_line_money as _apply_line_money
from app.services.line_money import money, xor_discounts

logger = logging.getLogger(__name__)

STANDARD_THRESHOLD = Decimal("10000.00")
TRN_RE = re.compile(r"^100[0-9]{12}$")
KIND_STANDARD = "STANDARD"
KIND_SIMPLIFIED = "SIMPLIFIED"
AED = "AED"
DEFAULT_SALES = "DEFAULT_SALES"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _strip(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_trn(value: Optional[str]) -> str:
    return _strip(value).replace(" ", "")


def _is_valid_trn(value: Optional[str]) -> bool:
    return bool(TRN_RE.fullmatch(_normalize_trn(value)))


def _raise(
    http_status: int,
    code: str,
    message: str,
    field: Optional[str] = None,
) -> NoReturn:
    raise HTTPException(
        status_code=http_status,
        detail=ErrorDetail(code=code, message=message, field=field).model_dump(),
    )


def _fta_blocked(field: str, message: str) -> NoReturn:
    logger.info("fta_send_blocked", extra={"fta_field": field})
    _raise(status.HTTP_400_BAD_REQUEST, ErrorCode.FTA_SEND_BLOCKED, message, field)


def _resolve_kind(client: Client, total: Decimal) -> str:
    if _is_valid_trn(client.tax_id):
        return KIND_STANDARD
    if total > STANDARD_THRESHOLD:
        return KIND_STANDARD
    return KIND_SIMPLIFIED


def _snapshot_trn(value: Optional[str]) -> Optional[str]:
    """Persist TRN only if it matches FTA seller shape ``^100[0-9]{12}$``."""
    if not _is_valid_trn(value):
        return None
    return _normalize_trn(value)


def _freeze_snapshots(
    invoice: Invoice, workspace: Workspace, client: Client, kind: str
) -> None:
    invoice.invoice_kind = kind
    invoice.seller_trn_snapshot = _snapshot_trn(workspace.trn)
    invoice.seller_name_snapshot = workspace.name
    invoice.seller_address_snapshot = _strip(workspace.address) or None
    invoice.buyer_trn_snapshot = _snapshot_trn(client.tax_id)
    invoice.buyer_name_snapshot = client.name
    invoice.buyer_address_snapshot = _strip(client.address) or None


async def _apply_send_snapshots(session: AsyncSession, invoice: Invoice) -> None:
    workspace, client, _items = await _load_send_context(session, invoice)
    kind = _resolve_kind(client, invoice.total_amount)
    _freeze_snapshots(invoice, workspace, client, kind)


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
    async def get_for_response(
        session: AsyncSession,
        invoice_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Optional[Invoice]:
        result = await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.items), selectinload(Invoice.payments))
            .where(Invoice.id == invoice_id)
            .where(Invoice.workspace_id == workspace_id)
            .where(Invoice.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_invoice(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        issue_date: date,
        due_date: date,
        currency: str = AED,
        notes: Optional[str] = None,
        items: Optional[List[dict]] = None,
        supply_date: Optional[date] = None,
        quotation_id: Optional[uuid.UUID] = None,
        customer_purchase_order_id: Optional[uuid.UUID] = None,
    ) -> Invoice:
        """Create a new invoice with gapless numbering and FTA line math."""
        _assert_aed(currency)
        resolved_supply = supply_date or issue_date
        _assert_supply_date(issue_date, resolved_supply)
        default_tax_rate = await _workspace_tax_rate(session, workspace_id)
        invoice_number = await InvoiceNumberService.generate_invoice_number(
            session, workspace_id
        )
        invoice = Invoice(
            workspace_id=workspace_id,
            client_id=client_id,
            invoice_number=invoice_number,
            currency=currency,
            status=InvoiceStatus.DRAFT,
            issue_date=issue_date,
            supply_date=resolved_supply,
            due_date=due_date,
            notes=notes,
            quotation_id=quotation_id,
            customer_purchase_order_id=customer_purchase_order_id,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(invoice)
        await session.flush()
        if items:
            await _add_items(session, invoice, workspace_id, default_tax_rate, items)
        await InvoiceService._recalculate_totals(session, invoice)
        await AuditService.log_invoice_created(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            items_count=len(items) if items else 0,
            total=invoice.total_amount,
            invoice_number=invoice_number,
        )
        return invoice

    @staticmethod
    async def update_draft(
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        patch: Dict[str, Any],
        items: Optional[List[dict]] = None,
    ) -> Invoice:
        """Replace draft header fields and optionally all lines."""
        if invoice.customer_purchase_order_id is not None:
            _raise(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                "Cannot edit an invoice linked to an LPO. "
                "Delete the DRAFT invoice and post remaining quantities again.",
            )
        if invoice.status != InvoiceStatus.DRAFT:
            _raise(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot edit invoice with status '{invoice.status.value}'. "
                "Only DRAFT invoices can be edited.",
            )
        default_tax_rate = await _workspace_tax_rate(session, invoice.workspace_id)
        _apply_header_patch(invoice, patch)
        if items is not None:
            await session.execute(
                delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
            )
            await session.flush()
            await _add_items(
                session, invoice, invoice.workspace_id, default_tax_rate, items
            )
        await InvoiceService._recalculate_totals(session, invoice)
        changed = list(patch.keys())
        if items is not None:
            changed.append("items")
        await AuditService.log_invoice_updated(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            changed_fields=changed,
        )
        return invoice

    @staticmethod
    async def _recalculate_totals(session: AsyncSession, invoice: Invoice) -> None:
        """Recompute stored line net/VAT then sum. Only totals path."""
        result = await session.execute(
            select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
        )
        items = result.scalars().all()
        for item in items:
            _apply_line_money(item)
        subtotal = sum((item.line_net for item in items), Decimal("0"))
        tax_amount = sum((item.tax_amount for item in items), Decimal("0"))
        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total_amount = money(subtotal + tax_amount)
        invoice.updated_at = _now()

    @staticmethod
    def calculate_balance_due(invoice: Invoice) -> Decimal:
        """
        Calculate remaining balance on invoice.

        ⚠️ CRITICAL: Only counts successful payments.
        Failed payments are kept for audit trail but don't affect balance.
        """
        total_paid = sum(
            p.amount for p in invoice.payments if p.status == PaymentStatus.SUCCESS
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
        cls, session: AsyncSession, invoice: Invoice, user_id: uuid.UUID
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
        await session.refresh(invoice, ["payments"])

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
                reason="automatic_from_payment",
            )

            return True

        return False

    @classmethod
    async def assert_fta_sendable(cls, session: AsyncSession, invoice: Invoice) -> None:
        """Hard-fail FTA fields before DRAFT→SENT. Raises HTTP 400 FTA_SEND_BLOCKED."""
        workspace, client, items = await _load_send_context(session, invoice)
        if invoice.currency != AED:
            _fta_blocked("currency", "Tax invoices must be in AED")
        if not items:
            _fta_blocked("items", "Invoice must have at least one line")
        if invoice.total_amount < 0:
            _fta_blocked("total_amount", "Invoice total cannot be negative")
        if not _is_valid_trn(workspace.trn):
            _fta_blocked(
                "workspace.trn",
                "Workspace TRN is required and must be 15 digits starting with 100",
            )
        if not _strip(workspace.address):
            _fta_blocked("workspace.address", "Workspace address is required to send")
        if not _strip(workspace.name):
            _fta_blocked("workspace.name", "Workspace name is required to send")
        if not _strip(client.name):
            _fta_blocked("client.name", "Client name is required to send")
        kind = _resolve_kind(client, invoice.total_amount)
        if kind == KIND_STANDARD:
            if not _is_valid_trn(client.tax_id):
                _fta_blocked(
                    "client.tax_id", "Buyer TRN is required for a standard tax invoice"
                )
            if not _strip(client.address):
                _fta_blocked(
                    "client.address",
                    "Buyer address is required for a standard tax invoice",
                )

    @classmethod
    async def send_invoice(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        sent_method: str = "email",
        recipient: Optional[str] = None,
    ) -> None:
        """DRAFT→SENT after FTA checks; freeze seller/buyer snapshots."""
        await cls.mark_as_sent(
            session=session,
            invoice=invoice,
            user_id=user_id,
            sent_method=sent_method,
            recipient=recipient,
        )

    @classmethod
    async def mark_as_sent(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
        sent_method: str = "email",
        recipient: Optional[str] = None,
    ) -> None:
        """DRAFT→SENT. Always FTA-checks and freezes snapshots."""
        if invoice.status != InvoiceStatus.DRAFT:
            _raise(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot mark as sent: invoice is {invoice.status.value}",
            )
        await cls.assert_fta_sendable(session, invoice)
        await _apply_send_snapshots(session, invoice)
        invoice.status = InvoiceStatus.SENT
        invoice.updated_at = datetime.now(timezone.utc)
        await AuditService.log_invoice_sent(
            session=session,
            invoice_id=invoice.id,
            user_id=user_id,
            sent_method=sent_method,
            recipient=recipient,
        )

    @classmethod
    async def void_invoice(
        cls, session: AsyncSession, invoice: Invoice, user_id: uuid.UUID, reason: str
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
            previous_status=old_status.value,
        )
        await _recalc_linked_lpo(session, invoice, user_id)

    @staticmethod
    async def can_delete(invoice: Invoice) -> bool:
        """Check if invoice can be soft deleted (only drafts allowed)."""
        return invoice.status == InvoiceStatus.DRAFT

    @classmethod
    async def soft_delete_draft(
        cls,
        session: AsyncSession,
        invoice: Invoice,
        user_id: uuid.UUID,
    ) -> None:
        """Soft-delete a DRAFT invoice and release LPO remaining qty."""
        if invoice.status != InvoiceStatus.DRAFT:
            _raise(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.INVALID_STATE,
                f"Cannot delete invoice with status '{invoice.status.value}'. "
                "Use POST /invoices/{id}/void instead.",
            )
        invoice.deleted_at = _now()
        invoice.updated_at = _now()
        await _recalc_linked_lpo(session, invoice, user_id)

    @staticmethod
    async def can_edit(invoice: Invoice) -> bool:
        """Check if invoice can be edited (only drafts allowed)."""
        return invoice.status == InvoiceStatus.DRAFT


def _assert_aed(currency: str) -> None:
    if currency != AED:
        _raise(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "Invoice currency must be AED",
            "currency",
        )


def _assert_supply_date(issue_date: date, supply_date: date) -> None:
    if supply_date > issue_date:
        _raise(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "supply_date may not be after issue_date",
            "supply_date",
        )


async def _workspace_tax_rate(
    session: AsyncSession, workspace_id: uuid.UUID
) -> Decimal:
    result = await session.execute(
        select(Workspace.default_tax_rate, Workspace.deleted_at).where(
            Workspace.id == workspace_id
        )
    )
    row = result.one_or_none()
    if row is None or row[1] is not None:
        _raise(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Workspace not found")
    return _dec(row[0])


def _apply_header_patch(invoice: Invoice, patch: Dict[str, Any]) -> None:
    if "currency" in patch:
        raw = patch["currency"]
        patch["currency"] = raw.value if hasattr(raw, "value") else raw
        _assert_aed(patch["currency"])
    issue_date = patch.get("issue_date", invoice.issue_date)
    supply_date = patch.get("supply_date", invoice.supply_date)
    _assert_supply_date(issue_date, supply_date)
    for field, value in patch.items():
        setattr(invoice, field, value)


async def _add_items(
    session: AsyncSession,
    invoice: Invoice,
    workspace_id: uuid.UUID,
    default_tax_rate: Decimal,
    items: Sequence[dict],
) -> None:
    for item_data in items:
        resolved = await _resolve_line(
            session, workspace_id, default_tax_rate, item_data
        )
        item = InvoiceItem(
            invoice_id=invoice.id,
            customer_purchase_order_item_id=item_data.get(
                "customer_purchase_order_item_id"
            ),
            **resolved,
            line_net=Decimal("0"),
            tax_amount=Decimal("0"),
            total_price=Decimal("0"),
            created_at=_now(),
            updated_at=_now(),
        )
        _apply_line_money(item)
        session.add(item)
    await session.flush()


async def _resolve_line(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    default_tax_rate: Decimal,
    item_data: dict,
    *,
    line_owner: str = "invoice",
) -> dict:
    product_id = item_data.get("product_id")
    product: Optional[Product] = None
    sku_snapshot = None
    uom_id = None
    if product_id is not None:
        product = await _load_invoice_product(
            session, workspace_id, product_id, line_owner=line_owner
        )
        sku_snapshot = product.internal_sku
        uom_id = product.base_uom_id
    description = _line_description(item_data, product)
    unit_price = await _line_unit_price(session, workspace_id, item_data, product)
    tax_rate = _line_tax_rate(item_data, product, default_tax_rate)
    discount_percent = _dec(item_data.get("discount_percent") or 0)
    discount_amount = _dec(item_data.get("discount_amount") or 0)
    xor_discounts(discount_percent, discount_amount)
    return {
        "product_id": product.id if product else None,
        "uom_id": uom_id,
        "sku_snapshot": sku_snapshot,
        "description": description,
        "quantity": _dec(item_data["quantity"]),
        "unit_price": unit_price,
        "tax_rate": tax_rate,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
    }


def _line_description(item_data: dict, product: Optional[Product]) -> str:
    raw = item_data.get("description")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    if product is not None:
        return product.name
    _raise(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_ERROR,
        "description is required when product_id is omitted",
        "description",
    )


async def _line_unit_price(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    item_data: dict,
    product: Optional[Product],
) -> Decimal:
    if item_data.get("unit_price") is not None:
        return _dec(item_data["unit_price"])
    if product is None:
        _raise(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "unit_price is required when product_id is omitted",
            "unit_price",
        )
    price = await _default_sales_price(session, workspace_id, product.id)
    if price is None:
        _raise(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.NO_LIST_PRICE,
            "Product has no DEFAULT_SALES list price",
            "product_id",
        )
    return price


def _line_tax_rate(
    item_data: dict, product: Optional[Product], default_tax_rate: Decimal
) -> Decimal:
    if item_data.get("tax_rate") is not None:
        return _dec(item_data["tax_rate"])
    if product is not None and product.tax_rate is not None:
        return _dec(product.tax_rate)
    return _dec(default_tax_rate)


async def _load_invoice_product(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    line_owner: str = "invoice",
) -> Product:
    result = await session.execute(
        select(Product).where(
            Product.id == product_id,
            Product.workspace_id == workspace_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        _raise(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Product not found")
    if not product.is_active:
        if line_owner == "quotation":
            target = "a quotation line"
        elif line_owner == "lpo":
            target = "an LPO line"
        else:
            target = "an invoice"
        _raise(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.VALIDATION_ERROR,
            f"Cannot add an inactive product to {target}",
            "product_id",
        )
    return product


async def _default_sales_price(
    session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> Optional[Decimal]:
    result = await session.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
            ProductPrice.workspace_id == workspace_id,
            ProductPrice.price_type == DEFAULT_SALES,
        )
    )
    row = result.scalars().first()
    return _dec(row.price) if row is not None else None


async def _recalc_linked_lpo(
    session: AsyncSession, invoice: Invoice, user_id: uuid.UUID
) -> None:
    if invoice.customer_purchase_order_id is None:
        return
    from app.services.customer_po_service import CustomerPurchaseOrderService

    await CustomerPurchaseOrderService.recalc_invoiced(
        session, invoice.customer_purchase_order_id, user_id
    )


async def _load_send_context(
    session: AsyncSession, invoice: Invoice
) -> tuple[Workspace, Client, Sequence[InvoiceItem]]:
    workspace = await session.get(Workspace, invoice.workspace_id)
    client = await session.get(Client, invoice.client_id)
    if workspace is None or client is None:
        _raise(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Invoice parties not found"
        )
    result = await session.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    )
    return workspace, client, result.scalars().all()
