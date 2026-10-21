"""MCP tool adapters for the Communication Agent operations."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agents.communication_agent import CommunicationAgent
from app.services.communication_service import CommunicationService

# Tool 1: dispatch_communication_outreach
OUTREACH_TOOL_NAME = "dispatch_communication_outreach"
OUTREACH_TOOL_DESC = "Initiate an interactive outreach session to matched blood sources with SLA tracking."
OUTREACH_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hospital_id": {"type": "integer"},
        "request_id": {"type": "integer"},
        "fulfillment_plan": {"type": "object"},
        "urgency": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        "hospital_name": {"type": ["string", "null"]},
        "custom_message": {"type": ["string", "null"]},
    },
    "required": ["hospital_id", "request_id", "fulfillment_plan"],
    "additionalProperties": False,
}
OUTREACH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "session_id": {"type": "string"},
        "request_id": {"type": "integer"},
        "urgency": {"type": "string"},
        "sla_minutes": {"type": "integer"},
        "total_targets": {"type": "integer"},
        "dispatched_count": {"type": "integer"},
    },
    "required": ["success", "session_id", "request_id", "dispatched_count"],
}


def handle_dispatch_communication_outreach(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Execute interactive outreach via CommunicationAgent."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")
    for req in ("hospital_id", "request_id", "fulfillment_plan"):
        if req not in arguments:
            raise ValueError(f"Missing required argument '{req}'.")

    plan = arguments["fulfillment_plan"]
    if not isinstance(plan, dict):
        raise ValueError("fulfillment_plan must be an object.")

    agent = CommunicationAgent(db=db)
    return agent.initiate_outreach(
        hospital_id=int(arguments["hospital_id"]),
        request_id=int(arguments["request_id"]),
        fulfillment_plan=plan,
        urgency=arguments.get("urgency", "MEDIUM"),
        hospital_name=arguments.get("hospital_name"),
        custom_message=arguments.get("custom_message"),
    )


# Tool 2: record_communication_response
RECORD_RESPONSE_TOOL_NAME = "record_communication_response"
RECORD_RESPONSE_TOOL_DESC = "Record donor or blood bank RSVP confirmation/decline for an outreach session."
RECORD_RESPONSE_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "recipient_type": {"type": "string", "enum": ["DONOR", "BLOOD_BANK", "HOSPITAL"]},
        "recipient_id": {"type": "integer"},
        "response_status": {"type": "string", "enum": ["CONFIRMED", "DECLINED", "DELAYED", "EN_ROUTE"]},
        "response_notes": {"type": ["string", "null"]},
        "eta_minutes": {"type": ["integer", "null"]},
    },
    "required": ["session_id", "recipient_type", "recipient_id", "response_status"],
    "additionalProperties": False,
}
RECORD_RESPONSE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "session_id": {"type": "string"},
        "response_status": {"type": "string"},
        "session_status": {"type": "string"},
        "confirmed_count": {"type": "integer"},
        "pending_count": {"type": "integer"},
    },
    "required": ["success", "session_id", "response_status"],
}


def handle_record_communication_response(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Record RSVP response via CommunicationAgent."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")
    for req in ("session_id", "recipient_type", "recipient_id", "response_status"):
        if req not in arguments:
            raise ValueError(f"Missing required argument '{req}'.")

    agent = CommunicationAgent(db=db)
    return agent.record_response(
        session_id=str(arguments["session_id"]),
        recipient_type=str(arguments["recipient_type"]),
        recipient_id=int(arguments["recipient_id"]),
        response_status=str(arguments["response_status"]),
        response_notes=arguments.get("response_notes"),
        eta_minutes=arguments.get("eta_minutes"),
    )


# Tool 3: check_communication_status
STATUS_TOOL_NAME = "check_communication_status"
STATUS_TOOL_DESC = "Check real-time communication session status, confirmations, and SLA health."
STATUS_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "integer"},
    },
    "required": ["request_id"],
    "additionalProperties": False,
}
STATUS_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "request_id": {"type": "integer"},
        "status": {"type": ["string", "null"]},
        "confirmed_count": {"type": ["integer", "null"]},
        "pending_count": {"type": ["integer", "null"]},
    },
    "required": ["found", "request_id"],
}


def handle_check_communication_status(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Check communication status via CommunicationAgent."""
    if not isinstance(arguments, dict) or "request_id" not in arguments:
        raise ValueError("Tool arguments must be a dictionary with 'request_id'.")
    agent = CommunicationAgent(db=db)
    return agent.get_status(request_id=int(arguments["request_id"]))


# Tool 4: trigger_communication_escalation
ESCALATE_TOOL_NAME = "trigger_communication_escalation"
ESCALATE_TOOL_DESC = "Evaluate SLA deadlines or manually escalate an unresponsive communication session."
ESCALATE_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "session_id": {"type": ["string", "null"]},
        "force": {"type": "boolean"},
    },
    "additionalProperties": False,
}
ESCALATE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "escalated_count": {"type": "integer"},
        "escalations": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["escalated_count", "escalations"],
}


def handle_trigger_communication_escalation(
    arguments: Dict[str, Any], db: Optional[Session] = None
) -> Dict[str, Any]:
    """Trigger escalation check via CommunicationAgent."""
    agent = CommunicationAgent(db=db)
    session_id = arguments.get("session_id") if isinstance(arguments, dict) else None
    force = bool(arguments.get("force", False)) if isinstance(arguments, dict) else False
    records = agent.evaluate_escalations(session_id=session_id, force=force)
    return {"escalated_count": len(records), "escalations": records}
