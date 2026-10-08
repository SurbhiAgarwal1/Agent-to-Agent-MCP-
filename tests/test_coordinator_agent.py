"""Tests for CoordinatorAgent and orchestration endpoints."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.match import Match
from app.models.enums import BloodGroup, UrgencyLevel, RequestStatus, MatchStatus, MatchSourceType
from app.agents.coordinator_agent import CoordinatorAgent
from app.main import app

# In-memory SQLite for isolated unit tests with StaticPool
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """Create a pristine database schema for each test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        # Seed test data
        h1 = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
        b1 = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
        b2 = BloodBank(bank_id=2, name="Metro Red Cross", latitude=28.7000, longitude=77.2500, address="North Delhi")
        session.add_all([h1, b1, b2])
        session.commit()

        # Inventories: b1 has 2 units A+, b2 has 3 units A+
        inv1 = BloodInventory(bank_id=1, blood_group="A+", units_available=2)
        inv2 = BloodInventory(bank_id=2, blood_group="A+", units_available=3)
        session.add_all([inv1, inv2])

        # Donor with A+
        d1 = Donor(donor_id=1, name="John Doe", blood_group="A+", latitude=28.6150, longitude=77.2080, available=True)
        session.add(d1)

        # Blood Request: Hospital 1 requests 3 units of A+
        req1 = BloodRequest(
            request_id=1,
            hospital_id=1,
            blood_group="A+",
            units_required=3,
            urgency=UrgencyLevel.CRITICAL.value,
            status=RequestStatus.PENDING.value,
            created_at=datetime.now(timezone.utc),
        )
        session.add(req1)
        session.commit()

        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_coordinator_priority_scoring():
    """Verify composite priority scoring logic."""
    coordinator = CoordinatorAgent()

    # Closer distance should score higher than far distance
    score_near = coordinator.calculate_priority_score(distance_km=2.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="CRITICAL")
    score_far = coordinator.calculate_priority_score(distance_km=25.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="CRITICAL")
    assert score_near > score_far

    # Blood bank should score higher than donor (institutional preference)
    score_bank = coordinator.calculate_priority_score(distance_km=5.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="HIGH")
    score_donor = coordinator.calculate_priority_score(distance_km=5.0, source_type="DONOR", is_exact_match=True, urgency="HIGH")
    assert score_bank > score_donor

    # Exact match should score higher than compatible match
    score_exact = coordinator.calculate_priority_score(distance_km=5.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="HIGH")
    score_compat = coordinator.calculate_priority_score(distance_km=5.0, source_type="BLOOD_BANK", is_exact_match=False, urgency="HIGH")
    assert score_exact > score_compat

    # CRITICAL should score higher than LOW urgency
    score_crit = coordinator.calculate_priority_score(distance_km=5.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="CRITICAL")
    score_low = coordinator.calculate_priority_score(distance_km=5.0, source_type="BLOOD_BANK", is_exact_match=True, urgency="LOW")
    assert score_crit > score_low


def test_coordinator_orchestrate_end_to_end(db_session):
    """Test full orchestration pipeline including resource allocation and DB persistence."""
    coordinator = CoordinatorAgent(db=db_session)
    result = coordinator.orchestrate(request_id=1, persist=True)

    assert result["success"] is True
    assert result["request_id"] == 1
    assert result["fulfillment_status"] == "FULFILLED"
    assert result["units_required"] == 3
    assert result["units_allocated"] == 3

    # Check allocation plan
    allocated = result["allocated_sources"]
    assert len(allocated) >= 1
    total_allocated_units = sum(item["units_allocated"] for item in allocated)
    assert total_allocated_units == 3

    # Verify execution audit trail
    log_steps = [entry["step"] for entry in result["execution_log"]]
    assert "INIT" in log_steps
    assert "REQUIREMENT_AGENT" in log_steps
    assert "MATCHING_AGENT" in log_steps
    assert "LOCATION_AND_RANKING" in log_steps
    assert "ALLOCATION_ENGINE" in log_steps
    assert "PERSISTENCE" in log_steps

    # Verify database persistence
    saved_matches = db_session.query(Match).filter(Match.request_id == 1).all()
    assert len(saved_matches) > 0
    accepted_matches = [m for m in saved_matches if m.status == MatchStatus.ACCEPTED.value]
    assert len(accepted_matches) == len(allocated)

    # Verify BloodRequest updated to FULFILLED
    updated_request = db_session.query(BloodRequest).filter(BloodRequest.request_id == 1).first()
    assert updated_request.status == RequestStatus.FULFILLED.value


