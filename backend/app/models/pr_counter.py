import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class PRCounter(SQLModel, table=True):
    """Workspace-scoped Purchase Request (PR) counter for gapless sequences.

    Mirrors InvoiceCounter/SPOCounter: composite primary key (workspace_id, year),
    locked with FOR UPDATE inside the transaction and only incremented when the
    PR successfully commits.
    """

    __tablename__ = "pr_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id",
        primary_key=True,
        nullable=False,
    )
    year: int = Field(primary_key=True, nullable=False)
    last_number: int = Field(default=0, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    def generate_number(self) -> str:
        """Generate formatted PR number: PR-2026-000001"""
        return f"PR-{self.year}-{self.last_number:06d}"
