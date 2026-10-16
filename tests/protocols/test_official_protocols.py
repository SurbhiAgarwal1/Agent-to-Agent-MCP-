"""Registration checks for services built with the official protocol SDKs."""

from app.agents.a2a.protocol_server import AGENT_APPS
from app.mcp.protocol_server import mcp


def test_every_agent_exposes_agent_card_and_jsonrpc_routes():
    for app in AGENT_APPS.values():
        paths = {route.path for route in app.routes}
        assert "/.well-known/agent-card.json" in paths
        assert "/a2a" in paths


def test_official_mcp_server_registers_domain_tools():
    tools = mcp._tool_manager.list_tools()
    assert {tool.name for tool in tools} == {
        "validate_blood_request",
        "find_blood_sources",
        "calculate_distance",
        "dispatch_notifications",
    }
