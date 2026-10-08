"""Tests for synthetic dataset seeding."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.database.seed import seed_database
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor


@pytest.fixture
def seed_session():
    """Create an isolated in-memory session for testing database seeding."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_seed_database_counts(seed_session):
    """Verify that seed_database populates 3 hospitals, 4 blood banks, 15 synthetic donors, and inventories."""
    result = seed_database(seed_session)
    assert result["status"] == "success"
    assert result["hospitals"] == 3
    assert result["blood_banks"] == 4
    assert result["donors"] == 15
    assert result["inventories"] > 0

    # Query directly to verify persisted counts
    assert seed_session.query(Hospital).count() == 3
    assert seed_session.query(BloodBank).count() == 4
    assert seed_session.query(Donor).count() == 15
    assert seed_session.query(BloodInventory).count() == result["inventories"]


def test_seed_database_idempotent(seed_session):
    """Verify that running seed_database twice does not duplicate records."""
    res1 = seed_database(seed_session)
    assert res1["status"] == "success"

    res2 = seed_database(seed_session)
    assert res2["status"] == "already_seeded"
    assert seed_session.query(Hospital).count() == 3
    assert seed_session.query(Donor).count() == 15
