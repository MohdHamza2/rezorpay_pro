"""add email log

Revision ID: 3d3f24d6ee00
Revises: 234d5639ef8c
Create Date: 2026-09-07 11:45:24.417950

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "3d3f24d6ee00"
down_revision: Union[str, None] = "234d5639ef8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    emailstatus = postgresql.ENUM(
        "QUEUED",
        "SENT",
        "DELIVERED",
        "BOUNCED",
        "FAILED",
        name="emailstatus",
        create_type=False,
    )
    emailstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "email_log",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("bcc", postgresql.JSONB(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("linked_entity_type", sa.String(length=50), nullable=True),
        sa.Column("linked_entity_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "QUEUED",
                "SENT",
                "DELIVERED",
                "BOUNCED",
                "FAILED",
                name="emailstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("resend_message_id", sa.String(length=128), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_log_workspace_id"),
        "email_log",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_log_workspace_id_created_at"),
        "email_log",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_log_workspace_linked"),
        "email_log",
        ["workspace_id", "linked_entity_type", "linked_entity_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_email_log_resend_message_id", "email_log", ["resend_message_id"]
    )

    op.create_table(
        "email_idempotency_keys",
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("email_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["email_log.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "key"),
    )
    op.create_index(
        op.f("ix_email_idempotency_keys_email_id"),
        "email_idempotency_keys",
        ["email_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_email_idempotency_keys_email_id"),
        table_name="email_idempotency_keys",
    )
    op.drop_table("email_idempotency_keys")
    op.drop_constraint("uq_email_log_resend_message_id", "email_log", type_="unique")
    op.drop_index(
        op.f("ix_email_log_workspace_linked"),
        table_name="email_log",
    )
    op.drop_index(
        op.f("ix_email_log_workspace_id_created_at"),
        table_name="email_log",
    )
    op.drop_index(
        op.f("ix_email_log_workspace_id"),
        table_name="email_log",
    )
    op.drop_table("email_log")
    emailstatus = postgresql.ENUM(name="emailstatus", create_type=False)
    emailstatus.drop(op.get_bind(), checkfirst=True)
