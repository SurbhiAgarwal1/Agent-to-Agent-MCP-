"""Comprehensive Unit and Integration Security Tests (Step 1A)."""

import os
import jwt
from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError

from app.config import get_settings, Settings
from app.models.user import User, UserRole
from app.auth.utils import create_access_token
from tests.conftest import make_user, auth_headers


# All protected endpoints and their HTTP methods
PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/hospitals"),
    ("GET", "/api/v1/blood-requests"),
    ("GET", "/api/v1/blood-requests/1"),
    ("GET", "/api/v1/blood-requests/1/matches"),
    ("GET", "/api/v1/mcp/tools"),
    ("GET", "/api/v1/mcp/tools/calculate_distance"),
    ("POST", "/api/v1/mcp/tools/calculate_distance/invoke"),
    ("POST", "/api/v1/blood-requests"),
    ("PATCH", "/api/v1/blood-requests/1/status"),
    ("POST", "/api/v1/blood-requests/1/orchestrate"),
    ("POST", "/api/v1/blood-requests/1/coordinate"),
    ("POST", "/api/v1/nl-request"),
    ("GET", "/api/v1/auth/audit-logs"),
    ("POST", "/api/v1/auth/users"),
]


# -----------------------------------------------------------------------------
# A. Anonymous Access
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_anonymous_access_rejected(client, method, path):
    """Verify anonymous access to protected endpoints returns HTTP 401."""
    kwargs = {}
    if method in ("POST", "PATCH"):
        kwargs["json"] = {}
    response = client.request(method, path, **kwargs)
    assert response.status_code == 401


def test_public_endpoints_accessible(client):
    """Verify GET /, GET /health, /auth/register, /auth/login are reachable without auth."""
    res_root = client.get("/")
    assert res_root.status_code == 200

    res_health = client.get("/health")
    assert res_health.status_code == 200

    res_reg = client.post("/api/v1/auth/register", json={})
    assert res_reg.status_code != 401

    res_login = client.post("/api/v1/auth/login", json={})
    assert res_login.status_code != 401


# -----------------------------------------------------------------------------
# B. Bad Tokens
# -----------------------------------------------------------------------------

def test_bad_token_garbage(client):
    """Verify garbage bearer token returns 401."""
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage-token-123"})
    assert resp.status_code == 401


