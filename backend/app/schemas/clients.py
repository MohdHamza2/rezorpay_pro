"""
Client CRUD Schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field


class ClientBase(BaseModel):
    """Base client schema with common fields."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    tax_id: Optional[str] = Field(
        None,
        max_length=50,
        validation_alias=AliasChoices("tax_id", "trn"),
    )


class ClientCreate(ClientBase):
    """Schema for creating a new client."""

    pass


class ClientUpdate(BaseModel):
    """Schema for updating a client."""

    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    tax_id: Optional[str] = Field(
        None,
        max_length=50,
        validation_alias=AliasChoices("tax_id", "trn"),
    )


class ClientResponse(ClientBase):
    """Schema for client response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ClientListResponse(BaseModel):
    """Schema for list of clients with pagination."""

    success: bool = True
    data: list[ClientResponse]
    pagination: dict
