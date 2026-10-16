"""Explicit, revocable organization memberships for staff accounts."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class HospitalMembership(Base):
    __tablename__ = "hospital_memberships"
    __table_args__ = (UniqueConstraint("user_id", "hospital_id", name="uq_hospital_membership_user_hospital"),)

    membership_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    membership_type = Column(String(40), nullable=False, default="STAFF")
    is_active = Column(Boolean, nullable=False, default=True)
    user = relationship("User", back_populates="hospital_memberships")
    hospital = relationship("Hospital", back_populates="memberships")


class BloodBankMembership(Base):
    __tablename__ = "blood_bank_memberships"
    __table_args__ = (UniqueConstraint("user_id", "bank_id", name="uq_blood_bank_membership_user_bank"),)

    membership_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_id = Column(Integer, ForeignKey("blood_banks.bank_id", ondelete="CASCADE"), nullable=False, index=True)
    membership_type = Column(String(40), nullable=False, default="STAFF")
    is_active = Column(Boolean, nullable=False, default=True)
    user = relationship("User", back_populates="blood_bank_memberships")
    blood_bank = relationship("BloodBank", back_populates="memberships")
