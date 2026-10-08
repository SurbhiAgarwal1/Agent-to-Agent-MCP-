"""MCP Tool: find_blood_sources wrapping MatchingAgent."""

from typing import Any, Dict, Optional, List
from sqlalchemy.orm import Session
from app.agents.matching_agent import MatchingAgent

TOOL_NAME = "find_blood_sources"
TOOL_DESCRIPTION = (
    "Discovers compatible blood bank inventories and registered voluntary donors "
    "for a blood request using medical RBC ABO/Rh compatibility rules."
)

INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "blood_group": {
            "type": "string",
            "description": "Recipient ABO/Rh blood group (e.g. 'O+', 'A-', 'B+').",
        },
        "request_id": {
            "type": "integer",
            "description": "Optional request identifier.",
        },
        "inventories": {
            "type": "array",
            "description": "Optional in-memory list of blood inventories for standalone execution.",
            "items": {"type": "object"},
        },
        "donors": {
            "type": "array",
            "description": "Optional in-memory list of donor records for standalone execution.",
            "items": {"type": "object"},
        },
    },
    "required": ["blood_group"],
    "additionalProperties": True,
}

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": ["integer", "null"]},
        "requested_blood_group": {"type": "string"},
        "compatible_groups": {
            "type": "array",
            "items": {"type": "string"},
        },
        "matches_count": {"type": "integer"},
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_type": {"type": "string"},
                    "source_id": {"type": "integer"},
                    "blood_group": {"type": "string"},
                    "units_available": {"type": "integer"},
                },
                "required": ["source_type", "source_id", "blood_group", "units_available"],
            },
        },
    },
    "required": ["requested_blood_group", "matches_count", "matches"],
}


def handle_find_blood_sources(
    arguments: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute MatchingAgent candidate search on the provided input arguments.
    
    Calls MatchingAgent directly without duplicating RBC compatibility logic.
    """
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")

    blood_group = arguments.get("blood_group")
    if not blood_group or not isinstance(blood_group, str):
        raise ValueError("Argument 'blood_group' must be a non-empty string.")

    agent = MatchingAgent(db=db)
    req_payload = {
        "request_id": arguments.get("request_id", 1),
        "blood_group": blood_group,
    }

    return agent.find_matches(
        request_data=req_payload,
        inventories=arguments.get("inventories"),
        donors=arguments.get("donors"),
    )
