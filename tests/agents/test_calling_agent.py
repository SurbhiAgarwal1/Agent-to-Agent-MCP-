"""Unit and integration tests for Calling Agent, IVR voice dispatch, and telephony workflows."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.calling import CallSession
from app.models.communication import CommunicationSession
from app.agents.calling_agent import CallingAgent
from app.agents.communication_agent import CommunicationAgent
from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.services.voice_providers import ConsoleVoiceProvider


@pytest.fixture
def db_session():
    """Create isolated in-memory SQLite database and seed test entities."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    try:
        hosp = Hospital(
            hospital_id=1,
            name="Max Super Speciality Hospital",
            latitude=28.5284,
            longitude=77.2188,
            address="Saket, New Delhi",
        )
        donor = Donor(
            donor_id=101,
            name="Rahul Sharma",
            blood_group="B+",
            latitude=28.5300,
            longitude=77.2200,
            available=True,
        )
        req = BloodRequest(
            request_id=5,
            hospital_id=1,
            blood_group="B+",
            units_required=2,
            urgency="CRITICAL",
        )
        session.add_all([hosp, donor, req])
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_dispatch_call_persists_session_and_tts(db_session):
    """Verify that dispatching a voice call creates CallSession with synthesized TTS."""
    provider = ConsoleVoiceProvider()
    agent = CallingAgent(db=db_session, voice_provider=provider)

    result = agent.dispatch_call(
        request_id=5,
        recipient_type="DONOR",
        recipient_id=101,
        recipient_phone="+919876543210",
        recipient_name="Rahul Sharma",
        hospital_id=1,
        hospital_name="Max Super Speciality Hospital",
        blood_group="B+",
        units_required=2,
        urgency="CRITICAL",
    )

    assert result["success"] is True
    assert "call_id" in result
    assert result["status"] == "INITIATED"
    assert "Max Super Speciality Hospital" in result["tts_script"]
    assert "Press 1 to CONFIRM" in result["tts_script"]

    # Verify database persistence
    session_row = db_session.query(CallSession).filter(CallSession.call_id == result["call_id"]).first()
    assert session_row is not None
    assert session_row.request_id == 5
    assert session_row.recipient_id == 101
    assert session_row.recipient_phone == "+919876543210"
    assert session_row.response_status == "NO_RESPONSE"


def test_process_callback_dtmf_confirm_and_delay(db_session):
    """Verify IVR touch-tone parsing for Confirm (1), Decline (2), and Delay (3)."""
    agent = CallingAgent(db=db_session)

    # 1. Dispatch call
    call = agent.dispatch_call(
        request_id=5,
        recipient_type="DONOR",
        recipient_id=101,
        recipient_phone="+919876543210",
    )
    call_id = call["call_id"]

    # 2. Simulate IVR DTMF '1' (Confirm)
    res = agent.process_callback(call_id=call_id, call_status="COMPLETED", digits_pressed="1", duration_seconds=35)
    assert res["success"] is True
    assert res["response_status"] == "CONFIRMED"
    assert res["digits_pressed"] == "1"

    row = db_session.query(CallSession).filter(CallSession.call_id == call_id).first()
    assert row.status == "COMPLETED"
    assert row.response_status == "CONFIRMED"
    assert row.duration_seconds == 35
    assert row.completed_at is not None

    # 3. Simulate another call with DTMF '3' (Delay)
    call2 = agent.dispatch_call(
        request_id=5,
        recipient_type="DONOR",
        recipient_id=101,
        recipient_phone="+919876543210",
    )
    res2 = agent.process_callback(call_id=call2["call_id"], call_status="COMPLETED", digits_pressed="3", duration_seconds=20)
    assert res2["response_status"] == "DELAYED"


