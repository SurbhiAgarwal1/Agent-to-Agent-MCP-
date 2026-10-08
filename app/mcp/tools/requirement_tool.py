"""MCP Tool: validate_blood_request wrapping RequirementAgent."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.agents.requirement_agent import RequirementAgent

TOOL_NAME = "validate_blood_request"
TOOL_DESCRIPTION = (
    "Validates and normalizes an emergency blood request payload. "
    "Verifies medical blood group standards, urgency classifications, positive unit counts, "
    "and checks hospital existence."
)

INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hospital_id": {
            "type": "integer",
            "description": "Unique identifier of the requesting hospital.",
        },
        "blood_group": {
            "type": "string",
            "description": "Requested ABO/Rh blood group (e.g. 'A+', 'O-', 'ab+').",
        },
        "units_required": {
            "type": "integer",
            "description": "Number of blood units required (must be > 0).",
        },
        "urgency": {
            "type": "string",
            "description": "Urgency classification: 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'.",
        },
        "request_id": {
            "type": "integer",
            "description": "Optional request identifier (defaults to 1).",
        },
    },
    "required": ["hospital_id", "blood_group", "units_required", "urgency"],
    "additionalProperties": True,
}

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "request_id": {"type": ["integer", "null"]},
        "blood_group": {"type": "string"},
        "units_required": {"type": "integer"},
        "urgency": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["valid"],
}


def handle_validate_blood_request(
    arguments: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute RequirementAgent validation on the provided input arguments.
    
    Calls RequirementAgent directly without duplicating validation logic.
    """
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")

    agent = RequirementAgent(db=db)
    payload = dict(arguments)
    if "request_id" not in payload:
        payload["request_id"] = 1

    return agent.process(payload)
