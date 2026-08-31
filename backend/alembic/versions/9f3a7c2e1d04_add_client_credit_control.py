"""add client credit control

Revision ID: 9f3a7c2e1d04
Revises: 59084165d346
Create Date: 2026-09-01 02:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "9f3a7c2e1d04"
down_revision: Union[str, None] = "59084165d346"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    creditstatus = postgresql.ENUM(
        "ACTIVE", "WARNING", "HOLD", name="creditstatus", create_type=False
    )
    crediteventreason = postgresql.ENUM(
        "EVALUATE",
        "PAYMENT",
        "SEND_CHECK",
        "RECEIVE_CHECK",
        name="crediteventreason",
        create_type=False,
    )
    creditstatus.create(op.get_bind(), checkfirst=True)
    crediteventreason.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "clients",
        sa.Column("credit_limit", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column(
            "payment_terms_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "credit_status",
            postgresql.ENUM(
                "ACTIVE", "WARNING", "HOLD", name="creditstatus", create_type=False
            ),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "credit_status_changed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "credit_status_changed_by", sqlmodel.sql.sqltypes.GUID(), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_clients_credit_status_changed_by",
        "clients",
        "users",
        ["credit_status_changed_by"],
        ["id"],
    )
    op.create_check_constraint(
        "check_client_credit_limit_nonneg",
        "clients",
        "credit_limit IS NULL OR credit_limit >= 0",
    )
    op.create_check_constraint(
        "check_client_payment_terms_days",
        "clients",
        "payment_terms_days IN (0, 30, 45, 60)",
    )

    op.create_table(
        "credit_status_events",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "previous_status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "new_status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("exposure", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("effective_limit", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("oldest_overdue_days", sa.Integer(), nullable=True),
        sa.Column(
            "reason",
            postgresql.ENUM(
                "EVALUATE",
                "PAYMENT",
                "SEND_CHECK",
                "RECEIVE_CHECK",
                name="crediteventreason",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("changed_by", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column(
            "metadata_log",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_status_events_client_id"),
        "credit_status_events",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_status_events_workspace_id"),
        "credit_status_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoices_workspace_id_client_id_status",
        "invoices",
        ["workspace_id", "client_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_workspace_id_client_id_status", table_name="invoices")
    op.drop_index(
        op.f("ix_credit_status_events_workspace_id"), table_name="credit_status_events"
    )
    op.drop_index(
        op.f("ix_credit_status_events_client_id"), table_name="credit_status_events"
    )
    op.drop_table("credit_status_events")
    op.drop_constraint("check_client_payment_terms_days", "clients", type_="check")
    op.drop_constraint("check_client_credit_limit_nonneg", "clients", type_="check")
    op.drop_constraint(
        "fk_clients_credit_status_changed_by", "clients", type_="foreignkey"
    )
    op.drop_column("clients", "credit_status_changed_by")
    op.drop_column("clients", "credit_status_changed_at")
    op.drop_column("clients", "credit_status")
    op.drop_column("clients", "payment_terms_days")
    op.drop_column("clients", "credit_limit")
    sa.Enum(name="crediteventreason").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="creditstatus").drop(op.get_bind(), checkfirst=True)
