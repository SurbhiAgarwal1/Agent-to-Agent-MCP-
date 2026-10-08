"""BloodRequest database model."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database.session import Base
from app.models.enums import UrgencyLevel, RequestStatus


class BloodRequest(Base):
    """Represents an emergency blood request submitted by a hospital."""
    __tablename__ = "blood_requests"

    request_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    blood_group = Column(String(5), nullable=False, index=True)
    units_required = Column(Integer, nullable=False)
    urgency = Column(String(20), nullable=False, default=UrgencyLevel.MEDIUM.value)
    status = Column(String(20), nullable=False, default=RequestStatus.PENDING.value)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    hospital = relationship("Hospital", back_populates="requests")
    matches = relationship("Match", back_populates="request", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<BloodRequest(id={self.request_id}, hospital_id={self.hospital_id}, group='{self.blood_group}', units={self.units_required}, status='{self.status}')>"
