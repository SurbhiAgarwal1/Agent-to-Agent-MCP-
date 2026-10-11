"""Safety rules in the Matching Agent: expired stock and donor donation gaps."""

from datetime import date, timedelta

import pytest

from app.agents.matching_agent import MatchingAgent
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor

TODAY = date(2026, 10, 11)
REQ = {"request_id": 1, "blood_group": "A+"}


def inv(bank_id, group, units, expiry):
    return {"bank_id": bank_id, "blood_group": group, "units_available": units, "expiry_date": expiry}


def donor(donor_id, group="A+", last=None, available=True):
    return {"donor_id": donor_id, "blood_group": group, "available": available, "last_donation_date": last}


def ids(result, source_type):
    return {m["source_id"] for m in result["matches"] if m["source_type"] == source_type}


# ------------------------------------------------------------------ expiry
def test_expired_inventory_is_never_matched():
    result = MatchingAgent().find_matches(
        REQ, inventories=[inv(1, "A+", 9, TODAY - timedelta(days=1)), inv(2, "A+", 4, TODAY + timedelta(days=5))],
        donors=[], today=TODAY,
    )
    assert ids(result, "BLOOD_BANK") == {2}


def test_inventory_expiring_today_is_matched():
    result = MatchingAgent().find_matches(REQ, inventories=[inv(1, "A+", 3, TODAY)], donors=[], today=TODAY)
    assert ids(result, "BLOOD_BANK") == {1}


def test_inventory_without_expiry_still_matches():
    result = MatchingAgent().find_matches(
        REQ, inventories=[{"bank_id": 1, "blood_group": "A+", "units_available": 3}], donors=[], today=TODAY)
    assert ids(result, "BLOOD_BANK") == {1}


def test_expired_compatible_alternate_is_also_excluded():
    # O- is compatible with A+, but this batch is expired
    result = MatchingAgent().find_matches(
        REQ, inventories=[inv(1, "O-", 9, TODAY - timedelta(days=3))], donors=[], today=TODAY)
    assert result["matches"] == []


def test_all_stock_expired_returns_no_matches_and_reports_why():
    result = MatchingAgent().find_matches(
        REQ, inventories=[inv(1, "A+", 9, TODAY - timedelta(days=1)), inv(2, "A+", 2, TODAY - timedelta(days=9))],
        donors=[], today=TODAY)
    assert result["matches"] == []
    assert result["excluded"]["expired_inventory_batches"] == 2


# ----------------------------------------------------------------- donor gap
def test_donor_in_cooldown_is_excluded():
    result = MatchingAgent().find_matches(
        REQ, inventories=[], donors=[donor(1, last=TODAY - timedelta(days=10)), donor(2, last=TODAY - timedelta(days=200))],
        today=TODAY)
    assert ids(result, "DONOR") == {2}
    assert result["excluded"]["donors_in_cooldown"] == 1


def test_donor_exactly_at_gap_is_eligible_and_one_day_short_is_not():
    result = MatchingAgent().find_matches(
        REQ, inventories=[],
        donors=[donor(1, last=TODAY - timedelta(days=56)), donor(2, last=TODAY - timedelta(days=55))], today=TODAY)
    assert ids(result, "DONOR") == {1}


def test_never_donated_donor_is_eligible():
    result = MatchingAgent().find_matches(REQ, inventories=[], donors=[donor(1, last=None)], today=TODAY)
    assert ids(result, "DONOR") == {1}


def test_unavailable_donor_still_excluded():
    result = MatchingAgent().find_matches(
        REQ, inventories=[], donors=[donor(1, last=None, available=False)], today=TODAY)
    assert result["matches"] == []


def test_gap_is_configurable_through_environment(monkeypatch):
    monkeypatch.setenv("DONOR_MIN_GAP_DAYS", "120")
    result = MatchingAgent().find_matches(
        REQ, inventories=[], donors=[donor(1, last=TODAY - timedelta(days=100))], today=TODAY)
    assert result["matches"] == []


# ----------------------------------------------------------- database-backed
def test_database_path_applies_both_rules(db_session):
    today = date.today()
    db_session.add_all([
        BloodInventory(bank_id=1, blood_group="A+", units_available=8, expiry_date=today - timedelta(days=2)),
        BloodInventory(bank_id=2, blood_group="A+", units_available=3, expiry_date=today + timedelta(days=9)),
        Donor(name="Recent", blood_group="A+", latitude=0, longitude=0, available=True,
              last_donation_date=today - timedelta(days=14)),
        Donor(name="Ready", blood_group="A+", latitude=0, longitude=0, available=True,
              last_donation_date=today - timedelta(days=300)),
    ])
    db_session.commit()

    result = MatchingAgent(db=db_session).find_matches(REQ)

    assert ids(result, "BLOOD_BANK") == {2}
    donor_ids = ids(result, "DONOR")
    assert len(donor_ids) == 1
    assert db_session.query(Donor).filter(Donor.donor_id.in_(donor_ids)).one().name == "Ready"
