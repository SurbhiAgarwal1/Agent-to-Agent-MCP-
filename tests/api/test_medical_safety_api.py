"""End-to-end: unsafe sources must never appear in a coordination plan."""

from datetime import date, timedelta

import pytest

from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.hospital import Hospital
from app.models.user import UserRole
from tests.conftest import auth_headers, make_user


@pytest.fixture
def world(client, db_session):
    today = date.today()
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add_all([
        BloodBank(bank_id=1, name="Expired Bank", latitude=28.61, longitude=77.21, address="x"),
        BloodBank(bank_id=2, name="Good Bank", latitude=28.62, longitude=77.22, address="x"),
    ])
    db_session.add_all([
        BloodInventory(bank_id=1, blood_group="A+", units_available=20, expiry_date=today - timedelta(days=1)),
        BloodInventory(bank_id=2, blood_group="A+", units_available=2, expiry_date=today + timedelta(days=10)),
    ])
    db_session.add_all([
        Donor(donor_id=11, name="Recent", blood_group="A+", latitude=28.60, longitude=77.20,
              available=True, last_donation_date=today - timedelta(days=7)),
        Donor(donor_id=12, name="Ready", blood_group="A+", latitude=28.60, longitude=77.21,
              available=True, last_donation_date=today - timedelta(days=200)),
    ])
    db_session.commit()
    staff = make_user(db_session, "nurse@h1.test", UserRole.HOSPITAL_STAFF)
    client.headers.update(auth_headers(staff))
    created = client.post("/api/v1/blood-requests",
                          json={"hospital_id": 1, "blood_group": "A+", "units_required": 4, "urgency": "HIGH"})
    assert created.status_code == 201
    return client, created.json()["request_id"]


def test_coordinate_excludes_expired_stock_and_cooldown_donors(world):
    client, rid = world
    res = client.post(f"/api/v1/blood-requests/{rid}/coordinate")
    assert res.status_code == 200
    sources = {(m["source_type"], m["source_id"]) for m in res.json()["ranked_matches"]}
    assert ("BLOOD_BANK", 1) not in sources   # expired
    assert ("DONOR", 11) not in sources       # donated 7 days ago
    assert ("BLOOD_BANK", 2) in sources and ("DONOR", 12) in sources
    planned = {(p["source_type"], p["source_id"]) for p in res.json()["fulfillment_plan"]["plan"]}
    assert planned == {("BLOOD_BANK", 2), ("DONOR", 12)}
    assert res.json()["fulfillment_plan"]["total_units"] == 3   # 2 + 1, not the 20 expired units


def test_orchestrate_excludes_expired_stock_and_cooldown_donors(world):
    client, rid = world
    res = client.post(f"/api/v1/blood-requests/{rid}/orchestrate")
    assert res.status_code == 200
    body = res.json()
    used = {(s["source_type"], s["source_id"]) for s in body["allocated_sources"] + body["standby_sources"]}
    assert ("BLOOD_BANK", 1) not in used and ("DONOR", 11) not in used
    assert body["units_allocated"] == 3
    assert body["fulfillment_status"] == "PARTIALLY_FULFILLED"


def test_mcp_find_blood_sources_applies_the_same_rules(world):
    client, _ = world
    res = client.post("/api/v1/mcp/tools/find_blood_sources/invoke", json={"arguments": {"blood_group": "A+"}})
    assert res.status_code == 200
    matches = res.json()["data"]["matches"]
    sources = {(m["source_type"], m["source_id"]) for m in matches}
    assert ("BLOOD_BANK", 1) not in sources and ("DONOR", 11) not in sources
