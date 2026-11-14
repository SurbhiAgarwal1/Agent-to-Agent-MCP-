"""In-app alerts shown to hospital staff when a blood bank or donor answers a request."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database.session import Base


class HospitalAlert(Base):
    __tablename__ = "hospital_alerts"
    __table_args__ = (UniqueConstraint("source_type", "notification_id", name="uq_alert_notification"),)

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("blood_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(20), nullable=False)          # BLOOD_BANK | DONOR
    source_id = Column(Integer, nullable=False)
    source_name = Column(String(150), nullable=True)
    notification_id = Column(Integer, nullable=False)
    response_status = Column(String(30), nullable=False)       # accepted | partially_available | rejected | ...
    confirmed_units = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = Column(DateTime, nullable=True)
