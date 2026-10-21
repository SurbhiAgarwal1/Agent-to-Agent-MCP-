"""Unit tests for the market-grade healthcare database generator."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.user import User
from app.models.blood_request import BloodRequest
from app.models.communication import CommunicationSession
from app.database.market_database import generate_market_database


@pytest.fixture
def memory_db():
    """Create in-memory SQLite database for testing market database generator."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_generate_market_database_creates_comprehensive_records(memory_db):
    """Verify market database generator populates 10 hospitals, 8 blood banks, donors, and staff accounts."""
    res = generate_market_database(memory_db, force=True)

    assert res["status"] == "success"
    assert res["hospitals"] == 10
    assert res["blood_banks"] == 8
    assert res["inventories"] == 64  # 8 blood banks * 8 blood types
    assert res["donors"] >= 40
    assert res["users"] >= 8
    assert res["requests"] >= 3

    # Verify query counts
    assert memory_db.query(Hospital).count() == 10
    assert memory_db.query(BloodBank).count() == 8
    assert memory_db.query(BloodInventory).count() == 64
    assert memory_db.query(User).count() >= 8
    assert memory_db.query(CommunicationSession).count() >= 1


def test_generate_market_database_idempotent(memory_db):
    """Verify running generator without force does not duplicate rows."""
    generate_market_database(memory_db, force=True)
    initial_hosp_count = memory_db.query(Hospital).count()

    res2 = generate_market_database(memory_db, force=False)
    assert res2["status"] == "already_populated"
    assert memory_db.query(Hospital).count() == initial_hosp_count
