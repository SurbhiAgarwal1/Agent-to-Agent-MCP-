"""Organization membership and resource-scope regression tests."""

import pytest
from app.models import BloodBank, BloodRequest, Hospital, Match, UserRole
from tests.conftest import auth_headers, make_user


@pytest.fixture
def organizations(db_session):
    hospital_a = Hospital(name="Hospital A", latitude=12, longitude=77, address="A")
    hospital_b = Hospital(name="Hospital B", latitude=13, longitude=78, address="B")
    bank_a = BloodBank(name="Bank A", latitude=12, longitude=77, address="A")
    bank_b = BloodBank(name="Bank B", latitude=13, longitude=78, address="B")
    db_session.add_all([hospital_a, hospital_b, bank_a, bank_b])
    db_session.commit()
    return hospital_a, hospital_b, bank_a, bank_b


def grant(client, admin, user_id, path, org_id):
    return client.post(path.format(user_id=user_id), json={"organization_id": org_id}, headers=auth_headers(admin))


def test_hospital_membership_scopes_requests_and_admin_override(client, db_session, organizations):
    hospital_a, hospital_b, _, _ = organizations
    admin = make_user(db_session, "membership-admin@example.test", UserRole.ADMIN)
    staff_a = make_user(db_session, "hospital-a@example.test", UserRole.HOSPITAL_STAFF)
    coworker_a = make_user(db_session, "hospital-a-coworker@example.test", UserRole.HOSPITAL_STAFF)
    staff_b = make_user(db_session, "hospital-b@example.test", UserRole.HOSPITAL_STAFF)
    normal_user = make_user(db_session, "normal-user@example.test", UserRole.USER)
    assert grant(client, admin, staff_a.id, "/api/v1/auth/users/{user_id}/hospital-memberships", hospital_a.hospital_id).status_code == 200
    assert grant(client, admin, coworker_a.id, "/api/v1/auth/users/{user_id}/hospital-memberships", hospital_a.hospital_id).status_code == 200
    membership_b = grant(client, admin, staff_b.id, "/api/v1/auth/users/{user_id}/hospital-memberships", hospital_b.hospital_id)
    assert membership_b.status_code == 200

    payload = {"hospital_id": hospital_a.hospital_id, "blood_group": "O+", "units_required": 1, "urgency": "HIGH"}
    created_a = client.post("/api/v1/blood-requests", json=payload, headers=auth_headers(staff_a))
    assert created_a.status_code == 201
    request_a = created_a.json()["request_id"]
    assert client.get(f"/api/v1/blood-requests/{request_a}", headers=auth_headers(coworker_a)).status_code == 200
    cross_create = client.post("/api/v1/blood-requests", json={**payload, "hospital_id": hospital_b.hospital_id}, headers=auth_headers(staff_a))
    assert cross_create.status_code == 403
    assert client.get(f"/api/v1/blood-requests/{request_a}", headers=auth_headers(staff_b)).status_code == 403
    assert client.patch(f"/api/v1/blood-requests/{request_a}/status", json={"status": "CANCELLED"}, headers=auth_headers(staff_b)).status_code == 403
    assert client.post(f"/api/v1/blood-requests/{request_a}/coordinate", headers=auth_headers(staff_b)).status_code == 403
    assert client.get(f"/api/v1/blood-requests/{request_a}", headers=auth_headers(normal_user)).status_code == 403
    assert client.get(f"/api/v1/blood-requests/{request_a}", headers=auth_headers(admin)).status_code == 200

    # Known request IDs and guessed match IDs cannot bypass organization membership.
    match = Match(request_id=request_a, source_type="BLOOD_BANK", source_id=1, status="PROPOSED")
    db_session.add(match)
    db_session.commit()
    assert client.post(f"/api/v1/blood-requests/{request_a}/matches/{match.match_id}/reject",
                       json={}, headers=auth_headers(staff_b)).status_code == 403
    assert client.post(f"/api/v1/blood-requests/{request_a}/matches/{match.match_id}/complete",
                       headers=auth_headers(staff_b)).status_code == 403

    membership_id = membership_b.json()["membership_id"]
    assert client.delete(f"/api/v1/auth/hospital-memberships/{membership_id}", headers=auth_headers(admin)).status_code == 200
    assert client.post("/api/v1/blood-requests", json={**payload, "hospital_id": hospital_b.hospital_id},
                       headers=auth_headers(staff_b)).status_code == 403


def test_unassigned_hospital_staff_and_unknown_organization_are_denied(client, db_session, organizations):
    hospital_a, _, _, _ = organizations
    admin = make_user(db_session, "membership-admin-two@example.test", UserRole.ADMIN)
    unassigned = make_user(db_session, "unassigned@example.test", UserRole.HOSPITAL_STAFF)
    payload = {"hospital_id": hospital_a.hospital_id, "blood_group": "A+", "units_required": 1, "urgency": "MEDIUM"}
    assert client.post("/api/v1/blood-requests", json=payload, headers=auth_headers(unassigned)).status_code == 403
    unknown_org = grant(client, admin, unassigned.id, "/api/v1/auth/users/{user_id}/hospital-memberships", 99999)
    assert unknown_org.status_code == 404


def test_blood_bank_membership_is_explicit_and_revocable(client, db_session, organizations):
    _, _, bank_a, bank_b = organizations
    admin = make_user(db_session, "membership-admin-three@example.test", UserRole.ADMIN)
    bank_staff = make_user(db_session, "bank-a@example.test", UserRole.BLOOD_BANK_STAFF)
    granted = grant(client, admin, bank_staff.id, "/api/v1/auth/users/{user_id}/blood-bank-memberships", bank_a.bank_id)
    assert granted.status_code == 200
    from app.auth.authorization import has_blood_bank_membership
    assert has_blood_bank_membership(db_session, bank_staff.id, bank_a.bank_id)
    assert not has_blood_bank_membership(db_session, bank_staff.id, bank_b.bank_id)
    membership_id = granted.json()["membership_id"]
    assert client.delete(f"/api/v1/auth/blood-bank-memberships/{membership_id}", headers=auth_headers(admin)).status_code == 200
    assert not has_blood_bank_membership(db_session, bank_staff.id, bank_a.bank_id)
