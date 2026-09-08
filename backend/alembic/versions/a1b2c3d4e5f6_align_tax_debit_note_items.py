"""Align tax_debit_note_items with credit_note_items shape

Revision ID: a1b2c3d4e5f6
Revises: c5b7a3e9f21d
Create Date: 2026-09-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c5b7a3e9f21d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # internal_sku -> sku_snapshot (credit-note/invoice parity)
    op.alter_column(
        "tax_debit_note_items",
        "internal_sku",
        new_column_name="sku_snapshot",
        existing_type=sa.String(),
        type_=sa.String(length=100),
    )
    op.add_column(
        "tax_debit_note_items",
        sa.Column("uom_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
    )
    op.create_foreign_key(
        None,
        "tax_debit_note_items",
        "units_of_measure",
        ["uom_id"],
        ["id"],
    )
    op.add_column(
        "tax_debit_note_items",
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "tax_debit_note_items",
        sa.Column(
            "line_net",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "tax_debit_note_items",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "tax_debit_note_items",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Backfill historical lines using pre-fix semantics then drop server defaults
    # discount_amount = qty * unit_price * discount_percent / 100
    op.execute(
        """
        UPDATE tax_debit_note_items
        SET discount_amount = ROUND(
                (quantity * unit_price * discount_percent / 100)::numeric, 2
            ),
            line_net = ROUND(
                (quantity * unit_price
                 - quantity * unit_price * discount_percent / 100)::numeric, 2
            )
        """
    )
    op.alter_column("tax_debit_note_items", "discount_amount", server_default=None)
    op.alter_column("tax_debit_note_items", "line_net", server_default=None)
    op.alter_column("tax_debit_note_items", "created_at", server_default=None)
    op.alter_column("tax_debit_note_items", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "tax_debit_note_items_uom_id_fkey",
        "tax_debit_note_items",
        type_="foreignkey",
    )
    op.drop_column("tax_debit_note_items", "updated_at")
    op.drop_column("tax_debit_note_items", "created_at")
    op.drop_column("tax_debit_note_items", "line_net")
    op.drop_column("tax_debit_note_items", "discount_amount")
    op.drop_column("tax_debit_note_items", "uom_id")
    op.alter_column(
        "tax_debit_note_items",
        "sku_snapshot",
        new_column_name="internal_sku",
    )
