"""Hospital database model."""

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from app.database.session import Base


class Hospital(Base):
    """Represents a hospital requesting blood units during emergencies."""
    __tablename__ = "hospitals"

    hospital_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(255), nullable=False)

    # Relationship: One Hospital has many BloodRequests
    requests = relationship("BloodRequest", back_populates="hospital", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Hospital(id={self.hospital_id}, name='{self.name}')>"
