import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status

from app.models.supplier_invoice import (
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierInvoiceStatus,
    MatchResult,
)
from app.schemas.supplier_invoices import (
    SupplierInvoiceCreate,
    SupplierInvoiceDiscrepancyResolution,
)
from app.models.spo import SupplierPurchaseOrder, SupplierPurchaseOrderItem
from app.models.grn import GoodsReceiptNote, GRNItem, GRNStatus
from app.models.landed_cost import LandedCostAllocation, LandedCostStatus
from sqlalchemy import func


class SupplierInvoiceService:
    async def create_supplier_invoice(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        invoice_in: SupplierInvoiceCreate,
    ) -> SupplierInvoice:
        # Check for duplicates (C-38)
        stmt = select(SupplierInvoice).where(
            SupplierInvoice.workspace_id == workspace_id,
            SupplierInvoice.supplier_id == invoice_in.supplier_id,
            SupplierInvoice.supplier_invoice_number
            == invoice_in.supplier_invoice_number,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="DUPLICATE_INVOICE: Invoice number already exists for this supplier.",
            )

        db_invoice = SupplierInvoice(
            workspace_id=workspace_id,
            supplier_id=invoice_in.supplier_id,
            supplier_invoice_number=invoice_in.supplier_invoice_number,
            our_reference=invoice_in.our_reference,
            invoice_date=invoice_in.invoice_date,
            due_date=invoice_in.due_date,
            currency=invoice_in.currency,
            subtotal=invoice_in.subtotal,
            discount_amount=invoice_in.discount_amount,
            vat_amount=invoice_in.vat_amount,
            total_amount=invoice_in.total_amount,
            balance_due=invoice_in.total_amount,
            primary_spo_id=invoice_in.primary_spo_id,
            status=SupplierInvoiceStatus.RECEIVED,
            three_way_match_status=MatchResult.NOT_CHECKED,
        )
        session.add(db_invoice)
        await session.flush()

        for item_in in invoice_in.items:
            db_item = SupplierInvoiceItem(
                supplier_invoice_id=db_invoice.id,
                spo_item_id=item_in.spo_item_id,
                grn_item_id=item_in.grn_item_id,
                product_id=item_in.product_id,
                description=item_in.description,
                quantity=item_in.quantity,
                uom_id=item_in.uom_id,
                unit_price=item_in.unit_price,
                discount_percent=item_in.discount_percent,
                vat_rate=item_in.vat_rate,
                vat_amount=item_in.vat_amount,
                total_price=item_in.total_price,
                currency=item_in.currency,
                match_status=MatchResult.NOT_CHECKED,
            )
            session.add(db_item)

        await session.commit()
        await session.refresh(db_invoice)
        await session.refresh(db_invoice, ["items"])
        return db_invoice

    async def _match_item(
        self,
        session: AsyncSession,
        invoice: SupplierInvoice,
        item: SupplierInvoiceItem,
    ) -> MatchResult:
        if not item.spo_item_id:
            return MatchResult.UNRECEIVED_ITEMS

        spo_item = await session.get(SupplierPurchaseOrderItem, item.spo_item_id)
        if not spo_item:
            return MatchResult.MANUAL_REVIEW

        spo = await session.get(SupplierPurchaseOrder, spo_item.spo_id)

        # 1. Supplier Match
        if invoice.supplier_id != spo.supplier_id:
            return MatchResult.FAILED_SUPPLIER

        # 2. Currency Match
        if invoice.currency != spo.currency:
            return MatchResult.FAILED_CURRENCY

        # 3. Product Match
        if item.product_id != spo_item.product_id:
            return MatchResult.FAILED_PRODUCT

        # 4. Quantity Match against GRN (per architecture 6.7)
        # GRN is physical truth — invoice qty must not exceed accepted qty
        stmt = (
            select(GRNItem)
            .join(GoodsReceiptNote)
            .where(
                GRNItem.spo_item_id == item.spo_item_id,
                GoodsReceiptNote.status.in_(
                    [GRNStatus.PARTIALLY_ACCEPTED, GRNStatus.ACCEPTED]
                ),
            )
        )
        grn_items = (await session.execute(stmt)).scalars().all()
        total_accepted_qty: Decimal = sum(
            (g.quantity_accepted for g in grn_items), Decimal("0")
        )

        if not grn_items or total_accepted_qty == Decimal("0"):
            return MatchResult.UNRECEIVED_ITEMS

        if item.quantity > total_accepted_qty:
            item.variance_quantity = item.quantity - total_accepted_qty
            return MatchResult.FAILED_QTY

        # 5. Price Match with 2% tolerance (D-25)
        spo_price: Decimal = spo_item.unit_price
        invoice_price: Decimal = item.unit_price

        if spo_price and spo_price > Decimal("0"):
            variance_pct = abs(invoice_price - spo_price) / spo_price * Decimal("100")
            if variance_pct > Decimal("2.0"):
                item.variance_price = invoice_price - spo_price
                return MatchResult.FAILED_PRICE
        elif invoice_price > Decimal("0"):
            # SPO price was 0 but invoice has price → fail
            item.variance_price = invoice_price
            return MatchResult.FAILED_PRICE

        # 6. Tax Match (6.9)
        expected_vat = (
            item.quantity * item.unit_price * (spo_item.vat_rate / Decimal("100"))
            if spo_item.vat_rate
            else Decimal("0")
        )
        # Allow minor rounding variance: 10% of expected + 0.10 AED
        tolerance = Decimal("0.1") * expected_vat + Decimal("0.10")
        if abs(item.vat_amount - expected_vat) > tolerance:
            item.variance_tax = item.vat_amount - expected_vat
            return MatchResult.FAILED_TAX

        # 7. Landed Cost Validation (D-22) - validation only
        # Check if GRN item has landed cost allocations
        stmt_lc = select(
            func.coalesce(func.sum(LandedCostAllocation.amount), Decimal("0"))
        ).where(
            LandedCostAllocation.grn_item_id.in_(
                select(GRNItem.id).where(GRNItem.spo_item_id == item.spo_item_id)
            ),
            LandedCostAllocation.status == LandedCostStatus.CAPITALIZED,
        )
        total_landed_cost = (await session.execute(stmt_lc)).scalar_one()

        if total_landed_cost > Decimal("0"):
            # Calculate expected landed cost per unit for this invoice item
            # We need to find the total accepted quantity for this SPO item across all GRNs
            stmt_qty = (
                select(func.coalesce(func.sum(GRNItem.quantity_accepted), Decimal("0")))
                .join(GoodsReceiptNote)
                .where(
                    GRNItem.spo_item_id == item.spo_item_id,
                    GoodsReceiptNote.status.in_(
                        [GRNStatus.PARTIALLY_ACCEPTED, GRNStatus.ACCEPTED]
                    ),
                )
            )
            total_accepted_qty_all_grns = (await session.execute(stmt_qty)).scalar_one()

            if total_accepted_qty_all_grns > Decimal("0"):
                landed_cost_per_unit = (
                    total_landed_cost / total_accepted_qty_all_grns
                ).quantize(Decimal("0.0001"))
                expected_landed_cost_for_item = (
                    landed_cost_per_unit * item.quantity
                ).quantize(Decimal("0.01"))

                # Check if invoice item total_price includes landed cost.
                # The item.total_price should be at least the discount-adjusted
                # product net plus the expected landed cost share. A small
                # tolerance absorbs 2dp quantization noise between the GRN-side
                # per-unit rounding and the supplier's own landed cost math.
                discount_pct = item.discount_percent or Decimal("0")
                if discount_pct < Decimal("0"):
                    discount_pct = Decimal("0")
                if discount_pct > Decimal("100"):
                    discount_pct = Decimal("100")
                product_net = (
                    item.unit_price
                    * item.quantity
                    * (Decimal("1") - discount_pct / Decimal("100"))
                ).quantize(Decimal("0.01"))
                expected_min_total = (
                    product_net + expected_landed_cost_for_item
                ).quantize(Decimal("0.01"))
                tolerance = max(
                    Decimal("0.05"),
                    (expected_landed_cost_for_item * Decimal("0.01")).quantize(
                        Decimal("0.01")
                    ),
                )

                if item.total_price < expected_min_total - tolerance:
                    item.variance_price = expected_min_total - item.total_price
                    return MatchResult.FAILED_PRICE

        return MatchResult.PASSED

    async def submit_matching(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> SupplierInvoice:
        stmt = select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id,
            SupplierInvoice.workspace_id == workspace_id,
        )
        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if invoice.status not in (
            SupplierInvoiceStatus.RECEIVED,
            SupplierInvoiceStatus.PENDING_MATCHING,
            SupplierInvoiceStatus.DISCREPANCY,
        ):
            raise HTTPException(
                status_code=400, detail="Invoice cannot be matched in current state"
            )

        invoice.status = SupplierInvoiceStatus.PENDING_MATCHING
        await session.flush()

        # Load items
        await session.refresh(invoice)
        await session.refresh(invoice, ["items"])

        overall_result = MatchResult.PASSED

        for item in invoice.items:
            res = await self._match_item(session, invoice, item)
            item.match_status = res
            if res != MatchResult.PASSED:
                overall_result = res

        invoice.three_way_match_status = overall_result
        invoice.matched_at = datetime.now(timezone.utc)

        if overall_result == MatchResult.PASSED:
            invoice.status = SupplierInvoiceStatus.MATCHED
        else:
            invoice.status = SupplierInvoiceStatus.DISCREPANCY

        await session.commit()
        await session.refresh(invoice)
        await session.refresh(invoice, ["items"])
        return invoice

    async def resolve_discrepancy(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        workspace_id: uuid.UUID,
        resolution: SupplierInvoiceDiscrepancyResolution,
    ) -> SupplierInvoice:
        stmt = select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id,
            SupplierInvoice.workspace_id == workspace_id,
        )
        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if invoice.status != SupplierInvoiceStatus.DISCREPANCY:
            raise HTTPException(
                status_code=400, detail="Invoice is not in DISCREPANCY state"
            )

        invoice.three_way_match_notes = resolution.notes
        invoice.status = SupplierInvoiceStatus.APPROVED
        invoice.approved_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(invoice)
        await session.refresh(invoice, ["items"])
        return invoice

    async def approve_invoice(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> SupplierInvoice:
        stmt = select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id,
            SupplierInvoice.workspace_id == workspace_id,
        )
        invoice = (await session.execute(stmt)).scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if invoice.status != SupplierInvoiceStatus.MATCHED:
            raise HTTPException(
                status_code=400,
                detail="Only MATCHED invoices can be directly approved",
            )

        if invoice.three_way_match_status != MatchResult.PASSED:
            raise HTTPException(
                status_code=400,
                detail="INV-6.1: AP cannot approve an invoice with an unresolved 3-Way Match discrepancy",
            )

        invoice.status = SupplierInvoiceStatus.APPROVED
        invoice.approved_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(invoice)
        await session.refresh(invoice, ["items"])
        return invoice


supplier_invoice_service = SupplierInvoiceService()