def test_coordinator_partial_fulfillment(db_session):
    """Test scenario where available units cannot fully meet large request."""
    # Create request for 20 units (database only has 2+3+1 = 6 units)
    big_req = BloodRequest(
        request_id=99,
        hospital_id=1,
        blood_group="A+",
        units_required=20,
        urgency=UrgencyLevel.HIGH.value,
        status=RequestStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(big_req)
    db_session.commit()

    coordinator = CoordinatorAgent(db=db_session)
    result = coordinator.orchestrate(request_id=99, persist=True)

    assert result["success"] is True
    assert result["fulfillment_status"] == "PARTIALLY_FULFILLED"
    assert result["units_allocated"] < 20
    assert result["units_allocated"] > 0

    updated_req = db_session.query(BloodRequest).filter(BloodRequest.request_id == 99).first()
    assert updated_req.status == RequestStatus.PARTIALLY_FULFILLED.value


def test_coordinator_nonexistent_request(db_session):
    """Test orchestrator error handling for invalid request ID."""
    coordinator = CoordinatorAgent(db=db_session)
    with pytest.raises(ValueError, match="not found"):
        coordinator.orchestrate(request_id=9999, persist=True)


def test_orchestrate_api_endpoint(db_session):
    """Test FastAPI POST /api/v1/blood-requests/{id}/orchestrate endpoint."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/api/v1/blood-requests/1/orchestrate")
    print("RESPONSE JSON:", response.json())
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["fulfillment_status"] == "FULFILLED"
    assert data["units_allocated"] == 3
    assert len(data["allocated_sources"]) > 0
    assert "execution_log" in data

    # Test 404 for non-existent request
    err_resp = client.post("/api/v1/blood-requests/9999/orchestrate")
    assert err_resp.status_code == 404

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# Part 9 Specific Tests (State Machine, Coordinate Endpoint, Distance Ranking)
# -----------------------------------------------------------------------------

def test_coordinator_part9_successful_flow(db_session):
    """Part 9: Test successful coordination flow with distance-ascending ranking."""
    coordinator = CoordinatorAgent(db=db_session)
    result = coordinator.coordinate(request_input=1, persist=True)

    assert result["success"] is True
    assert result["current_state"] == "COMPLETED"
    assert result["request_id"] == 1
    assert result["candidates_count"] >= 2

    # Verify ranked strictly by distance ascending
    matches = result["ranked_matches"]
    distances = [m["distance_km"] for m in matches]
    assert distances == sorted(distances)


def test_coordinator_part9_state_transitions(db_session):
    """Part 9: Test state machine transitions: RECEIVED -> VALIDATED -> MATCHED -> LOCATED -> COMPLETED."""
    coordinator = CoordinatorAgent(db=db_session)
    result = coordinator.coordinate(request_input=1, persist=False)

    states = [step["state"] for step in result["state_history"]]
    assert states == ["RECEIVED", "VALIDATED", "MATCHED", "LOCATED", "COMPLETED"]


def test_coordinator_part9_invalid_request(db_session):
    """Part 9: Test invalid request handling halts at VALIDATION with FAILED state."""
    coordinator = CoordinatorAgent(db=db_session)
    bad_payload = {
        "hospital_id": 1,
        "blood_group": "INVALID_GROUP",
        "units_required": 2,
        "urgency": "CRITICAL",
    }
    result = coordinator.coordinate(request_input=bad_payload, persist=False)

    assert result["success"] is False
    assert result["current_state"] == "FAILED"
    assert result["failed_at"] == "VALIDATION"
    assert "validation failed" in result["error"].lower()


def test_coordinator_part9_no_matches_found(db_session):
    """Part 9: Test no matches found halts at MATCHING with FAILED state."""
    coordinator = CoordinatorAgent(db=db_session)
    # Request AB- when our test seed only has A+ inventory/donor
    rare_payload = {
        "request_id": 1,
        "hospital_id": 1,
        "blood_group": "AB-",
        "units_required": 1,
        "urgency": "HIGH",
    }
    result = coordinator.coordinate(request_input=rare_payload, persist=False)

    assert result["success"] is False
    assert result["current_state"] == "FAILED"
    assert result["failed_at"] == "MATCHING"
    assert "no compatible blood sources found" in result["error"].lower()


def test_coordinator_part9_location_error(db_session):
    """Part 9: Test location agent error halts at LOCATION with FAILED state."""
    coordinator = CoordinatorAgent(db=db_session)
    # Hospital 1 exists in DB so validation passes, but candidate source has no coordinates
    no_loc_payload = {
        "request_id": 1,
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 1,
        "urgency": "MEDIUM",
        # Pass inventory with unresolvable source_id=9999 and no coords so matching passes but location fails
        "inventories": [{
            "source_type": "BLOOD_BANK",
            "source_id": 9999,
            "blood_group": "A+",
            "units_available": 2,
            "latitude": None,
            "longitude": None,
        }],
    }
    result = coordinator.coordinate(request_input=no_loc_payload, persist=False)

    assert result["success"] is False
    assert result["current_state"] == "FAILED"
    assert result["failed_at"] == "LOCATION"


def test_coordinator_part9_persistence(db_session):
    """Part 9: Verify Match records are persisted with PROPOSED status and request updated."""
    coordinator = CoordinatorAgent(db=db_session)
    result = coordinator.coordinate(request_input=1, persist=True)

    assert result["success"] is True

    # Check matches in database
    db_matches = db_session.query(Match).filter(Match.request_id == 1).all()
    assert len(db_matches) > 0
    for m in db_matches:
        assert m.status == "PROPOSED"
        assert m.distance_km is not None

    # Check request status updated to PROCESSING
    br = db_session.query(BloodRequest).filter(BloodRequest.request_id == 1).first()
    assert br.status == "PROCESSING"


def test_coordinator_part9_api_endpoint(db_session):
    """Part 9: Test POST /api/v1/blood-requests/{id}/coordinate endpoint."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. Successful coordinate call
    res = client.post("/api/v1/blood-requests/1/coordinate")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["current_state"] == "COMPLETED"
    assert len(data["ranked_matches"]) > 0

    # 2. 404 on non-existent request
    res_404 = client.post("/api/v1/blood-requests/9999/coordinate")
    assert res_404.status_code == 404

    app.dependency_overrides.clear()

