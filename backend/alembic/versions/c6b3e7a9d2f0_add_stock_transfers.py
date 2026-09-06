"""add stock transfers

Revision ID: c6b3e7a9d2f0
Revises: b2a4d6f8e1c0
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "c6b3e7a9d2f0"
down_revision: Union[str, None] = "b2a4d6f8e1c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_levels",
        sa.Column(
            "in_transit",
            sa.Numeric(precision=12, scale=2),
            server_default="0.00",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "chk_inventory_in_transit_positive",
        "inventory_levels",
        "in_transit >= 0",
    )
    op.create_table(
        "stock_transfers",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("transfer_number", sa.String(length=50), nullable=False),
        sa.Column("source_warehouse_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "destination_warehouse_id", sqlmodel.sql.sqltypes.GUID(), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "APPROVED",
                "IN_TRANSIT",
                "RECEIVED",
                "CANCELLED",
                name="transferstatus",
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_warehouse_id != destination_warehouse_id",
            name="chk_st_transfer_distinct_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["destination_warehouse_id"],
            ["warehouses.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_warehouse_id"],
            ["warehouses.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_transfers_destination_warehouse_id"),
        "stock_transfers",
        ["destination_warehouse_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfers_source_warehouse_id"),
        "stock_transfers",
        ["source_warehouse_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfers_transfer_number"),
        "stock_transfers",
        ["transfer_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfers_workspace_id"),
        "stock_transfers",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "stock_transfer_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("transfer_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "received_quantity", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column("source_bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("destination_bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="chk_st_item_quantity_positive"),
        sa.CheckConstraint(
            "received_quantity >= 0", name="chk_st_item_received_positive"
        ),
        sa.CheckConstraint(
            "received_quantity <= quantity",
            name="chk_st_item_received_leq_quantity",
        ),
        sa.ForeignKeyConstraint(
            ["destination_bin_id"],
            ["warehouse_bins.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_bin_id"],
            ["warehouse_bins.id"],
        ),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["stock_transfers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_transfer_items_destination_bin_id"),
        "stock_transfer_items",
        ["destination_bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfer_items_product_id"),
        "stock_transfer_items",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfer_items_source_bin_id"),
        "stock_transfer_items",
        ["source_bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_transfer_items_transfer_id"),
        "stock_transfer_items",
        ["transfer_id"],
        unique=False,
    )
    op.create_table(
        "stock_transfer_counters",
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("workspace_id", "year"),
    )


def downgrade() -> None:
    op.drop_table("stock_transfer_counters")
    op.drop_index(
        op.f("ix_stock_transfer_items_transfer_id"),
        table_name="stock_transfer_items",
    )
    op.drop_index(
        op.f("ix_stock_transfer_items_source_bin_id"),
        table_name="stock_transfer_items",
    )
    op.drop_index(
        op.f("ix_stock_transfer_items_product_id"),
        table_name="stock_transfer_items",
    )
    op.drop_index(
        op.f("ix_stock_transfer_items_destination_bin_id"),
        table_name="stock_transfer_items",
    )
    op.drop_table("stock_transfer_items")
    op.drop_index(
        op.f("ix_stock_transfers_workspace_id"),
        table_name="stock_transfers",
    )
    op.drop_index(
        op.f("ix_stock_transfers_transfer_number"),
        table_name="stock_transfers",
    )
    op.drop_index(
        op.f("ix_stock_transfers_source_warehouse_id"),
        table_name="stock_transfers",
    )
    op.drop_index(
        op.f("ix_stock_transfers_destination_warehouse_id"),
        table_name="stock_transfers",
    )
    op.drop_table("stock_transfers")
    op.execute("DROP TYPE IF EXISTS transferstatus")
    op.drop_constraint(
        "chk_inventory_in_transit_positive",
        "inventory_levels",
        type_="check",
    )
    op.drop_column("inventory_levels", "in_transit")
