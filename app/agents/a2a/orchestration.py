"""A2A entry point that runs the discovery flow through the Coordinator.

Agents never message each other. The CoordinatorAgent is the hub: it sends each agent a
request over the in-process MessageBus and receives the reply. This function runs that same
flow as a read-only preview (nothing is saved, no notifications are sent).
"""

import uuid
from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session

from app.models.blood_request import BloodRequest
from app.agents.a2a.bus import MessageBus
from app.agents.a2a.message import A2AMessageType


def orchestrate_a2a_flow(
    request_data: Union[Dict[str, Any], BloodRequest],
    db: Optional[Session] = None,
    bus: Optional[MessageBus] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Requirement -> Matching -> Location through the Coordinator hub (preview only).

    Returns:
        success, correlation_id, final_message_type, result (requirement, hospital and
        located candidates), error (if any) and trace (every A2A message exchanged).
    """
    from app.agents.coordinator_agent import CoordinatorAgent

    if isinstance(request_data, BloodRequest):
        payload = {
            "request_id": request_data.request_id,
            "hospital_id": request_data.hospital_id,
            "blood_group": request_data.blood_group,
            "units_required": request_data.units_required,
            "urgency": request_data.urgency,
        }
    else:
        payload = dict(request_data)

    corr_id = correlation_id or f"corr-{payload.get('request_id', 'anon')}-{uuid.uuid4().hex[:8]}"
    coordinator = CoordinatorAgent(db=db, bus=bus)
    outcome = coordinator.coordinate(request_input=payload, correlation_id=corr_id, persist=False)
    trace = [
        {k: m[k] for k in ("message_id", "sender", "receiver", "type", "timestamp")}
        for m in outcome["a2a_trace"]
    ]

    if not outcome["success"]:
        return {
            "success": False,
            "correlation_id": corr_id,
            "final_message_type": A2AMessageType.A2A_ERROR,
            "result": {"error": outcome["error"], "details": outcome.get("details")},
            "error": outcome["error"],
            "trace": trace,
        }

    return {
        "success": True,
        "correlation_id": corr_id,
        "final_message_type": A2AMessageType.LOCATION_DISTANCES_CALCULATED_EVENT,
        "result": {
            "hospital_id": outcome["hospital"]["hospital_id"],
            "hospital_coords": outcome["hospital"],
            "requirement": outcome["requirement"],
            "candidates_count": outcome["candidates_count"],
            "candidates": outcome["ranked_matches"],
        },
        "error": None,
        "trace": trace,
    }
