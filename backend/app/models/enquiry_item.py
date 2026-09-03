import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.enquiry import Enquiry
    from app.models.product import Product
    from app.models.unit_of_measure import UnitOfMeasure


class EnquiryItem(SQLModel, table=True):
    __tablename__ = "enquiry_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    enquiry_id: uuid.UUID = Field(foreign_key="enquiries.id", index=True, nullable=False)
    product_id: Optional[uuid.UUID] = Field(foreign_key="products.id", nullable=True)

    description: str  # The requested item description
    quantity_requested: Decimal = Field(max_digits=12, decimal_places=4)
    uom_id: Optional[uuid.UUID] = Field(foreign_key="units_of_measure.id", nullable=True)

    notes: Optional[str] = None

    # Relationships
    enquiry: Optional["Enquiry"] = Relationship(back_populates="items")
    product: Optional["Product"] = Relationship()
    uom: Optional["UnitOfMeasure"] = Relationship()
