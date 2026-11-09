"""Minimal Model Context Protocol (MCP) Server for Blood Donation Matching System."""

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session

from app.mcp.tools.requirement_tool import (
    TOOL_NAME as VALIDATE_TOOL_NAME,
    TOOL_DESCRIPTION as VALIDATE_TOOL_DESC,
    INPUT_SCHEMA as VALIDATE_INPUT_SCHEMA,
    OUTPUT_SCHEMA as VALIDATE_OUTPUT_SCHEMA,
    handle_validate_blood_request,
)
from app.mcp.tools.matching_tool import (
    TOOL_NAME as MATCHING_TOOL_NAME,
    TOOL_DESCRIPTION as MATCHING_TOOL_DESC,
    INPUT_SCHEMA as MATCHING_INPUT_SCHEMA,
    OUTPUT_SCHEMA as MATCHING_OUTPUT_SCHEMA,
    handle_find_blood_sources,
)
from app.mcp.tools.location_tool import (
    TOOL_NAME as LOCATION_TOOL_NAME,
    TOOL_DESCRIPTION as LOCATION_TOOL_DESC,
    INPUT_SCHEMA as LOCATION_INPUT_SCHEMA,
    OUTPUT_SCHEMA as LOCATION_OUTPUT_SCHEMA,
    handle_calculate_distance,
)
from app.mcp.tools.notification_tool import (
    TOOL_NAME as NOTIFICATION_TOOL_NAME,
    TOOL_DESCRIPTION as NOTIFICATION_TOOL_DESC,
    INPUT_SCHEMA as NOTIFICATION_INPUT_SCHEMA,
    OUTPUT_SCHEMA as NOTIFICATION_OUTPUT_SCHEMA,
    handle_dispatch_notifications,
)


@dataclass
class MCPTool:
    """Represents an executable MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any], Optional[Session]], Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool definition to standard MCP schema dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }


class MCPServer:
    """Model Context Protocol (MCP) Server exposing agent tools to external LLMs/orchestrators."""

    def __init__(self, server_name: str = "blood-donation-mcp-server", version: str = "1.0.0"):
        self.server_name = server_name
        self.version = version
        self._tools: Dict[str, MCPTool] = {}

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool definition on the server."""
        self._tools[tool.name] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools and their schemas."""
        return [tool.to_dict() for tool in self._tools.values()]

    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve schema metadata for a specific tool."""
        tool = self._tools.get(tool_name)
        return tool.to_dict() if tool else None

    def validate_arguments(self, tool: MCPTool, arguments: Dict[str, Any]) -> None:
        """Validate input arguments against the tool's required JSON schema properties."""
        if not isinstance(arguments, dict):
            raise ValueError(f"Arguments for tool '{tool.name}' must be a dictionary.")

        required_fields = tool.input_schema.get("required", [])
        missing_fields = [f for f in required_fields if f not in arguments]
        if missing_fields:
            raise ValueError(
                f"Missing required arguments for tool '{tool.name}': {', '.join(missing_fields)}"
            )

    def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Invoke an MCP tool with provided arguments and return standard MCP response."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool '{tool_name}' not found."}],
                "error": f"Tool '{tool_name}' not found on server '{self.server_name}'.",
            }

        try:
            self.validate_arguments(tool, arguments)
            result = tool.handler(arguments, db=db)
            return {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(result)}],
                "data": result,
            }
        except Exception as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool invocation error: {str(exc)}"}],
                "error": str(exc),
            }


def create_default_mcp_server() -> MCPServer:
    """Factory creating an MCPServer pre-configured with all blood donation agent tools."""
    server = MCPServer()

    # Tool 1: validate_blood_request
    server.register_tool(
        MCPTool(
            name=VALIDATE_TOOL_NAME,
            description=VALIDATE_TOOL_DESC,
            input_schema=VALIDATE_INPUT_SCHEMA,
            output_schema=VALIDATE_OUTPUT_SCHEMA,
            handler=handle_validate_blood_request,
        )
    )

    # Tool 2: find_blood_sources
    server.register_tool(
        MCPTool(
            name=MATCHING_TOOL_NAME,
            description=MATCHING_TOOL_DESC,
            input_schema=MATCHING_INPUT_SCHEMA,
            output_schema=MATCHING_OUTPUT_SCHEMA,
            handler=handle_find_blood_sources,
        )
    )

    # Tool 3: calculate_distance
    server.register_tool(
        MCPTool(
            name=LOCATION_TOOL_NAME,
            description=LOCATION_TOOL_DESC,
            input_schema=LOCATION_INPUT_SCHEMA,
            output_schema=LOCATION_OUTPUT_SCHEMA,
            handler=handle_calculate_distance,
        )
    )

    server.register_tool(
        MCPTool(
            name=NOTIFICATION_TOOL_NAME,
            description=NOTIFICATION_TOOL_DESC,
            input_schema=NOTIFICATION_INPUT_SCHEMA,
            output_schema=NOTIFICATION_OUTPUT_SCHEMA,
            handler=handle_dispatch_notifications,
        )
    )

    return server


