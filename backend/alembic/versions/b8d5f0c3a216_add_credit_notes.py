"""add tax credit notes

Revision ID: b8d5f0c3a216
Revises: a7c4e9d2b105
Create Date: 2026-09-01 05:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "b8d5f0c3a216"
down_revision: Union[str, None] = "a7c4e9d2b105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TYPE invoiceeventtype ADD VALUE IF NOT EXISTS 'CREDIT_NOTE_ISSUED'"
        )
    )

    op.add_column(
        "invoices",
        sa.Column(
            "amount_credited",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "check_amount_credited_nonneg",
        "invoices",
        "amount_credited >= 0",
    )

    op.add_column(
        "clients",
        sa.Column(
            "credit_balance",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "check_client_credit_balance_nonneg",
        "clients",
        "credit_balance >= 0",
    )

    op.create_table(
        "credit_note_counters",
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
        "credit_notes",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("invoice_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("credit_note_number", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "ISSUED", name="creditnotestatus"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "SALES_RETURN",
                "INVOICE_ERROR",
                "DISCOUNT",
                "GOODWILL",
                "OTHER",
                name="creditnotereason",
            ),
            nullable=False,
        ),
        sa.Column("reason_notes", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("original_invoice_number", sa.String(length=50), nullable=True),
        sa.Column("original_issue_date", sa.Date(), nullable=True),
        sa.Column("invoice_kind", sa.String(length=20), nullable=True),
        sa.Column("seller_trn_snapshot", sa.String(length=15), nullable=True),
        sa.Column("seller_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("seller_address_snapshot", sa.Text(), nullable=True),
        sa.Column("buyer_trn_snapshot", sa.String(length=15), nullable=True),
        sa.Column("buyer_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("buyer_address_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("subtotal >= 0", name="check_cn_subtotal_positive"),
        sa.CheckConstraint("tax_amount >= 0", name="check_cn_tax_amount_positive"),
        sa.CheckConstraint("total_amount >= 0", name="check_cn_total_amount_positive"),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "credit_note_number",
            name="uq_workspace_credit_note_number",
        ),
    )
    op.create_index(
        op.f("ix_credit_notes_client_id"),
        "credit_notes",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_notes_created_at"),
        "credit_notes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_notes_credit_note_number"),
        "credit_notes",
        ["credit_note_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_notes_invoice_id"),
        "credit_notes",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_notes_workspace_id"),
        "credit_notes",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "credit_note_events",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("credit_note_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "CN_CREATED",
                "CN_UPDATED",
                "CN_ISSUED",
                name="creditnoteeventtype",
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
            ["credit_note_id"],
            ["credit_notes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_note_events_credit_note_id"),
        "credit_note_events",
        ["credit_note_id"],
        unique=False,
    )
    op.create_table(
        "credit_note_items",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("credit_note_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("invoice_item_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("product_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("uom_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("sku_snapshot", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="check_cn_item_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="check_cn_item_unit_price_positive"),
        sa.CheckConstraint("tax_rate >= 0", name="check_cn_item_tax_rate_positive"),
        sa.CheckConstraint(
            "total_price >= 0", name="check_cn_item_total_price_positive"
        ),
        sa.CheckConstraint(
            "discount_percent >= 0", name="check_cn_item_discount_percent_nonneg"
        ),
        sa.CheckConstraint(
            "discount_amount >= 0", name="check_cn_item_discount_amount_nonneg"
        ),
        sa.CheckConstraint("line_net >= 0", name="check_cn_item_line_net_nonneg"),
        sa.CheckConstraint("tax_amount >= 0", name="check_cn_item_tax_amount_nonneg"),
        sa.ForeignKeyConstraint(
            ["credit_note_id"],
            ["credit_notes.id"],
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
        op.f("ix_credit_note_items_credit_note_id"),
        "credit_note_items",
        ["credit_note_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_note_items_invoice_item_id"),
        "credit_note_items",
        ["invoice_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_note_items_product_id"),
        "credit_note_items",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_credit_note_items_product_id"), table_name="credit_note_items"
    )
    op.drop_index(
        op.f("ix_credit_note_items_invoice_item_id"),
        table_name="credit_note_items",
    )
    op.drop_index(
        op.f("ix_credit_note_items_credit_note_id"),
        table_name="credit_note_items",
    )
    op.drop_table("credit_note_items")
    op.drop_index(
        op.f("ix_credit_note_events_credit_note_id"),
        table_name="credit_note_events",
    )
    op.drop_table("credit_note_events")
    op.drop_index(op.f("ix_credit_notes_workspace_id"), table_name="credit_notes")
    op.drop_index(op.f("ix_credit_notes_invoice_id"), table_name="credit_notes")
    op.drop_index(op.f("ix_credit_notes_credit_note_number"), table_name="credit_notes")
    op.drop_index(op.f("ix_credit_notes_created_at"), table_name="credit_notes")
    op.drop_index(op.f("ix_credit_notes_client_id"), table_name="credit_notes")
    op.drop_table("credit_notes")
    op.drop_table("credit_note_counters")
    op.execute("DROP TYPE IF EXISTS creditnoteeventtype")
    op.execute("DROP TYPE IF EXISTS creditnotereason")
    op.execute("DROP TYPE IF EXISTS creditnotestatus")
    op.drop_constraint("check_client_credit_balance_nonneg", "clients", type_="check")
    op.drop_column("clients", "credit_balance")
    op.drop_constraint("check_amount_credited_nonneg", "invoices", type_="check")
    op.drop_column("invoices", "amount_credited")
