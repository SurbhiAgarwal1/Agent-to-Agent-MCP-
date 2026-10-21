"""MCP tool adapters for the Calling Agent voice dispatch operations."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agents.calling_agent import CallingAgent

# Tool 1: dispatch_emergency_call
DISPATCH_CALL_TOOL_NAME = "dispatch_emergency_call"
DISPATCH_CALL_TOOL_DESC = "Dispatch an automated outbound emergency phone call to a voluntary donor or blood bank."
DISPATCH_CALL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "integer"},
        "recipient_type": {"type": "string", "enum": ["DONOR", "BLOOD_BANK", "HOSPITAL"]},
        "recipient_id": {"type": "integer"},
        "recipient_phone": {"type": "string"},
        "recipient_name": {"type": ["string", "null"]},
        "hospital_id": {"type": ["integer", "null"]},
        "hospital_name": {"type": ["string", "null"]},
        "blood_group": {"type": "string"},
        "units_required": {"type": "integer"},
        "urgency": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        "custom_prompt": {"type": ["string", "null"]},
    },
    "required": ["request_id", "recipient_type", "recipient_id", "recipient_phone"],
    "additionalProperties": False,
}
DISPATCH_CALL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "call_id": {"type": "string"},
        "request_id": {"type": "integer"},
        "recipient_phone": {"type": "string"},
        "status": {"type": "string"},
        "tts_script": {"type": "string"},
    },
    "required": ["success", "call_id", "request_id", "recipient_phone", "status"],
}


def handle_dispatch_emergency_call(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Execute outbound call via CallingAgent."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")
    for req in ("request_id", "recipient_type", "recipient_id", "recipient_phone"):
        if req not in arguments:
            raise ValueError(f"Missing required argument '{req}'.")

    agent = CallingAgent(db=db)
    return agent.dispatch_call(
        request_id=int(arguments["request_id"]),
        recipient_type=str(arguments["recipient_type"]),
        recipient_id=int(arguments["recipient_id"]),
        recipient_phone=str(arguments["recipient_phone"]),
        recipient_name=arguments.get("recipient_name"),
        hospital_id=arguments.get("hospital_id"),
        hospital_name=arguments.get("hospital_name"),
        blood_group=arguments.get("blood_group", "O+"),
        units_required=int(arguments.get("units_required", 1)),
        urgency=arguments.get("urgency", "CRITICAL"),
        custom_prompt=arguments.get("custom_prompt"),
    )


# Tool 2: check_call_session_status
CHECK_CALL_TOOL_NAME = "check_call_session_status"
CHECK_CALL_TOOL_DESC = "Check call dispatch history and donor touch-tone keypress response for a blood request."
CHECK_CALL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "integer"},
    },
    "required": ["request_id"],
    "additionalProperties": False,
}
CHECK_CALL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "integer"},
        "call_count": {"type": "integer"},
        "calls": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["request_id", "call_count", "calls"],
}


def handle_check_call_session_status(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Check call history via CallingAgent."""
    if not isinstance(arguments, dict) or "request_id" not in arguments:
        raise ValueError("Tool arguments must be a dictionary with 'request_id'.")
    agent = CallingAgent(db=db)
    logs = agent.get_logs(request_id=int(arguments["request_id"]))
    return {"request_id": int(arguments["request_id"]), "call_count": len(logs), "calls": logs}
