import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer
from sqlmodel import Field, SQLModel


class InvoiceCounter(SQLModel, table=True):
    """
    Workspace-scoped invoice number counter for gapless sequences.
    
    Uses composite primary key (workspace_id, year) to track
    per-workspace, per-year counters.
    
    Gapless Guarantee:
    - Counter is locked with FOR UPDATE inside transaction
    - Only incremented when invoice successfully commits
    - If transaction fails, counter rolls back (no gaps)
    """
    __tablename__ = "invoice_counters"
    
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id",
        primary_key=True,
        nullable=False
    )
    year: int = Field(primary_key=True, nullable=False)
    last_number: int = Field(default=0, nullable=False)
    
    # Timestamps for audit
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    def generate_number(self) -> str:
        """Generate formatted invoice number: INV-2026-0001"""
        return f"INV-{self.year}-{self.last_number:04d}"
