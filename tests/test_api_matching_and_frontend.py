"""Unit tests for the matching pipeline and frontend endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base, get_db
from app.main import app
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.enums import RequestStatus


@pytest.fixture
def client_and_db():
    """Create test client with isolated in-memory database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Seed hospital
    hosp = Hospital(
        name="Apex Emergency Hospital",
        latitude=28.6139,
        longitude=77.2090,
        address="10 Medical Way",
    )
    session.add(hosp)
    session.commit()

    # Seed blood bank & inventory
    bank = BloodBank(
        name="Apex Blood Bank",
        latitude=28.6200,
        longitude=77.2150,
        address="20 Red Cross Blvd",
    )
    session.add(bank)
    session.commit()

    session.add(
        BloodInventory(
            bank_id=bank.bank_id,
            blood_group="O+",
            units_available=8,
        )
    )

    # Seed donor
    donor = Donor(
        name="Alex Donor",
        blood_group="O+",
        latitude=28.6300,
        longitude=77.2200,
        available=True,
    )
    session.add(donor)
    session.commit()

    client = TestClient(app)
    try:
        yield client, session, hosp
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_list_hospitals_endpoint(client_and_db):
    """Verify GET /api/v1/hospitals returns registered hospitals."""
    client, _, hosp = client_and_db
    res = client.get("/api/v1/hospitals")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "Apex Emergency Hospital"


def test_get_dashboard_endpoint(client_and_db):
    """Verify GET /dashboard returns HTML frontend."""
    client, _, _ = client_and_db
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Blood Donation Matching" in res.text


def test_get_request_matches_pipeline_endpoint(client_and_db):
    """Verify GET /api/v1/blood-requests/{id}/matches runs all 3 agents."""
    client, session, hosp = client_and_db

    # Create request
    req = BloodRequest(
        hospital_id=hosp.hospital_id,
        blood_group="O+",
        units_required=3,
        urgency="CRITICAL",
        status=RequestStatus.PENDING.value,
    )
    session.add(req)
    session.commit()

    res = client.get(f"/api/v1/blood-requests/{req.request_id}/matches")
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"] == req.request_id
    assert data["matches_count"] >= 2  # 1 bank + 1 donor
    assert "requirement_validation" in data
    assert data["requirement_validation"]["valid"] is True

    # Verify Location Agent attached distance and ETA
    first_match = data["matches"][0]
    assert "distance_km" in first_match
    assert "estimated_time" in first_match
    assert first_match["distance_km"] > 0
