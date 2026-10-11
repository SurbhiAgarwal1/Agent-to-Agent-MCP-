"""FastAPI HTTP transport endpoints for MCP tools (Part 14)."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.mcp.server import default_mcp_server
from app.auth.dependencies import get_current_user

mcp_router = APIRouter(prefix="/mcp", tags=["MCP Tools"], dependencies=[Depends(get_current_user)])


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
