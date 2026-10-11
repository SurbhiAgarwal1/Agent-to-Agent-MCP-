"""AuditLog database model (Part 15)."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database.session import Base


class AuditLog(Base):
    """Audit log recording sensitive security and operational events."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    resource_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    details = Column(Text, nullable=True)
