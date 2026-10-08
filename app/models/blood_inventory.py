"""BloodInventory database model."""

from datetime import date
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database.session import Base


class BloodInventory(Base):
    """Represents available stock of a specific blood group at a blood bank."""
    __tablename__ = "blood_inventories"

    inventory_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey("blood_banks.bank_id", ondelete="CASCADE"), nullable=False, index=True)
    blood_group = Column(String(5), nullable=False, index=True)
    units_available = Column(Integer, nullable=False, default=0)
    expiry_date = Column(Date, nullable=True)

    # Relationship: Many BloodInventory records belong to One BloodBank
    blood_bank = relationship("BloodBank", back_populates="inventory")

    def __repr__(self) -> str:
        return f"<BloodInventory(id={self.inventory_id}, bank_id={self.bank_id}, group='{self.blood_group}', units={self.units_available})>"
