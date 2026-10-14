"""Database-backed organization authorization checks."""

from sqlalchemy.orm import Session
from app.models.membership import HospitalMembership, BloodBankMembership


def has_hospital_membership(db: Session, user_id: int, hospital_id: int) -> bool:
    return db.query(HospitalMembership.membership_id).filter(
        HospitalMembership.user_id == user_id,
        HospitalMembership.hospital_id == hospital_id,
        HospitalMembership.is_active.is_(True),
    ).first() is not None


def active_hospital_ids(db: Session, user_id: int) -> set[int]:
    return {row[0] for row in db.query(HospitalMembership.hospital_id).filter(
        HospitalMembership.user_id == user_id,
        HospitalMembership.is_active.is_(True),
    ).all()}


def has_blood_bank_membership(db: Session, user_id: int, bank_id: int) -> bool:
    return db.query(BloodBankMembership.membership_id).filter(
        BloodBankMembership.user_id == user_id,
        BloodBankMembership.bank_id == bank_id,
        BloodBankMembership.is_active.is_(True),
    ).first() is not None
