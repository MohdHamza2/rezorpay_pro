"""Add missing check_amount_debited_nonneg constraint to invoices

Revision ID: e1f0aabb01aa
Revises: a1b2c3d4e5f6
Create Date: 2026-09-08 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f0aabb01aa"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Model declares CheckConstraint since Wave 28; the constraint was never
    # added by any migration (efe95b8ac5ec added amount_debited without it).
    op.create_check_constraint(
        "check_amount_debited_nonneg",
        "invoices",
        "amount_debited >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "check_amount_debited_nonneg",
        "invoices",
        type_="check",
    )
