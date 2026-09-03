import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class EnquiryCounter(SQLModel, table=True):
    __tablename__ = "enquiry_counters"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", primary_key=True, nullable=False
    )
    year: int = Field(primary_key=True, nullable=False)
    last_number: int = Field(default=0, nullable=False)

    # Timestamps for audit
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    def generate_number(self) -> str:
        """Generate formatted enquiry number: ENQ-2026-0001"""
        return f"ENQ-{self.year}-{self.last_number:04d}"
