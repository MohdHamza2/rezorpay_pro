import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import Column, DateTime, Numeric, String, UniqueConstraint, CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.product import Product

class Warehouse(SQLModel, table=True):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_workspace_warehouse_code"),
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", nullable=False, index=True)
    
    code: str = Field(max_length=50, index=True)
    name: str = Field(max_length=255)
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

class WarehouseBin(SQLModel, table=True):
    __tablename__ = "warehouse_bins"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_warehouse_bin_code"),
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False, index=True)
    
    code: str = Field(max_length=50, index=True)
    barcode: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)

class InventoryLevel(SQLModel, table=True):
    """
    Real-time snapshot of inventory at the Bin level.
    Rule 1.3: Available Stock = on_hand - reserved - damaged
    """
    __tablename__ = "inventory_levels"
    __table_args__ = (
        UniqueConstraint("product_id", "bin_id", name="uq_inventory_product_bin"),
        CheckConstraint("on_hand >= 0", name="chk_inventory_on_hand_positive"),
        CheckConstraint("reserved >= 0", name="chk_inventory_reserved_positive"),
        CheckConstraint("damaged >= 0", name="chk_inventory_damaged_positive"),
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", nullable=False, index=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False, index=True)
    bin_id: uuid.UUID = Field(foreign_key="warehouse_bins.id", nullable=False, index=True)
    
    on_hand: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2), nullable=False))
    reserved: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2), nullable=False))
    damaged: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2), nullable=False))
    
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

class TransactionType(str, Enum):
    INITIAL = "INITIAL"
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"

class InventoryTransaction(SQLModel, table=True):
    """
    Rule 1.2: StockTransaction is an IMMUTABLE ledger. All changes flow through business events.
    """
    __tablename__ = "inventory_transactions"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", nullable=False, index=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    
    transaction_type: TransactionType = Field(nullable=False)
    
    # Positive for Receipt/In, Negative for Issue/Out
    quantity: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    
    source_bin_id: Optional[uuid.UUID] = Field(default=None, foreign_key="warehouse_bins.id")
    destination_bin_id: Optional[uuid.UUID] = Field(default=None, foreign_key="warehouse_bins.id")
    
    reference_type: Optional[str] = Field(default=None, max_length=50) # e.g. GRN, DO, INVOICE
    reference_id: Optional[uuid.UUID] = Field(default=None) # Foreign key to the exact document
    
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
