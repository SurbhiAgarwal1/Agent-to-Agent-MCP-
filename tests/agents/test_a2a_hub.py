"""A2A hub-and-spoke: every agent conversation goes through the Coordinator."""

from datetime import date, timedelta

import pytest

from app.agents.a2a.bus import MessageBus
from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.agents.a2a.orchestration import orchestrate_a2a_flow
from app.agents.coordinator_agent import COORDINATOR_NAME, CoordinatorAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.notification_agent import NotificationAgent
from app.agents.requirement_agent import RequirementAgent
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital

T = A2AMessageType


@pytest.fixture
def world(db_session):
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add(BloodBank(bank_id=1, name="Bank", latitude=28.61, longitude=77.21, address="x"))
    db_session.add(BloodInventory(bank_id=1, blood_group="A+", units_available=6,
                                  expiry_date=date.today() + timedelta(days=9)))
    db_session.add(BloodRequest(request_id=1, hospital_id=1, blood_group="A+", units_required=2,
                                urgency="HIGH", status="PENDING"))
    db_session.commit()
    return db_session


def pairs(trace):
    return [(m["sender"], m["receiver"], m["type"]) for m in trace]


def only_hub(trace):
    return all(COORDINATOR_NAME in (m["sender"], m["receiver"]) for m in trace)


# ------------------------------------------------------------------ routing
def test_preview_flow_runs_each_agent_through_the_coordinator(world):
    res = CoordinatorAgent(db=world).coordinate(1, persist=False)
    assert res["success"]
    assert pairs(res["a2a_trace"]) == [
        (COORDINATOR_NAME, "RequirementAgent", T.REQUIREMENT_VALIDATE_REQUEST),
        ("RequirementAgent", COORDINATOR_NAME, T.REQUIREMENT_VALIDATED_EVENT),
        (COORDINATOR_NAME, "MatchingAgent", T.MATCHING_FIND_SOURCES_REQUEST),
        ("MatchingAgent", COORDINATOR_NAME, T.MATCHING_SOURCES_FOUND_EVENT),
        (COORDINATOR_NAME, "LocationAgent", T.LOCATION_CALCULATE_DISTANCES_REQUEST),
        ("LocationAgent", COORDINATOR_NAME, T.LOCATION_DISTANCES_CALCULATED_EVENT),
    ]


def test_persisted_flow_notifies_through_the_bus_after_reservation(world):
    res = CoordinatorAgent(db=world).coordinate(1, persist=True)
    trace = pairs(res["a2a_trace"])
    assert trace[-2:] == [
        (COORDINATOR_NAME, "NotificationAgent", T.NOTIFICATION_DISPATCH_REQUEST),
        ("NotificationAgent", COORDINATOR_NAME, T.NOTIFICATION_DISPATCHED_EVENT),
    ]
    assert res["notifications"]["dispatched_count"] >= 2   # hospital + at least one source


def test_preview_never_sends_notifications(world):
    res = CoordinatorAgent(db=world).coordinate(1, persist=False)
    assert res["notifications"]["dispatched_count"] == 0
    assert T.NOTIFICATION_DISPATCH_REQUEST not in [m["type"] for m in res["a2a_trace"]]


def test_no_notification_when_nothing_was_found(world):
    world.add(BloodRequest(request_id=2, hospital_id=1, blood_group="AB-", units_required=1,
                           urgency="LOW", status="PENDING"))
    world.query(BloodInventory).delete()
    world.commit()
    res = CoordinatorAgent(db=world).coordinate(2, persist=True)
    assert res["success"] is False and res["failed_at"] == "MATCHING"
    assert T.NOTIFICATION_DISPATCH_REQUEST not in [m["type"] for m in res["a2a_trace"]]


def test_every_message_involves_the_coordinator_and_shares_one_correlation_id(world):
    res = CoordinatorAgent(db=world).coordinate(1, persist=True, correlation_id="corr-xyz")
    assert res["correlation_id"] == "corr-xyz"
    assert only_hub(res["a2a_trace"])
    bus_ids = {m["correlation_id"] for m in res["a2a_trace"]}
    assert bus_ids == {"corr-xyz"}


