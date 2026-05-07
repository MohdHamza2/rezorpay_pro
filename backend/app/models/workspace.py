from datetime import datetime, timezone
from typing import Optional, List
import uuid

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship, SQLModel


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(
        sa_column=Column(
            String(255),
            unique=True,
            index=True,
            nullable=False,
        )
    )
    
    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    # Relationships
    users: List["User"] = Relationship(back_populates="workspace")
    clients: List["Client"] = Relationship(back_populates="workspace")
    invoices: List["Invoice"] = Relationship(back_populates="workspace")
