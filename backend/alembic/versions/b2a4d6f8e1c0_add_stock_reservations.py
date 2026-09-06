"""add stock reservations

Revision ID: b2a4d6f8e1c0
Revises: 9f3a2c1e5d84
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "b2a4d6f8e1c0"
down_revision: Union[str, None] = "9f3a2c1e5d84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_reservations",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "DISPATCHED", "CANCELLED", "EXPIRED", name="reservationstatus"
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_purchase_order_id"],
            ["customer_purchase_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_reservations_customer_purchase_order_id"),
        "stock_reservations",
        ["customer_purchase_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservations_workspace_id"),
        "stock_reservations",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "stock_reservation_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("reservation_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_item_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=False,
        ),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("warehouse_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "quantity_consumed", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "DISPATCHED", "CANCELLED", "EXPIRED", name="reservationstatus"
            ),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="chk_reservation_item_qty_positive"),
        sa.CheckConstraint(
            "quantity_consumed >= 0", name="chk_reservation_item_consumed_positive"
        ),
        sa.CheckConstraint(
            "quantity_consumed <= quantity",
            name="chk_reservation_item_consumed_lte_qty",
        ),
        sa.ForeignKeyConstraint(
            ["bin_id"],
            ["warehouse_bins.id"],
        ),
        sa.ForeignKeyConstraint(
            ["customer_purchase_order_item_id"],
            ["customer_purchase_order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["stock_reservations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_reservation_items_bin_id"),
        "stock_reservation_items",
        ["bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservation_items_customer_purchase_order_item_id"),
        "stock_reservation_items",
        ["customer_purchase_order_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservation_items_product_id"),
        "stock_reservation_items",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservation_items_reservation_id"),
        "stock_reservation_items",
        ["reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservation_items_warehouse_id"),
        "stock_reservation_items",
        ["warehouse_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_stock_reservation_items_warehouse_id"),
        table_name="stock_reservation_items",
    )
    op.drop_index(
        op.f("ix_stock_reservation_items_reservation_id"),
        table_name="stock_reservation_items",
    )
    op.drop_index(
        op.f("ix_stock_reservation_items_product_id"),
        table_name="stock_reservation_items",
    )
    op.drop_index(
        op.f("ix_stock_reservation_items_customer_purchase_order_item_id"),
        table_name="stock_reservation_items",
    )
    op.drop_index(
        op.f("ix_stock_reservation_items_bin_id"),
        table_name="stock_reservation_items",
    )
    op.drop_table("stock_reservation_items")
    op.drop_index(
        op.f("ix_stock_reservations_workspace_id"),
        table_name="stock_reservations",
    )
    op.drop_index(
        op.f("ix_stock_reservations_customer_purchase_order_id"),
        table_name="stock_reservations",
    )
    op.drop_table("stock_reservations")
    op.execute("DROP TYPE IF EXISTS reservationstatus")
