"""MCP adapter for the existing notification dispatch operation."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agents.notification_agent import NotificationAgent

TOOL_NAME = "dispatch_notifications"
TOOL_DESCRIPTION = "Dispatch notifications for an existing blood fulfillment plan."
INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hospital_id": {"type": "integer"},
        "request_id": {"type": "integer"},
        "fulfillment_plan": {"type": "object"},
        "hospital_name": {"type": ["string", "null"]},
    },
    "required": ["hospital_id", "request_id", "fulfillment_plan"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "request_id": {"type": "integer"},
        "dispatched_count": {"type": "integer"},
        "notifications": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["success", "request_id", "dispatched_count", "notifications"],
}


def handle_dispatch_notifications(
    arguments: Dict[str, Any], db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute the established NotificationAgent business operation."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")
    required = ("hospital_id", "request_id", "fulfillment_plan")
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join(missing)}")
    plan = arguments["fulfillment_plan"]
    if not isinstance(plan, dict):
        raise ValueError("fulfillment_plan must be an object.")
    return NotificationAgent().notify_plan(
        hospital_id=arguments["hospital_id"],
        request_id=arguments["request_id"],
        fulfillment_plan=plan,
        hospital_name=arguments.get("hospital_name"),
    )
