"""Minimal Model Context Protocol (MCP) Server for Blood Donation Matching System."""

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.database.session import get_db
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

    return server


# -----------------------------------------------------------------------------
# Local HTTP Transport: FastAPI Router for MCP
# -----------------------------------------------------------------------------

default_mcp_server = create_default_mcp_server()
mcp_router = APIRouter(prefix="/mcp", tags=["MCP Tools"])


class ToolInvocationPayload(BaseModel):
    """Payload format for tool invocation."""
    arguments: Dict[str, Any]


@mcp_router.get("/tools", summary="List MCP tools")
def list_mcp_tools():
    """List all registered MCP tools and their JSON schemas."""
    return {
        "server": default_mcp_server.server_name,
        "version": default_mcp_server.version,
        "tools": default_mcp_server.list_tools(),
    }


@mcp_router.get("/tools/{tool_name}", summary="Describe an MCP tool")
def describe_mcp_tool(tool_name: str):
    """Retrieve JSON schema details for a specific MCP tool."""
    tool_meta = default_mcp_server.describe_tool(tool_name)
    if not tool_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP tool '{tool_name}' not found.",
        )
    return tool_meta


@mcp_router.post("/tools/{tool_name}/invoke", summary="Invoke an MCP tool")
def invoke_mcp_tool(
    tool_name: str,
    payload: ToolInvocationPayload,
    db: Session = Depends(get_db),
):
    """Execute an MCP tool via HTTP transport."""
    result = default_mcp_server.invoke_tool(tool_name, payload.arguments, db=db)
    if result.get("isError"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Tool execution failed."),
        )
    return result
