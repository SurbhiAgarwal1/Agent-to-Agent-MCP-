"""Tests for Communication Agent MCP Tools."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.mcp.server import create_extended_mcp_server


@pytest.fixture
def db_session():
    """Create in-memory SQLite database and seed test data."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    try:
        hosp = Hospital(hospital_id=1, name="Apex Trauma Center", latitude=28.6139, longitude=77.2090, address="New Delhi")
        donor = Donor(donor_id=1, name="John Doe", blood_group="A+", latitude=28.62, longitude=77.21, available=True)
        req = BloodRequest(request_id=10, hospital_id=1, blood_group="A+", units_required=1, urgency="HIGH")
        session.add_all([hosp, donor, req])
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_extended_mcp_server_includes_communication_tools():
    """Verify that extended MCP server registers all communication agent tools."""
    server = create_extended_mcp_server()
    tools = server.list_tools()
    tool_names = [t["name"] for t in tools]

    assert "dispatch_communication_outreach" in tool_names
    assert "record_communication_response" in tool_names
    assert "check_communication_status" in tool_names
    assert "trigger_communication_escalation" in tool_names
    assert len(tools) >= 8  # Core (4) + Communication (4) + Calling (2) = 10


def test_mcp_invoke_dispatch_and_response(db_session):
    """Verify executing communication tools via MCP server invocation interface."""
    server = create_extended_mcp_server()

    # 1. Invoke outreach tool
    outreach_res = server.invoke_tool(
        "dispatch_communication_outreach",
        {
            "hospital_id": 1,
            "request_id": 10,
            "urgency": "HIGH",
            "fulfillment_plan": {
                "status": "FULLY_FULFILLED",
                "total_units": 1,
                "plan": [{"source_type": "DONOR", "source_id": 1, "units": 1}],
            },
        },
        db=db_session,
    )
    assert outreach_res["isError"] is False
    out_payload = outreach_res["content"][0]["text"]
    import json
    data = json.loads(out_payload)
    assert data["success"] is True
    session_id = data["session_id"]

    # 2. Invoke check status tool
    status_res = server.invoke_tool(
        "check_communication_status",
        {"request_id": 10},
        db=db_session,
    )
    assert status_res["isError"] is False
    status_data = json.loads(status_res["content"][0]["text"])
    assert status_data["found"] is True
    assert status_data["session_id"] == session_id

    # 3. Invoke record response tool
    resp_res = server.invoke_tool(
        "record_communication_response",
        {
            "session_id": session_id,
            "recipient_type": "DONOR",
            "recipient_id": 1,
            "response_status": "CONFIRMED",
            "eta_minutes": 15,
        },
        db=db_session,
    )
    assert resp_res["isError"] is False
    resp_data = json.loads(resp_res["content"][0]["text"])
    assert resp_data["success"] is True
    assert resp_data["session_status"] == "ALL_CONFIRMED"
