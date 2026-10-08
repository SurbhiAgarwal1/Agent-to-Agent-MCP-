"""Donor database model for synthetic demo donor data."""

from datetime import date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date
from app.database.session import Base


class Donor(Base):
    """Represents a voluntary blood donor.
    
    IMPORTANT: All donor records in this project are strictly synthetic/fictional
    demo data for student/OJT simulation purposes. No real personal info is used.
    """
    __tablename__ = "donors"

    donor_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    blood_group = Column(String(5), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    available = Column(Boolean, nullable=False, default=True)
    last_donation_date = Column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<Donor(id={self.donor_id}, name='{self.name}', group='{self.blood_group}', available={self.available})>"
