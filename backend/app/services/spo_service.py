import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from fastapi import HTTPException

from app.models.spo import (
    SPOAmendment,
    SPOAmendmentField,
    SPOAmendmentLine,
    SPOAmendmentStatus,
    SupplierPurchaseOrder,
    SupplierPurchaseOrderItem,
    SPOStatus,
    SPOStatusHistory,
)
from sqlalchemy.orm import selectinload
from app.schemas.spo import (
    SPOAmendmentApplyRequest,
    SPOAmendmentCreate,
    SPOCreate,
    SPOAcknowledgeReq,
)
from app.services.spo_number import SPONumberService

# SPO statuses after which the order is terminal — amendments can no longer
# be proposed (mirrors the cancel() terminal set).
TERMINAL_SPO_STATUSES = (
    SPOStatus.REJECTED,
    SPOStatus.CANCELLED,
    SPOStatus.PARTIALLY_CANCELLED,
    SPOStatus.SHORT_CLOSED,
    SPOStatus.CLOSED,
)

# Amendment statuses that keep an SPOAmendment "open" (unresolved).
OPEN_AMENDMENT_STATUSES = (
    SPOAmendmentStatus.PROPOSED,
    SPOAmendmentStatus.PENDING_APPROVAL,
    SPOAmendmentStatus.APPROVED,
)

# Amendment line fields that force supplier reconfirmation on apply (§4.6).
RECONFIRMATION_FIELDS = (
    SPOAmendmentField.UNIT_PRICE,
    SPOAmendmentField.QUANTITY_ORDERED,
)


