"""Per-product UOM conversion resolution — Wave 31 Item 2.9.

Implements the deferred remainder of Rule 1.8
(``architecture/business-rules.md``) against the LIVE star data model
(locked by ``architecture/wave-3-product-master-addendum.md`` §3,
"LIVE MODEL WINS").

Live storage shape (no ``from_uom_id`` column, no migration here):

- Every ``ProductUOMConversion`` row is a directed edge
  ``Product.base_uom_id -> to_uom_id`` with the locked semantic
  "1 ``to_uom`` = ``conversion_factor`` base units".
- The stored graph is therefore a star centered on the base UOM.
  Maximum path depth is 2 (non-base -> base -> non-base).

Resolution semantics (locked examples; the returned factor ``f`` always
satisfies ``quantity_in_to_uom = quantity_in_from_uom * f``):

- ``from == to`` → ``Decimal("1")`` (no rows required).
- non-base → base → stored ``conversion_factor`` (multiply:
  3 BOX × 10 = 30 PCS).
- base → non-base → ``1 / conversion_factor`` (divide:
  30 PCS × (1/10) = 3 BOX).
- non-base → non-base through base → ``factor_from / factor_to``.
  Example (locked): base PCS, BOX = 10 PCS, CARTON = 50 PCS,
  BOX → CARTON = 10 / 50 = 0.2, CARTON → BOX = 50 / 10 = 5.
- No path → ``None`` (no custom exception; callers map ``None`` onto
  their own established errors, e.g. award non-comparability 422s).
- Full-precision ``Decimal`` throughout; the resolver never quantizes.
  Caller-side rounding (money ``0.01``, quantity ``(12,4)``/``(12,2)``)
  stays exactly as each consumer already does it.
- A visited-set BFS guard is kept for Rule 1.8 circular-prevention
  compliance and future-proofing, even though cycles are not
  representable in the current star schema. A cycle resolves as ``None``.

Scope (D1 OPTION 1): this module introduces the reusable resolver and
nothing else. No existing consumer (award flow, 3-way match, SPO, GRN,
inventory, pricing, receipts) is rewired here, so no live behavior
changes. All queries are scoped to ``(workspace_id, product_id)``.
"""

from __future__ import annotations

import uuid
from collections import deque
from decimal import Decimal
from typing import Optional, Sequence

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.product import Product, ProductUOMConversion


def _valid_factors(
    conversions: Sequence[ProductUOMConversion],
) -> dict[uuid.UUID, Decimal]:
    """Map ``to_uom_id`` -> factor, skipping unusable stored rows.

    Zero/negative factors cannot pass API validation, but rows inserted
    beneath the API must never cause division errors: they are treated
    as absent (unresolvable) rather than raising.
    """
    factors: dict[uuid.UUID, Decimal] = {}
    for row in conversions:
        factor = row.conversion_factor
        if factor is None:
            continue
        if not isinstance(factor, Decimal):
            factor = Decimal(str(factor))
        if factor <= 0:
            continue
        factors[row.to_uom_id] = factor
    return factors


def resolve_factor(
    *,
    base_uom_id: uuid.UUID,
    from_uom_id: uuid.UUID,
    to_uom_id: uuid.UUID,
    conversions: Sequence[ProductUOMConversion],
) -> Optional[Decimal]:
    """Pure factor resolver over pre-loaded conversion rows.

    Returns the multiplier ``f`` such that
    ``quantity_in_to_uom = quantity_in_from_uom * f``.
    ``None`` when no path exists. Never rounds; never raises for
    missing paths.
    """
    if from_uom_id == to_uom_id:
        return Decimal(1)
    factors = _valid_factors(conversions)

    def _neighbors(node: uuid.UUID) -> list[tuple[uuid.UUID, Decimal]]:
        if node == base_uom_id:
            # base -> to: divide by the stored factor (full precision).
            return [(to_id, Decimal(1) / factor) for to_id, factor in factors.items()]
        factor = factors.get(node)
        if factor is None:
            return []
        # to -> base: multiply by the stored factor.
        return [(base_uom_id, factor)]

    # BFS with visited set (Rule 1.8 circular prevention). On the live
    # star schema this terminates after at most two hops, but the guard
    # keeps the resolver correct if storage ever gains more edge types.
    visited = {from_uom_id}
    queue: deque[tuple[uuid.UUID, Decimal]] = deque([(from_uom_id, Decimal(1))])
    while queue:
        node, accumulated = queue.popleft()
        for neighbor, leg in _neighbors(node):
            if neighbor in visited:
                continue
            total = accumulated * leg
            if neighbor == to_uom_id:
                return total
            visited.add(neighbor)
            queue.append((neighbor, total))
    return None


def convert_quantity(
    *,
    base_uom_id: uuid.UUID,
    from_uom_id: uuid.UUID,
    to_uom_id: uuid.UUID,
    quantity: Decimal,
    conversions: Sequence[ProductUOMConversion],
) -> Optional[Decimal]:
    """Thin wrapper: ``quantity`` expressed in ``to_uom`` (full precision).

    ``None`` when unresolvable. No rounding is applied here; the caller
    quantizes per its own money/quantity conventions.
    """
    factor = resolve_factor(
        base_uom_id=base_uom_id,
        from_uom_id=from_uom_id,
        to_uom_id=to_uom_id,
        conversions=conversions,
    )
    if factor is None:
        return None
    amount = quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
    return amount * factor


async def _load_product_base_uom(
    session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> uuid.UUID:
    """Scoped product load; unknown/cross-workspace/deleted → 404.

    Follows product-service conventions (workspace scope + live rows
    only, ``"Product not found"``); no new error codes.
    """
    result = await session.execute(
        select(Product).where(
            Product.id == product_id,
            Product.workspace_id == workspace_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    return product.base_uom_id


async def _load_conversions(
    session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> list[ProductUOMConversion]:
    """Single bulk scoped load of every conversion row for the product."""
    result = await session.execute(
        select(ProductUOMConversion).where(
            ProductUOMConversion.workspace_id == workspace_id,
            ProductUOMConversion.product_id == product_id,
        )
    )
    return list(result.scalars().all())


async def resolve_factor_for_product(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    from_uom_id: uuid.UUID,
    to_uom_id: uuid.UUID,
) -> Optional[Decimal]:
    """DB-backed resolution: at most two queries, never per-leg N+1.

    One scoped product load (validates scope, yields the base UOM),
    then one bulk conversion-row load resolved in memory. Unknown or
    cross-workspace product → 404; known product without a path → None.
    """
    base_uom_id = await _load_product_base_uom(session, workspace_id, product_id)
    if from_uom_id == to_uom_id:
        return Decimal(1)
    rows = await _load_conversions(session, workspace_id, product_id)
    return resolve_factor(
        base_uom_id=base_uom_id,
        from_uom_id=from_uom_id,
        to_uom_id=to_uom_id,
        conversions=rows,
    )


async def convert_quantity_for_product(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    from_uom_id: uuid.UUID,
    to_uom_id: uuid.UUID,
    quantity: Decimal,
) -> Optional[Decimal]:
    """DB-backed quantity conversion (full precision, ``None`` if no path)."""
    base_uom_id = await _load_product_base_uom(session, workspace_id, product_id)
    if from_uom_id == to_uom_id:
        amount = quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
        return amount
    rows = await _load_conversions(session, workspace_id, product_id)
    return convert_quantity(
        base_uom_id=base_uom_id,
        from_uom_id=from_uom_id,
        to_uom_id=to_uom_id,
        quantity=quantity,
        conversions=rows,
    )
