"""SQLAlchemy model for Calling Agent voice dispatch logs and IVR telephony sessions."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


class CallSession(Base):
    """Represents an automated outbound voice call dispatched to a donor or blood bank."""

    __tablename__ = "call_sessions"

    call_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(Integer, ForeignKey("blood_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), nullable=True)
    recipient_type = Column(String(20), nullable=False)  # DONOR, BLOOD_BANK, HOSPITAL
    recipient_id = Column(Integer, nullable=False, index=True)
    recipient_phone = Column(String(30), nullable=False)
    recipient_name = Column(String(100), nullable=True)
    status = Column(
        String(20),
        default="INITIATED",
        nullable=False,
        # INITIATED, RINGING, IN_PROGRESS, COMPLETED, NO_ANSWER, BUSY, FAILED
    )
    duration_seconds = Column(Integer, default=0, nullable=False)
    dtmf_input = Column(String(10), nullable=True)  # "1"=Confirm, "2"=Decline, "3"=Delay
    response_status = Column(
        String(20),
        default="NO_RESPONSE",
        nullable=False,
        # NO_RESPONSE, CONFIRMED, DECLINED, DELAYED
    )
    tts_script = Column(Text, nullable=False)
    telephony_provider = Column(String(30), default="CONSOLE_MOCK", nullable=False)
    call_sid = Column(String(100), nullable=True)
    initiated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=True)
