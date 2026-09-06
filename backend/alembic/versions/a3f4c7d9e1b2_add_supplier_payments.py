"""add supplier payments (Wave 22 AP)

Revision ID: a3f4c7d9e1b2
Revises: e1f5b8a2c3d4
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "a3f4c7d9e1b2"
down_revision: Union[str, None] = "e1f5b8a2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_payments",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("supplier_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("supplier_invoice_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payment_method",
            postgresql.ENUM(
                "CASH",
                "BANK_TRANSFER",
                "CHEQUE",
                "PDC",
                "CREDIT_CARD",
                name="paymentmethod",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "SUCCESS",
                "FAILED",
                "CANCELLED",
                "REFUNDED",
                name="paymentstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="check_supplier_payment_amount_positive"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_invoice_id"],
            ["supplier_invoices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_supplier_payments_payment_date"),
        "supplier_payments",
        ["payment_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_payments_supplier_id"),
        "supplier_payments",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_payments_supplier_invoice_id"),
        "supplier_payments",
        ["supplier_invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_payments_workspace_id"),
        "supplier_payments",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "supplier_payment_idempotency_keys",
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("supplier_payment_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["supplier_payment_id"],
            ["supplier_payments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("workspace_id", "key"),
    )
    op.create_index(
        op.f("ix_supplier_payment_idempotency_keys_supplier_payment_id"),
        "supplier_payment_idempotency_keys",
        ["supplier_payment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_supplier_payment_idempotency_keys_supplier_payment_id"),
        table_name="supplier_payment_idempotency_keys",
    )
    op.drop_table("supplier_payment_idempotency_keys")
    op.drop_index(
        op.f("ix_supplier_payments_workspace_id"),
        table_name="supplier_payments",
    )
    op.drop_index(
        op.f("ix_supplier_payments_supplier_invoice_id"),
        table_name="supplier_payments",
    )
    op.drop_index(
        op.f("ix_supplier_payments_supplier_id"),
        table_name="supplier_payments",
    )
    op.drop_index(
        op.f("ix_supplier_payments_payment_date"),
        table_name="supplier_payments",
    )
    op.drop_table("supplier_payments")
