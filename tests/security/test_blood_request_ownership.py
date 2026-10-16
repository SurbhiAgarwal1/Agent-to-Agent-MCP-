"""Blood request ownership (created_by_user_id), legacy compatibility and inactive memberships."""

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database.session import ensure_schema
from app.models import BloodBank, BloodRequest, Hospital, UserRole
from app.models.membership import BloodBankMembership, HospitalMembership
from tests.conftest import auth_headers, make_user

PAYLOAD = {"blood_group": "O+", "units_required": 1, "urgency": "HIGH"}


@pytest.fixture
def hospital(db_session):
    record = Hospital(name="Ownership Hospital", latitude=12, longitude=77, address="A")
    db_session.add(record)
    db_session.commit()
    return record


def test_new_request_records_authenticated_creator_not_client_supplied_value(client, db_session, hospital):
    staff = make_user(db_session, "owner-staff@example.test", UserRole.HOSPITAL_STAFF, hospital_ids=[hospital.hospital_id])
    other = make_user(db_session, "someone-else@example.test", UserRole.USER)
    # A client-supplied creator is not part of the schema and must never be trusted.
    body = {**PAYLOAD, "hospital_id": hospital.hospital_id, "created_by_user_id": other.id}
    created = client.post("/api/v1/blood-requests", json=body, headers=auth_headers(staff))
    assert created.status_code == 201
    assert "created_by_user_id" not in created.json()
    stored = db_session.get(BloodRequest, created.json()["request_id"])
    assert stored.created_by_user_id == staff.id


def test_admin_created_request_records_admin_as_creator(client, db_session, hospital):
    admin = make_user(db_session, "owner-admin@example.test", UserRole.ADMIN)
    created = client.post("/api/v1/blood-requests", json={**PAYLOAD, "hospital_id": hospital.hospital_id},
                          headers=auth_headers(admin))
    assert created.status_code == 201
    assert db_session.get(BloodRequest, created.json()["request_id"]).created_by_user_id == admin.id


def test_legacy_request_without_creator_follows_membership_and_admin_rules(client, db_session, hospital):
    member = make_user(db_session, "legacy-member@example.test", UserRole.HOSPITAL_STAFF, hospital_ids=[hospital.hospital_id])
    outsider = make_user(db_session, "legacy-outsider@example.test", UserRole.HOSPITAL_STAFF)
    admin = make_user(db_session, "legacy-admin@example.test", UserRole.ADMIN)
    legacy = BloodRequest(hospital_id=hospital.hospital_id, blood_group="A+", units_required=2,
                          urgency="MEDIUM", status="PENDING")
    db_session.add(legacy)
    db_session.commit()
    assert legacy.created_by_user_id is None
    path = f"/api/v1/blood-requests/{legacy.request_id}"
    assert client.get(path, headers=auth_headers(member)).status_code == 200
    assert client.get(path, headers=auth_headers(admin)).status_code == 200
    assert client.get(path, headers=auth_headers(outsider)).status_code == 403


def test_deleting_creator_keeps_request_and_clears_ownership(db_session, hospital):
    staff = make_user(db_session, "ephemeral@example.test", UserRole.HOSPITAL_STAFF, hospital_ids=[hospital.hospital_id])
    request = BloodRequest(hospital_id=hospital.hospital_id, created_by_user_id=staff.id,
                           blood_group="B+", units_required=1, urgency="LOW", status="PENDING")
    db_session.add(request)
    db_session.commit()
    assert request.created_by.id == staff.id
    request_id = request.request_id
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    db_session.delete(staff)
    db_session.commit()
    db_session.expire_all()
    survivor = db_session.get(BloodRequest, request_id)
    assert survivor is not None
    assert survivor.created_by_user_id is None


def test_inactive_hospital_membership_grants_no_access(client, db_session, hospital):
    staff = make_user(db_session, "inactive-staff@example.test", UserRole.HOSPITAL_STAFF, hospital_ids=[hospital.hospital_id])
    request = BloodRequest(hospital_id=hospital.hospital_id, created_by_user_id=staff.id,
                           blood_group="O-", units_required=1, urgency="HIGH", status="PENDING")
    db_session.add(request)
    db_session.commit()
    path = f"/api/v1/blood-requests/{request.request_id}"
    assert client.get(path, headers=auth_headers(staff)).status_code == 200

    membership = db_session.query(HospitalMembership).filter_by(user_id=staff.id).one()
    membership.is_active = False
    db_session.commit()

    # Even the request's own creator loses access once the membership is inactive.
    assert client.get(path, headers=auth_headers(staff)).status_code == 403
    assert client.get("/api/v1/blood-requests", headers=auth_headers(staff)).json() == []
    assert client.post("/api/v1/blood-requests", json={**PAYLOAD, "hospital_id": hospital.hospital_id},
                       headers=auth_headers(staff)).status_code == 403


def test_inactive_blood_bank_membership_grants_no_access(db_session):
    from app.auth.authorization import has_blood_bank_membership

    bank = BloodBank(name="Inactive Bank", latitude=12, longitude=77, address="A")
    db_session.add(bank)
    db_session.commit()
    staff = make_user(db_session, "inactive-bank@example.test", UserRole.BLOOD_BANK_STAFF, bank_ids=[bank.bank_id])
    assert has_blood_bank_membership(db_session, staff.id, bank.bank_id)
    db_session.query(BloodBankMembership).filter_by(user_id=staff.id).one().is_active = False
    db_session.commit()
    assert not has_blood_bank_membership(db_session, staff.id, bank.bank_id)


def test_ensure_schema_adds_creator_column_to_legacy_database_idempotently():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE blood_requests (request_id INTEGER PRIMARY KEY, hospital_id INTEGER NOT NULL, "
            "blood_group VARCHAR(5) NOT NULL, units_required INTEGER NOT NULL, urgency VARCHAR(20) NOT NULL, "
            "status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO blood_requests VALUES (1, 1, 'O+', 1, 'HIGH', 'PENDING', '2026-01-01 00:00:00')"
        ))
    ensure_schema(engine)
    ensure_schema(engine)  # second run must be a no-op
    columns = {c["name"] for c in inspect(engine).get_columns("blood_requests")}
    assert "created_by_user_id" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT created_by_user_id FROM blood_requests WHERE request_id = 1")).scalar() is None