def test_orchestrate_view_also_exposes_the_trace(world):
    out = CoordinatorAgent(db=world).orchestrate(1)
    assert out["success"] and only_hub(out["a2a_trace"])


# ----------------------------------------------------------------- failures
def test_validation_failure_travels_as_an_a2a_error(world):
    res = CoordinatorAgent(db=world).coordinate({"request_id": 5, "hospital_id": 1, "blood_group": "ZZ",
                                                 "units_required": 1, "urgency": "LOW"}, persist=False)
    assert res["success"] is False and res["failed_at"] == "VALIDATION"
    assert res["a2a_trace"][-1]["type"] == T.A2A_ERROR and res["a2a_trace"][-1]["sender"] == "RequirementAgent"
    assert res["details"]


def test_a_crashing_agent_is_reported_not_raised(world):
    coord = CoordinatorAgent(db=world)

    def boom(_msg):
        raise RuntimeError("routing service down")

    coord.bus.register_agent("LocationAgent", boom)
    res = coord.coordinate(1, persist=True)
    assert res["success"] is False and res["failed_at"] == "LOCATION"
    assert "routing service down" in res["error"]
    assert world.get(BloodRequest, 1).status == "PENDING"      # nothing reserved


# ------------------------------------------------------------------- hub rule
def test_bus_with_a_hub_rejects_agent_to_agent_messages():
    bus = MessageBus(hub="CoordinatorAgent")
    bus.register_agent("MatchingAgent", lambda m: m.create_response("MatchingAgent", T.MATCHING_SOURCES_FOUND_EVENT, {}))
    direct = A2AMessage.create("RequirementAgent", "MatchingAgent", T.MATCHING_FIND_SOURCES_REQUEST, {}, "c1")
    reply = bus.send(direct)
    assert reply.message_type == T.A2A_ERROR
    assert "CoordinatorAgent" in reply.payload["error"]


def test_bus_with_a_hub_allows_hub_traffic():
    bus = MessageBus(hub="CoordinatorAgent")
    bus.register_agent("MatchingAgent", lambda m: m.create_response("MatchingAgent", T.MATCHING_SOURCES_FOUND_EVENT, {}))
    ok = A2AMessage.create("CoordinatorAgent", "MatchingAgent", T.MATCHING_FIND_SOURCES_REQUEST, {}, "c2")
    assert bus.send(ok).message_type == T.MATCHING_SOURCES_FOUND_EVENT


def test_bus_without_a_hub_is_unrestricted():
    bus = MessageBus()
    bus.register_agent("B", lambda m: m.create_response("B", T.MATCHING_SOURCES_FOUND_EVENT, {}))
    assert bus.send(A2AMessage.create("A", "B", T.MATCHING_FIND_SOURCES_REQUEST, {}, "c3")).message_type == \
        T.MATCHING_SOURCES_FOUND_EVENT


def test_coordinator_makes_a_supplied_bus_hub_only():
    bus = MessageBus()
    CoordinatorAgent(bus=bus)
    assert bus.hub == COORDINATOR_NAME


# ------------------------------------------------------- agents do not chain
def test_agents_reply_to_the_sender_instead_of_forwarding(world):
    bus = MessageBus()
    req = RequirementAgent(db=world, bus=bus)
    bus.register_agent("RequirementAgent", req.handle_a2a_message)
    bus.register_agent("MatchingAgent", MatchingAgent(db=world, bus=bus).handle_a2a_message)
    msg = A2AMessage.create(COORDINATOR_NAME, "RequirementAgent", T.REQUIREMENT_VALIDATE_REQUEST,
                            {"request_id": 1, "hospital_id": 1, "blood_group": "A+", "units_required": 1,
                             "urgency": "LOW"}, "c4")
    reply = bus.send(msg)
    assert reply.message_type == T.REQUIREMENT_VALIDATED_EVENT and reply.receiver_agent == COORDINATOR_NAME
    assert [m.receiver_agent for m in bus.get_messages_for_correlation_id("c4")] == ["RequirementAgent", COORDINATOR_NAME]


