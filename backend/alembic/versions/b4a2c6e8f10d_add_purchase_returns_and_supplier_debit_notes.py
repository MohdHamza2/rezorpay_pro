"""add purchase returns and supplier debit notes (Wave 23 AP)

Revision ID: b4a2c6e8f10d
Revises: a3f4c7d9e1b2
Create Date: 2026-09-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "b4a2c6e8f10d"
down_revision: Union[str, None] = "a3f4c7d9e1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    purchasereturnstatus = postgresql.ENUM(
        "DRAFT",
        "PENDING_SUPPLIER",
        "APPROVED",
        "DISPATCHED",
        "COMPLETED",
        "REJECTED",
        "CANCELLED",
        name="purchasereturnstatus",
    )
    purchasereturntype = postgresql.ENUM(
        "QUALITY_ISSUE",
        "DAMAGE",
        "WRONG_ITEM",
        "EXCESS",
        name="purchasereturntype",
    )
    supplierdebitnotestatus = postgresql.ENUM(
        "DRAFT",
        "ISSUED",
        "APPLIED",
        "CANCELLED",
        name="supplierdebitnotestatus",
    )
    purchasereturnstatus.create(op.get_bind(), checkfirst=True)
    purchasereturntype.create(op.get_bind(), checkfirst=True)
    supplierdebitnotestatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "purchase_return_counters",
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
    op.create_table(
        "purchase_returns",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("supplier_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("grn_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("prn_number", sa.Text(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DRAFT",
                "PENDING_SUPPLIER",
                "APPROVED",
                "DISPATCHED",
                "COMPLETED",
                "REJECTED",
                "CANCELLED",
                name="purchasereturnstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["grn_id"],
            ["goods_receipt_notes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "prn_number", name="uq_purchase_return_workspace_number"
        ),
    )
    op.create_index(
        op.f("ix_purchase_returns_grn_id"),
        "purchase_returns",
        ["grn_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_returns_prn_number"),
        "purchase_returns",
        ["prn_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_returns_supplier_id"),
        "purchase_returns",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_returns_workspace_id"),
        "purchase_returns",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "purchase_return_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("purchase_return_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("grn_item_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("internal_sku", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("uom_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("stock_out_qty", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column(
            "return_type",
            postgresql.ENUM(
                "QUALITY_ISSUE",
                "DAMAGE",
                "WRONG_ITEM",
                "EXCESS",
                name="purchasereturntype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "quantity > 0", name="chk_preturn_item_quantity_positive"
        ),
        sa.CheckConstraint(
            "stock_out_qty >= 0", name="chk_preturn_item_stock_out_nonneg"
        ),
        sa.CheckConstraint(
            "unit_price > 0", name="chk_preturn_item_unit_price_positive"
        ),
        sa.ForeignKeyConstraint(
            ["grn_item_id"],
            ["grn_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"],
            ["purchase_returns.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uom_id"],
            ["units_of_measure.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_purchase_return_items_grn_item_id"),
        "purchase_return_items",
        ["grn_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_return_items_purchase_return_id"),
        "purchase_return_items",
        ["purchase_return_id"],
        unique=False,
    )
    op.create_table(
        "supplier_debit_note_counters",
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
    op.create_table(
        "supplier_debit_notes",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("supplier_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("purchase_return_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("dn_number", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DRAFT",
                "ISSUED",
                "APPLIED",
                "CANCELLED",
                name="supplierdebitnotestatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("applied_invoice_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="chk_sdn_amount_positive"),
        sa.ForeignKeyConstraint(
            ["applied_invoice_id"],
            ["supplier_invoices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"],
            ["purchase_returns.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "dn_number", name="uq_supplier_dn_workspace_number"
        ),
    )
    op.create_index(
        op.f("ix_supplier_debit_notes_applied_invoice_id"),
        "supplier_debit_notes",
        ["applied_invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_debit_notes_dn_number"),
        "supplier_debit_notes",
        ["dn_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_debit_notes_purchase_return_id"),
        "supplier_debit_notes",
        ["purchase_return_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_debit_notes_supplier_id"),
        "supplier_debit_notes",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_debit_notes_workspace_id"),
        "supplier_debit_notes",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_supplier_debit_notes_workspace_id"),
        table_name="supplier_debit_notes",
    )
    op.drop_index(
        op.f("ix_supplier_debit_notes_supplier_id"),
        table_name="supplier_debit_notes",
    )
    op.drop_index(
        op.f("ix_supplier_debit_notes_purchase_return_id"),
        table_name="supplier_debit_notes",
    )
    op.drop_index(
        op.f("ix_supplier_debit_notes_dn_number"),
        table_name="supplier_debit_notes",
    )
    op.drop_index(
        op.f("ix_supplier_debit_notes_applied_invoice_id"),
        table_name="supplier_debit_notes",
    )
    op.drop_table("supplier_debit_notes")
    op.drop_table("supplier_debit_note_counters")
    op.drop_index(
        op.f("ix_purchase_return_items_purchase_return_id"),
        table_name="purchase_return_items",
    )
    op.drop_index(
        op.f("ix_purchase_return_items_grn_item_id"),
        table_name="purchase_return_items",
    )
    op.drop_table("purchase_return_items")
    op.drop_index(
        op.f("ix_purchase_returns_workspace_id"),
        table_name="purchase_returns",
    )
    op.drop_index(
        op.f("ix_purchase_returns_supplier_id"),
        table_name="purchase_returns",
    )
    op.drop_index(
        op.f("ix_purchase_returns_prn_number"),
        table_name="purchase_returns",
    )
    op.drop_index(
        op.f("ix_purchase_returns_grn_id"),
        table_name="purchase_returns",
    )
    op.drop_table("purchase_returns")
    op.drop_table("purchase_return_counters")
    op.execute("DROP TYPE IF EXISTS supplierdebitnotestatus")
    op.execute("DROP TYPE IF EXISTS purchasereturntype")
    op.execute("DROP TYPE IF EXISTS purchasereturnstatus")