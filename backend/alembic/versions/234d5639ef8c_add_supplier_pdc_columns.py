"""add supplier PDC columns

Revision ID: 234d5639ef8c
Revises: b4a2c6e8f10d
Create Date: 2026-09-07 03:57:50.440449

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "234d5639ef8c"
down_revision: Union[str, None] = "b4a2c6e8f10d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy.dialects import postgresql

    pdc_status_enum = postgresql.ENUM(
        "RECEIVED",
        "DEPOSITED",
        "CLEARED",
        "BOUNCED",
        "RETURNED",
        name="pdcstatus",
        create_type=False,
    )
    pdc_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("supplier_payments", sa.Column("pdc_date", sa.Date(), nullable=True))
    op.add_column(
        "supplier_payments",
        sa.Column(
            "pdc_status",
            sa.Enum(
                "RECEIVED",
                "DEPOSITED",
                "CLEARED",
                "BOUNCED",
                "RETURNED",
                name="pdcstatus",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("supplier_payments", "pdc_status")
    op.drop_column("supplier_payments", "pdc_date")
