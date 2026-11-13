from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Index, Text
from sqlalchemy.orm import relationship
from .database import Base

class Donor(Base):
    __tablename__="donors"
    id=Column(Integer,primary_key=True)
    name=Column(String(120),nullable=False)
    age=Column(Integer,nullable=False)
    gender=Column(String(16),nullable=True)
    blood_group=Column(String(3),nullable=False,index=True)
    city=Column(String(80),nullable=False,index=True)
    district=Column(String(80),nullable=False,index=True)
    state=Column(String(80),nullable=False,index=True)
    pin_code=Column(String(8),nullable=False,index=True)
    latitude=Column(Float,nullable=False,index=True)
    longitude=Column(Float,nullable=False,index=True)
    phone=Column(String(24),nullable=False)
    email=Column(String(140),nullable=False,unique=True)
    registration_date=Column(Date,nullable=False)
    last_donation_date=Column(Date,nullable=True,index=True)
    donation_count=Column(Integer,nullable=False,default=0)
    available=Column(Boolean,nullable=False,default=True,index=True)
    preferred_contact_method=Column(String(12),nullable=False)
    notification_consent=Column(Boolean,nullable=False,default=False,index=True)
    verification_status=Column(String(24),nullable=False,index=True)
    eligibility_status=Column(String(28),nullable=False,index=True)
    temporary_deferral_reason=Column(String(100),nullable=True)
    last_updated=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    donations=relationship("DonationHistory",back_populates="donor",cascade="all, delete-orphan")

class DonationHistory(Base):
    __tablename__="donation_history"
    id=Column(Integer,primary_key=True)
    donor_id=Column(Integer,ForeignKey("donors.id",ondelete="CASCADE"),nullable=False,index=True)
    donation_date=Column(Date,nullable=False,index=True)
    blood_bank_id=Column(Integer,nullable=False,index=True) # belongs to independent blood-bank API database
    donation_type=Column(String(32),nullable=False)
    donation_status=Column(String(20),nullable=False,index=True)
    units_collected=Column(Integer,nullable=False)
    next_eligible_date=Column(Date,nullable=True)
    donor=relationship("Donor",back_populates="donations")

class DonorNotification(Base):
    __tablename__="donor_notifications"
    id=Column(Integer,primary_key=True)
    donor_id=Column(Integer,ForeignKey("donors.id",ondelete="CASCADE"),nullable=False,index=True)
    attempted_at=Column(DateTime(timezone=True),nullable=False,index=True)
    channel=Column(String(16),nullable=False)
    status=Column(String(24),nullable=False,index=True)
    consent_at_attempt=Column(Boolean,nullable=False)
    response=Column(String(24),nullable=True)
    request_reference=Column(String(40),nullable=False)
    blood_request_id=Column(Integer,nullable=True,index=True)
    blood_group=Column(String(3),nullable=True)
    delivery_status=Column(String(16),nullable=False,default="simulated",index=True)
    response_status=Column(String(24),nullable=False,default="pending",index=True)
    sent_at=Column(DateTime(timezone=True),nullable=True)
    delivered_at=Column(DateTime(timezone=True),nullable=True)
    response_at=Column(DateTime(timezone=True),nullable=True)
    error_details=Column(Text,nullable=True)
    idempotency_key=Column(String(160),nullable=True,unique=True)
    response_token_hash=Column(String(64),nullable=True)
    response_token_expires_at=Column(DateTime(timezone=True),nullable=True)

    __table_args__=(Index("ix_donor_notification_request_status","blood_request_id","delivery_status"),)
