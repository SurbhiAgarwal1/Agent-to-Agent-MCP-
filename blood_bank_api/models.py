from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base

class BloodBank(Base):
    __tablename__ = "blood_banks"
    id = Column(Integer, primary_key=True)
    name = Column(String(180), nullable=False, index=True)
    registration_number = Column(String(40), unique=True, nullable=False)
    address = Column(String(240), nullable=False)
    city = Column(String(80), nullable=False, index=True)
    district = Column(String(80), nullable=False, index=True)
    state = Column(String(80), nullable=False, index=True)
    pin_code = Column(String(8), nullable=False, index=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    contact_number = Column(String(24), nullable=False)
    contact_email = Column(String(140), nullable=False)
    operating_hours = Column(String(80), nullable=False)
    emergency_available = Column(Boolean, nullable=False, default=True, index=True)
    verification_status = Column(String(24), nullable=False, index=True)
    bank_type = Column(String(24), nullable=False, index=True)
    last_updated = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    inventory = relationship("BloodInventory", back_populates="blood_bank", cascade="all, delete-orphan")

class BloodInventory(Base):
    __tablename__ = "blood_inventory"
    id = Column(Integer, primary_key=True)
    blood_bank_id = Column(Integer, ForeignKey("blood_banks.id", ondelete="CASCADE"), nullable=False, index=True)
    blood_group = Column(String(3), nullable=False, index=True)
    component_type = Column(String(32), nullable=False, index=True)
    available_units = Column(Integer, nullable=False, default=0, index=True)
    reserved_units = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expiry_date = Column(DateTime(timezone=True), nullable=False, index=True)
    availability_status = Column(String(24), nullable=False, index=True)
    blood_bank = relationship("BloodBank", back_populates="inventory")
    __table_args__ = (
        Index("ix_inventory_group_component", "blood_group", "component_type"),
        Index("uq_inventory_bank_group_component", "blood_bank_id", "blood_group", "component_type", unique=True),
    )

class Hospital(Base):
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True)
    name = Column(String(180), nullable=False, index=True)
    hospital_type = Column(String(24), nullable=False, index=True)
    address = Column(String(240), nullable=False)
    city = Column(String(80), nullable=False, index=True)
    district = Column(String(80), nullable=False, index=True)
    state = Column(String(80), nullable=False, index=True)
    pin_code = Column(String(8), nullable=False, index=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    emergency_contact = Column(String(24), nullable=False)
    contact_email = Column(String(140), nullable=False)
    associated_blood_bank_ids = Column(Text, nullable=False, default="[]")
    operating_status = Column(String(20), nullable=False, index=True)

class BloodRequest(Base):
    __tablename__ = "blood_requests"
    id = Column(Integer, primary_key=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    required_blood_group = Column(String(3), nullable=False, index=True)
    required_units = Column(Integer, nullable=False)
    component_type = Column(String(32), nullable=False)
    request_date = Column(DateTime(timezone=True), nullable=False, index=True)
    required_by = Column(DateTime(timezone=True), nullable=False, index=True)
    priority = Column(String(16), nullable=False, index=True)
    status = Column(String(24), nullable=False, index=True)
    assigned_blood_bank_ids = Column(Text, nullable=False, default="[]")
    notes = Column(String(300), nullable=False, default="Synthetic historical scenario")

class BloodBankNotification(Base):
    __tablename__ = "blood_bank_notifications"
    id = Column(Integer, primary_key=True)
    blood_bank_id = Column(Integer, ForeignKey("blood_banks.id"), nullable=False, index=True)
    blood_request_id = Column(Integer, nullable=False, index=True)
    blood_group = Column(String(3), nullable=False)
    inventory_blood_group = Column(String(3), nullable=False)
    component_type = Column(String(32), nullable=False)
    required_units = Column(Integer, nullable=False)
    channel = Column(String(16), nullable=False)
    delivery_status = Column(String(16), nullable=False, default="pending", index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    response_status = Column(String(24), nullable=False, default="pending", index=True)
    response_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_available_units = Column(Integer, nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    error_details = Column(Text, nullable=True)
    idempotency_key = Column(String(160), nullable=False, unique=True)
    response_token_hash = Column(String(64), nullable=True)
    response_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("ix_bank_notification_request_status", "blood_request_id", "delivery_status"),)
