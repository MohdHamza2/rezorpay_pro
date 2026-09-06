"""add stock counts

Revision ID: e1f5b8a2c3d4
Revises: c6b3e7a9d2f0
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "e1f5b8a2c3d4"
down_revision: Union[str, None] = "c6b3e7a9d2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_counts",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("count_number", sa.String(length=50), nullable=False),
        sa.Column("warehouse_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SCHEDULED",
                "IN_PROGRESS",
                "COMPLETED",
                "RECONCILED",
                "CANCELLED",
                name="stockcountstatus",
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_counts_count_number"),
        "stock_counts",
        ["count_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_counts_warehouse_id"),
        "stock_counts",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_counts_workspace_id"),
        "stock_counts",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "stock_count_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("count_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "expected_quantity", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column("counted_quantity", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "requires_approval", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("approved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expected_quantity >= 0", name="chk_count_item_expected_positive"
        ),
        sa.CheckConstraint(
            "counted_quantity >= 0", name="chk_count_item_counted_positive"
        ),
        sa.ForeignKeyConstraint(
            ["bin_id"],
            ["warehouse_bins.id"],
        ),
        sa.ForeignKeyConstraint(
            ["count_id"],
            ["stock_counts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "count_id", "product_id", "bin_id", name="uq_count_item_product_bin"
        ),
    )
    op.create_index(
        op.f("ix_stock_count_items_bin_id"),
        "stock_count_items",
        ["bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_count_items_count_id"),
        "stock_count_items",
        ["count_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_count_items_product_id"),
        "stock_count_items",
        ["product_id"],
        unique=False,
    )
    op.create_table(
        "stock_count_counters",
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
    op.drop_table("stock_count_counters")
    op.drop_index(
        op.f("ix_stock_count_items_product_id"),
        table_name="stock_count_items",
    )
    op.drop_index(
        op.f("ix_stock_count_items_count_id"),
        table_name="stock_count_items",
    )
    op.drop_index(
        op.f("ix_stock_count_items_bin_id"),
        table_name="stock_count_items",
    )
    op.drop_table("stock_count_items")
    op.drop_index(
        op.f("ix_stock_counts_workspace_id"),
        table_name="stock_counts",
    )
    op.drop_index(
        op.f("ix_stock_counts_warehouse_id"),
        table_name="stock_counts",
    )
    op.drop_index(
        op.f("ix_stock_counts_count_number"),
        table_name="stock_counts",
    )
    op.drop_table("stock_counts")
    op.execute("DROP TYPE IF EXISTS stockcountstatus")
