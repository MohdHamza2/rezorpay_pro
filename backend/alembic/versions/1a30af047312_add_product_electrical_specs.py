"""add product electrical specs

Revision ID: 1a30af047312
Revises: b8d5f0c3a216
Create Date: 2026-09-01 13:57:26.558242

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "1a30af047312"
down_revision: Union[str, None] = "b8d5f0c3a216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("amp_rating", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("cable_size_mm2", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column("products", sa.Column("cores", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("poles", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("voltage", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_products_workspace_amp_rating",
        "products",
        ["workspace_id", "amp_rating"],
        unique=False,
        postgresql_where=sa.text("amp_rating IS NOT NULL"),
    )
    op.create_index(
        "ix_products_workspace_cable_size_mm2",
        "products",
        ["workspace_id", "cable_size_mm2"],
        unique=False,
        postgresql_where=sa.text("cable_size_mm2 IS NOT NULL"),
    )
    op.create_index(
        "ix_products_workspace_cores",
        "products",
        ["workspace_id", "cores"],
        unique=False,
        postgresql_where=sa.text("cores IS NOT NULL"),
    )
    op.create_index(
        "ix_products_workspace_poles",
        "products",
        ["workspace_id", "poles"],
        unique=False,
        postgresql_where=sa.text("poles IS NOT NULL"),
    )
    op.create_index(
        "ix_products_workspace_voltage",
        "products",
        ["workspace_id", "voltage"],
        unique=False,
        postgresql_where=sa.text("voltage IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_products_workspace_voltage",
        table_name="products",
        postgresql_where=sa.text("voltage IS NOT NULL"),
    )
    op.drop_index(
        "ix_products_workspace_poles",
        table_name="products",
        postgresql_where=sa.text("poles IS NOT NULL"),
    )
    op.drop_index(
        "ix_products_workspace_cores",
        table_name="products",
        postgresql_where=sa.text("cores IS NOT NULL"),
    )
    op.drop_index(
        "ix_products_workspace_cable_size_mm2",
        table_name="products",
        postgresql_where=sa.text("cable_size_mm2 IS NOT NULL"),
    )
    op.drop_index(
        "ix_products_workspace_amp_rating",
        table_name="products",
        postgresql_where=sa.text("amp_rating IS NOT NULL"),
    )
    op.drop_column("products", "voltage")
    op.drop_column("products", "poles")
    op.drop_column("products", "cores")
    op.drop_column("products", "cable_size_mm2")
    op.drop_column("products", "amp_rating")
