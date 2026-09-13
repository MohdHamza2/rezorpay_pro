"""RFQ award flow service — Wave 31 Item 2.1+1 (Item 2.3).

Minimum viable award slice over the previously API-less RFQ quote/award
models: supplier quote intake with normalization, read-only LOWEST_PRICE
comparison, award draft/approve with maker-checker, and idempotent conversion
into DRAFT SPOs.

Hard boundaries (locked):
- No stock, PR-quantity, ledger, payment, PDC, aging, VAT-report, or D-22
  writes anywhere in this flow.
- Ranking uses normalized net unit prices only. There is no discount column
  on quotes, so the discount factor is fixed at 1.0 (documented, not faked).
- The word "landed cost" does not appear in this module on purpose: RFQ
  comparison must never read landed_cost_allocations or GRN capitalization.
- WEIGHTED_SCORE is not implemented. Sealed-bid enforcement, expiry jobs,
  shortlists, revisions lifecycle, supplier portal, and notifications are
  deferred.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.product import Product, ProductUOMConversion, UnitOfMeasure
from app.models.rfq import (
    AwardStatus,
    QuoteCompleteness,
    QuoteStatus,
    RFQ,
    RFQAwardMode,
    RFQItem,
    RFQAward,
    RFQAwardLine,
    RFQStatus,
    SupplierQuoteItem,
    SupplierRFQResponse,
)
from app.models.supplier import Supplier
from app.models.workspace import Workspace
from app.schemas.rfq import (
    AwardCreate,
    ComparisonLineGroup,
    ComparisonResponse,
    ComparisonRow,
    GenerateSPOsRequest,
    GenerateSPOsResponse,
    QuoteResponseCreate,
)
from app.services.award_number import AwardNumberService

# RFQ statuses that close the request to new quotes and new awards.
CLOSED_RFQ_STATUSES = (RFQStatus.AWARDED, RFQStatus.EXPIRED)

# Award statuses whose lines reserve RFQ quantity (commitment point).
COMMITTED_AWARD_STATUSES = (AwardStatus.APPROVED, AwardStatus.CONVERTED)


class AwardService:
    # ------------------------------------------------------------------
    # Loading helpers (workspace-scoped; 404 hides cross-tenant existence)
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_scoped_rfq(
        session: AsyncSession, workspace_id: uuid.UUID, rfq_id: uuid.UUID
    ) -> RFQ:
        result = await session.execute(
            select(RFQ)
            .where(RFQ.id == rfq_id, RFQ.workspace_id == workspace_id)
            .options(
                selectinload(RFQ.items),
                selectinload(RFQ.responses).selectinload(
                    SupplierRFQResponse.quote_items
                ),
                selectinload(RFQ.awards).selectinload(RFQAward.award_lines),
            )
        )
        rfq = result.scalar_one_or_none()
        if not rfq:
            raise HTTPException(status_code=404, detail="RFQ not found")
        return rfq

    @staticmethod
    async def _get_workspace_supplier(
        session: AsyncSession, workspace_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier:
        supplier = await session.get(Supplier, supplier_id)
        if not supplier or supplier.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return supplier

    # ------------------------------------------------------------------
    # Normalization helpers (LOWEST_PRICE only)
    # ------------------------------------------------------------------

    @staticmethod
    async def _uom_factor(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        product_id: Optional[uuid.UUID],
        from_uom_id: uuid.UUID,
        base_uom_id: uuid.UUID,
    ) -> Optional[Decimal]:
        """Base-UOM units per one from_uom unit; None when unresolvable."""
        if from_uom_id == base_uom_id:
            return Decimal(1)
        if product_id is None:
            return None
        result = await session.execute(
            select(ProductUOMConversion.conversion_factor).where(
                ProductUOMConversion.product_id == product_id,
                ProductUOMConversion.to_uom_id == from_uom_id,
                ProductUOMConversion.workspace_id == workspace_id,
            )
        )
        factor = result.scalar_one_or_none()
        if factor is None or factor <= 0:
            return None
        return factor

    @staticmethod
    def _normalize(
        quoted_unit_price: Decimal, exchange_rate: Decimal, factor: Decimal
    ) -> Decimal:
        return (quoted_unit_price * exchange_rate / factor).quantize(Decimal("0.01"))

    @staticmethod
    def _quote_product_id(quote_item: SupplierQuoteItem, rfq_item: RFQItem):
        if quote_item.is_alternate:
            return quote_item.alternate_product_id
        return rfq_item.product_id

    @staticmethod
    def _latest_responses(
        responses: list[SupplierRFQResponse],
    ) -> dict[uuid.UUID, SupplierRFQResponse]:
        """Latest RECEIVED revision per supplier; history is never mutated."""
        latest: dict[uuid.UUID, SupplierRFQResponse] = {}
        for response in sorted(responses, key=lambda r: r.revision_number):
            if response.status == QuoteStatus.RECEIVED:
                latest[response.supplier_id] = response
        return latest

    # ------------------------------------------------------------------
    # RFQ send (minimal gate enabling intake)
    # ------------------------------------------------------------------

    @staticmethod
    async def send_rfq(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        rfq_id: uuid.UUID,
    ) -> RFQ:
        rfq = await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)
        if rfq.status != RFQStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        rfq.status = RFQStatus.SENT
        rfq.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)

    # ------------------------------------------------------------------
    # Quote intake
    # ------------------------------------------------------------------

    @staticmethod
    async def submit_quote(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        rfq_id: uuid.UUID,
        data: QuoteResponseCreate,
    ) -> SupplierRFQResponse:
        rfq = await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)
        if rfq.status in CLOSED_RFQ_STATUSES:
            raise HTTPException(status_code=400, detail="RFQ is closed to new quotes")
        if rfq.status == RFQStatus.DRAFT:
            raise HTTPException(
                status_code=400, detail="RFQ must be sent before quoting"
            )

        supplier = await AwardService._get_workspace_supplier(
            session, workspace_id, data.supplier_id
        )
        if supplier.status != "ACTIVE":
            # RFQ-012 mapping onto the existing ACTIVE/INACTIVE/HOLD enum:
            # only ACTIVE suppliers are eligible.
            raise HTTPException(
                status_code=422, detail="Supplier is not eligible for RFQ quotes"
            )

        # Next revision under lock (concurrent same-supplier submits serialize).
        existing = await session.execute(
            select(SupplierRFQResponse.revision_number)
            .where(
                SupplierRFQResponse.rfq_id == rfq.id,
                SupplierRFQResponse.supplier_id == supplier.id,
            )
            .with_for_update()
        )
        taken = [row for row, in existing.all()]
        revision = (max(taken) + 1) if taken else 1

        rfq_items = {item.id: item for item in rfq.items}
        products: dict[uuid.UUID, Product] = {}
        lines: list[SupplierQuoteItem] = []
        for line_in in data.items:
            rfq_item = rfq_items.get(line_in.rfq_item_id)
            if rfq_item is None:
                raise HTTPException(
                    status_code=404, detail="RFQ item not found on this request"
                )
            if line_in.is_alternate and line_in.alternate_product_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="Alternate quote lines require alternate_product_id",
                )
            if not line_in.is_alternate and line_in.alternate_product_id is not None:
                raise HTTPException(
                    status_code=422,
                    detail="alternate_product_id requires is_alternate",
                )
            quote_uom = line_in.uom_id or rfq_item.uom_id
            uom = await session.get(UnitOfMeasure, quote_uom)
            if not uom or uom.workspace_id != workspace_id:
                raise HTTPException(status_code=404, detail="UOM not found")
            product_id = (
                line_in.alternate_product_id
                if line_in.is_alternate
                else rfq_item.product_id
            )
            product = None
            base_uom = None
            if product_id is not None:
                product = products.get(product_id)
                if product is None:
                    product = await session.get(Product, product_id)
                    if not product or product.workspace_id != workspace_id:
                        raise HTTPException(status_code=404, detail="Product not found")
                    products[product_id] = product
                base_uom = product.base_uom_id

            normalized: Optional[Decimal] = None
            if base_uom is not None:
                factor = await AwardService._uom_factor(
                    session, workspace_id, product_id, quote_uom, base_uom
                )
                if factor is not None:
                    normalized = AwardService._normalize(
                        line_in.quoted_unit_price, data.exchange_rate, factor
                    )
            lines.append(
                SupplierQuoteItem(
                    rfq_item_id=rfq_item.id,
                    is_alternate=line_in.is_alternate,
                    alternate_product_id=line_in.alternate_product_id,
                    quantity_available=line_in.quantity_available,
                    quoted_unit_price=line_in.quoted_unit_price,
                    normalized_unit_price=normalized,
                    uom_id=quote_uom,
                )
            )

        covered = {line.rfq_item_id for line in lines}
        if len(covered) >= len(rfq_items) and rfq_items:
            completeness = QuoteCompleteness.FULL
        elif covered:
            completeness = QuoteCompleteness.PARTIAL
        else:
            completeness = QuoteCompleteness.INCOMPLETE

        comparable_total: Optional[Decimal] = None
        for line in lines:
            if line.normalized_unit_price is not None:
                chunk = line.normalized_unit_price * line.quantity_available
                comparable_total = (
                    chunk if comparable_total is None else comparable_total + chunk
                )
        if comparable_total is not None:
            comparable_total = comparable_total.quantize(Decimal("0.01"))

        response = SupplierRFQResponse(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            revision_number=revision,
            status=QuoteStatus.RECEIVED,
            completeness=completeness,
            quote_currency=data.quote_currency,
            exchange_rate=data.exchange_rate,
            normalized_total=comparable_total,
        )
        session.add(response)
        await session.flush()
        for line in lines:
            line.response_id = response.id
            session.add(line)
        if rfq.status == RFQStatus.SENT:
            rfq.status = RFQStatus.UNDER_EVALUATION
            rfq.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(response, ["quote_items"])
        return response

    # ------------------------------------------------------------------
    # Comparison (read-only)
    # ------------------------------------------------------------------

    @staticmethod
    async def comparison(
        session: AsyncSession, workspace_id: uuid.UUID, rfq_id: uuid.UUID
    ):
        rfq = await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)
        latest = AwardService._latest_responses(list(rfq.responses))
        suppliers = {response.supplier_id: response for response in latest.values()}
        names: dict[uuid.UUID, str] = {}
        if suppliers:
            rows = await session.execute(
                select(Supplier).where(
                    Supplier.workspace_id == workspace_id,
                    Supplier.id.in_(list(suppliers)),
                )
            )
            names = {s.id: s.name for s in rows.scalars().all()}

        quote_items: dict[uuid.UUID, list[SupplierQuoteItem]] = {}
        for response in latest.values():
            for line in response.quote_items:
                quote_items.setdefault(line.rfq_item_id, []).append(line)

        groups: list[ComparisonLineGroup] = []
        for rfq_item in rfq.items:
            rows = []
            minima = [
                line.normalized_unit_price
                for line in quote_items.get(rfq_item.id, [])
                if line.normalized_unit_price is not None
            ]
            floor = min(minima) if minima else None
            for line in quote_items.get(rfq_item.id, []):
                response = next(r for r in latest.values() if r.id == line.response_id)
                comparable = line.normalized_unit_price is not None
                rows.append(
                    ComparisonRow(
                        supplier_id=response.supplier_id,
                        supplier_name=names.get(response.supplier_id, ""),
                        quote_item_id=line.id,
                        quoted_unit_price=line.quoted_unit_price,
                        normalized_unit_price=line.normalized_unit_price,
                        comparable=comparable,
                        non_comparable_reason=(
                            None if comparable else "no UOM conversion to base unit"
                        ),
                        is_lowest=bool(
                            comparable
                            and floor is not None
                            and line.normalized_unit_price == floor
                        ),
                    )
                )
            groups.append(
                ComparisonLineGroup(
                    rfq_item_id=rfq_item.id,
                    requested_quantity=rfq_item.quantity,
                    rows=rows,
                )
            )
        return ComparisonResponse(rfq_id=rfq.id, currency=rfq.currency, lines=groups)

    @staticmethod
    async def _rank_minima(
        session: AsyncSession, workspace_id: uuid.UUID, rfq_id: uuid.UUID
    ) -> dict[uuid.UUID, Optional[Decimal]]:
        """Minimum comparable normalized price per RFQ line (None if none)."""
        comparison = await AwardService.comparison(session, workspace_id, rfq_id)
        minima: dict[uuid.UUID, Optional[Decimal]] = {}
        for group in comparison.lines:
            values = [row.normalized_unit_price for row in group.rows if row.comparable]
            minima[group.rfq_item_id] = min(values) if values else None
        return minima

    @staticmethod
    async def _approved_awarded_totals(
        session: AsyncSession, rfq_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]:
        """Awarded quantity per RFQ line across APPROVED+CONVERTED awards."""
        result = await session.execute(
            select(
                SupplierQuoteItem.rfq_item_id,
                func.coalesce(func.sum(RFQAwardLine.awarded_quantity), Decimal(0)),
            )
            .join(RFQAwardLine, RFQAwardLine.quote_item_id == SupplierQuoteItem.id)
            .join(RFQAward, RFQAwardLine.award_id == RFQAward.id)
            .where(
                RFQAward.rfq_id == rfq_id,
                RFQAward.status.in_([AwardStatus.APPROVED, AwardStatus.CONVERTED]),
            )
            .group_by(SupplierQuoteItem.rfq_item_id)
        )
        return {rfq_item_id: total for rfq_item_id, total in result.all()}

    @staticmethod
    async def _line_rfq_unit_value(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        rfq_item: RFQItem,
        product_id: Optional[uuid.UUID],
        normalized_unit_price: Decimal,
    ) -> Decimal:
        """Value of one RFQ-line-UOM unit at the normalized base-unit price."""
        base_uom = None
        if product_id is not None:
            product = await session.get(Product, product_id)
            base_uom = product.base_uom_id if product else None
        if base_uom is None or rfq_item.uom_id == base_uom:
            factor = Decimal(1)
        else:
            factor = await AwardService._uom_factor(
                session, workspace_id, product_id, rfq_item.uom_id, base_uom
            )
            if factor is None:
                raise HTTPException(
                    status_code=422,
                    detail="RFQ line UOM cannot be converted to base unit",
                )
        return (normalized_unit_price * factor).quantize(Decimal("0.01"))

    # ------------------------------------------------------------------
    # Award draft
    # ------------------------------------------------------------------

    @staticmethod
    async def draft_award(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        rfq_id: uuid.UUID,
        data: AwardCreate,
        current_user_id: uuid.UUID,
    ) -> RFQAward:
        from app.models.workspace import Workspace

        rfq = await AwardService._get_scoped_rfq(session, workspace_id, rfq_id)
        if rfq.status in CLOSED_RFQ_STATUSES:
            raise HTTPException(status_code=400, detail="RFQ is closed to new awards")
        supplier = await AwardService._get_workspace_supplier(
            session, workspace_id, data.supplier_id
        )
        if supplier.status != "ACTIVE":
            raise HTTPException(
                status_code=422, detail="Supplier is not eligible for awards"
            )
        if rfq.award_mode == RFQAwardMode.SINGLE and rfq.awards:
            raise HTTPException(
                status_code=400,
                detail="SINGLE award mode allows exactly one award header",
            )

        latest = AwardService._latest_responses(list(rfq.responses))
        quote_items: dict[uuid.UUID, SupplierQuoteItem] = {}
        quote_responses: dict[uuid.UUID, SupplierRFQResponse] = {}
        for response in latest.values():
            for line in response.quote_items:
                quote_items[line.id] = line
                quote_responses[line.id] = response
        rfq_items = {item.id: item for item in rfq.items}
        minima = await AwardService._rank_minima(session, workspace_id, rfq_id)
        committed = await AwardService._approved_awarded_totals(session, rfq_id)

        prepared = []
        for line_in in data.lines:
            quote_item = quote_items.get(line_in.quote_item_id)
            if quote_item is None:
                raise HTTPException(
                    status_code=404, detail="Quote item not found on this RFQ"
                )
            response = quote_responses.get(quote_item.id)
            if response is None or response.supplier_id != supplier.id:
                raise HTTPException(
                    status_code=422,
                    detail="Quote item does not belong to the awarded supplier",
                )
            if quote_item.normalized_unit_price is None:
                raise HTTPException(
                    status_code=422,
                    detail="Non-comparable quote lines cannot be awarded",
                )
            if line_in.awarded_quantity > quote_item.quantity_available:
                raise HTTPException(
                    status_code=422,
                    detail="Awarded quantity exceeds supplier availability",
                )
            rfq_item = rfq_items[quote_item.rfq_item_id]
            remainder = rfq_item.quantity - committed.get(rfq_item.id, Decimal(0))
            if line_in.awarded_quantity > remainder:
                raise HTTPException(
                    status_code=422,
                    detail="Awarded quantity exceeds unawarded RFQ remainder",
                )
            floor = minima.get(rfq_item.id)
            is_lowest = floor is not None and quote_item.normalized_unit_price == floor
            if not is_lowest and (
                not line_in.deviation_reason
                or len(line_in.deviation_reason.strip()) < 10
            ):
                # RFQ-024: non-lowest awards require justification.
                raise HTTPException(
                    status_code=422,
                    detail="deviation_reason (min 10 chars) is required for non-lowest awards",
                )
            product_id = AwardService._quote_product_id(quote_item, rfq_item)
            unit_value = await AwardService._line_rfq_unit_value(
                session,
                workspace_id,
                rfq_item,
                product_id,
                quote_item.normalized_unit_price,
            )
            prepared.append((quote_item, rfq_item, is_lowest, unit_value))

        impact = sum(
            (
                line_in.awarded_quantity * unit_value
                for (_, _, _, unit_value), line_in in zip(prepared, data.lines)
            ),
            Decimal(0),
        ).quantize(Decimal("0.01"))

        workspace = await session.get(Workspace, workspace_id)
        threshold = (
            workspace.rfq_award_approval_threshold
            if workspace and workspace.rfq_award_approval_threshold is not None
            else Decimal(0)
        )

        award_number = await AwardNumberService.generate_award_number(
            session, workspace_id
        )
        award = RFQAward(
            workspace_id=workspace_id,
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            award_number=award_number,
            total_awarded_value=impact,
            status=(
                AwardStatus.PENDING_APPROVAL
                if impact > threshold
                else AwardStatus.APPROVED
            ),
            justification=data.justification,
            awarded_by=current_user_id,
            approved_by=(current_user_id if impact <= threshold else None),
        )
        session.add(award)
        await session.flush()
        for (quote_item, _, is_lowest, _), line_in in zip(prepared, data.lines):
            session.add(
                RFQAwardLine(
                    award_id=award.id,
                    quote_item_id=quote_item.id,
                    awarded_quantity=line_in.awarded_quantity,
                    is_lowest_price=is_lowest,
                    deviation_reason=line_in.deviation_reason,
                )
            )
        await session.flush()
        await session.refresh(award, ["award_lines"])
        return award

    @staticmethod
    def _quote_product_id(
        quote_item: SupplierQuoteItem, rfq_item: RFQItem
    ) -> Optional[uuid.UUID]:
        if quote_item.is_alternate:
            return quote_item.alternate_product_id
        return rfq_item.product_id

    # ------------------------------------------------------------------
    # Award approve
    # ------------------------------------------------------------------

    @staticmethod
    async def approve_award(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        award_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> RFQAward:
        result = await session.execute(
            select(RFQAward)
            .where(
                RFQAward.id == award_id,
                RFQAward.workspace_id == workspace_id,
            )
            .options(selectinload(RFQAward.award_lines))
            .with_for_update()
        )
        award = result.scalar_one_or_none()
        if not award:
            raise HTTPException(status_code=404, detail="RFQ award not found")
        if award.status != AwardStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=400, detail="Only pending awards can be approved"
            )
        if award.awarded_by == current_user_id:
            raise HTTPException(
                status_code=400,
                detail="Maker-checker: approver must differ from proposer",
            )
        supplier = await session.get(Supplier, award.supplier_id)
        if not supplier or supplier.status != "ACTIVE":
            raise HTTPException(
                status_code=422, detail="Supplier is no longer eligible"
            )

        rfq = await AwardService._get_scoped_rfq(session, workspace_id, award.rfq_id)
        rfq_items = {item.id: item for item in rfq.items}
        quote_ids = [line.quote_item_id for line in award.award_lines]
        quote_rows = await session.execute(
            select(SupplierQuoteItem).where(SupplierQuoteItem.id.in_(quote_ids))
        )
        quotes = {q.id: q for q in quote_rows.scalars().all()}
        committed = await AwardService._approved_awarded_totals(session, rfq.id)
        for line in award.award_lines:
            quote_item = quotes.get(line.quote_item_id)
            if quote_item is None:
                raise HTTPException(
                    status_code=422, detail="Award line quote no longer exists"
                )
            rfq_item = rfq_items.get(quote_item.rfq_item_id)
            if rfq_item is None:
                raise HTTPException(
                    status_code=422, detail="Award line RFQ item no longer exists"
                )
            remainder = rfq_item.quantity - committed.get(rfq_item.id, Decimal(0))
            if line.awarded_quantity > remainder:
                raise HTTPException(
                    status_code=422,
                    detail="Awarded quantity exceeds unawarded RFQ remainder",
                )

        award.status = AwardStatus.APPROVED
        award.approved_by = current_user_id
        await session.flush()

        # Roll up awarded quantities; recompute RFQ + response statuses.
        for line in award.award_lines:
            rfq_item = rfq_items[quotes[line.quote_item_id].rfq_item_id]
            rfq_item.awarded_quantity = (
                rfq_item.awarded_quantity + line.awarded_quantity
            )
        await AwardService._refresh_contention_statuses(session, workspace_id, rfq)
        await session.commit()
        await session.refresh(award, ["award_lines"])
        return award

    @staticmethod
    async def _refresh_contention_statuses(
        session: AsyncSession, workspace_id: uuid.UUID, rfq: RFQ
    ) -> None:
        """Refresh response + RFQ statuses after an approval.

        Per-response coverage is computed across ALL approved/converted awards:
        fully covered responses become SELECTED, partially covered become
        PARTIALLY_SELECTED, uninvolved responses stay RECEIVED until the RFQ is
        fully awarded, when leftovers become NOT_SELECTED.
        """
        latest = AwardService._latest_responses(list(rfq.responses))
        if not latest:
            return
        covered: dict[uuid.UUID, Decimal] = {}
        awarded_per_item: dict[uuid.UUID, Decimal] = {}
        result = await session.execute(
            select(RFQAwardLine, SupplierQuoteItem)
            .join(SupplierQuoteItem, RFQAwardLine.quote_item_id == SupplierQuoteItem.id)
            .join(RFQAward, RFQAwardLine.award_id == RFQAward.id)
            .where(
                RFQAward.rfq_id == rfq.id,
                RFQAward.status.in_([AwardStatus.APPROVED, AwardStatus.CONVERTED]),
            )
        )
        for award_line, quote_item in result.all():
            key = (quote_item.response_id, quote_item.id)
            covered[key] = covered.get(key, Decimal(0)) + award_line.awarded_quantity
            awarded_per_item[quote_item.rfq_item_id] = (
                awarded_per_item.get(quote_item.rfq_item_id, Decimal(0))
                + award_line.awarded_quantity
            )

        for response in latest.values():
            response_lines = [line for line in response.quote_items]
            if not response_lines:
                continue
            fully = all(
                covered.get((response.id, line.id), Decimal(0))
                >= line.quantity_available
                for line in response_lines
            )
            any_awarded = any(
                covered.get((response.id, line.id), Decimal(0)) > 0
                for line in response_lines
            )
            if fully:
                response.status = QuoteStatus.SELECTED
            elif any_awarded:
                response.status = QuoteStatus.PARTIALLY_SELECTED

        fully_covered = (
            all(
                awarded_per_item.get(item.id, Decimal(0)) >= item.quantity
                for item in rfq.items
            )
            if rfq.items
            else False
        )
        if fully_covered:
            rfq.status = RFQStatus.AWARDED
            for response in latest.values():
                if response.status == QuoteStatus.RECEIVED:
                    response.status = QuoteStatus.NOT_SELECTED
        elif any(awarded_per_item.values()):
            rfq.status = RFQStatus.PARTIALLY_AWARDED
        rfq.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Award conversion (idempotent SPO generation, RFQ-028)
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_spos(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        award_id: uuid.UUID,
        data: GenerateSPOsRequest,
        current_user_id: uuid.UUID,
    ) -> GenerateSPOsResponse:
        from app.services.spo_service import SPOService
        from app.schemas.spo import SPOCreate, SPOItemCreate
        from app.models.spo import ProcurementMethod

        award = await AwardService._get_scoped_award(session, workspace_id, award_id)
        if award.status == AwardStatus.CONVERTED:
            existing = await AwardService._linked_spo_ids(session, workspace_id, award)
            return GenerateSPOsResponse(award_id=award.id, spo_ids=existing)
        if award.status != AwardStatus.APPROVED:
            raise HTTPException(
                status_code=400, detail="Only approved awards can be converted"
            )
        supplier = await session.get(Supplier, award.supplier_id)
        if not supplier or supplier.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if supplier.status != "ACTIVE":
            raise HTTPException(
                status_code=422, detail="Supplier is no longer eligible"
            )
        warehouse = await AwardService._get_workspace_warehouse(
            session, workspace_id, data.warehouse_id
        )
        rfq = await AwardService._get_scoped_rfq(session, workspace_id, award.rfq_id)

        already = set(await AwardService._linked_spo_ids(session, workspace_id, award))
        quote_ids = [line.quote_item_id for line in award.award_lines]
        quote_rows = await session.execute(
            select(SupplierQuoteItem).where(SupplierQuoteItem.id.in_(quote_ids))
        )
        quotes = {q.id: q for q in quote_rows.scalars().all()}
        rfq_items = {item.id: item for item in rfq.items}
        products: dict[uuid.UUID, object] = {}

        async def _product(product_id):
            if product_id is None:
                return None
            if product_id not in products:
                product = await session.get(Product, product_id)
                if not product or product.workspace_id != workspace_id:
                    raise HTTPException(status_code=404, detail="Product not found")
                products[product_id] = product
            return products[product_id]

        workspace = await session.get(Workspace, workspace_id)
        default_vat = workspace.default_tax_rate if workspace else Decimal("5.00")
        spo_lines = []
        line_number = 1
        for award_line in award.award_lines:
            quote_item = quotes.get(award_line.quote_item_id)
            if quote_item is None:
                raise HTTPException(
                    status_code=422, detail="Award line quote no longer exists"
                )
            rfq_item = rfq_items.get(quote_item.rfq_item_id)
            if rfq_item is None:
                raise HTTPException(
                    status_code=422, detail="Award line RFQ item no longer exists"
                )
            if award_line.id in already:
                continue
            product_id = AwardService._quote_product_id(quote_item, rfq_item)
            if product_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="Cannot convert a product-less award line",
                )
            product = await _product(product_id)
            unit_value = await AwardService._line_rfq_unit_value(
                session,
                workspace_id,
                rfq_item,
                product_id,
                quote_item.normalized_unit_price,
            )
            vat_rate = product.tax_rate if product.tax_rate is not None else default_vat
            spo_lines.append(
                SPOItemCreate(
                    product_id=product_id,
                    description=product.name,
                    uom_id=rfq_item.uom_id,
                    quantity_ordered=award_line.awarded_quantity,
                    unit_price=unit_value,
                    vat_rate=vat_rate,
                    rfq_award_line_id=award_line.id,
                    line_number=line_number,
                )
            )
            line_number += 1

        if not spo_lines:
            award.status = AwardStatus.CONVERTED
            await session.commit()
            existing = await AwardService._linked_spo_ids(session, workspace_id, award)
            return GenerateSPOsResponse(award_id=award.id, spo_ids=existing)

        spo = await SPOService.create_draft(
            session,
            workspace_id,
            SPOCreate(
                supplier_id=supplier.id,
                rfq_id=rfq.id,
                procurement_method=ProcurementMethod.RFQ,
                warehouse_id=warehouse.id,
                currency=rfq.currency,
                items=spo_lines,
            ),
            current_user_id,
        )
        award.status = AwardStatus.CONVERTED
        await session.commit()
        return GenerateSPOsResponse(award_id=award.id, spo_ids=[spo.id])

    @staticmethod
    async def _linked_spo_ids(
        session: AsyncSession, workspace_id: uuid.UUID, award
    ) -> list[uuid.UUID]:
        """SPOs already generated from this award's lines (idempotency)."""
        from app.models.spo import SupplierPurchaseOrder, SupplierPurchaseOrderItem

        line_ids = [line.id for line in award.award_lines]
        if not line_ids:
            return []
        result = await session.execute(
            select(SupplierPurchaseOrderItem.spo_id)
            .join(
                SupplierPurchaseOrder,
                SupplierPurchaseOrderItem.spo_id == SupplierPurchaseOrder.id,
            )
            .where(
                SupplierPurchaseOrderItem.rfq_award_line_id.in_(line_ids),
                SupplierPurchaseOrder.workspace_id == workspace_id,
            )
            .distinct()
        )
        return [row for row, in result.all()]

    @staticmethod
    async def _get_workspace_warehouse(session, workspace_id, warehouse_id):
        from app.models.inventory import Warehouse

        warehouse = await session.get(Warehouse, warehouse_id)
        if not warehouse or warehouse.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        return warehouse

    @staticmethod
    async def _get_scoped_award(
        session: AsyncSession, workspace_id: uuid.UUID, award_id: uuid.UUID
    ):
        result = await session.execute(
            select(RFQAward)
            .where(
                RFQAward.id == award_id,
                RFQAward.workspace_id == workspace_id,
            )
            .options(selectinload(RFQAward.award_lines))
            .with_for_update()
        )
        award = result.scalar_one_or_none()
        if not award:
            raise HTTPException(status_code=404, detail="RFQ award not found")
        return award