def test_bad_token_wrong_secret(client):
    """Verify token signed with wrong secret returns 401."""
    token = jwt.encode(
        {"sub": "1", "email": "test@example.com", "role": "ADMIN", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret-key-that-is-at-least-32-chars-long",
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_bad_token_expired(client):
    """Verify expired token returns 401."""
    secret = os.getenv("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
    token = jwt.encode(
        {"sub": "1", "email": "test@example.com", "role": "ADMIN", "exp": datetime.now(timezone.utc) - timedelta(minutes=10)},
        secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_bad_token_non_integer_sub(client):
    """Verify token with non-integer sub returns 401 without 500 error."""
    secret = os.getenv("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
    token = jwt.encode(
        {"sub": "not-an-integer", "email": "test@example.com", "role": "ADMIN", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_bad_token_deleted_user(client):
    """Verify valid token for a non-existent/deleted user returns 401."""
    secret = os.getenv("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
    token = jwt.encode(
        {"sub": "99999", "email": "deleted@example.com", "role": "ADMIN", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# -----------------------------------------------------------------------------
# C. Role Matrix
# -----------------------------------------------------------------------------

ROLE_MATRIX_CASES = [
    # Any role
    ("HOSPITAL_STAFF", "GET", "/api/v1/auth/me", True),
    ("BLOOD_BANK_STAFF", "GET", "/api/v1/auth/me", True),
    ("ADMIN", "GET", "/api/v1/auth/me", True),
    ("HOSPITAL_STAFF", "GET", "/api/v1/hospitals", True),
    ("BLOOD_BANK_STAFF", "GET", "/api/v1/hospitals", True),
    ("ADMIN", "GET", "/api/v1/hospitals", True),
    ("HOSPITAL_STAFF", "GET", "/api/v1/blood-requests", True),
    ("BLOOD_BANK_STAFF", "GET", "/api/v1/blood-requests", False),
    ("ADMIN", "GET", "/api/v1/blood-requests", True),

    # HOSPITAL_STAFF or ADMIN only
    ("HOSPITAL_STAFF", "POST", "/api/v1/blood-requests", True),
    ("ADMIN", "POST", "/api/v1/blood-requests", True),
    ("BLOOD_BANK_STAFF", "POST", "/api/v1/blood-requests", False),

    ("HOSPITAL_STAFF", "PATCH", "/api/v1/blood-requests/1/status", True),
    ("ADMIN", "PATCH", "/api/v1/blood-requests/1/status", True),
    ("BLOOD_BANK_STAFF", "PATCH", "/api/v1/blood-requests/1/status", False),

    ("HOSPITAL_STAFF", "POST", "/api/v1/blood-requests/1/orchestrate", True),
    ("ADMIN", "POST", "/api/v1/blood-requests/1/orchestrate", True),
    ("BLOOD_BANK_STAFF", "POST", "/api/v1/blood-requests/1/orchestrate", False),

    ("HOSPITAL_STAFF", "POST", "/api/v1/blood-requests/1/coordinate", True),
    ("ADMIN", "POST", "/api/v1/blood-requests/1/coordinate", True),
    ("BLOOD_BANK_STAFF", "POST", "/api/v1/blood-requests/1/coordinate", False),

    ("HOSPITAL_STAFF", "POST", "/api/v1/nl-request", True),
    ("ADMIN", "POST", "/api/v1/nl-request", True),
    ("BLOOD_BANK_STAFF", "POST", "/api/v1/nl-request", False),

    # ADMIN only
    ("ADMIN", "GET", "/api/v1/auth/audit-logs", True),
    ("HOSPITAL_STAFF", "GET", "/api/v1/auth/audit-logs", False),
    ("BLOOD_BANK_STAFF", "GET", "/api/v1/auth/audit-logs", False),


    ("ADMIN", "POST", "/api/v1/auth/users", True),
    ("HOSPITAL_STAFF", "POST", "/api/v1/auth/users", False),
    ("BLOOD_BANK_STAFF", "POST", "/api/v1/auth/users", False),
]


@pytest.mark.parametrize("role,method,path,allowed", ROLE_MATRIX_CASES)
def test_role_access_matrix(client, db_session, role, method, path, allowed):
    """Verify role permissions against ACCESS RULES."""
    user = make_user(db_session, f"role_{role.lower()}@example.com", role)
    headers = auth_headers(user)
    kwargs = {"headers": headers}
    if method in ("POST", "PATCH"):
        kwargs["json"] = {}

    resp = client.request(method, path, **kwargs)

    if allowed:
        assert resp.status_code not in (401, 403)
    else:
        assert resp.status_code == 403


# -----------------------------------------------------------------------------
# D. Registration Rules
# -----------------------------------------------------------------------------

def test_registration_default_role(client):
    """Verify public registration without role defaults to HOSPITAL_STAFF."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "defaultrole@hospital.org", "password": "Passw0rd!123"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "HOSPITAL_STAFF"


def test_registration_rejects_admin_or_bloodbank(client):
    """Verify public registration rejects ADMIN or BLOOD_BANK_STAFF role requests."""
    resp_admin = client.post(
        "/api/v1/auth/register",
        json={"email": "fakeadmin@hospital.org", "password": "Passw0rd!123", "role": "ADMIN"},
    )
    assert resp_admin.status_code == 403

    resp_bb = client.post(
        "/api/v1/auth/register",
        json={"email": "fakebb@hospital.org", "password": "Passw0rd!123", "role": "BLOOD_BANK_STAFF"},
    )
    assert resp_bb.status_code == 403


def test_registration_hospital_staff_allowed(client):
    """Verify public registration with explicit HOSPITAL_STAFF role works."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "explicitstaff@hospital.org", "password": "Passw0rd!123", "role": "HOSPITAL_STAFF"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "HOSPITAL_STAFF"


def test_registration_duplicate_email(client):
    """Verify public registration fails with 400 on duplicate email."""
    payload = {"email": "dup@hospital.org", "password": "Passw0rd!123"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400


# -----------------------------------------------------------------------------
# E. Admin User Creation Endpoint (POST /api/v1/auth/users)
# -----------------------------------------------------------------------------

def test_admin_create_users_all_roles(client, db_session):
    """Verify ADMIN can create users with any valid role."""
    admin = make_user(db_session, "admin_user@test.org", "ADMIN")
    headers = auth_headers(admin)

    for target_role in ["HOSPITAL_STAFF", "BLOOD_BANK_STAFF", "ADMIN"]:
        email = f"new_{target_role.lower()}@test.org"
        resp = client.post(
            "/api/v1/auth/users",
            json={"email": email, "password": "NewPassword123!", "role": target_role},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert data["role"] == target_role

        # Verify created user can log in
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "NewPassword123!"},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["role"] == target_role


def test_admin_create_user_validations(client, db_session):
    """Verify error responses for invalid payload, non-admin callers, and duplicates."""
    admin = make_user(db_session, "admin_val@test.org", "ADMIN")
    staff = make_user(db_session, "staff_val@test.org", "HOSPITAL_STAFF")

    # 1. Non-admin caller -> 403
    r_staff = client.post(
        "/api/v1/auth/users",
        json={"email": "test1@test.org", "password": "Passw0rd!123", "role": "HOSPITAL_STAFF"},
        headers=auth_headers(staff),
    )
    assert r_staff.status_code == 403

    # 2. Anonymous caller -> 401
    r_anon = client.post(
        "/api/v1/auth/users",
        json={"email": "test2@test.org", "password": "Passw0rd!123", "role": "HOSPITAL_STAFF"},
    )
    assert r_anon.status_code == 401

    # 3. Invalid role -> 400 or 422
    r_bad_role = client.post(
        "/api/v1/auth/users",
        json={"email": "test3@test.org", "password": "Passw0rd!123", "role": "INVALID_ROLE"},
        headers=auth_headers(admin),
    )
    assert r_bad_role.status_code in (400, 422)

    # 4. Duplicate email -> 400
    r_dup1 = client.post(
        "/api/v1/auth/users",
        json={"email": "testdup@test.org", "password": "Passw0rd!123", "role": "HOSPITAL_STAFF"},
        headers=auth_headers(admin),
    )
    assert r_dup1.status_code == 201

    r_dup2 = client.post(
        "/api/v1/auth/users",
        json={"email": "testdup@test.org", "password": "Passw0rd!123", "role": "HOSPITAL_STAFF"},
        headers=auth_headers(admin),
    )
    assert r_dup2.status_code == 400


# -----------------------------------------------------------------------------
# F. Admin-Only Endpoints
# -----------------------------------------------------------------------------

def test_admin_only_endpoints_enforcement(client, db_session):
    """Verify the administrative audit route remains role-protected."""
    admin = make_user(db_session, "admin_audit@test.org", "ADMIN")
    staff = make_user(db_session, "staff_audit@test.org", "HOSPITAL_STAFF")
    bank = make_user(db_session, "bank_audit@test.org", "BLOOD_BANK_STAFF")

    for path in ["/api/v1/auth/audit-logs"]:
        # Anonymous -> 401
        assert client.get(path).status_code == 401
        # Non-admin roles -> 403
        assert client.get(path, headers=auth_headers(staff)).status_code == 403
        assert client.get(path, headers=auth_headers(bank)).status_code == 403
        # ADMIN -> 200
        assert client.get(path, headers=auth_headers(admin)).status_code == 200


def test_observability_metrics_are_not_exposed_through_gateway(client, db_session):
    """The admin-only observability UI/network is separate from the application API."""
    admin = make_user(db_session, "observability-admin@test.org", "ADMIN")
    staff = make_user(db_session, "observability-staff@test.org", "HOSPITAL_STAFF")
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics", headers=auth_headers(admin)).status_code == 404
    assert client.get("/metrics", headers=auth_headers(staff)).status_code == 404


# -----------------------------------------------------------------------------
# G. JWT Secret Configuration & Validation
# -----------------------------------------------------------------------------

def test_jwt_secret_validation(monkeypatch):
    """Verify JWT_SECRET_KEY settings validations."""
    get_settings.cache_clear()

    # 1. Missing secret
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    # 2. Secret too short (< 32 chars)
    monkeypatch.setenv("JWT_SECRET_KEY", "short-secret-key-too-short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    # 3. Rejection of old hardcoded default 1
    monkeypatch.setenv("JWT_SECRET_KEY", "emergency-blood-secret-key-3c9f28a1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    # 4. Rejection of old hardcoded default 2
    monkeypatch.setenv("JWT_SECRET_KEY", "production-emergency-blood-key-928f01a3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    get_settings.cache_clear()


def test_token_signed_with_old_default_secret_rejected(client):
    """Verify API rejects tokens signed with the legacy default secret key."""
    old_secret = "emergency-blood-secret-key-3c9f28a1"
    token = jwt.encode(
        {"sub": "1", "email": "test@example.com", "role": "ADMIN", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        old_secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# -----------------------------------------------------------------------------
# H. CORS Configuration
# -----------------------------------------------------------------------------

def test_cors_origins_validation(monkeypatch):
    """Verify CORS_ORIGINS rejects wildcard '*'."""
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    get_settings.cache_clear()


def test_cors_preflight_headers(client):
    """Verify CORS OPTIONS preflight behavior for allowed vs disallowed origins."""
    headers_allowed = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    }
    res_allowed = client.options("/api/v1/blood-requests", headers=headers_allowed)
    assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    headers_evil = {
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
    }
    res_evil = client.options("/api/v1/blood-requests", headers=headers_evil)
    assert res_evil.headers.get("access-control-allow-origin") != "https://evil.example"


# -----------------------------------------------------------------------------
# I. End-to-End Multirole Workflow
# -----------------------------------------------------------------------------

def test_multirole_request_access_boundary(client, db_session):
    """Verify request ownership and role boundaries independent of remote services."""
    # Seed hospital & data needed for workflow
    from app.models.hospital import Hospital
    from app.models.blood_bank import BloodBank
    from app.models.blood_inventory import BloodInventory

    h = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
    b = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
    inv = BloodInventory(inventory_id=1, bank_id=1, blood_group="A+", units_available=5)
    db_session.add_all([h, b, inv])
    db_session.commit()

    # 1. Create users
    hosp_staff = make_user(db_session, "hosp_staff@test.org", "HOSPITAL_STAFF", "Passw0rd!123", hospital_ids=[1])
    bank_staff = make_user(db_session, "bank_staff@test.org", "BLOOD_BANK_STAFF", "Passw0rd!123")

    # 2. HOSPITAL_STAFF logs in
    login_hosp = client.post(
        "/api/v1/auth/login",
        json={"email": "hosp_staff@test.org", "password": "Passw0rd!123"},
    )
    assert login_hosp.status_code == 200
    hosp_token = login_hosp.json()["access_token"]
    hosp_headers = {"Authorization": f"Bearer {hosp_token}"}

    # 3. HOSPITAL_STAFF creates a blood request
    req_payload = {
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 2,
        "urgency": "HIGH",
    }
    create_res = client.post("/api/v1/blood-requests", json=req_payload, headers=hosp_headers)
    assert create_res.status_code == 201
    req_id = create_res.json()["request_id"]

    # 4. BLOOD_BANK_STAFF logs in
    login_bank = client.post(
        "/api/v1/auth/login",
        json={"email": "bank_staff@test.org", "password": "Passw0rd!123"},
    )
    assert login_bank.status_code == 200
    bank_token = login_bank.json()["access_token"]
    bank_headers = {"Authorization": f"Bearer {bank_token}"}

    # Cross-organization access is not granted because no bank membership mapping exists yet.
    get_req_res = client.get(f"/api/v1/blood-requests/{req_id}", headers=bank_headers)
    assert get_req_res.status_code == 403

    get_matches_res = client.get(f"/api/v1/blood-requests/{req_id}/matches", headers=bank_headers)
    assert get_matches_res.status_code == 403


def test_blood_request_idor_is_concealed(client, db_session):
    """A hospital staff account cannot retrieve or mutate another user's request."""
    from app.models.hospital import Hospital
    from app.models.blood_request import BloodRequest

    hospital = Hospital(name="IDOR Test A", latitude=12, longitude=77, address="Test")
    other_hospital = Hospital(name="IDOR Test B", latitude=12, longitude=78, address="Other")
    db_session.add_all([hospital, other_hospital])
    db_session.flush()
    owner = make_user(db_session, "owner-idor@test.org", "HOSPITAL_STAFF", hospital_ids=[hospital.hospital_id])
    other = make_user(db_session, "other-idor@test.org", "HOSPITAL_STAFF", hospital_ids=[other_hospital.hospital_id])
    request = BloodRequest(
        hospital_id=hospital.hospital_id, created_by_user_id=owner.id,
        blood_group="O+", units_required=1, urgency="HIGH", status="PENDING",
    )
    db_session.add(request)
    db_session.commit()
    path = f"/api/v1/blood-requests/{request.request_id}"

    assert client.get(path, headers=auth_headers(other)).status_code == 403
    assert client.get(path + "/matches", headers=auth_headers(other)).status_code == 403
    assert client.patch(path + "/status", json={"status": "CANCELLED"}, headers=auth_headers(other)).status_code == 403
    assert client.post(path + "/coordinate", headers=auth_headers(other)).status_code == 403
    assert client.post(path + "/orchestrate", headers=auth_headers(other)).status_code == 403
