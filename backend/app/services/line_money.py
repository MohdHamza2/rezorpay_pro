"""Shared ROUND_HALF_UP fils math for invoice and quotation lines.

Do not fork. Header totals = Σ line_net, Σ line_vat, money(subtotal + tax).
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status

from app.schemas.common import ErrorCode, ErrorDetail

FILS = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value: Decimal) -> Decimal:
    """ROUND_HALF_UP to 0.01 (fils) — per line, then sum."""
    return Decimal(value).quantize(FILS, rounding=ROUND_HALF_UP)


def apply_line_money(item: Any) -> None:
    """Set line_net, tax_amount, total_price (gross) on a line-shaped object."""
    extended = money(item.quantity * item.unit_price)
    if item.discount_amount > 0:
        disc = money(item.discount_amount)
    else:
        disc = money(extended * item.discount_percent / HUNDRED)
    if disc > extended:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="Discount exceeds line extended amount",
                field="discount_amount",
            ).model_dump(),
        )
    item.line_net = money(extended - disc)
    item.tax_amount = money(item.line_net * item.tax_rate / HUNDRED)
    item.total_price = money(item.line_net + item.tax_amount)


def xor_discounts(discount_percent: Decimal, discount_amount: Decimal) -> None:
    """Reject both percent and amount discounts on one line."""
    if discount_percent > 0 and discount_amount > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="Provide either discount_percent or discount_amount, not both",
                field=None,
            ).model_dump(),
        )
