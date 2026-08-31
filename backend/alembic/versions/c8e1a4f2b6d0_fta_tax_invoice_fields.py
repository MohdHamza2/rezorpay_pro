"""Add FTA tax invoice fields

Revision ID: c8e1a4f2b6d0
Revises: 06c9b4b1dcda
Create Date: 2026-08-31

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "c8e1a4f2b6d0"
down_revision: Union[str, None] = "06c9b4b1dcda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("address", sa.Text(), nullable=True))

    op.add_column("invoices", sa.Column("supply_date", sa.Date(), nullable=True))
    op.execute("UPDATE invoices SET supply_date = issue_date WHERE supply_date IS NULL")
    op.alter_column("invoices", "supply_date", nullable=False)
    op.add_column(
        "invoices", sa.Column("invoice_kind", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "invoices",
        sa.Column("seller_trn_snapshot", sa.String(length=15), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("seller_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "invoices", sa.Column("seller_address_snapshot", sa.Text(), nullable=True)
    )
    op.add_column(
        "invoices", sa.Column("buyer_trn_snapshot", sa.String(length=15), nullable=True)
    )
    op.add_column(
        "invoices",
        sa.Column("buyer_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "invoices", sa.Column("buyer_address_snapshot", sa.Text(), nullable=True)
    )

    op.add_column(
        "invoice_items",
        sa.Column(
            "product_id",
            sqlmodel.sql.sqltypes.GUID(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "uom_id",
            sqlmodel.sql.sqltypes.GUID(),
            sa.ForeignKey("units_of_measure.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "invoice_items", sa.Column("sku_snapshot", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "line_net",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "tax_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        """
        UPDATE invoice_items SET
            line_net = ROUND(quantity * unit_price, 2),
            tax_amount = ROUND(ROUND(quantity * unit_price, 2) * tax_rate / 100, 2),
            total_price = ROUND(quantity * unit_price, 2)
                + ROUND(ROUND(quantity * unit_price, 2) * tax_rate / 100, 2)
        """
    )
    op.alter_column("invoice_items", "discount_percent", server_default=None)
    op.alter_column("invoice_items", "discount_amount", server_default=None)
    op.alter_column("invoice_items", "line_net", server_default=None)
    op.alter_column("invoice_items", "tax_amount", server_default=None)

    op.create_index(
        op.f("ix_invoice_items_product_id"),
        "invoice_items",
        ["product_id"],
        unique=False,
    )
    op.create_check_constraint(
        "check_discount_percent_nonneg", "invoice_items", "discount_percent >= 0"
    )
    op.create_check_constraint(
        "check_discount_amount_nonneg", "invoice_items", "discount_amount >= 0"
    )
    op.create_check_constraint(
        "check_line_net_nonneg", "invoice_items", "line_net >= 0"
    )
    op.create_check_constraint(
        "check_item_tax_amount_nonneg", "invoice_items", "tax_amount >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("check_item_tax_amount_nonneg", "invoice_items", type_="check")
    op.drop_constraint("check_line_net_nonneg", "invoice_items", type_="check")
    op.drop_constraint("check_discount_amount_nonneg", "invoice_items", type_="check")
    op.drop_constraint("check_discount_percent_nonneg", "invoice_items", type_="check")
    op.drop_index(op.f("ix_invoice_items_product_id"), table_name="invoice_items")
    op.drop_column("invoice_items", "tax_amount")
    op.drop_column("invoice_items", "line_net")
    op.drop_column("invoice_items", "discount_amount")
    op.drop_column("invoice_items", "discount_percent")
    op.drop_column("invoice_items", "sku_snapshot")
    op.drop_column("invoice_items", "uom_id")
    op.drop_column("invoice_items", "product_id")
    op.drop_column("invoices", "buyer_address_snapshot")
    op.drop_column("invoices", "buyer_name_snapshot")
    op.drop_column("invoices", "buyer_trn_snapshot")
    op.drop_column("invoices", "seller_address_snapshot")
    op.drop_column("invoices", "seller_name_snapshot")
    op.drop_column("invoices", "seller_trn_snapshot")
    op.drop_column("invoices", "invoice_kind")
    op.drop_column("invoices", "supply_date")
    op.drop_column("workspaces", "address")