def test_matching_agent_replies_without_calling_location():
    bus = MessageBus()
    agent = MatchingAgent(bus=bus)
    bus.register_agent("MatchingAgent", agent.handle_a2a_message)
    msg = A2AMessage.create(COORDINATOR_NAME, "MatchingAgent", T.MATCHING_FIND_SOURCES_REQUEST,
                            {"requirement": {"request_id": 1, "blood_group": "A+"},
                             "inventories": [{"bank_id": 1, "blood_group": "A+", "units_available": 2}],
                             "donors": []}, "c5")
    reply = bus.send(msg)
    assert reply.message_type == T.MATCHING_SOURCES_FOUND_EVENT
    assert reply.payload["matches"][0]["source_id"] == 1
    assert len(bus.get_messages_for_correlation_id("c5")) == 2


# --------------------------------------------------------- notification agent
def test_notification_agent_handles_dispatch_messages():
    agent = NotificationAgent()
    plan = {"status": "FULLY_FULFILLED", "total_units": 1, "details": {"units_required": 1},
            "plan": [{"source_type": "BLOOD_BANK", "source_id": 1, "units": 1, "distance_km": 1.0}]}
    msg = A2AMessage.create(COORDINATOR_NAME, "NotificationAgent", T.NOTIFICATION_DISPATCH_REQUEST,
                            {"hospital_id": 1, "request_id": 7, "fulfillment_plan": plan, "hospital_name": "H"}, "c6")
    reply = agent.handle_a2a_message(msg)
    assert reply.message_type == T.NOTIFICATION_DISPATCHED_EVENT
    assert reply.payload["dispatched_count"] == 2


def test_notification_agent_rejects_wrong_or_malformed_messages():
    agent = NotificationAgent()
    wrong = A2AMessage.create("x", "NotificationAgent", T.MATCHING_FIND_SOURCES_REQUEST, {}, "c7")
    assert agent.handle_a2a_message(wrong).message_type == T.A2A_ERROR
    bad = A2AMessage.create("x", "NotificationAgent", T.NOTIFICATION_DISPATCH_REQUEST, {"request_id": 1}, "c8")
    assert agent.handle_a2a_message(bad).message_type == T.A2A_ERROR


# ------------------------------------------------------- legacy entry points
def test_orchestrate_a2a_flow_now_runs_through_the_coordinator(world):
    result = orchestrate_a2a_flow({"request_id": 101, "hospital_id": 1, "blood_group": "a+",
                                   "units_required": 1, "urgency": "critical"}, db=world,
                                  correlation_id="legacy-1")
    assert result["success"] and result["correlation_id"] == "legacy-1"
    assert result["final_message_type"] == T.LOCATION_DISTANCES_CALCULATED_EVENT
    assert result["result"]["candidates_count"] == len(result["result"]["candidates"]) > 0
    assert only_hub(result["trace"])
    assert world.query(BloodRequest).filter_by(request_id=101).count() == 0   # preview wrote nothing


def test_orchestrate_a2a_flow_reports_errors():
    result = orchestrate_a2a_flow({"request_id": 1, "hospital_id": 1, "blood_group": "??",
                                   "units_required": 1, "urgency": "LOW"})
    assert result["success"] is False and result["final_message_type"] == T.A2A_ERROR and result["error"]


def test_preview_with_a_made_up_request_id_ignores_a_real_closed_request(world):
    world.add(BloodRequest(request_id=999, hospital_id=1, blood_group="O+", units_required=1,
                           urgency="LOW", status="FULFILLED"))
    world.commit()
    res = CoordinatorAgent(db=world).coordinate(
        {"request_id": 999, "hospital_id": 1, "blood_group": "A+", "units_required": 1, "urgency": "LOW"},
        persist=False)
    assert res["success"] is True
