"""Single Orchestration function for Agent-to-Agent (A2A) message flow.

Coordinates the Requirement -> Matching -> Location agent flow strictly through
the in-process MessageBus.
"""

import uuid
from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session

from app.models.blood_request import BloodRequest
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent
from app.agents.a2a.bus import MessageBus
from app.agents.a2a.message import A2AMessage, A2AMessageType


def orchestrate_a2a_flow(
    request_data: Union[Dict[str, Any], BloodRequest],
    db: Optional[Session] = None,
    bus: Optional[MessageBus] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the sequential A2A communication flow across the three core agents.
    
    Flow:
        Orchestrator -> (A2A Message) -> RequirementAgent
                     -> (A2A Message) -> MatchingAgent
                     -> (A2A Message) -> LocationAgent
                     -> (A2A Response) -> Orchestrator
                     
    Args:
        request_data: Dictionary or BloodRequest instance with request fields.
        db: Optional SQLAlchemy Session.
        bus: Optional MessageBus instance (created if not provided).
        correlation_id: Optional tracking ID to trace across all messages.
        
    Returns:
        Structured dictionary containing:
            - success: bool
            - correlation_id: str
            - result: dict (annotated candidates & requirement)
            - error: Optional error string if any step failed
            - trace: list of message summaries showing full A2A message exchange
    """
    message_bus = bus or MessageBus()

    # 1. Instantiate the agents with reference to the message bus
    req_agent = RequirementAgent(db=db, bus=message_bus)
    match_agent = MatchingAgent(db=db, bus=message_bus)
    loc_agent = LocationAgent(bus=message_bus)

    # 2. Register each agent on the message bus
    message_bus.register_agent("RequirementAgent", req_agent.handle_a2a_message)
    message_bus.register_agent("MatchingAgent", match_agent.handle_a2a_message)
    message_bus.register_agent("LocationAgent", loc_agent.handle_a2a_message)

    # 3. Format input payload
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

    req_id = payload.get("request_id", "anon")
    corr_id = correlation_id or f"corr-{req_id}-{uuid.uuid4().hex[:8]}"

    # 4. Create initial A2A message to RequirementAgent
    initial_message = A2AMessage.create(
        sender_agent="A2AOrchestrator",
        receiver_agent="RequirementAgent",
        message_type=A2AMessageType.REQUIREMENT_VALIDATE_REQUEST,
        payload=payload,
        correlation_id=corr_id,
    )

    # 5. Dispatch message through the bus
    final_message = message_bus.send(initial_message)

    # 6. Extract trace logs for this correlation_id
    messages_trace = message_bus.get_messages_for_correlation_id(corr_id)
    trace_summary = [
        {
            "message_id": m.message_id,
            "sender": m.sender_agent,
            "receiver": m.receiver_agent,
            "type": m.message_type,
            "timestamp": m.timestamp,
        }
        for m in messages_trace
    ]

    is_error = (final_message.message_type == A2AMessageType.A2A_ERROR)

    return {
        "success": not is_error,
        "correlation_id": corr_id,
        "final_message_type": final_message.message_type,
        "result": final_message.payload,
        "error": final_message.payload.get("error") if is_error else None,
        "trace": trace_summary,
    }
