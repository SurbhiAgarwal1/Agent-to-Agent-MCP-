"""Unified coordinator flow: unit reservation (holds), re-coordination and request state."""

from datetime import date, timedelta

import pytest

from app.agents.coordinator_agent import CoordinatorAgent
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.hospital import Hospital
from app.models.match import Match
from app.services.fulfillment_service import complete_match, reject_match


@pytest.fixture
def world(db_session):
    today = date.today()
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add_all([
        BloodBank(bank_id=1, name="Near Bank", latitude=28.61, longitude=77.21, address="x"),
        BloodBank(bank_id=2, name="Far Bank", latitude=28.90, longitude=77.50, address="x"),
    ])
    db_session.add_all([
        BloodInventory(bank_id=1, blood_group="A+", units_available=3, expiry_date=today + timedelta(days=10)),
        BloodInventory(bank_id=2, blood_group="A+", units_available=5, expiry_date=today + timedelta(days=10)),
    ])
    db_session.commit()
    return db_session


def make_request(db, rid, units=2, group="A+", urgency="MEDIUM", status="PENDING"):
    db.add(BloodRequest(request_id=rid, hospital_id=1, blood_group=group, units_required=units,
                        urgency=urgency, status=status))
    db.commit()


def held(db, request_id):
    return {(m.source_type, m.source_id): m.units
            for m in db.query(Match).filter(Match.request_id == request_id, Match.status == "ACCEPTED")}


def test_plan_entries_become_accepted_holds_with_units_and_group(world):
    make_request(world, 1, units=2)
    res = CoordinatorAgent(db=world).coordinate(1)
    assert res["success"]
    assert held(world, 1) == {("BLOOD_BANK", 1): 2}
    row = world.query(Match).filter_by(request_id=1, status="ACCEPTED").one()
    assert row.blood_group == "A+" and row.units == 2
    assert row.priority_score is not None and row.priority_score != round(row.distance_km, 2)


def test_non_plan_candidates_are_proposed_without_units(world):
    make_request(world, 1, units=2)
    CoordinatorAgent(db=world).coordinate(1)
    alt = world.query(Match).filter_by(request_id=1, status="PROPOSED").all()
    assert alt and all(m.units is None for m in alt)


def test_request_is_processing_not_fulfilled_until_delivery_confirmed(world):
    make_request(world, 1, units=2)
    CoordinatorAgent(db=world).coordinate(1)
    assert world.get(BloodRequest, 1).status == "PROCESSING"


def test_shortage_marks_request_partially_fulfilled(world):
    make_request(world, 1, units=50)
    res = CoordinatorAgent(db=world).coordinate(1)
    assert res["fulfillment_plan"]["status"] == "PARTIALLY_FULFILLED"
    assert world.get(BloodRequest, 1).status == "PARTIALLY_FULFILLED"


def test_second_request_cannot_double_book_held_units(world):
    make_request(world, 1, units=3)   # takes all 3 near-bank units
    make_request(world, 2, units=3)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    coord.coordinate(2)
    assert held(world, 1) == {("BLOOD_BANK", 1): 3}
    assert ("BLOOD_BANK", 1) not in held(world, 2)
    assert held(world, 2) == {("BLOOD_BANK", 2): 3}


def test_partially_held_stock_is_offered_with_reduced_units(world):
    make_request(world, 1, units=2)   # near bank: 2 of 3 held
    make_request(world, 2, units=3)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    coord.coordinate(2)
    assert held(world, 2).get(("BLOOD_BANK", 1)) == 1   # only the 1 free unit
    assert sum(held(world, 2).values()) == 3


def test_recoordinating_same_request_replaces_its_own_holds(world):
    make_request(world, 1, units=3)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    coord.coordinate(1)
    assert held(world, 1) == {("BLOOD_BANK", 1): 3}   # not 0 free units, not double rows
    assert world.query(Match).filter_by(request_id=1, status="ACCEPTED").count() == 1


def test_donor_held_by_one_request_is_not_offered_to_another(world):
    world.add(Donor(donor_id=7, name="D", blood_group="A+", latitude=28.60, longitude=77.20, available=True))
    world.query(BloodInventory).delete()
    world.commit()
    make_request(world, 1, units=1)
    make_request(world, 2, units=1)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    res2 = coord.coordinate(2)
    assert held(world, 1) == {("DONOR", 7): 1}
    assert held(world, 2) == {}
    assert res2["success"] is False and res2["failed_at"] == "MATCHING"   # nothing left to offer


def test_rejected_source_is_not_offered_again_to_same_request(world):
    make_request(world, 1, units=2)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    mid = world.query(Match).filter_by(request_id=1, status="ACCEPTED").one().match_id
    reject_match(world, 1, mid, reason="bank closed")
    coord.coordinate(1)
    assert ("BLOOD_BANK", 1) not in held(world, 1)
    assert held(world, 1) == {("BLOOD_BANK", 2): 2}


def test_completed_units_reduce_what_is_still_needed(world):
    make_request(world, 1, units=5)
    coord = CoordinatorAgent(db=world)
    coord.coordinate(1)
    mid = world.query(Match).filter_by(request_id=1, status="ACCEPTED", source_id=1).one().match_id
    complete_match(world, 1, mid)                      # 3 units delivered from the near bank
    res = coord.coordinate(1)
    assert res["fulfillment_plan"]["details"]["units_required"] == 2
    assert sum(held(world, 1).values()) == 2


@pytest.mark.parametrize("state", ["FULFILLED", "CANCELLED"])
def test_closed_requests_are_not_coordinated(world, state):
    make_request(world, 1, units=1, status=state)
    res = CoordinatorAgent(db=world).coordinate(1)
    assert res["success"] is False and res["failed_at"] == "STATE"
    assert world.query(Match).filter_by(request_id=1).count() == 0


def test_orchestrate_is_the_same_flow_as_coordinate(world):
    make_request(world, 1, units=4)
    out = CoordinatorAgent(db=world).orchestrate(1)
    assert out["success"] and out["units_allocated"] == 4
    assert out["fulfillment_status"] == "FULFILLED"           # plan fully covers the request
    assert {(s["source_type"], s["source_id"]): s["units_allocated"] for s in out["allocated_sources"]} == held(world, 1)
    assert not any(s["source_id"] in () for s in out["standby_sources"])
    assert world.get(BloodRequest, 1).status == "PROCESSING"   # still not delivered
    assert {"INIT", "MATCHING_AGENT", "ALLOCATION_ENGINE", "PERSISTENCE"} <= {e["step"] for e in out["execution_log"]}


def test_orchestrate_unknown_request_raises_value_error(world):
    with pytest.raises(ValueError, match="not found"):
        CoordinatorAgent(db=world).orchestrate(999)


def test_persist_false_writes_nothing(world):
    make_request(world, 1, units=2)
    CoordinatorAgent(db=world).coordinate(1, persist=False)
    assert world.query(Match).count() == 0
    assert world.get(BloodRequest, 1).status == "PENDING"
