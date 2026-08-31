import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class DnCounter(SQLModel, table=True):
    """
    Workspace-scoped delivery-note number counter (operational sequence).

    Composite primary key (workspace_id, year). Locked with FOR UPDATE
    inside the create transaction. Soft-delete does not rewind.
    """

    __tablename__ = "dn_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", primary_key=True, nullable=False
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
        """Generate formatted delivery-note number: DN-2026-0001."""
        return f"DN-{self.year}-{self.last_number:04d}"
