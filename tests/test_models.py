"""Unit tests for SQLAlchemy models, database connection, and relationships."""

import pytest
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.enums import BloodGroup, UrgencyLevel, RequestStatus, MatchSourceType, MatchStatus
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.match import Match


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_database_connection(db_session):
    """Verify that the database session connects and executes simple queries."""
    result = db_session.execute(db_session.query(Hospital).statement).fetchall()
    assert result == []


def test_table_creation(db_session):
    """Verify that all required tables exist in the metadata."""
    expected_tables = {
        "hospitals",
        "blood_banks",
        "blood_inventories",
        "donors",
        "blood_requests",
        "matches",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_hospital_creation(db_session):
    """Verify Hospital entity creation and persistence."""
    hospital = Hospital(
        name="Apollo City Hospital",
        latitude=28.6139,
        longitude=77.2090,
        address="10 Main Road, Sector 5",
    )
    db_session.add(hospital)
    db_session.commit()
    db_session.refresh(hospital)

    assert hospital.hospital_id is not None
    assert hospital.name == "Apollo City Hospital"
    assert hospital.latitude == 28.6139
    assert hospital.longitude == 77.2090


def test_blood_bank_creation(db_session):
    """Verify BloodBank entity creation and persistence."""
    bank = BloodBank(
        name="Rotary Regional Blood Bank",
        latitude=28.6200,
        longitude=77.2150,
        address="84 Community Center",
    )
    db_session.add(bank)
    db_session.commit()
    db_session.refresh(bank)

    assert bank.bank_id is not None
    assert bank.name == "Rotary Regional Blood Bank"


def test_inventory_creation(db_session):
    """Verify BloodInventory creation with foreign key to BloodBank."""
    bank = BloodBank(
        name="Metro Blood Bank",
        latitude=28.62,
        longitude=77.21,
        address="12 Care Ave",
    )
    db_session.add(bank)
    db_session.commit()

    inventory = BloodInventory(
        bank_id=bank.bank_id,
        blood_group=BloodGroup.O_NEG.value,
        units_available=8,
        expiry_date=date(2026, 12, 31),
    )
    db_session.add(inventory)
    db_session.commit()
    db_session.refresh(inventory)

    assert inventory.inventory_id is not None
    assert inventory.bank_id == bank.bank_id
    assert inventory.blood_group == "O-"
    assert inventory.units_available == 8


def test_donor_creation(db_session):
    """Verify synthetic Donor creation."""
    donor = Donor(
        name="Synthetic Demo Donor 1",
        blood_group=BloodGroup.AB_POS.value,
        latitude=28.6150,
        longitude=77.2110,
        available=True,
        last_donation_date=date(2026, 6, 15),
    )
    db_session.add(donor)
    db_session.commit()
    db_session.refresh(donor)

    assert donor.donor_id is not None
    assert donor.name == "Synthetic Demo Donor 1"
    assert donor.blood_group == "AB+"
    assert donor.available is True


def test_blood_request_creation(db_session):
    """Verify BloodRequest creation referencing Hospital."""
    hospital = Hospital(
        name="Trauma Center",
        latitude=28.60,
        longitude=77.20,
        address="9 Emergency Drive",
    )
    db_session.add(hospital)
    db_session.commit()

    req = BloodRequest(
        hospital_id=hospital.hospital_id,
        blood_group=BloodGroup.B_POS.value,
        units_required=3,
        urgency=UrgencyLevel.CRITICAL.value,
        status=RequestStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    assert req.request_id is not None
    assert req.hospital_id == hospital.hospital_id
    assert req.urgency == "CRITICAL"
    assert req.status == "PENDING"
    assert req.units_required == 3


def test_match_creation(db_session):
    """Verify Match creation referencing BloodRequest."""
    hospital = Hospital(name="Hosp A", latitude=28.0, longitude=77.0, address="Addr")
    db_session.add(hospital)
    db_session.commit()

    req = BloodRequest(
        hospital_id=hospital.hospital_id,
        blood_group=BloodGroup.A_POS.value,
        units_required=1,
    )
    db_session.add(req)
    db_session.commit()

    match_record = Match(
        request_id=req.request_id,
        source_type=MatchSourceType.BLOOD_BANK.value,
        source_id=1,
        distance_km=4.2,
        estimated_time="15 mins",
        priority_score=0.92,
        status=MatchStatus.PROPOSED.value,
    )
    db_session.add(match_record)
    db_session.commit()
    db_session.refresh(match_record)

    assert match_record.match_id is not None
    assert match_record.request_id == req.request_id
    assert match_record.source_type == "BLOOD_BANK"
    assert match_record.distance_km == 4.2


def test_relationships(db_session):
    """Verify bidirectional relationship navigation across entities."""
    # 1. Hospital -> BloodRequest
    hospital = Hospital(name="Apex Hospital", latitude=28.61, longitude=77.21, address="Road 1")
    db_session.add(hospital)
    db_session.commit()

    req1 = BloodRequest(hospital=hospital, blood_group="O+", units_required=2)
    req2 = BloodRequest(hospital=hospital, blood_group="O-", units_required=1)
    db_session.add_all([req1, req2])
    db_session.commit()

    db_session.refresh(hospital)
    assert len(hospital.requests) == 2
    assert hospital.requests[0].blood_group in ["O+", "O-"]

    # 2. BloodBank -> BloodInventory
    bank = BloodBank(name="City Blood Vault", latitude=28.62, longitude=77.22, address="Road 2")
    db_session.add(bank)
    db_session.commit()

    inv1 = BloodInventory(blood_bank=bank, blood_group="A+", units_available=5)
    inv2 = BloodInventory(blood_bank=bank, blood_group="B+", units_available=10)
    db_session.add_all([inv1, inv2])
    db_session.commit()

    db_session.refresh(bank)
    assert len(bank.inventory) == 2
    assert inv1.blood_bank.name == "City Blood Vault"

    # 3. BloodRequest -> Match
    match1 = Match(request=req1, source_type=MatchSourceType.BLOOD_BANK.value, source_id=bank.bank_id, distance_km=3.5)
    db_session.add(match1)
    db_session.commit()

    db_session.refresh(req1)
    assert len(req1.matches) == 1
    assert req1.matches[0].request.hospital.name == "Apex Hospital"
