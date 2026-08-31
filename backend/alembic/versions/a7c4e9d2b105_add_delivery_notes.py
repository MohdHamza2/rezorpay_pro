"""add delivery notes

Revision ID: a7c4e9d2b105
Revises: 9f3a7c2e1d04
Create Date: 2026-09-01 04:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "a7c4e9d2b105"
down_revision: Union[str, None] = "9f3a7c2e1d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER TYPE crediteventreason ADD VALUE IF NOT EXISTS 'DN_CONFIRM'")
    )

    op.add_column(
        "customer_purchase_order_items",
        sa.Column(
            "quantity_delivered",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "check_cpo_qty_delivered_nonneg",
        "customer_purchase_order_items",
        "quantity_delivered >= 0",
    )
    op.create_check_constraint(
        "check_cpo_qty_delivered_lte_qty",
        "customer_purchase_order_items",
        "quantity_delivered <= quantity",
    )
    op.alter_column(
        "customer_purchase_order_items",
        "quantity_delivered",
        server_default=None,
    )

    op.add_column(
        "inventory_transactions",
        sa.Column("reason", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "inventory_transactions",
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "dn_counters",
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
        "delivery_notes",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=True,
        ),
        sa.Column("invoice_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("warehouse_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("dn_number", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "CONFIRMED",
                "CANCELLED",
                name="deliverynotestatus",
            ),
            nullable=False,
        ),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("shipping_address", sa.Text(), nullable=True),
        sa.Column("vehicle_number", sa.String(length=100), nullable=True),
        sa.Column("driver_name", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(customer_purchase_order_id IS NULL) <> (invoice_id IS NULL)",
            name="check_dn_parent_xor",
        ),
        sa.ForeignKeyConstraint(
            ["bin_id"],
            ["warehouse_bins.id"],
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["customer_purchase_order_id"],
            ["customer_purchase_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
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
        sa.UniqueConstraint("workspace_id", "dn_number", name="uq_workspace_dn_number"),
    )
    op.create_index(
        op.f("ix_delivery_notes_bin_id"),
        "delivery_notes",
        ["bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_client_id"),
        "delivery_notes",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_created_at"),
        "delivery_notes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_customer_purchase_order_id"),
        "delivery_notes",
        ["customer_purchase_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_dn_number"),
        "delivery_notes",
        ["dn_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_invoice_id"),
        "delivery_notes",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_warehouse_id"),
        "delivery_notes",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_notes_workspace_id"),
        "delivery_notes",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "delivery_note_events",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("delivery_note_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "DN_CREATED",
                "DN_UPDATED",
                "DN_CONFIRMED",
                "DN_CANCELLED",
                name="deliverynoteeventtype",
            ),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "metadata_log", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["delivery_note_id"],
            ["delivery_notes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delivery_note_events_delivery_note_id"),
        "delivery_note_events",
        ["delivery_note_id"],
        unique=False,
    )
    op.create_table(
        "delivery_note_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("delivery_note_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_item_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=True,
        ),
        sa.Column("invoice_item_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("uom_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("sku_snapshot", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("bin_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="check_dn_item_qty_positive"),
        sa.CheckConstraint(
            "(customer_purchase_order_item_id IS NULL) <> (invoice_item_id IS NULL)",
            name="check_dn_item_parent_xor",
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
            ["delivery_note_id"],
            ["delivery_notes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invoice_item_id"],
            ["invoice_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uom_id"],
            ["units_of_measure.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delivery_note_items_bin_id"),
        "delivery_note_items",
        ["bin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_note_items_customer_purchase_order_item_id"),
        "delivery_note_items",
        ["customer_purchase_order_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_note_items_delivery_note_id"),
        "delivery_note_items",
        ["delivery_note_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_note_items_invoice_item_id"),
        "delivery_note_items",
        ["invoice_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delivery_note_items_product_id"),
        "delivery_note_items",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_delivery_note_items_product_id"), table_name="delivery_note_items"
    )
    op.drop_index(
        op.f("ix_delivery_note_items_invoice_item_id"),
        table_name="delivery_note_items",
    )
    op.drop_index(
        op.f("ix_delivery_note_items_delivery_note_id"),
        table_name="delivery_note_items",
    )
    op.drop_index(
        op.f("ix_delivery_note_items_customer_purchase_order_item_id"),
        table_name="delivery_note_items",
    )
    op.drop_index(
        op.f("ix_delivery_note_items_bin_id"), table_name="delivery_note_items"
    )
    op.drop_table("delivery_note_items")
    op.drop_index(
        op.f("ix_delivery_note_events_delivery_note_id"),
        table_name="delivery_note_events",
    )
    op.drop_table("delivery_note_events")
    op.drop_index(op.f("ix_delivery_notes_workspace_id"), table_name="delivery_notes")
    op.drop_index(op.f("ix_delivery_notes_warehouse_id"), table_name="delivery_notes")
    op.drop_index(op.f("ix_delivery_notes_invoice_id"), table_name="delivery_notes")
    op.drop_index(op.f("ix_delivery_notes_dn_number"), table_name="delivery_notes")
    op.drop_index(
        op.f("ix_delivery_notes_customer_purchase_order_id"),
        table_name="delivery_notes",
    )
    op.drop_index(op.f("ix_delivery_notes_created_at"), table_name="delivery_notes")
    op.drop_index(op.f("ix_delivery_notes_client_id"), table_name="delivery_notes")
    op.drop_index(op.f("ix_delivery_notes_bin_id"), table_name="delivery_notes")
    op.drop_table("delivery_notes")
    op.drop_table("dn_counters")
    op.execute("DROP TYPE IF EXISTS deliverynoteeventtype")
    op.execute("DROP TYPE IF EXISTS deliverynotestatus")
    op.drop_column("inventory_transactions", "notes")
    op.drop_column("inventory_transactions", "reason")
    op.drop_constraint(
        "check_cpo_qty_delivered_lte_qty",
        "customer_purchase_order_items",
        type_="check",
    )
    op.drop_constraint(
        "check_cpo_qty_delivered_nonneg",
        "customer_purchase_order_items",
        type_="check",
    )
    op.drop_column("customer_purchase_order_items", "quantity_delivered")
