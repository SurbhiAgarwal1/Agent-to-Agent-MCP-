"""Integration tests for Communication Agent REST API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_request import BloodRequest
from tests.conftest import make_user, auth_headers


@pytest.fixture
def client_and_db():
    """Create test client with isolated in-memory SQLite database."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    hosp1 = Hospital(hospital_id=1, name="Apex General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
    hosp2 = Hospital(hospital_id=2, name="Metro Care Hospital", latitude=28.7041, longitude=77.1025, address="North Delhi")
    req = BloodRequest(request_id=1, hospital_id=1, blood_group="A+", units_required=2, urgency="HIGH")
    session.add_all([hosp1, hosp2, req])
    session.commit()

    admin_user = make_user(session, "admin_comm@test.org", "ADMIN")
    hosp1_user = make_user(session, "hosp1_comm@test.org", "HOSPITAL_STAFF", hospital_ids=[1])
    hosp2_user = make_user(session, "hosp2_comm@test.org", "HOSPITAL_STAFF", hospital_ids=[2])

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield {
        "client": client,
        "db": session,
        "admin_headers": auth_headers(admin_user),
        "hosp1_headers": auth_headers(hosp1_user),
        "hosp2_headers": auth_headers(hosp2_user),
    }

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=test_engine)


def test_outreach_requires_authentication(client_and_db):
    """Verify unauthenticated request to /communication/outreach returns 401."""
    client = client_and_db["client"]
    resp = client.post("/api/v1/communication/outreach", json={"request_id": 1, "hospital_id": 1})
    assert resp.status_code == 401


def test_outreach_forbidden_for_other_hospital(client_and_db):
    """Verify hospital 2 cannot trigger outreach for hospital 1's request."""
    client = client_and_db["client"]
    h2_headers = client_and_db["hosp2_headers"]
    resp = client.post(
        "/api/v1/communication/outreach",
        json={"request_id": 1, "hospital_id": 1, "fulfillment_plan": {"plan": []}},
        headers=h2_headers,
    )
    assert resp.status_code == 403


def test_outreach_successful_dispatch_and_session_retrieval(client_and_db):
    """Verify successful outreach dispatch and subsequent session retrieval."""
    client = client_and_db["client"]
    h1_headers = client_and_db["hosp1_headers"]

    payload = {
        "request_id": 1,
        "hospital_id": 1,
        "urgency": "CRITICAL",
        "hospital_name": "Apex General Hospital",
        "fulfillment_plan": {
            "status": "PARTIALLY_FULFILLED",
            "total_units": 1,
            "plan": [
                {"source_type": "DONOR", "source_id": 10, "units": 1, "distance_km": 3.0},
            ],
        },
    }
    resp = client.post("/api/v1/communication/outreach", json=payload, headers=h1_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "session_id" in data
    session_id = data["session_id"]

    # Retrieve session details
    get_resp = client.get("/api/v1/communication/sessions/1", headers=h1_headers)
    assert get_resp.status_code == 200
    sess_data = get_resp.json()
    assert sess_data["session_id"] == session_id
    assert sess_data["request_id"] == 1
    assert sess_data["urgency"] == "CRITICAL"
    assert len(sess_data["messages"]) >= 2  # 1 hospital + 1 donor


def test_donor_respond_and_stats(client_and_db):
    """Verify recording response via API and checking communication KPI stats."""
    client = client_and_db["client"]
    admin_headers = client_and_db["admin_headers"]

    # 1. Initiate outreach
    out_resp = client.post(
        "/api/v1/communication/outreach",
        json={
            "request_id": 1,
            "hospital_id": 1,
            "fulfillment_plan": {
                "status": "FULLY_FULFILLED",
                "total_units": 1,
                "plan": [{"source_type": "DONOR", "source_id": 4, "units": 1}],
            },
        },
        headers=admin_headers,
    )
    session_id = out_resp.json()["session_id"]

    # 2. Record donor response
    resp = client.post(
        "/api/v1/communication/respond",
        json={
            "session_id": session_id,
            "recipient_type": "DONOR",
            "recipient_id": 4,
            "response_status": "CONFIRMED",
            "response_notes": "Confirmed arrival in 15 mins",
            "eta_minutes": 15,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["response_status"] == "CONFIRMED"
    assert res_data["session_status"] == "ALL_CONFIRMED"

    # 3. Retrieve system-wide stats
    stats_resp = client.get("/api/v1/communication/stats", headers=admin_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_sessions"] >= 1
    assert stats["fully_confirmed_sessions"] >= 1


def test_manual_escalate_session(client_and_db):
    """Verify manual escalation via POST /api/v1/communication/escalate/{session_id}."""
    client = client_and_db["client"]
    admin_headers = client_and_db["admin_headers"]

    out_resp = client.post(
        "/api/v1/communication/outreach",
        json={
            "request_id": 1,
            "hospital_id": 1,
            "fulfillment_plan": {
                "status": "UNFULFILLED",
                "total_units": 0,
                "plan": [{"source_type": "DONOR", "source_id": 8, "units": 1}],
            },
        },
        headers=admin_headers,
    )
    session_id = out_resp.json()["session_id"]

    esc_resp = client.post(f"/api/v1/communication/escalate/{session_id}?force=true", headers=admin_headers)
    assert esc_resp.status_code == 200
    esc_data = esc_resp.json()
    assert esc_data["session_id"] == session_id
    assert esc_data["escalated"] is True
