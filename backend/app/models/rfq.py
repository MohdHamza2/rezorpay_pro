import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Numeric,
    UniqueConstraint,
    Text,
    Boolean,
    Integer,
)
from sqlmodel import Field, Relationship, SQLModel


class RFQType(str, Enum):
    STANDARD = "STANDARD"
    URGENT = "URGENT"
    MARKET_DISCOVERY = "MARKET_DISCOVERY"
    ANNUAL_CONTRACT = "ANNUAL_CONTRACT"


class RFQAwardMode(str, Enum):
    SINGLE = "SINGLE"
    SPLIT = "SPLIT"


class RFQEvalCriteria(str, Enum):
    LOWEST_PRICE = "LOWEST_PRICE"
    LOWEST_LANDED_COST = "LOWEST_LANDED_COST"
    WEIGHTED_SCORE = "WEIGHTED_SCORE"


class RFQStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIALLY_RESPONDED = "PARTIALLY_RESPONDED"
    FULLY_RESPONDED = "FULLY_RESPONDED"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    PARTIALLY_AWARDED = "PARTIALLY_AWARDED"
    AWARDED = "AWARDED"
    EXPIRED = "EXPIRED"


class QuoteCompleteness(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"


class QuoteStatus(str, Enum):
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    SHORTLISTED = "SHORTLISTED"
    SELECTED = "SELECTED"
    PARTIALLY_SELECTED = "PARTIALLY_SELECTED"
    NOT_SELECTED = "NOT_SELECTED"
    DECLINED = "DECLINED"
    NO_RESPONSE = "NO_RESPONSE"
    WITHDRAWN = "WITHDRAWN"
    SUPERSEDED = "SUPERSEDED"


class AwardStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    CONVERTED = "CONVERTED"


# --- Models ---


class RFQ(SQLModel, table=True):
    __tablename__ = "rfqs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "rfq_number", name="uq_workspace_rfq_number"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )

    rfq_number: str = Field(max_length=50, index=True)
    rfq_type: RFQType = Field(default=RFQType.STANDARD)
    award_mode: RFQAwardMode = Field(default=RFQAwardMode.SPLIT)
    evaluation_criteria: RFQEvalCriteria = Field(
        default=RFQEvalCriteria.LOWEST_LANDED_COST
    )

    deadline: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    sealed_until: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )

    currency: str = Field(default="AED", max_length=3)
    status: RFQStatus = Field(default=RFQStatus.DRAFT)

    created_by_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    items: List["RFQItem"] = Relationship(back_populates="rfq")
    responses: List["SupplierRFQResponse"] = Relationship(back_populates="rfq")


class RFQItem(SQLModel, table=True):
    __tablename__ = "rfq_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    rfq_id: uuid.UUID = Field(foreign_key="rfqs.id", nullable=False, index=True)

    product_id: Optional[uuid.UUID] = Field(default=None, foreign_key="products.id")
    quantity: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    uom_id: uuid.UUID = Field(foreign_key="units_of_measure.id", nullable=False)

    is_mandatory: bool = Field(default=True, sa_column=Column(Boolean))
    awarded_quantity: Decimal = Field(default=0, sa_column=Column(Numeric(12, 2)))

    rfq: RFQ = Relationship(back_populates="items")
    sources: List["RFQItemSource"] = Relationship(back_populates="rfq_item")


class RFQItemSource(SQLModel, table=True):
    __tablename__ = "rfq_item_sources"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    rfq_item_id: uuid.UUID = Field(
        foreign_key="rfq_items.id", nullable=False, index=True
    )
    procurement_request_item_id: uuid.UUID = Field(
        foreign_key="procurement_request_items.id", nullable=False
    )
    quantity_from_source: Decimal = Field(
        sa_column=Column(Numeric(12, 2), nullable=False)
    )

    rfq_item: RFQItem = Relationship(back_populates="sources")


class SupplierRFQResponse(SQLModel, table=True):
    __tablename__ = "supplier_rfq_responses"
    __table_args__ = (
        UniqueConstraint(
            "rfq_id", "supplier_id", "revision_number", name="uq_rfq_supplier_revision"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    rfq_id: uuid.UUID = Field(foreign_key="rfqs.id", nullable=False, index=True)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", nullable=False)

    revision_number: int = Field(default=1, sa_column=Column(Integer))
    status: QuoteStatus = Field(default=QuoteStatus.PENDING)
    completeness: QuoteCompleteness = Field(default=QuoteCompleteness.INCOMPLETE)

    quote_currency: str = Field(default="AED", max_length=3)
    exchange_rate: Decimal = Field(default=1.0, sa_column=Column(Numeric(12, 6)))
    normalized_total: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2))
    )

    rfq: RFQ = Relationship(back_populates="responses")
    quote_items: List["SupplierQuoteItem"] = Relationship(back_populates="response")


class SupplierQuoteItem(SQLModel, table=True):
    __tablename__ = "supplier_quote_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    response_id: uuid.UUID = Field(
        foreign_key="supplier_rfq_responses.id", nullable=False, index=True
    )
    rfq_item_id: uuid.UUID = Field(foreign_key="rfq_items.id", nullable=False)

    is_alternate: bool = Field(default=False, sa_column=Column(Boolean))
    alternate_product_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="products.id"
    )

    quantity_available: Decimal = Field(sa_column=Column(Numeric(12, 2)))
    quoted_unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2)))
    normalized_unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2)))

    response: SupplierRFQResponse = Relationship(back_populates="quote_items")


class RFQAward(SQLModel, table=True):
    __tablename__ = "rfq_awards"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "award_number", name="uq_workspace_award_number"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspaces.id", nullable=False, index=True
    )
    rfq_id: uuid.UUID = Field(foreign_key="rfqs.id", nullable=False)
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", nullable=False)

    award_number: str = Field(max_length=50, index=True)
    total_awarded_value: Decimal = Field(sa_column=Column(Numeric(12, 2)))

    status: AwardStatus = Field(default=AwardStatus.DRAFT)
    justification: Optional[str] = Field(default=None, sa_column=Column(Text))

    award_lines: List["RFQAwardLine"] = Relationship(back_populates="award")


class RFQAwardLine(SQLModel, table=True):
    __tablename__ = "rfq_award_lines"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    award_id: uuid.UUID = Field(foreign_key="rfq_awards.id", nullable=False, index=True)
    quote_item_id: uuid.UUID = Field(
        foreign_key="supplier_quote_items.id", nullable=False
    )

    awarded_quantity: Decimal = Field(sa_column=Column(Numeric(12, 2)))
    is_lowest_price: bool = Field(default=True, sa_column=Column(Boolean))
    deviation_reason: Optional[str] = Field(default=None, sa_column=Column(Text))

    award: RFQAward = Relationship(back_populates="award_lines")
