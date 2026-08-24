"""add spo_counters (gapless SPO numbering)

Revision ID: b7e2f4a9c1d3
Revises: 12bdad2ae924
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7e2f4a9c1d3'
down_revision: Union[str, None] = '12bdad2ae924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'spo_counters',
        sa.Column('workspace_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('workspace_id', 'year'),
    )


def downgrade() -> None:
    op.drop_table('spo_counters')
