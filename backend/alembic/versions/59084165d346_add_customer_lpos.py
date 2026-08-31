"""add customer lpos

Revision ID: 59084165d346
Revises: cb01b6bef962
Create Date: 2026-09-01 01:33:47.717361

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "59084165d346"
down_revision: Union[str, None] = "cb01b6bef962"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lpo_counters",
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
        "customer_purchase_orders",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("quotation_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("lpo_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "customer_po_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "RECEIVED",
                "PARTIAL",
                "INVOICED",
                "CANCELLED",
                name="customerpurchaseorderstatus",
            ),
            nullable=False,
        ),
        sa.Column("lpo_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("subtotal >= 0", name="check_cpo_subtotal_positive"),
        sa.CheckConstraint("tax_amount >= 0", name="check_cpo_tax_amount_positive"),
        sa.CheckConstraint("total_amount >= 0", name="check_cpo_total_positive"),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
        ),
        sa.ForeignKeyConstraint(
            ["quotation_id"],
            ["quotations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "lpo_number", name="uq_workspace_lpo_number"
        ),
    )
    op.create_index(
        op.f("ix_customer_purchase_orders_client_id"),
        "customer_purchase_orders",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_purchase_orders_created_at"),
        "customer_purchase_orders",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_purchase_orders_lpo_number"),
        "customer_purchase_orders",
        ["lpo_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_purchase_orders_quotation_id"),
        "customer_purchase_orders",
        ["quotation_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_customer_purchase_orders_workspace_id"),
        "customer_purchase_orders",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_cpo_workspace_client_po_number",
        "customer_purchase_orders",
        ["workspace_id", "client_id", "customer_po_number"],
        unique=True,
        postgresql_where=sa.text("customer_po_number IS NOT NULL"),
    )
    op.create_table(
        "customer_purchase_order_events",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "CPO_CREATED",
                "CPO_UPDATED",
                "CPO_RECEIVED",
                "CPO_INVOICE_CREATED",
                "CPO_CANCELLED",
                "CPO_RECALC",
                name="customerpurchaseordereventtype",
            ),
            nullable=False,
        ),
        sa.Column("previous_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("new_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
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
            ["customer_purchase_order_id"],
            ["customer_purchase_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customer_purchase_order_events_customer_purchase_order_id"),
        "customer_purchase_order_events",
        ["customer_purchase_order_id"],
        unique=False,
    )
    op.create_table(
        "customer_purchase_order_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "customer_purchase_order_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=False,
        ),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("uom_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("sku_snapshot", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "quantity_invoiced", sa.Numeric(precision=10, scale=2), nullable=False
        ),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("discount_amount >= 0", name="check_cpo_disc_amt_nonneg"),
        sa.CheckConstraint("discount_percent >= 0", name="check_cpo_disc_pct_nonneg"),
        sa.CheckConstraint("line_net >= 0", name="check_cpo_line_net_nonneg"),
        sa.CheckConstraint("quantity > 0", name="check_cpo_item_qty_positive"),
        sa.CheckConstraint(
            "quantity_invoiced <= quantity", name="check_cpo_qty_invoiced_lte_qty"
        ),
        sa.CheckConstraint(
            "quantity_invoiced >= 0", name="check_cpo_qty_invoiced_nonneg"
        ),
        sa.CheckConstraint("tax_amount >= 0", name="check_cpo_item_tax_nonneg"),
        sa.CheckConstraint("tax_rate >= 0", name="check_cpo_item_tax_rate_positive"),
        sa.CheckConstraint("total_price >= 0", name="check_cpo_item_total_positive"),
        sa.CheckConstraint("unit_price >= 0", name="check_cpo_item_price_positive"),
        sa.ForeignKeyConstraint(
            ["customer_purchase_order_id"],
            ["customer_purchase_orders.id"],
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
        op.f("ix_customer_purchase_order_items_customer_purchase_order_id"),
        "customer_purchase_order_items",
        ["customer_purchase_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_purchase_order_items_product_id"),
        "customer_purchase_order_items",
        ["product_id"],
        unique=False,
    )
    op.add_column(
        "invoice_items",
        sa.Column(
            "customer_purchase_order_item_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_invoice_items_customer_purchase_order_item_id"),
        "invoice_items",
        ["customer_purchase_order_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_invoice_items_cpo_item_id",
        "invoice_items",
        "customer_purchase_order_items",
        ["customer_purchase_order_item_id"],
        ["id"],
    )
    op.add_column(
        "invoices",
        sa.Column(
            "customer_purchase_order_id",
            sqlmodel.sql.sqltypes.GUID(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_invoices_customer_purchase_order_id"),
        "invoices",
        ["customer_purchase_order_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_invoices_customer_purchase_order_id",
        "invoices",
        "customer_purchase_orders",
        ["customer_purchase_order_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_invoices_customer_purchase_order_id", "invoices", type_="foreignkey"
    )
    op.drop_index(op.f("ix_invoices_customer_purchase_order_id"), table_name="invoices")
    op.drop_column("invoices", "customer_purchase_order_id")
    op.drop_constraint(
        "fk_invoice_items_cpo_item_id", "invoice_items", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_invoice_items_customer_purchase_order_item_id"),
        table_name="invoice_items",
    )
    op.drop_column("invoice_items", "customer_purchase_order_item_id")
    op.drop_index(
        op.f("ix_customer_purchase_order_items_product_id"),
        table_name="customer_purchase_order_items",
    )
    op.drop_index(
        op.f("ix_customer_purchase_order_items_customer_purchase_order_id"),
        table_name="customer_purchase_order_items",
    )
    op.drop_table("customer_purchase_order_items")
    op.drop_index(
        op.f("ix_customer_purchase_order_events_customer_purchase_order_id"),
        table_name="customer_purchase_order_events",
    )
    op.drop_table("customer_purchase_order_events")
    op.drop_index(
        "uq_cpo_workspace_client_po_number",
        table_name="customer_purchase_orders",
        postgresql_where=sa.text("customer_po_number IS NOT NULL"),
    )
    op.drop_index(
        op.f("ix_customer_purchase_orders_workspace_id"),
        table_name="customer_purchase_orders",
    )
    op.drop_index(
        op.f("ix_customer_purchase_orders_quotation_id"),
        table_name="customer_purchase_orders",
    )
    op.drop_index(
        op.f("ix_customer_purchase_orders_lpo_number"),
        table_name="customer_purchase_orders",
    )
    op.drop_index(
        op.f("ix_customer_purchase_orders_created_at"),
        table_name="customer_purchase_orders",
    )
    op.drop_index(
        op.f("ix_customer_purchase_orders_client_id"),
        table_name="customer_purchase_orders",
    )
    op.drop_table("customer_purchase_orders")
    op.drop_table("lpo_counters")
    op.execute("DROP TYPE IF EXISTS customerpurchaseordereventtype")
    op.execute("DROP TYPE IF EXISTS customerpurchaseorderstatus")
