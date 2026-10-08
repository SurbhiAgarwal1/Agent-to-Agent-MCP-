"""Match database model."""

from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database.session import Base
from app.models.enums import MatchSourceType, MatchStatus


class Match(Base):
    """Represents a candidate or finalized match between a blood request and a source (blood bank or donor)."""
    __tablename__ = "matches"

    match_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("blood_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False)  # BLOOD_BANK or DONOR
    source_id = Column(Integer, nullable=False)        # bank_id or donor_id
    distance_km = Column(Float, nullable=True)
    estimated_time = Column(String(50), nullable=True) # e.g. "20 mins"
    priority_score = Column(Float, nullable=True)      # e.g. composite score
    status = Column(String(20), nullable=False, default=MatchStatus.PROPOSED.value)

    # Relationship: Many Matches belong to One BloodRequest
    request = relationship("BloodRequest", back_populates="matches")

    def __repr__(self) -> str:
        return f"<Match(id={self.match_id}, request_id={self.request_id}, source={self.source_type}#{self.source_id}, status='{self.status}')>"
