"""Tests for Agent-to-Agent (A2A) Communication protocol, MessageBus, and orchestration flow."""

import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent
from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.agents.a2a.bus import MessageBus
from app.agents.a2a.orchestration import orchestrate_a2a_flow


# Setup isolated in-memory test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """Create in-memory schema and seed test data."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        # Seed test hospital
        hosp = Hospital(
            hospital_id=1,
            name="Apex General Hospital",
            latitude=28.6139,
            longitude=77.2090,
            address="Connaught Place, New Delhi",
        )
        # Seed test blood bank
        bank = BloodBank(
            bank_id=1,
            name="Central Red Cross Blood Bank",
            latitude=28.6250,
            longitude=77.2150,
            address="Barakhamba Road, New Delhi",
        )
        session.add_all([hosp, bank])
        session.commit()

        # Seed inventory: bank 1 has 5 units of O+
        inv = BloodInventory(bank_id=1, blood_group="O+", units_available=5)
        # Seed donor: donor 1 has O+
        donor = Donor(
            donor_id=1,
            name="Alice Walker",
            blood_group="O+",
            latitude=28.6180,
            longitude=77.2110,
            available=True,
        )
        session.add_all([inv, donor])
        session.commit()

        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


# -----------------------------------------------------------------------------
# 1. Message Envelope Tests
# -----------------------------------------------------------------------------

def test_message_envelope_creation_and_defaults():
    """Verify A2AMessage instantiation, automatic UUID, and ISO timestamp generation."""
    corr_id = "test-corr-123"
    msg = A2AMessage.create(
        sender_agent="AgentA",
        receiver_agent="AgentB",
        message_type=A2AMessageType.REQUIREMENT_VALIDATE_REQUEST,
        payload={"sample": "data"},
        correlation_id=corr_id,
    )

    assert msg.message_id is not None
    assert len(msg.message_id) > 10
    assert msg.sender_agent == "AgentA"
    assert msg.receiver_agent == "AgentB"
    assert msg.message_type == A2AMessageType.REQUIREMENT_VALIDATE_REQUEST
    assert msg.payload == {"sample": "data"}
    assert msg.correlation_id == corr_id
    assert msg.timestamp is not None


def test_message_envelope_response_preserves_correlation_id():
    """Verify create_response reverses sender/receiver and preserves correlation_id."""
    original = A2AMessage.create(
        sender_agent="RequirementAgent",
        receiver_agent="MatchingAgent",
        message_type="PING",
        payload={"data": 1},
        correlation_id="corr-999",
    )

    resp = original.create_response(
        sender_agent="MatchingAgent",
        message_type="PONG",
        payload={"status": "ok"},
    )

    assert resp.sender_agent == "MatchingAgent"
    assert resp.receiver_agent == "RequirementAgent"
    assert resp.correlation_id == "corr-999"
    assert resp.message_id != original.message_id


def test_message_envelope_validation_error():
    """Verify Pydantic validation fails when required fields are missing."""
    with pytest.raises(ValidationError):
        # Missing receiver_agent and correlation_id
        A2AMessage(
            sender_agent="AgentA",
            message_type="TEST",
        )


# -----------------------------------------------------------------------------
# 2. In-Process Message Bus Tests
# -----------------------------------------------------------------------------

def test_message_bus_routing_success():
    """Verify bus routes message to registered handler and logs execution."""
    bus = MessageBus()

    def dummy_handler(msg: A2AMessage) -> A2AMessage:
        return msg.create_response(
            sender_agent="DummyAgent",
            message_type="ECHO_RESPONSE",
            payload={"echo": msg.payload},
        )

    bus.register_agent("DummyAgent", dummy_handler)

    msg = A2AMessage.create(
        sender_agent="Sender",
        receiver_agent="DummyAgent",
        message_type="ECHO_REQUEST",
        payload={"hello": "world"},
        correlation_id="corr-abc",
    )

    response = bus.send(msg)
    assert response.message_type == "ECHO_RESPONSE"
    assert response.payload == {"echo": {"hello": "world"}}
    assert response.correlation_id == "corr-abc"

    # Verify message trace log
    trace = bus.get_messages_for_correlation_id("corr-abc")
    assert len(trace) == 2
    assert trace[0].sender_agent == "Sender"
    assert trace[1].sender_agent == "DummyAgent"


def test_message_bus_unregistered_agent_returns_error():
    """Verify sending to an unregistered agent returns a structured A2A error without crashing."""
    bus = MessageBus()

    msg = A2AMessage.create(
        sender_agent="Sender",
        receiver_agent="NonExistentAgent",
        message_type="DO_SOMETHING",
        payload={},
        correlation_id="corr-err",
    )

    error_response = bus.send(msg)
    assert error_response.message_type == A2AMessageType.A2A_ERROR
    assert "not registered" in error_response.payload["error"]
    assert error_response.correlation_id == "corr-err"


# -----------------------------------------------------------------------------
# 3. Successful Round-Trip Flow (Requirement -> Matching -> Location)
# -----------------------------------------------------------------------------