class SPOService:
    @staticmethod
    async def _add_history(
        session: AsyncSession,
        spo_id: uuid.UUID,
        from_status: str,
        to_status: str,
        user_id: uuid.UUID,
        reason: Optional[str] = None,
    ):
        history = SPOStatusHistory(
            spo_id=spo_id,
            from_status=from_status,
            to_status=to_status,
            triggered_by=user_id,
            trigger_reason=reason,
        )
        session.add(history)

    @staticmethod
    async def _get_scoped_spo(
        session: AsyncSession, spo_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> SupplierPurchaseOrder:
        """Load an SPO by id, scoped to the workspace (multi-tenancy guard).

        Returns 404 for both missing and cross-tenant SPOs so callers cannot probe
        the existence of another workspace's orders.
        """
        result = await session.execute(
            select(SupplierPurchaseOrder)
            .where(SupplierPurchaseOrder.id == spo_id)
            .where(SupplierPurchaseOrder.workspace_id == workspace_id)
            .options(
                selectinload(SupplierPurchaseOrder.items),
                selectinload(SupplierPurchaseOrder.amendments).selectinload(
                    SPOAmendment.lines
                ),
            )
        )
        spo = result.scalar_one_or_none()
        if not spo:
            raise HTTPException(status_code=404, detail="SPO not found")
        return spo

    @staticmethod
    async def _lock_spo_row(
        session: AsyncSession, spo_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        """Take a FOR UPDATE row lock on the SPO (serializes numbering/flags)."""
        result = await session.execute(
            select(SupplierPurchaseOrder.id)
            .where(SupplierPurchaseOrder.id == spo_id)
            .where(SupplierPurchaseOrder.workspace_id == workspace_id)
            .with_for_update()
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="SPO not found")

    @staticmethod
    def _refresh_header_totals(spo: SupplierPurchaseOrder) -> None:
        """Recompute derived header totals from lines (C-25/SPO-007).

        Totals are always derived, never directly settable.
        """
        spo.quantity_ordered_total = sum(
            (i.quantity_ordered for i in spo.items), Decimal(0)
        )
        spo.quantity_confirmed_total = sum(
            (i.quantity_confirmed for i in spo.items), Decimal(0)
        )
        spo.quantity_backordered_total = sum(
            (i.quantity_backordered for i in spo.items), Decimal(0)
        )
        spo.subtotal = sum((i.total_price for i in spo.items), Decimal(0))
        spo.vat_amount = sum((i.vat_amount for i in spo.items), Decimal(0))
        spo.total_amount = spo.subtotal + spo.vat_amount

    @staticmethod
    async def _refresh_open_amendment_flag(
        session: AsyncSession, spo: SupplierPurchaseOrder
    ) -> None:
        """Recompute has_open_amendment from unresolved amendment rows."""
        result = await session.execute(
            select(func.count(SPOAmendment.id)).where(
                SPOAmendment.spo_id == spo.id,
                SPOAmendment.status.in_(OPEN_AMENDMENT_STATUSES),
            )
        )
        spo.has_open_amendment = result.scalar_one() > 0

    @staticmethod
    async def _next_amendment_number(session: AsyncSession, spo_id: uuid.UUID) -> int:
        """Next sequential amendment number for the SPO (caller holds row lock)."""
        result = await session.execute(
            select(func.coalesce(func.max(SPOAmendment.amendment_number), 0)).where(
                SPOAmendment.spo_id == spo_id
            )
        )
        return int(result.scalar_one()) + 1

    @staticmethod
    def _canonical_decimal(raw: str, field: str) -> Decimal:
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            raise HTTPException(
                status_code=422, detail=f"Invalid decimal new_value for {field}"
            )
        if value < 0:
            raise HTTPException(
                status_code=422, detail=f"new_value for {field} cannot be negative"
            )
        return value

    @staticmethod
    def _canonical_old_value(
        field_name: SPOAmendmentField, item, spo: SupplierPurchaseOrder
    ) -> str:
        if field_name == SPOAmendmentField.QUANTITY_ORDERED:
            return str(item.quantity_ordered)
        if field_name == SPOAmendmentField.UNIT_PRICE:
            return str(item.unit_price)
        if field_name == SPOAmendmentField.DELIVERY_DATE:
            return (
                item.expected_delivery_date.isoformat()
                if item.expected_delivery_date
                else ""
            )
        if field_name == SPOAmendmentField.DELIVERY_TERMS:
            return spo.delivery_terms or ""
        return ""

    @staticmethod
    def _parse_new_value(field_name: SPOAmendmentField, raw_value: str, item) -> str:
        """Validate and canonicalize a proposed new_value. Returns stored string."""
        if field_name in (
            SPOAmendmentField.QUANTITY_ORDERED,
            SPOAmendmentField.UNIT_PRICE,
        ):
            value = SPOService._canonical_decimal(raw_value, field_name.value)
            if (
                field_name == SPOAmendmentField.QUANTITY_ORDERED
                and value < item.quantity_received
            ):
                # SPO-013: cannot amend away physically received goods.
                raise HTTPException(
                    status_code=422,
                    detail="SPO-013: quantity_ordered cannot go below quantity_received",
                )
            return str(value)
        if field_name == SPOAmendmentField.DELIVERY_DATE:
            try:
                parsed = date.fromisoformat(str(raw_value))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=422,
                    detail="new_value for DELIVERY_DATE must be an ISO date",
                )
            return parsed.isoformat()
        if not str(raw_value).strip():
            raise HTTPException(
                status_code=422,
                detail=f"new_value for {field_name.value} cannot be empty",
            )
        return str(raw_value).strip()

    @staticmethod
    def _line_value_impact(
        field_name: SPOAmendmentField,
        old_raw: str,
        new_raw: str,
        item,
    ) -> Decimal:
        """Absolute AED impact of one amendment line (threshold comparison)."""
        if field_name == SPOAmendmentField.QUANTITY_ORDERED:
            return abs(Decimal(new_raw) - Decimal(old_raw)) * item.unit_price
        if field_name == SPOAmendmentField.UNIT_PRICE:
            return abs(Decimal(new_raw) - Decimal(old_raw)) * item.quantity_ordered
        return Decimal(0)

    @staticmethod
    async def create_draft(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_in: SPOCreate,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        # Gapless, workspace-scoped SPO number (SELECT FOR UPDATE on the counter)
        spo_number = await SPONumberService.generate_spo_number(session, workspace_id)

        spo = SupplierPurchaseOrder(
            workspace_id=workspace_id,
            spo_number=spo_number,
            **spo_in.model_dump(exclude={"items"}),
        )
        session.add(spo)
        await session.flush()

        subtotal = Decimal(0)
        vat_amount = Decimal(0)
        qty_total = Decimal(0)

        for item_in in spo_in.items:
            item_total = item_in.quantity_ordered * item_in.unit_price
            item_vat = item_total * (item_in.vat_rate / Decimal(100))

            item = SupplierPurchaseOrderItem(
                spo_id=spo.id,
                **item_in.model_dump(),
                total_price=item_total,
                vat_amount=item_vat,
                quantity_confirmed=item_in.quantity_ordered,
                open_quantity=item_in.quantity_ordered,
            )
            subtotal += item_total
            vat_amount += item_vat
            qty_total += item_in.quantity_ordered
            session.add(item)

        spo.subtotal = subtotal
        spo.vat_amount = vat_amount
        spo.total_amount = subtotal + vat_amount
        spo.quantity_ordered_total = qty_total
        spo.quantity_confirmed_total = qty_total

        await SPOService._add_history(
            session, spo.id, "NEW", SPOStatus.DRAFT.value, current_user_id
        )
        await session.commit()
        return (
            await session.scalars(
                select(SupplierPurchaseOrder)
                .where(SupplierPurchaseOrder.id == spo.id)
                .options(
                    selectinload(SupplierPurchaseOrder.items),
                    selectinload(SupplierPurchaseOrder.amendments).selectinload(
                        SPOAmendment.lines
                    ),
                )
            )
        ).first()

    @staticmethod
    async def submit_for_approval(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.PENDING_APPROVAL
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.DRAFT.value,
            SPOStatus.PENDING_APPROVAL.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def approve(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.PENDING_APPROVAL:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.APPROVED
        spo.approved_by = current_user_id
        spo.approved_at = datetime.now(timezone.utc)
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.PENDING_APPROVAL.value,
            SPOStatus.APPROVED.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def send(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status != SPOStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Invalid state transition")
        spo.status = SPOStatus.SENT
        spo.sent_at = datetime.now(timezone.utc)
        await SPOService._add_history(
            session,
            spo.id,
            SPOStatus.APPROVED.value,
            SPOStatus.SENT.value,
            current_user_id,
        )
        await session.commit()
        return spo

    @staticmethod
    async def acknowledge(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        ack_req: SPOAcknowledgeReq,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status not in (SPOStatus.SENT, SPOStatus.PARTIALLY_ACKNOWLEDGED):
            raise HTTPException(status_code=400, detail="Invalid state transition")
        if spo.has_open_amendment:
            # SPO-014: no acknowledgement while an amendment is unresolved.
            raise HTTPException(
                status_code=400,
                detail="SPO has an open amendment; resolve it before acknowledging",
            )

        all_rejected = True

        for item in spo.items:
            if item.id in ack_req.lines:
                ack_line = ack_req.lines[item.id]
                item.quantity_confirmed = ack_line.quantity_confirmed
                item.quantity_backordered = (
                    item.quantity_ordered - ack_line.quantity_confirmed
                )
                item.open_quantity = item.quantity_confirmed
                if ack_line.unit_price != item.unit_price:
                    item.price_amendment_pending = True
                    # SPO-005/D-14: persist the supplier-stated price change as
                    # a pending amendment instead of only flagging the line.
                    await SPOService._record_ack_price_amendment(
                        session, workspace_id, spo, item, ack_line, current_user_id
                    )

            if item.quantity_confirmed > 0:
                all_rejected = False

        # C-25/SPO-007: header derived totals are recomputed from lines —
        # partial confirmation must refresh confirmed/backordered rollups.
        SPOService._refresh_header_totals(spo)

        if all_rejected:
            new_status = SPOStatus.REJECTED
        elif not any(i.price_amendment_pending for i in spo.items):
            new_status = SPOStatus.ACKNOWLEDGED
            spo.acknowledged_at = datetime.now(timezone.utc)
        else:
            new_status = SPOStatus.PARTIALLY_ACKNOWLEDGED

        await SPOService._add_history(
            session,
            spo.id,
            spo.status.value,
            new_status.value,
            current_user_id,
            "Supplier acknowledged",
        )
        spo.status = new_status
        await session.commit()
        return spo

    @staticmethod
    async def _record_ack_price_amendment(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo: SupplierPurchaseOrder,
        item: SupplierPurchaseOrderItem,
        ack_line,
        current_user_id: uuid.UUID,
    ) -> None:
        """Persist a supplier-stated price change from acknowledgement (SPO-005).

        Creates a PENDING_APPROVAL amendment; the line stays unresolved until
        the amendment is approved and applied. Re-acknowledging the same price
        does not duplicate the row.
        """
        new_value = str(ack_line.unit_price)
        for existing in spo.amendments:
            if existing.status in OPEN_AMENDMENT_STATUSES and any(
                line.spo_item_id == item.id
                and line.field_name == SPOAmendmentField.UNIT_PRICE
                and line.new_value == new_value
                for line in existing.lines
            ):
                spo.has_open_amendment = True
                return

        await SPOService._lock_spo_row(session, spo.id, workspace_id)
        amendment = SPOAmendment(
            spo_id=spo.id,
            amendment_number=await SPOService._next_amendment_number(session, spo.id),
            status=SPOAmendmentStatus.PENDING_APPROVAL,
            reason=(
                "Price change on acknowledgement: " f"{item.unit_price} -> {new_value}"
            ),
            requires_supplier_reconfirmation=True,
            amended_by=current_user_id,
        )
        session.add(amendment)
        await session.flush()
        session.add(
            SPOAmendmentLine(
                amendment_id=amendment.id,
                spo_item_id=item.id,
                field_name=SPOAmendmentField.UNIT_PRICE,
                old_value=str(item.unit_price),
                new_value=new_value,
            )
        )
        spo.has_open_amendment = True
        await session.flush()

    @staticmethod
    async def _get_scoped_amendment(
        session: AsyncSession,
        spo_id: uuid.UUID,
        amendment_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> SPOAmendment:
        """Load an amendment by id, scoped to the workspace via its SPO."""
        result = await session.execute(
            select(SPOAmendment)
            .join(
                SupplierPurchaseOrder,
                SPOAmendment.spo_id == SupplierPurchaseOrder.id,
            )
            .where(
                SPOAmendment.id == amendment_id,
                SPOAmendment.spo_id == spo_id,
                SupplierPurchaseOrder.workspace_id == workspace_id,
            )
            .options(selectinload(SPOAmendment.lines))
            .with_for_update()
        )
        amendment = result.scalar_one_or_none()
        if not amendment:
            raise HTTPException(status_code=404, detail="SPO amendment not found")
        return amendment

    @staticmethod
    def _workspace_amendment_threshold(workspace) -> Decimal:
        return workspace.spo_amendment_approval_threshold or Decimal(0)

    @staticmethod
    async def propose_amendment(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        data: SPOAmendmentCreate,
        current_user_id: uuid.UUID,
    ) -> SPOAmendment:
        """Propose a buyer-initiated amendment (Item 2.2, §4.10).

        Validates every line, snapshots old values server-side, enforces the
        SPO-013 received floor, and routes above-threshold amendments to
        PENDING_APPROVAL (maker-checker) while auto-approving the rest.
        Identical re-submissions against an already-open amendment return the
        existing row instead of duplicating it. Never mutates SPO state.
        """
        from app.models.workspace import Workspace

        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status in TERMINAL_SPO_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Amendments cannot be proposed on a terminal SPO",
            )
        if not data.lines:
            raise HTTPException(
                status_code=422, detail="Amendment must include at least one line"
            )

        items_by_id = {item.id: item for item in spo.items}
        parsed: list[tuple[SupplierPurchaseOrderItem, SPOAmendmentField, str, str]] = []
        impact = Decimal(0)
        requires_reconfirmation = False
        for line_in in data.lines:
            item = items_by_id.get(line_in.spo_item_id)
            if item is None:
                raise HTTPException(
                    status_code=404,
                    detail="SPO item not found on this order",
                )
            old_value = SPOService._canonical_old_value(line_in.field_name, item, spo)
            new_value = SPOService._parse_new_value(
                line_in.field_name, line_in.new_value, item
            )
            if new_value == old_value:
                raise HTTPException(
                    status_code=422,
                    detail=f"new_value for {line_in.field_name.value} is unchanged",
                )
            parsed.append((item, line_in.field_name, old_value, new_value))
            impact += SPOService._line_value_impact(
                line_in.field_name, old_value, new_value, item
            )
            if line_in.field_name in RECONFIRMATION_FIELDS:
                requires_reconfirmation = True

        workspace = await session.get(Workspace, workspace_id)
        threshold = (
            SPOService._workspace_amendment_threshold(workspace)
            if workspace
            else Decimal(0)
        )

        await SPOService._lock_spo_row(session, spo.id, workspace_id)

        # Idempotency: evaluated under the row lock against a fresh read so
        # concurrent identical submissions cannot both slip through. An
        # identical still-open amendment is returned as-is.
        wanted = sorted(
            (str(item.id), field.value, new_value)
            for item, field, _, new_value in parsed
        )
        open_rows = (
            (
                await session.execute(
                    select(SPOAmendment)
                    .where(
                        SPOAmendment.spo_id == spo.id,
                        SPOAmendment.status.in_(OPEN_AMENDMENT_STATUSES),
                    )
                    .options(selectinload(SPOAmendment.lines))
                )
            )
            .scalars()
            .all()
        )
        for existing in open_rows:
            existing_lines = sorted(
                (str(line.spo_item_id), line.field_name.value, line.new_value or "")
                for line in existing.lines
            )
            if existing.reason == data.reason and existing_lines == wanted:
                return existing

        amendment = SPOAmendment(
            spo_id=spo.id,
            amendment_number=await SPOService._next_amendment_number(session, spo.id),
            status=(
                SPOAmendmentStatus.PENDING_APPROVAL
                if impact > threshold
                else SPOAmendmentStatus.APPROVED
            ),
            reason=data.reason,
            requires_supplier_reconfirmation=requires_reconfirmation,
            amended_by=current_user_id,
            approved_by=(current_user_id if impact <= threshold else None),
        )
        session.add(amendment)
        await session.flush()
        for item, field_name, old_value, new_value in parsed:
            session.add(
                SPOAmendmentLine(
                    amendment_id=amendment.id,
                    spo_item_id=item.id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                )
            )
        spo.has_open_amendment = True
        await session.flush()
        await session.refresh(amendment, ["lines"])
        return amendment

    @staticmethod
    async def approve_amendment(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        amendment_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SPOAmendment:
        """Maker-checker approval of a pending amendment (SPO-012)."""
        amendment = await SPOService._get_scoped_amendment(
            session, spo_id, amendment_id, workspace_id
        )
        if amendment.status != SPOAmendmentStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=400, detail="Only pending amendments can be approved"
            )
        if amendment.amended_by == current_user_id:
            raise HTTPException(
                status_code=400,
                detail="Maker-checker: approver must differ from proposer",
            )
        amendment.status = SPOAmendmentStatus.APPROVED
        amendment.approved_by = current_user_id
        await session.flush()
        await session.refresh(amendment, ["lines"])
        return amendment

    @staticmethod
    async def apply_amendment(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        amendment_id: uuid.UUID,
        data: SPOAmendmentApplyRequest,
    ) -> SPOAmendment:
        """Apply an approved amendment onto the SPO in place (§4.6).

        Writes the new values onto the referenced SPO lines/header, recomputes
        derived totals (C-25), clears resolved price flags, stamps APPLIED, and
        recomputes the open-amendment flag. Never touches GRN snapshots,
        landed-cost rows, invoices, or payments.
        """
        amendment = await SPOService._get_scoped_amendment(
            session, spo_id, amendment_id, workspace_id
        )
        if amendment.status != SPOAmendmentStatus.APPROVED:
            raise HTTPException(
                status_code=400, detail="Only approved amendments can be applied"
            )
        if amendment.requires_supplier_reconfirmation and not data.supplier_reconfirmed:
            raise HTTPException(
                status_code=422,
                detail="Supplier reconfirmation is required before applying",
            )

        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        items_by_id = {item.id: item for item in spo.items}
        for line in amendment.lines:
            item = items_by_id.get(line.spo_item_id)
            if item is None:
                raise HTTPException(
                    status_code=422,
                    detail="Amendment references an SPO line that no longer exists",
                )
            if line.field_name == SPOAmendmentField.QUANTITY_ORDERED:
                item.quantity_ordered = Decimal(line.new_value or "0")
                item.quantity_backordered = (
                    item.quantity_ordered - item.quantity_confirmed
                )
            elif line.field_name == SPOAmendmentField.UNIT_PRICE:
                item.unit_price = Decimal(line.new_value or "0")
                item.price_amendment_pending = False
            elif line.field_name == SPOAmendmentField.DELIVERY_DATE:
                item.expected_delivery_date = (
                    date.fromisoformat(line.new_value) if line.new_value else None
                )
            elif line.field_name == SPOAmendmentField.DELIVERY_TERMS:
                spo.delivery_terms = line.new_value
            # OTHER is recorded for audit only and mutates nothing.

        # Re-derive money totals for every touched line from its final
        # (ordered, price, vat_rate) so multi-line amendments are order
        # independent, mirroring the create_draft computation basis.
        for line in amendment.lines:
            item = items_by_id.get(line.spo_item_id)
            if item is None:
                continue
            if line.field_name in (
                SPOAmendmentField.QUANTITY_ORDERED,
                SPOAmendmentField.UNIT_PRICE,
            ):
                item.total_price = item.quantity_ordered * item.unit_price
                item.vat_amount = item.total_price * (item.vat_rate / Decimal(100))

        SPOService._refresh_header_totals(spo)
        amendment.status = SPOAmendmentStatus.APPLIED
        amendment.applied_at = datetime.now(timezone.utc)
        await session.flush()
        await SPOService._refresh_open_amendment_flag(session, spo)
        await session.refresh(amendment, ["lines"])
        return amendment

    @staticmethod
    async def cancel(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        spo_id: uuid.UUID,
        reason: str,
        current_user_id: uuid.UUID,
    ) -> SupplierPurchaseOrder:
        spo = await SPOService._get_scoped_spo(session, spo_id, workspace_id)
        if spo.status in (
            SPOStatus.CANCELLED,
            SPOStatus.CLOSED,
            SPOStatus.SHORT_CLOSED,
        ):
            raise HTTPException(status_code=400, detail="Invalid state transition")

        has_receipt = any(item.quantity_received > 0 for item in spo.items)
        if has_receipt:
            new_status = SPOStatus.PARTIALLY_CANCELLED
            for item in spo.items:
                if item.open_quantity > 0:
                    item.quantity_cancelled = item.open_quantity
                    item.open_quantity = Decimal(0)
        else:
            new_status = SPOStatus.CANCELLED
            for item in spo.items:
                item.quantity_cancelled = item.quantity_confirmed
                item.open_quantity = Decimal(0)

        await SPOService._add_history(
            session, spo.id, spo.status.value, new_status.value, current_user_id, reason
        )
        spo.status = new_status
        await session.commit()
        return await SPOService._get_scoped_spo(session, spo_id, workspace_id)
