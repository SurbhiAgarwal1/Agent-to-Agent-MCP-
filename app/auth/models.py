"""Authentication and Audit Log Database Models (Part 15)."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from app.database.session import Base


class UserRole:
    """Allowed user authorization roles."""
    HOSPITAL_STAFF = "HOSPITAL_STAFF"
    BLOOD_BANK_STAFF = "BLOOD_BANK_STAFF"
    ADMIN = "ADMIN"
    ALL_ROLES = [HOSPITAL_STAFF, BLOOD_BANK_STAFF, ADMIN]


class User(Base):
    """Registered user account model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default=UserRole.HOSPITAL_STAFF)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


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
