"""add whatsapp messages

Revision ID: c5b7a3e9f21d
Revises: 3d3f24d6ee00
Create Date: 2026-09-07 16:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "c5b7a3e9f21d"
down_revision: Union[str, None] = "3d3f24d6ee00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    whatsappdirection = postgresql.ENUM(
        "INBOUND",
        "OUTBOUND",
        name="whatsappdirection",
        create_type=False,
    )
    whatsappdirection.create(op.get_bind(), checkfirst=True)

    whatsappmessagestatus = postgresql.ENUM(
        "QUEUED",
        "SENT",
        "DELIVERED",
        "READ",
        "RECEIVED",
        "FAILED",
        name="whatsappmessagestatus",
        create_type=False,
    )
    whatsappmessagestatus.create(op.get_bind(), checkfirst=True)

    whatsappmessagetype = postgresql.ENUM(
        "TEXT",
        "DOCUMENT",
        "MEDIA",
        name="whatsappmessagetype",
        create_type=False,
    )
    whatsappmessagetype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column(
            "direction",
            postgresql.ENUM(
                "INBOUND", "OUTBOUND", name="whatsappdirection", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "message_type",
            postgresql.ENUM(
                "TEXT",
                "DOCUMENT",
                "MEDIA",
                name="whatsappmessagetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("to_number", sa.String(length=20), nullable=True),
        sa.Column("from_number", sa.String(length=20), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=True),
        sa.Column("caption", sa.String(length=1024), nullable=True),
        sa.Column("document_type", sa.String(length=50), nullable=True),
        sa.Column("document_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column("document_filename", sa.String(length=255), nullable=True),
        sa.Column("media_id", sa.String(length=128), nullable=True),
        sa.Column("statement_from", sa.Date(), nullable=True),
        sa.Column("statement_to", sa.Date(), nullable=True),
        sa.Column("linked_entity_type", sa.String(length=50), nullable=True),
        sa.Column("linked_entity_id", sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "QUEUED",
                "SENT",
                "DELIVERED",
                "READ",
                "RECEIVED",
                "FAILED",
                name="whatsappmessagestatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("whatsapp_message_id", sa.String(length=128), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("provider_error_code", sa.String(length=64), nullable=True),
        sa.Column("provider_error_category", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_whatsapp_messages_workspace_id"),
        "whatsapp_messages",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_messages_workspace_id_created_at"),
        "whatsapp_messages",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_messages_workspace_linked"),
        "whatsapp_messages",
        ["workspace_id", "linked_entity_type", "linked_entity_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_whatsapp_messages_whatsapp_message_id",
        "whatsapp_messages",
        ["whatsapp_message_id"],
    )

    op.create_table(
        "whatsapp_idempotency_keys",
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("message_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["whatsapp_messages.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "key"),
    )
    op.create_index(
        op.f("ix_whatsapp_idempotency_keys_message_id"),
        "whatsapp_idempotency_keys",
        ["message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_whatsapp_idempotency_keys_message_id"),
        table_name="whatsapp_idempotency_keys",
    )
    op.drop_table("whatsapp_idempotency_keys")
    op.drop_constraint(
        "uq_whatsapp_messages_whatsapp_message_id", "whatsapp_messages", type_="unique"
    )
    op.drop_index(
        op.f("ix_whatsapp_messages_workspace_linked"),
        table_name="whatsapp_messages",
    )
    op.drop_index(
        op.f("ix_whatsapp_messages_workspace_id_created_at"),
        table_name="whatsapp_messages",
    )
    op.drop_index(
        op.f("ix_whatsapp_messages_workspace_id"),
        table_name="whatsapp_messages",
    )
    op.drop_table("whatsapp_messages")
    whatsappmessagetype = postgresql.ENUM(name="whatsappmessagetype", create_type=False)
    whatsappmessagetype.drop(op.get_bind(), checkfirst=True)
    whatsappmessagestatus = postgresql.ENUM(
        name="whatsappmessagestatus", create_type=False
    )
    whatsappmessagestatus.drop(op.get_bind(), checkfirst=True)
    whatsappdirection = postgresql.ENUM(name="whatsappdirection", create_type=False)
    whatsappdirection.drop(op.get_bind(), checkfirst=True)
