"""Completing and rejecting matches: stock decrements, donor cool-down, request status."""

from datetime import date, timedelta

import pytest

from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.hospital import Hospital
from app.models.match import Match
from app.services.fulfillment_service import (
    InsufficientStock, InvalidMatchState, MatchNotFound, complete_match, reject_match,
)

TODAY = date(2026, 10, 11)


@pytest.fixture
def db(db_session):
    db_session.add(Hospital(hospital_id=1, name="H", latitude=0, longitude=0, address="x"))
    db_session.add(BloodBank(bank_id=1, name="B", latitude=0, longitude=0, address="x"))
    db_session.add(Donor(donor_id=5, name="D", blood_group="A+", latitude=0, longitude=0, available=True))
    db_session.add(BloodRequest(request_id=1, hospital_id=1, blood_group="A+", units_required=4,
                                urgency="MEDIUM", status="PROCESSING"))
    db_session.commit()
    return db_session


def add_match(db, source_type="BLOOD_BANK", source_id=1, units=3, status="ACCEPTED", request_id=1, group="A+"):
    m = Match(request_id=request_id, source_type=source_type, source_id=source_id, units=units,
              blood_group=group, status=status, distance_km=1.0)
    db.add(m)
    db.commit()
    return m


def add_batch(db, units, days, group="A+"):
    expiry = None if days is None else TODAY + timedelta(days=days)
    db.add(BloodInventory(bank_id=1, blood_group=group, units_available=units, expiry_date=expiry))
    db.commit()


def stock(db):
    return {i.expiry_date: i.units_available for i in db.query(BloodInventory)}


def test_complete_bank_match_takes_stock_from_earliest_expiry_first(db):
    add_batch(db, 2, 20)
    add_batch(db, 2, 5)
    m = add_match(db, units=3)
    complete_match(db, 1, m.match_id, today=TODAY)
    assert stock(db) == {TODAY + timedelta(days=5): 0, TODAY + timedelta(days=20): 1}
    assert db.get(Match, m.match_id).status == "COMPLETED"


def test_complete_never_uses_expired_batches(db):
    add_batch(db, 5, -1)
    add_batch(db, 1, 10)
    m = add_match(db, units=2)
    with pytest.raises(InsufficientStock):
        complete_match(db, 1, m.match_id, today=TODAY)
    assert db.get(Match, m.match_id).status == "ACCEPTED"
    assert sorted(stock(db).values()) == [1, 5]          # nothing changed


def test_batches_without_expiry_are_used_last(db):
    add_batch(db, 5, None)
    add_batch(db, 1, 3)
    m = add_match(db, units=2)
    complete_match(db, 1, m.match_id, today=TODAY)
    assert stock(db) == {TODAY + timedelta(days=3): 0, None: 4}


def test_complete_only_uses_matching_blood_group(db):
    add_batch(db, 9, 10, group="B+")
    m = add_match(db, units=1)
    with pytest.raises(InsufficientStock):
        complete_match(db, 1, m.match_id, today=TODAY)


def test_complete_donor_match_starts_cooldown(db):
    m = add_match(db, source_type="DONOR", source_id=5, units=1)
    complete_match(db, 1, m.match_id, today=TODAY)
    donor = db.get(Donor, 5)
    assert donor.available is False and donor.last_donation_date == TODAY


def test_request_becomes_fulfilled_when_all_units_delivered(db):
    add_batch(db, 9, 10)
    a = add_match(db, units=3)
    b = add_match(db, source_type="DONOR", source_id=5, units=1)
    complete_match(db, 1, a.match_id, today=TODAY)
    assert db.get(BloodRequest, 1).status == "PARTIALLY_FULFILLED"
    complete_match(db, 1, b.match_id, today=TODAY)
    assert db.get(BloodRequest, 1).status == "FULFILLED"


def test_complete_requires_accepted_status(db):
    add_batch(db, 9, 10)
    for status in ("PROPOSED", "REJECTED", "COMPLETED"):
        m = add_match(db, status=status)
        with pytest.raises(InvalidMatchState):
            complete_match(db, 1, m.match_id, today=TODAY)


def test_legacy_match_without_units_cannot_be_completed(db):
    m = add_match(db, units=None)
    with pytest.raises(InvalidMatchState):
        complete_match(db, 1, m.match_id, today=TODAY)


def test_match_must_belong_to_the_request(db):
    db.add(BloodRequest(request_id=2, hospital_id=1, blood_group="A+", units_required=1,
                        urgency="LOW", status="PENDING"))
    db.commit()
    m = add_match(db, request_id=2)
    with pytest.raises(MatchNotFound):
        complete_match(db, 1, m.match_id)
    with pytest.raises(MatchNotFound):
        reject_match(db, 1, 9999)


def test_reject_releases_hold_and_resets_request(db):
    m = add_match(db, units=3)
    reject_match(db, 1, m.match_id, reason="bank closed")
    assert db.get(Match, m.match_id).status == "REJECTED"
    assert db.get(BloodRequest, 1).status == "PENDING"


def test_reject_keeps_request_partial_if_something_was_delivered(db):
    add_batch(db, 9, 10)
    a = add_match(db, units=3)
    b = add_match(db, source_type="DONOR", source_id=5, units=1)
    complete_match(db, 1, a.match_id, today=TODAY)
    reject_match(db, 1, b.match_id)
    assert db.get(BloodRequest, 1).status == "PARTIALLY_FULFILLED"


def test_reject_keeps_processing_while_other_holds_remain(db):
    a = add_match(db, units=3)
    add_match(db, source_type="DONOR", source_id=5, units=1)
    reject_match(db, 1, a.match_id)
    assert db.get(BloodRequest, 1).status == "PROCESSING"


def test_cannot_reject_completed_match(db):
    add_batch(db, 9, 10)
    m = add_match(db, units=1)
    complete_match(db, 1, m.match_id, today=TODAY)
    with pytest.raises(InvalidMatchState):
        reject_match(db, 1, m.match_id)


def test_cancelled_request_status_is_not_overwritten(db):
    db.get(BloodRequest, 1).status = "CANCELLED"
    db.commit()
    m = add_match(db, units=1)
    reject_match(db, 1, m.match_id)
    assert db.get(BloodRequest, 1).status == "CANCELLED"
