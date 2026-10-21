"""Unit and integration tests for the Communication Agent, interactive outreach, and A2A protocol."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.communication import CommunicationSession, CommunicationMessage
from app.agents.communication_agent import CommunicationAgent
from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.services.notification_providers.console_provider import ConsoleNotificationProvider


@pytest.fixture
def db_session():
    """Create in-memory schema and seed test data."""
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
            name="Apollo Emergency Hospital",
            latitude=28.6139,
            longitude=77.2090,
            address="Connaught Place, New Delhi",
        )
        bank = BloodBank(
            bank_id=1,
            name="Central Red Cross Blood Bank",
            latitude=28.6250,
            longitude=77.2150,
            address="Barakhamba Road, New Delhi",
        )
        donor = Donor(
            donor_id=1,
            name="Sarah Jenkins",
            blood_group="O+",
            latitude=28.6180,
            longitude=77.2110,
            available=True,
        )
        req = BloodRequest(
            request_id=1,
            hospital_id=1,
            blood_group="O+",
            units_required=2,
            urgency="CRITICAL",
        )
        session.add_all([hosp, bank, donor, req])
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_initiate_outreach_creates_session_and_messages(db_session):
    """Verify that initiate_outreach initializes a tracked session and dispatches target messages."""
    console = ConsoleNotificationProvider()
    agent = CommunicationAgent(db=db_session, provider=console)

    plan = {
        "status": "FULLY_FULFILLED",
        "total_units": 2,
        "plan": [
            {"source_type": "BLOOD_BANK", "source_id": 1, "units": 1, "distance_km": 2.5, "estimated_time": "8 mins"},
            {"source_type": "DONOR", "source_id": 1, "units": 1, "distance_km": 1.2, "estimated_time": "5 mins"},
        ],
        "details": {"units_required": 2, "units_shortage": 0},
    }

    res = agent.initiate_outreach(
        hospital_id=1,
        request_id=1,
        fulfillment_plan=plan,
        urgency="CRITICAL",
        hospital_name="Apollo Emergency Hospital",
        custom_message="Immediate transfusion required for trauma surgery.",
    )

    assert res["success"] is True
    assert res["request_id"] == 1
    assert res["urgency"] == "CRITICAL"
    assert res["sla_minutes"] == 15  # CRITICAL SLA is 15 mins
    assert res["dispatched_count"] == 3  # 1 hospital + 2 sources

    # Verify session persisted
    sess = db_session.query(CommunicationSession).filter(CommunicationSession.request_id == 1).first()
    assert sess is not None
    assert sess.status == "ACTIVE"
    assert sess.pending_count == 2
    assert sess.confirmed_count == 0

    # Verify messages persisted
    msgs = db_session.query(CommunicationMessage).filter(CommunicationMessage.session_id == sess.session_id).all()
    assert len(msgs) == 3


def test_urgency_adapts_sla_and_channels(db_session):
    """Verify SLA calculation and delivery channel selection adapted to urgency."""
    agent = CommunicationAgent(db=db_session)

    # Critical SLA = 15 mins, channels = SMS + CONSOLE
    crit_sla, _ = agent.service.calculate_sla_deadline("CRITICAL")
    assert crit_sla == 15
    assert "SMS" in agent.service.select_channels_for_urgency("CRITICAL")

    # High SLA = 30 mins
    high_sla, _ = agent.service.calculate_sla_deadline("HIGH")
    assert high_sla == 30

    # Medium SLA = 60 mins, channels = EMAIL + CONSOLE
    med_sla, _ = agent.service.calculate_sla_deadline("MEDIUM")
    assert med_sla == 60
    assert "EMAIL" in agent.service.select_channels_for_urgency("MEDIUM")


def test_record_donor_response_confirmation_and_completion(db_session):
    """Verify recording donor RSVP updates session aggregates and marks completion."""
    agent = CommunicationAgent(db=db_session)
    plan = {
        "status": "FULLY_FULFILLED",
        "total_units": 1,
        "plan": [
            {"source_type": "DONOR", "source_id": 1, "units": 1, "distance_km": 1.2},
        ],
    }
    outreach = agent.initiate_outreach(hospital_id=1, request_id=1, fulfillment_plan=plan, urgency="HIGH")
    session_id = outreach["session_id"]

    # Record donor confirmation with ETA
    resp = agent.record_response(
        session_id=session_id,
        recipient_type="DONOR",
        recipient_id=1,
        response_status="CONFIRMED",
        response_notes="On my way to Apollo Hospital now",
        eta_minutes=20,
    )

    assert resp["success"] is True
    assert resp["session_status"] == "ALL_CONFIRMED"
    assert resp["confirmed_count"] == 1
    assert resp["pending_count"] == 0

    # Check database state
    sess = db_session.query(CommunicationSession).filter(CommunicationSession.session_id == session_id).first()
    assert sess.status == "ALL_CONFIRMED"


def test_record_donor_decline_triggers_escalation(db_session):
    """Verify that when prospective sources decline, session state transitions to ESCALATED."""
    agent = CommunicationAgent(db=db_session)
    plan = {
        "status": "PARTIALLY_FULFILLED",
        "total_units": 1,
        "plan": [
            {"source_type": "DONOR", "source_id": 1, "units": 1},
        ],
    }
    outreach = agent.initiate_outreach(hospital_id=1, request_id=1, fulfillment_plan=plan, urgency="MEDIUM")
    session_id = outreach["session_id"]

    resp = agent.record_response(
        session_id=session_id,
        recipient_type="DONOR",
        recipient_id=1,
        response_status="DECLINED",
        response_notes="Out of town until next week",
    )

    assert resp["success"] is True
    assert resp["session_status"] == "ESCALATED"


def test_sla_breach_and_manual_escalation(db_session):
    """Verify that expired SLA automatically marks timed out sessions as ESCALATED."""
    agent = CommunicationAgent(db=db_session)
    plan = {
        "status": "FULLY_FULFILLED",
        "total_units": 1,
        "plan": [{"source_type": "DONOR", "source_id": 1, "units": 1}],
    }
    outreach = agent.initiate_outreach(hospital_id=1, request_id=1, fulfillment_plan=plan, urgency="CRITICAL")
    session_id = outreach["session_id"]

    # Manually backdate SLA expiry to simulate SLA breach
    sess = db_session.query(CommunicationSession).filter(CommunicationSession.session_id == session_id).first()
    sess.sla_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    # Trigger escalation evaluation
    escalated = agent.evaluate_escalations()
    assert len(escalated) == 1
    assert escalated[0]["session_id"] == session_id
    assert escalated[0]["escalated"] is True
    assert "SLA timeout" in escalated[0]["escalation_reason"]

    # Verify session marked as escalated
    db_session.refresh(sess)
    assert sess.is_escalated is True
    assert sess.status == "ESCALATED"


def test_communication_agent_a2a_outreach_flow(db_session):
    """Verify CommunicationAgent processes A2AMessageType.COMMUNICATION_OUTREACH_REQUEST."""
    agent = CommunicationAgent(db=db_session)
    msg = A2AMessage.create(
        sender_agent="CoordinatorAgent",
        receiver_agent="CommunicationAgent",
        message_type=A2AMessageType.COMMUNICATION_OUTREACH_REQUEST,
        payload={
            "hospital_id": 1,
            "request_id": 1,
            "urgency": "HIGH",
            "fulfillment_plan": {
                "status": "FULLY_FULFILLED",
                "total_units": 1,
                "plan": [{"source_type": "BLOOD_BANK", "source_id": 1, "units": 1}],
            },
        },
        correlation_id="corr-comm-001",
    )

    reply = agent.handle_a2a_message(msg)
    assert reply.message_type == A2AMessageType.COMMUNICATION_OUTREACH_DISPATCHED
    assert reply.correlation_id == "corr-comm-001"
    assert reply.payload["success"] is True
    assert "session_id" in reply.payload


def test_communication_agent_backward_compatibility_notification(db_session):
    """Verify CommunicationAgent transparently handles legacy NOTIFICATION_DISPATCH_REQUEST."""
    agent = CommunicationAgent(db=db_session)
    msg = A2AMessage.create(
        sender_agent="CoordinatorAgent",
        receiver_agent="CommunicationAgent",
        message_type=A2AMessageType.NOTIFICATION_DISPATCH_REQUEST,
        payload={
            "hospital_id": 1,
            "request_id": 1,
            "fulfillment_plan": {
                "status": "FULLY_FULFILLED",
                "total_units": 1,
                "plan": [{"source_type": "BLOOD_BANK", "source_id": 1, "units": 1}],
            },
        },
        correlation_id="corr-legacy-001",
    )

    reply = agent.handle_a2a_message(msg)
    assert reply.message_type == A2AMessageType.NOTIFICATION_DISPATCHED_EVENT
    assert reply.payload["success"] is True
    assert reply.payload["dispatched_count"] >= 1