def register_communication_tools(server: MCPServer) -> MCPServer:
    """Register CommunicationAgent tools onto an MCPServer instance."""
    from app.mcp.tools.communication_tool import (
        OUTREACH_TOOL_NAME,
        OUTREACH_TOOL_DESC,
        OUTREACH_INPUT_SCHEMA,
        OUTREACH_OUTPUT_SCHEMA,
        handle_dispatch_communication_outreach,
        RECORD_RESPONSE_TOOL_NAME,
        RECORD_RESPONSE_TOOL_DESC,
        RECORD_RESPONSE_INPUT_SCHEMA,
        RECORD_RESPONSE_OUTPUT_SCHEMA,
        handle_record_communication_response,
        STATUS_TOOL_NAME,
        STATUS_TOOL_DESC,
        STATUS_INPUT_SCHEMA,
        STATUS_OUTPUT_SCHEMA,
        handle_check_communication_status,
        ESCALATE_TOOL_NAME,
        ESCALATE_TOOL_DESC,
        ESCALATE_INPUT_SCHEMA,
        ESCALATE_OUTPUT_SCHEMA,
        handle_trigger_communication_escalation,
    )

    server.register_tool(
        MCPTool(
            name=OUTREACH_TOOL_NAME,
            description=OUTREACH_TOOL_DESC,
            input_schema=OUTREACH_INPUT_SCHEMA,
            output_schema=OUTREACH_OUTPUT_SCHEMA,
            handler=handle_dispatch_communication_outreach,
        )
    )
    server.register_tool(
        MCPTool(
            name=RECORD_RESPONSE_TOOL_NAME,
            description=RECORD_RESPONSE_TOOL_DESC,
            input_schema=RECORD_RESPONSE_INPUT_SCHEMA,
            output_schema=RECORD_RESPONSE_OUTPUT_SCHEMA,
            handler=handle_record_communication_response,
        )
    )
    server.register_tool(
        MCPTool(
            name=STATUS_TOOL_NAME,
            description=STATUS_TOOL_DESC,
            input_schema=STATUS_INPUT_SCHEMA,
            output_schema=STATUS_OUTPUT_SCHEMA,
            handler=handle_check_communication_status,
        )
    )
    server.register_tool(
        MCPTool(
            name=ESCALATE_TOOL_NAME,
            description=ESCALATE_TOOL_DESC,
            input_schema=ESCALATE_INPUT_SCHEMA,
            output_schema=ESCALATE_OUTPUT_SCHEMA,
            handler=handle_trigger_communication_escalation,
        )
    )
    return server


def register_calling_tools(server: MCPServer) -> MCPServer:
    """Register CallingAgent tools onto an MCPServer instance."""
    from app.mcp.tools.calling_tool import (
        DISPATCH_CALL_TOOL_NAME,
        DISPATCH_CALL_TOOL_DESC,
        DISPATCH_CALL_INPUT_SCHEMA,
        DISPATCH_CALL_OUTPUT_SCHEMA,
        handle_dispatch_emergency_call,
        CHECK_CALL_TOOL_NAME,
        CHECK_CALL_TOOL_DESC,
        CHECK_CALL_INPUT_SCHEMA,
        CHECK_CALL_OUTPUT_SCHEMA,
        handle_check_call_session_status,
    )

    server.register_tool(
        MCPTool(
            name=DISPATCH_CALL_TOOL_NAME,
            description=DISPATCH_CALL_TOOL_DESC,
            input_schema=DISPATCH_CALL_INPUT_SCHEMA,
            output_schema=DISPATCH_CALL_OUTPUT_SCHEMA,
            handler=handle_dispatch_emergency_call,
        )
    )
    server.register_tool(
        MCPTool(
            name=CHECK_CALL_TOOL_NAME,
            description=CHECK_CALL_TOOL_DESC,
            input_schema=CHECK_CALL_INPUT_SCHEMA,
            output_schema=CHECK_CALL_OUTPUT_SCHEMA,
            handler=handle_check_call_session_status,
        )
    )
    return server


def register_pharmacy_tools(server: MCPServer) -> MCPServer:
    """Register Pharmacy and Truemeds substitute tools onto an MCPServer instance."""
    from app.mcp.tools.pharmacy_tool import (
        FIND_SUBSTITUTES_TOOL_NAME,
        FIND_SUBSTITUTES_TOOL_DESC,
        FIND_SUBSTITUTES_INPUT_SCHEMA,
        FIND_SUBSTITUTES_OUTPUT_SCHEMA,
        handle_find_medicine_substitutes,
        CHECK_STOCK_TOOL_NAME,
        CHECK_STOCK_TOOL_DESC,
        CHECK_STOCK_INPUT_SCHEMA,
        CHECK_STOCK_OUTPUT_SCHEMA,
        handle_check_pharmacy_stock,
    )

    server.register_tool(
        MCPTool(
            name=FIND_SUBSTITUTES_TOOL_NAME,
            description=FIND_SUBSTITUTES_TOOL_DESC,
            input_schema=FIND_SUBSTITUTES_INPUT_SCHEMA,
            output_schema=FIND_SUBSTITUTES_OUTPUT_SCHEMA,
            handler=handle_find_medicine_substitutes,
        )
    )
    server.register_tool(
        MCPTool(
            name=CHECK_STOCK_TOOL_NAME,
            description=CHECK_STOCK_TOOL_DESC,
            input_schema=CHECK_STOCK_INPUT_SCHEMA,
            output_schema=CHECK_STOCK_OUTPUT_SCHEMA,
            handler=handle_check_pharmacy_stock,
        )
    )
    return server


def create_extended_mcp_server() -> MCPServer:
    """Factory creating an MCPServer pre-configured with core, communication, calling, and pharmacy tools."""
    server = create_default_mcp_server()
    register_communication_tools(server)
    register_calling_tools(server)
    register_pharmacy_tools(server)
    return server


default_mcp_server = create_default_mcp_server()