def test_voice_callback_syncs_with_communication_session(db_session):
    """Verify that voice IVR confirmation syncs directly to active CommunicationSession."""
    comm_agent = CommunicationAgent(db=db_session)
    calling_agent = CallingAgent(db=db_session)

    # 1. Initialize outreach communication session
    plan = {
        "status": "FULLY_FULFILLED",
        "total_units": 1,
        "plan": [{"source_type": "DONOR", "source_id": 101, "units": 1}],
    }
    comm_outreach = comm_agent.initiate_outreach(hospital_id=1, request_id=5, fulfillment_plan=plan, urgency="HIGH")
    assert comm_outreach["success"] is True

    # 2. Dispatch emergency voice call
    call = calling_agent.dispatch_call(
        request_id=5,
        recipient_type="DONOR",
        recipient_id=101,
        recipient_phone="+919876543210",
    )

    # 3. Process voice touchtone '1' (Confirmed)
    calling_agent.process_callback(call_id=call["call_id"], call_status="COMPLETED", digits_pressed="1", duration_seconds=42)

    # 4. Verify communication session auto-updated to ALL_CONFIRMED
    sess = db_session.query(CommunicationSession).filter(CommunicationSession.request_id == 5).first()
    assert sess.confirmed_count == 1
    assert sess.pending_count == 0
    assert sess.status == "ALL_CONFIRMED"


def test_calling_stats_calculation(db_session):
    """Verify telephony KPI metrics computation."""
    agent = CallingAgent(db=db_session)

    # Call 1: Confirmed (40s)
    c1 = agent.dispatch_call(request_id=5, recipient_type="DONOR", recipient_id=101, recipient_phone="+919876543210")
    agent.process_callback(call_id=c1["call_id"], call_status="COMPLETED", digits_pressed="1", duration_seconds=40)

    # Call 2: Declined (20s)
    c2 = agent.dispatch_call(request_id=5, recipient_type="DONOR", recipient_id=101, recipient_phone="+919876543210")
    agent.process_callback(call_id=c2["call_id"], call_status="COMPLETED", digits_pressed="2", duration_seconds=20)

    # Call 3: No Answer (0s)
    c3 = agent.dispatch_call(request_id=5, recipient_type="DONOR", recipient_id=101, recipient_phone="+919876543210")
    agent.process_callback(call_id=c3["call_id"], call_status="NO_ANSWER", duration_seconds=0)

    stats = agent.service.get_telephony_stats()
    assert stats["total_calls"] == 3
    assert stats["completed_calls"] == 2
    assert stats["confirmed_count"] == 1
    assert stats["declined_count"] == 1
    assert stats["no_answer_count"] == 1
    assert stats["avg_duration_seconds"] == 30.0
    assert stats["voice_confirmation_rate_pct"] == 50.0


def test_calling_agent_a2a_protocol_exchange(db_session):
    """Verify CallingAgent handles A2A messages: dispatch, callback, and status poll."""
    agent = CallingAgent(db=db_session)

    # 1. CALLING_DISPATCH_REQUEST
    dispatch_msg = A2AMessage.create(
        sender_agent="CoordinatorAgent",
        receiver_agent="CallingAgent",
        message_type=A2AMessageType.CALLING_DISPATCH_REQUEST,
        payload={
            "request_id": 5,
            "recipient_type": "DONOR",
            "recipient_id": 101,
            "recipient_phone": "+919876543210",
            "recipient_name": "Rahul Sharma",
            "urgency": "CRITICAL",
        },
        correlation_id="corr-call-101",
    )
    dispatch_resp = agent.handle_a2a_message(dispatch_msg)
    assert dispatch_resp.message_type == A2AMessageType.CALLING_DISPATCH_RESULT
    assert dispatch_resp.payload["success"] is True
    call_id = dispatch_resp.payload["call_id"]

    # 2. CALLING_CALLBACK_EVENT
    callback_msg = A2AMessage.create(
        sender_agent="TelephonyBridge",
        receiver_agent="CallingAgent",
        message_type=A2AMessageType.CALLING_CALLBACK_EVENT,
        payload={
            "call_id": call_id,
            "call_status": "COMPLETED",
            "digits_pressed": "1",
            "duration_seconds": 38,
        },
        correlation_id="corr-call-102",
    )
    cb_resp = agent.handle_a2a_message(callback_msg)
    assert cb_resp.message_type == "CALLING_STATUS_UPDATED"
    assert cb_resp.payload["response_status"] == "CONFIRMED"

    # 3. CALLING_STATUS_POLL
    poll_msg = A2AMessage.create(
        sender_agent="CoordinatorAgent",
        receiver_agent="CallingAgent",
        message_type=A2AMessageType.CALLING_STATUS_POLL,
        payload={"request_id": 5},
        correlation_id="corr-call-103",
    )
    poll_resp = agent.handle_a2a_message(poll_msg)
    assert poll_resp.message_type == "CALLING_STATUS_REPORT"
    assert poll_resp.payload["call_count"] >= 1
