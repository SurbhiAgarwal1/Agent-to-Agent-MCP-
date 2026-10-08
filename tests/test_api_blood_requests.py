"""Integration tests for Blood Request API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_request import BloodRequest
from app.models.enums import BloodGroup, UrgencyLevel, RequestStatus


@pytest.fixture
def client():
    """Create a test client with an isolated in-memory SQLite database using StaticPool."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Seed an initial test hospital with ID 1
    with TestingSession() as seed_session:
        test_hospital = Hospital(
            name="Apex Test General Hospital",
            latitude=28.6139,
            longitude=77.2090,
            address="10 Medical Drive, Test City",
        )
        seed_session.add(test_hospital)
        seed_session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


# 1. Successful request creation
def test_create_blood_request_success(client):
    """Test successful creation of a blood request returning HTTP 201."""
    payload = {
        "hospital_id": 1,
        "blood_group": "O+",
        "units_required": 4,
        "urgency": "CRITICAL",
    }
    response = client.post("/api/v1/blood-requests", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["request_id"] is not None
    assert data["hospital_id"] == 1
    assert data["blood_group"] == "O+"
    assert data["units_required"] == 4
    assert data["urgency"] == "CRITICAL"
    assert data["status"] == "PENDING"
    assert "created_at" in data


# 2. Invalid blood group
def test_create_blood_request_invalid_blood_group(client):
    """Test validation rejection when blood group is invalid returning HTTP 422."""
    payload = {
        "hospital_id": 1,
        "blood_group": "XYZ+",
        "units_required": 2,
        "urgency": "HIGH",
    }
    response = client.post("/api/v1/blood-requests", json=payload)
    assert response.status_code == 422


# 3. Zero units
def test_create_blood_request_zero_units(client):
    """Test validation rejection when units_required is 0 returning HTTP 422."""
    payload = {
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 0,
        "urgency": "MEDIUM",
    }
    response = client.post("/api/v1/blood-requests", json=payload)
    assert response.status_code == 422


# 4. Hospital not found
def test_create_blood_request_hospital_not_found(client):
    """Test rejection when referenced hospital_id does not exist returning HTTP 404."""
    payload = {
        "hospital_id": 9999,
        "blood_group": "B+",
        "units_required": 3,
        "urgency": "HIGH",
    }
    response = client.post("/api/v1/blood-requests", json=payload)
    assert response.status_code == 404
    assert "Hospital with ID 9999 not found" in response.json()["detail"]


# 5. Request not found
def test_get_blood_request_not_found(client):
    """Test fetching a non-existent request ID returning HTTP 404."""
    response = client.get("/api/v1/blood-requests/9999")
    assert response.status_code == 404
    assert "Blood request with ID 9999 not found" in response.json()["detail"]


# 6. Status update
def test_update_blood_request_status_success(client):
    """Test updating request status returning HTTP 200 with new status."""
    # First create a request
    create_payload = {
        "hospital_id": 1,
        "blood_group": "AB-",
        "units_required": 1,
        "urgency": "LOW",
    }
    create_res = client.post("/api/v1/blood-requests", json=create_payload)
    assert create_res.status_code == 201
    req_id = create_res.json()["request_id"]

    # Now update its status to FULFILLED
    update_payload = {"status": "FULFILLED"}
    patch_res = client.patch(f"/api/v1/blood-requests/{req_id}/status", json=update_payload)
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "FULFILLED"

    # Also verify via GET
    get_res = client.get(f"/api/v1/blood-requests/{req_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "FULFILLED"


# 7. Invalid status
def test_update_blood_request_invalid_status(client):
    """Test updating request with an unrecognized status returning HTTP 422."""
    # Create request
    create_payload = {
        "hospital_id": 1,
        "blood_group": "O-",
        "units_required": 2,
        "urgency": "CRITICAL",
    }
    create_res = client.post("/api/v1/blood-requests", json=create_payload)
    req_id = create_res.json()["request_id"]

    # Attempt to update with invalid status
    invalid_patch = {"status": "NOT_A_REAL_STATUS"}
    patch_res = client.patch(f"/api/v1/blood-requests/{req_id}/status", json=invalid_patch)
    assert patch_res.status_code == 422


# 8. Listing requests
def test_list_blood_requests(client):
    """Test retrieving list of all blood requests returning HTTP 200."""
    # Create two requests
    client.post("/api/v1/blood-requests", json={
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 2,
        "urgency": "MEDIUM",
    })
    client.post("/api/v1/blood-requests", json={
        "hospital_id": 1,
        "blood_group": "B-",
        "units_required": 1,
        "urgency": "HIGH",
    })

    response = client.get("/api/v1/blood-requests")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
