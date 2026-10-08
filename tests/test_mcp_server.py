"""Tests for Model Context Protocol (MCP) Server and Tools."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent
from app.mcp.server import (
    MCPServer,
    create_default_mcp_server,
    default_mcp_server,
)
from app.main import app

# In-memory SQLite with StaticPool for test isolation
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
            name="Metro Emergency Hospital",
            latitude=28.6139,
            longitude=77.2090,
            address="Barakhamba Road, New Delhi",
        )
        # Seed test blood bank
        bank = BloodBank(
            bank_id=1,
            name="Red Cross Main Vault",
            latitude=28.6200,
            longitude=77.2150,
            address="Connaught Place, New Delhi",
        )
        session.add_all([hosp, bank])
        session.commit()

        # Seed inventory
        inv = BloodInventory(bank_id=1, blood_group="A+", units_available=4)
        donor = Donor(
            donor_id=1,
            name="Bob Smith",
            blood_group="A+",
            latitude=28.6180,
            longitude=77.2100,
            available=True,
        )
        session.add_all([inv, donor])
        session.commit()

        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


# -----------------------------------------------------------------------------
# 1. Tool Registration and Listing Tests
# -----------------------------------------------------------------------------

def test_mcp_server_tool_registration_and_listing():
    """Verify default MCP server registers and lists all three core tools."""
    server = create_default_mcp_server()
    tools = server.list_tools()

    assert len(tools) == 3
    tool_names = [t["name"] for t in tools]
    assert "validate_blood_request" in tool_names
    assert "find_blood_sources" in tool_names
    assert "calculate_distance" in tool_names

    # Check schema completeness for each tool
    for t in tools:
        assert "description" in t
        assert "inputSchema" in t
        assert "outputSchema" in t
        assert t["inputSchema"]["type"] == "object"


def test_mcp_server_describe_tool():
    """Verify describe_tool returns schema for existing tool and None for unknown."""
    server = create_default_mcp_server()

    tool_meta = server.describe_tool("validate_blood_request")
    assert tool_meta is not None
    assert tool_meta["name"] == "validate_blood_request"
    assert "required" in tool_meta["inputSchema"]

    assert server.describe_tool("non_existent_tool") is None


# -----------------------------------------------------------------------------
# 2. Input Validation Tests
# -----------------------------------------------------------------------------

def test_mcp_tool_missing_required_arguments():
    """Verify invoking a tool with missing required arguments returns isError=True."""
    server = create_default_mcp_server()

    # Missing blood_group, units_required, urgency
    res = server.invoke_tool("validate_blood_request", {"hospital_id": 1})
    assert res["isError"] is True
    assert "Missing required arguments" in res["error"]


def test_mcp_tool_non_dict_arguments():
    """Verify invoking a tool with non-dict arguments returns isError=True."""
    server = create_default_mcp_server()
    res = server.invoke_tool("calculate_distance", "not_a_dict")  # type: ignore
    assert res["isError"] is True


def test_mcp_tool_not_found():
    """Verify invoking an unrecognised tool returns isError=True."""
    server = create_default_mcp_server()
    res = server.invoke_tool("unknown_tool", {})
    assert res["isError"] is True
    assert "not found" in res["error"]


# -----------------------------------------------------------------------------
# 3. Successful Tool Invocations
# -----------------------------------------------------------------------------

def test_mcp_tool_validate_blood_request_success(db_session):
    """Verify successful invocation of validate_blood_request tool."""
    server = create_default_mcp_server()
    args = {
        "hospital_id": 1,
        "blood_group": "a+",
        "units_required": 2,
        "urgency": "critical",
    }

    res = server.invoke_tool("validate_blood_request", args, db=db_session)
    assert res["isError"] is False
    assert res["data"]["valid"] is True
    assert res["data"]["blood_group"] == "A+"
    assert res["data"]["urgency"] == "CRITICAL"


def test_mcp_tool_find_blood_sources_success(db_session):
    """Verify successful invocation of find_blood_sources tool."""
    server = create_default_mcp_server()
    args = {"blood_group": "A+", "request_id": 1}

    res = server.invoke_tool("find_blood_sources", args, db=db_session)
    assert res["isError"] is False
    assert len(res["data"]["matches"]) >= 2
    assert "matches" in res["data"]


def test_mcp_tool_calculate_distance_success():
    """Verify successful invocation of calculate_distance tool."""
    server = create_default_mcp_server()
    args = {
        "origin_latitude": 28.6139,
        "origin_longitude": 77.2090,
        "destination_latitude": 28.6250,
        "destination_longitude": 77.2150,
        "include_eta": True,
    }

    res = server.invoke_tool("calculate_distance", args)
    assert res["isError"] is False
    assert res["data"]["distance_km"] > 0.0
    assert "estimated_time" in res["data"]


# -----------------------------------------------------------------------------
# 4. Behavioral Parity (No Behavior Drift from Agents)
# -----------------------------------------------------------------------------

def test_mcp_tools_no_behavior_drift(db_session):
    """Verify MCP tools return identical results to direct agent invocations."""
    server = create_default_mcp_server()

    # 1. validate_blood_request vs RequirementAgent
    val_args = {"request_id": 1, "hospital_id": 1, "blood_group": "o+", "units_required": 3, "urgency": "high"}
    agent_val = RequirementAgent(db=db_session).process(val_args)
    tool_val = server.invoke_tool("validate_blood_request", val_args, db=db_session)
    assert tool_val["data"] == agent_val

    # 2. find_blood_sources vs MatchingAgent
    match_args = {"blood_group": "A+", "request_id": 1}
    agent_match = MatchingAgent(db=db_session).find_matches(match_args)
    tool_match = server.invoke_tool("find_blood_sources", match_args, db=db_session)
    assert tool_match["data"] == agent_match

    # 3. calculate_distance vs LocationAgent
    dist_args = {
        "origin_latitude": 28.6139,
        "origin_longitude": 77.2090,
        "destination_latitude": 28.7000,
        "destination_longitude": 77.2500,
        "include_eta": True,
    }
    agent_dist = LocationAgent().process(dist_args, include_eta=True)
    tool_dist = server.invoke_tool("calculate_distance", dist_args)
    assert tool_dist["data"] == agent_dist


# -----------------------------------------------------------------------------
# 5. Local HTTP Transport Tests
# -----------------------------------------------------------------------------

def test_mcp_http_endpoints(db_session):
    """Verify FastAPI HTTP endpoints for listing and invoking MCP tools."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. GET /api/v1/mcp/tools
    res_list = client.get("/api/v1/mcp/tools")
    assert res_list.status_code == 200
    data_list = res_list.json()
    assert len(data_list["tools"]) == 3

    # 2. GET /api/v1/mcp/tools/{tool_name}
    res_desc = client.get("/api/v1/mcp/tools/calculate_distance")
    assert res_desc.status_code == 200
    assert res_desc.json()["name"] == "calculate_distance"

    # 3. POST /api/v1/mcp/tools/{tool_name}/invoke
    invoke_payload = {
        "arguments": {
            "origin_latitude": 28.6139,
            "origin_longitude": 77.2090,
            "destination_latitude": 28.6250,
            "destination_longitude": 77.2150,
        }
    }
    res_invoke = client.post("/api/v1/mcp/tools/calculate_distance/invoke", json=invoke_payload)
    assert res_invoke.status_code == 200
    assert res_invoke.json()["data"]["distance_km"] > 0.0

    app.dependency_overrides.clear()
