"""MCP Tools package."""

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

__all__ = [
    "VALIDATE_TOOL_NAME",
    "VALIDATE_TOOL_DESC",
    "VALIDATE_INPUT_SCHEMA",
    "VALIDATE_OUTPUT_SCHEMA",
    "handle_validate_blood_request",
    "MATCHING_TOOL_NAME",
    "MATCHING_TOOL_DESC",
    "MATCHING_INPUT_SCHEMA",
    "MATCHING_OUTPUT_SCHEMA",
    "handle_find_blood_sources",
    "LOCATION_TOOL_NAME",
    "LOCATION_TOOL_DESC",
    "LOCATION_INPUT_SCHEMA",
    "LOCATION_OUTPUT_SCHEMA",
    "handle_calculate_distance",
    "NOTIFICATION_TOOL_NAME",
    "NOTIFICATION_TOOL_DESC",
    "NOTIFICATION_INPUT_SCHEMA",
    "NOTIFICATION_OUTPUT_SCHEMA",
    "handle_dispatch_notifications",
]
