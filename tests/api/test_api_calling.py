"""Integration tests for Calling Agent REST API endpoints and carrier webhooks."""

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

    hosp1 = Hospital(hospital_id=1, name="Medanta Medicity", latitude=28.4395, longitude=77.0427, address="Gurugram")
    hosp2 = Hospital(hospital_id=2, name="Fortis Memorial", latitude=28.4595, longitude=77.0725, address="Gurugram")
    req = BloodRequest(request_id=10, hospital_id=1, blood_group="AB+", units_required=3, urgency="CRITICAL")
    session.add_all([hosp1, hosp2, req])
    session.commit()

    admin_user = make_user(session, "admin_call@test.org", "ADMIN")
    hosp1_user = make_user(session, "hosp1_call@test.org", "HOSPITAL_STAFF", hospital_ids=[1])
    hosp2_user = make_user(session, "hosp2_call@test.org", "HOSPITAL_STAFF", hospital_ids=[2])

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


def test_dispatch_call_requires_authentication(client_and_db):
    """Verify dispatching a voice call requires a valid bearer token."""
    client = client_and_db["client"]
    resp = client.post(
        "/api/v1/calling/dispatch",
        json={"request_id": 10, "recipient_type": "DONOR", "recipient_id": 5, "recipient_phone": "+919876543210"},
    )
    assert resp.status_code == 401


def test_dispatch_call_forbidden_for_other_hospital(client_and_db):
    """Verify hospital staff cannot dispatch voice calls for other hospitals' requests."""
    client = client_and_db["client"]
    h2_headers = client_and_db["hosp2_headers"]
    resp = client.post(
        "/api/v1/calling/dispatch",
        json={"request_id": 10, "recipient_type": "DONOR", "recipient_id": 5, "recipient_phone": "+919876543210"},
        headers=h2_headers,
    )
    assert resp.status_code == 403


def test_dispatch_call_success_and_logs_retrieval(client_and_db):
    """Verify dispatching a voice call and viewing its session log."""
    client = client_and_db["client"]
    h1_headers = client_and_db["hosp1_headers"]

    payload = {
        "request_id": 10,
        "recipient_type": "DONOR",
        "recipient_id": 7,
        "recipient_phone": "+919988776655",
        "recipient_name": "Vikram Singh",
        "hospital_id": 1,
        "hospital_name": "Medanta Medicity",
        "blood_group": "AB+",
        "units_required": 3,
        "urgency": "CRITICAL",
    }
    resp = client.post("/api/v1/calling/dispatch", json=payload, headers=h1_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert "call_id" in res_data
    call_id = res_data["call_id"]

    # Retrieve logs for request
    logs_resp = client.get("/api/v1/calling/logs/10", headers=h1_headers)
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert len(logs) == 1
    assert logs[0]["call_id"] == call_id
    assert logs[0]["recipient_name"] == "Vikram Singh"
    assert logs[0]["status"] == "INITIATED"


def test_telephony_webhook_callback(client_and_db):
    """Verify carrier callback receives touch-tone DTMF digit and updates status without auth."""
    client = client_and_db["client"]
    admin_headers = client_and_db["admin_headers"]

    # 1. Dispatch call
    out_resp = client.post(
        "/api/v1/calling/dispatch",
        json={"request_id": 10, "recipient_type": "DONOR", "recipient_id": 9, "recipient_phone": "+919811223344"},
        headers=admin_headers,
    )
    call_id = out_resp.json()["call_id"]

    # 2. Carrier posts webhook callback (public webhook endpoint)
    wh_payload = {
        "call_id": call_id,
        "call_status": "COMPLETED",
        "digits_pressed": "1",
        "duration_seconds": 45,
    }
    wh_resp = client.post("/api/v1/calling/webhook", json=wh_payload)
    assert wh_resp.status_code == 200
    wh_data = wh_resp.json()
    assert wh_data["success"] is True
    assert wh_data["response_status"] == "CONFIRMED"
    assert wh_data["digits_pressed"] == "1"

    # 3. Check logs to confirm updated status
    logs_resp = client.get("/api/v1/calling/logs/10", headers=admin_headers)
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    matched = [c for c in logs if c["call_id"] == call_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "COMPLETED"
    assert matched[0]["response_status"] == "CONFIRMED"
    assert matched[0]["duration_seconds"] == 45


def test_calling_stats_endpoint(client_and_db):
    """Verify aggregated telephony KPIs endpoint."""
    client = client_and_db["client"]
    admin_headers = client_and_db["admin_headers"]

    # Fetch stats
    stats_resp = client.get("/api/v1/calling/stats", headers=admin_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_calls" in stats
    assert "completed_calls" in stats
    assert "voice_confirmation_rate_pct" in stats
