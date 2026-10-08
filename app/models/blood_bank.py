"""BloodBank database model."""

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from app.database.session import Base


class BloodBank(Base):
    """Represents a blood bank facility storing blood inventories."""
    __tablename__ = "blood_banks"

    bank_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(255), nullable=False)

    # Relationship: One BloodBank has many BloodInventory records
    inventory = relationship("BloodInventory", back_populates="blood_bank", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<BloodBank(id={self.bank_id}, name='{self.name}')>"
