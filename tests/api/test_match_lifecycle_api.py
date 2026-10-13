"""HTTP flow: coordinate -> complete / reject, with auth and audit."""

from datetime import date, timedelta

import pytest

from app.models.audit_log import AuditLog
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.match import Match
from app.models.user import UserRole
from tests.conftest import auth_headers, make_user


@pytest.fixture
def world(client, db_session):
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add(BloodBank(bank_id=1, name="Bank", latitude=28.61, longitude=77.21, address="x"))
    db_session.add(BloodInventory(bank_id=1, blood_group="A+", units_available=5,
                                  expiry_date=date.today() + timedelta(days=9)))
    db_session.commit()
    staff = make_user(db_session, "nurse@h1.test", UserRole.HOSPITAL_STAFF)
    client.headers.update(auth_headers(staff))
    rid = client.post("/api/v1/blood-requests",
                      json={"hospital_id": 1, "blood_group": "A+", "units_required": 2, "urgency": "HIGH"}
                      ).json()["request_id"]
    plan = client.post(f"/api/v1/blood-requests/{rid}/coordinate").json()
    mid = db_session.query(Match).filter_by(request_id=rid, status="ACCEPTED").one().match_id
    return client, rid, mid, plan


def url(rid, mid, action):
    return f"/api/v1/blood-requests/{rid}/matches/{mid}/{action}"


def test_complete_decrements_stock_and_fulfils_request(world, db_session):
    client, rid, mid, _ = world
    res = client.post(url(rid, mid, "complete"))
    assert res.status_code == 200
    assert res.json()["match_status"] == "COMPLETED" and res.json()["request_status"] == "FULFILLED"
    db_session.expire_all()
    assert db_session.query(BloodInventory).one().units_available == 3
    assert db_session.get(BloodRequest, rid).status == "FULFILLED"


def test_complete_twice_conflicts(world):
    client, rid, mid, _ = world
    client.post(url(rid, mid, "complete"))
    assert client.post(url(rid, mid, "complete")).status_code == 409


def test_reject_releases_hold(world, db_session):
    client, rid, mid, _ = world
    res = client.post(url(rid, mid, "reject"), json={"reason": "bank closed"})
    assert res.status_code == 200 and res.json()["match_status"] == "REJECTED"
    db_session.expire_all()
    assert db_session.get(BloodRequest, rid).status == "PENDING"
    assert db_session.query(BloodInventory).one().units_available == 5


def test_reject_without_body_is_allowed(world):
    client, rid, mid, _ = world
    assert client.post(url(rid, mid, "reject")).status_code == 200


def test_unknown_match_or_wrong_request_is_404(world):
    client, rid, mid, _ = world
    assert client.post(url(rid, 9999, "complete")).status_code == 404
    assert client.post(url(9999, mid, "reject")).status_code == 404


def test_insufficient_stock_is_409_and_changes_nothing(world, db_session):
    client, rid, mid, _ = world
    db_session.query(BloodInventory).update({"units_available": 1})
    db_session.commit()
    assert client.post(url(rid, mid, "complete")).status_code == 409
    db_session.expire_all()
    assert db_session.get(Match, mid).status == "ACCEPTED"


def test_endpoints_require_login_and_correct_role(world, db_session):
    client, rid, mid, _ = world
    client.headers.pop("Authorization")
    assert client.post(url(rid, mid, "complete")).status_code == 401
    bank_staff = make_user(db_session, "bank@x.test", UserRole.BLOOD_BANK_STAFF)
    client.headers.update(auth_headers(bank_staff))
    assert client.post(url(rid, mid, "complete")).status_code == 403
    assert client.post(url(rid, mid, "reject")).status_code == 403


def test_actions_are_audited(world, db_session):
    client, rid, mid, _ = world
    client.post(url(rid, mid, "complete"))
    actions = {a.action for a in db_session.query(AuditLog)}
    assert "COMPLETE_MATCH" in actions


def test_recoordinating_a_fulfilled_request_is_409(world):
    client, rid, mid, _ = world
    client.post(url(rid, mid, "complete"))
    assert client.post(f"/api/v1/blood-requests/{rid}/coordinate").status_code == 409
