"""Tests for Calling Agent MCP Tools."""

import json
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


def test_extended_mcp_server_includes_calling_tools():
    """Verify that extended MCP server registers all calling agent tools."""
    server = create_extended_mcp_server()
    tools = server.list_tools()
    tool_names = [t["name"] for t in tools]

    assert "dispatch_emergency_call" in tool_names
    assert "check_call_session_status" in tool_names
    assert len(tools) >= 10  # 4 core + 4 comm + 2 calling


def test_mcp_invoke_calling_tools(db_session):
    """Verify invoking calling agent tools via MCP server."""
    server = create_extended_mcp_server()

    # 1. Dispatch emergency call
    dispatch_res = server.invoke_tool(
        "dispatch_emergency_call",
        {
            "request_id": 10,
            "recipient_type": "DONOR",
            "recipient_id": 1,
            "recipient_phone": "+919876543210",
            "recipient_name": "John Doe",
            "hospital_name": "Apex Trauma Center",
            "blood_group": "A+",
            "units_required": 1,
            "urgency": "HIGH",
        },
        db=db_session,
    )
    assert dispatch_res["isError"] is False
    data = json.loads(dispatch_res["content"][0]["text"])
    assert data["success"] is True
    assert data["status"] == "INITIATED"
    call_id = data["call_id"]

    # 2. Check call status
    status_res = server.invoke_tool(
        "check_call_session_status",
        {"request_id": 10},
        db=db_session,
    )
    assert status_res["isError"] is False
    status_data = json.loads(status_res["content"][0]["text"])
    assert status_data["request_id"] == 10
    assert status_data["call_count"] == 1
    assert status_data["calls"][0]["call_id"] == call_id
