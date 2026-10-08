"""Unit and Integration Tests for Part 15 Authentication and Audit Logging."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.auth.models import User, UserRole, AuditLog


@pytest.fixture
def auth_client():
    """Create test client with isolated SQLite database and seed data."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    with TestingSession() as session:
        h = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
        b = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
        inv = BloodInventory(inventory_id=1, bank_id=1, blood_group="A+", units_available=5)
        session.add_all([h, b, inv])
        session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSession()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_auth_register_and_login_success(auth_client):
    """Verify user registration and subsequent successful JWT login."""
    client, _ = auth_client

    # 1. Register
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "staff@hospital.org", "password": "securepassword123", "role": "HOSPITAL_STAFF"},
    )
    assert reg_resp.status_code == 201
    user_data = reg_resp.json()
    assert user_data["email"] == "staff@hospital.org"
    assert user_data["role"] == "HOSPITAL_STAFF"

    # 2. Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@hospital.org", "password": "securepassword123"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["role"] == "HOSPITAL_STAFF"


def test_auth_register_duplicate_email_fails(auth_client):
    """Verify registration rejects duplicate email."""
    client, _ = auth_client

    payload = {"email": "duplicate@hospital.org", "password": "password123", "role": "HOSPITAL_STAFF"}
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


def test_auth_login_invalid_credentials_fails(auth_client):
    """Verify login fails with 401 on incorrect password or non-existent user."""
    client, _ = auth_client

    # Non-existent user
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@test.org", "password": "password123"})
    assert resp.status_code == 401

    # Wrong password
    client.post("/api/v1/auth/register", json={"email": "user@test.org", "password": "correctpassword", "role": "ADMIN"})
    wrong_resp = client.post("/api/v1/auth/login", json={"email": "user@test.org", "password": "wrongpassword"})
    assert wrong_resp.status_code == 401


def test_protected_endpoint_rejects_unauthenticated(auth_client):
    """Verify protected /auth/me endpoint rejects unauthenticated request with 401."""
    client, _ = auth_client
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_protected_endpoint_accepts_authenticated(auth_client):
    """Verify protected /auth/me accepts valid Bearer token."""
    client, _ = auth_client

    client.post("/api/v1/auth/register", json={"email": "doctor@hospital.org", "password": "secretpass123", "role": "HOSPITAL_STAFF"})
    login_resp = client.post("/api/v1/auth/login", json={"email": "doctor@hospital.org", "password": "secretpass123"})
    token = login_resp.json()["access_token"]

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "doctor@hospital.org"


def test_audit_logs_created_on_key_actions(auth_client):
    """Verify AuditLog records created on request creation, status update, and coordination."""
    client, session = auth_client

    # 1. Action: CREATE_REQUEST
    req_resp = client.post(
        "/api/v1/blood-requests",
        json={"hospital_id": 1, "blood_group": "A+", "units_required": 2, "urgency": "HIGH"},
    )
    assert req_resp.status_code == 201
    req_id = req_resp.json()["request_id"]

    # 2. Action: UPDATE_STATUS
    client.patch(
        f"/api/v1/blood-requests/{req_id}/status",
        json={"status": "PROCESSING"},
    )

    # 3. Action: COORDINATE
    client.post(f"/api/v1/blood-requests/{req_id}/coordinate")

    # Check database for audit log entries
    logs = session.query(AuditLog).all()
    actions = [l.action for l in logs]
    assert "CREATE_REQUEST" in actions
    assert "UPDATE_STATUS" in actions
    assert "COORDINATE" in actions
