"""MCP Tool: calculate_distance wrapping LocationAgent."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.agents.location_agent import LocationAgent

TOOL_NAME = "calculate_distance"
TOOL_DESCRIPTION = (
    "Calculates straight-line geodesic distance (in km) and estimated emergency travel duration "
    "between two coordinate pairs using the Haversine formula."
)

INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "origin_latitude": {
            "type": "number",
            "description": "Origin latitude in degrees (-90.0 to 90.0).",
        },
        "origin_longitude": {
            "type": "number",
            "description": "Origin longitude in degrees (-180.0 to 180.0).",
        },
        "destination_latitude": {
            "type": "number",
            "description": "Destination latitude in degrees (-90.0 to 90.0).",
        },
        "destination_longitude": {
            "type": "number",
            "description": "Destination longitude in degrees (-180.0 to 180.0).",
        },
        "include_eta": {
            "type": "boolean",
            "description": "Whether to return approximate emergency transit duration.",
            "default": True,
        },
    },
    "required": [
        "origin_latitude",
        "origin_longitude",
        "destination_latitude",
        "destination_longitude",
    ],
    "additionalProperties": True,
}

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "distance_km": {
            "type": "number",
            "description": "Calculated geodesic distance in kilometers.",
        },
        "estimated_time": {
            "type": "string",
            "description": "Human-readable estimated travel duration.",
        },
    },
    "required": ["distance_km"],
}


def handle_calculate_distance(
    arguments: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute LocationAgent distance calculation on the provided coordinate arguments.
    
    Calls LocationAgent directly without duplicating Haversine math.
    """
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")

    agent = LocationAgent()
    include_eta = arguments.get("include_eta", True)

    return agent.process(arguments, include_eta=include_eta)