def test_successful_round_trip_a2a_orchestration(db_session):
    """Verify complete sequential A2A communication flow across all 3 agents."""
    request_data = {
        "request_id": 101,
        "hospital_id": 1,
        "blood_group": "o+",
        "units_required": 2,
        "urgency": "critical",
    }

    result = orchestrate_a2a_flow(request_data, db=db_session, correlation_id="test-corr-flow-101")

    assert result["success"] is True
    assert result["correlation_id"] == "test-corr-flow-101"
    assert result["final_message_type"] == A2AMessageType.LOCATION_DISTANCES_CALCULATED_EVENT

    payload = result["result"]
    assert payload["requirement"]["blood_group"] == "O+"
    assert payload["requirement"]["valid"] is True
    assert payload["candidates_count"] > 0

    # Ensure candidates have distance and travel time calculated by LocationAgent
    candidates = payload["candidates"]
    assert len(candidates) >= 2  # 1 blood bank + 1 donor
    first_candidate = candidates[0]
    assert "distance_km" in first_candidate
    assert "estimated_time" in first_candidate
    assert isinstance(first_candidate["distance_km"], float)
    assert first_candidate["distance_km"] > 0.0


# -----------------------------------------------------------------------------
# 4. Correlation ID Consistency Across the Flow
# -----------------------------------------------------------------------------

def test_correlation_id_consistency_across_flow(db_session):
    """Verify every message in the A2A dispatch pipeline preserves the exact correlation_id."""
    fixed_corr_id = f"flow-audit-{uuid.uuid4().hex[:6]}"
    request_data = {
        "request_id": 50,
        "hospital_id": 1,
        "blood_group": "O+",
        "units_required": 1,
        "urgency": "HIGH",
    }

    bus = MessageBus()
    result = orchestrate_a2a_flow(request_data, db=db_session, bus=bus, correlation_id=fixed_corr_id)

    assert result["success"] is True
    assert result["correlation_id"] == fixed_corr_id

    # Check all messages logged on the bus for this correlation ID
    logged_messages = bus.get_messages_for_correlation_id(fixed_corr_id)
    assert len(logged_messages) >= 4  # Initial -> Req -> Match -> Loc

    for msg in logged_messages:
        assert msg.correlation_id == fixed_corr_id, f"Message {msg.message_id} broke correlation ID chain"


# -----------------------------------------------------------------------------
# 5. Malformed Message Handling
# -----------------------------------------------------------------------------

def test_malformed_message_requirement_agent_invalid_payload():
    """Verify RequirementAgent returns structured error when payload is not a dictionary."""
    agent = RequirementAgent()
    malformed_msg = A2AMessage(
        message_id="m1",
        sender_agent="Test",
        receiver_agent="RequirementAgent",
        message_type=A2AMessageType.REQUIREMENT_VALIDATE_REQUEST,
        payload={"hospital_id": 1, "blood_group": "INVALID_XYZ", "units_required": -5},
        correlation_id="err-req",
    )

    err_resp = agent.handle_a2a_message(malformed_msg)
    assert err_resp.message_type == A2AMessageType.A2A_ERROR
    assert "validation failed" in err_resp.payload["error"].lower()
    assert err_resp.correlation_id == "err-req"


def test_malformed_message_matching_agent_missing_blood_group():
    """Verify MatchingAgent returns structured error when payload is missing requirement info."""
    agent = MatchingAgent()
    malformed_msg = A2AMessage(
        message_id="m2",
        sender_agent="Test",
        receiver_agent="MatchingAgent",
        message_type=A2AMessageType.MATCHING_FIND_SOURCES_REQUEST,
        payload={"requirement": {}},  # Missing blood_group
        correlation_id="err-match",
    )

    err_resp = agent.handle_a2a_message(malformed_msg)
    assert err_resp.message_type == A2AMessageType.A2A_ERROR
    assert "missing requirement or blood_group" in err_resp.payload["error"].lower()


def test_malformed_message_location_agent_invalid_coords():
    """Verify LocationAgent returns structured error when coordinates are missing or invalid."""
    agent = LocationAgent()
    malformed_msg = A2AMessage(
        message_id="m3",
        sender_agent="Test",
        receiver_agent="LocationAgent",
        message_type=A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST,
        payload={"hospital_coords": {"latitude": "NOT_A_FLOAT", "longitude": 77.0}},
        correlation_id="err-loc",
    )

    err_resp = agent.handle_a2a_message(malformed_msg)
    assert err_resp.message_type == A2AMessageType.A2A_ERROR
    assert "invalid hospital coordinates" in err_resp.payload["error"].lower()


# -----------------------------------------------------------------------------
# 6. Direct Call Regression Tests (Ensuring Direct Calls Still Function)
# -----------------------------------------------------------------------------

def test_direct_calls_no_regression(db_session):
    """Verify that all three agents continue to function identically when called directly."""
    # 1. RequirementAgent direct call
    req_agent = RequirementAgent(db=db_session)
    req_res = req_agent.process({
        "request_id": 10,
        "hospital_id": 1,
        "blood_group": "b+",
        "units_required": 3,
        "urgency": "medium",
    })
    assert req_res["valid"] is True
    assert req_res["blood_group"] == "B+"

    # 2. MatchingAgent direct call
    match_agent = MatchingAgent(db=db_session)
    match_res = match_agent.find_matches(req_res)
    assert "matches" in match_res
    assert isinstance(match_res["matches"], list)

    # 3. LocationAgent direct call
    loc_agent = LocationAgent()
    loc_res = loc_agent.calculate_distance(
        origin_lat=28.6139,
        origin_lon=77.2090,
        dest_lat=28.6250,
        dest_lon=77.2150,
        include_eta=True,
    )
    assert loc_res["distance_km"] > 0.0
    assert "estimated_time" in loc_res
