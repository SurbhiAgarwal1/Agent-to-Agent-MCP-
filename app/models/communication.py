"""SQLAlchemy models for the Communication Agent and interactive outreach subsystem."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


class CommunicationSession(Base):
    """Represents an interactive multi-agent communication session for a blood request."""

    __tablename__ = "communication_sessions"

    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(Integer, ForeignKey("blood_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=True)
    urgency = Column(String(20), default="MEDIUM", nullable=False)
    status = Column(
        String(30),
        default="INITIATED",
        nullable=False,
        # Statuses: INITIATED, ACTIVE, PARTIALLY_CONFIRMED, ALL_CONFIRMED, ESCALATED, EXPIRED, CLOSED
    )
    total_targets = Column(Integer, default=0, nullable=False)
    confirmed_count = Column(Integer, default=0, nullable=False)
    declined_count = Column(Integer, default=0, nullable=False)
    pending_count = Column(Integer, default=0, nullable=False)
    sla_minutes = Column(Integer, default=30, nullable=False)
    sla_expires_at = Column(DateTime, nullable=True)
    is_escalated = Column(Boolean, default=False, nullable=False)
    escalation_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to individual recipient messages
    messages = relationship(
        "CommunicationMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CommunicationMessage.sent_at",
    )


class CommunicationMessage(Base):
    """Represents an individual communication log/dispatch to a donor, blood bank, or hospital."""

    __tablename__ = "communication_messages"

    message_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("communication_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_type = Column(String(20), nullable=False)  # HOSPITAL, BLOOD_BANK, DONOR
    recipient_id = Column(Integer, nullable=False, index=True)
    channel = Column(String(20), default="CONSOLE", nullable=False)  # CONSOLE, SMS, EMAIL, PUSH, CHAT
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    units_requested = Column(Integer, default=1, nullable=False)
    delivery_status = Column(String(20), default="DELIVERED", nullable=False)  # PENDING, DELIVERED, FAILED
    response_status = Column(String(20), default="PENDING", nullable=False)  # PENDING, CONFIRMED, DECLINED, DELAYED, EN_ROUTE, TIMEOUT
    response_notes = Column(Text, nullable=True)
    eta_minutes = Column(Integer, nullable=True)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    responded_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=True)

    session = relationship("CommunicationSession", back_populates="messages")
