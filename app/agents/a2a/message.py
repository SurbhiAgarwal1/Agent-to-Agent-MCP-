"""Standard Agent-to-Agent (A2A) Message Envelope."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class A2AMessageType:
    """Standard message types exchanged across agents."""
    # Requirement Agent messages
    REQUIREMENT_VALIDATE_REQUEST = "REQUIREMENT_VALIDATE_REQUEST"
    REQUIREMENT_VALIDATED_EVENT = "REQUIREMENT_VALIDATED_EVENT"
    
    # Matching Agent messages
    MATCHING_FIND_SOURCES_REQUEST = "MATCHING_FIND_SOURCES_REQUEST"
    MATCHING_SOURCES_FOUND_EVENT = "MATCHING_SOURCES_FOUND_EVENT"
    
    # Location Agent messages
    LOCATION_CALCULATE_DISTANCES_REQUEST = "LOCATION_CALCULATE_DISTANCES_REQUEST"
    LOCATION_DISTANCES_CALCULATED_EVENT = "LOCATION_DISTANCES_CALCULATED_EVENT"
    
    # Error message
    A2A_ERROR = "A2A_ERROR"


class A2AMessage(BaseModel):
    """Standard message envelope used by all agents in the A2A communication protocol.
    
    Attributes:
        message_id: Unique message identifier (UUID).
        sender_agent: Name/Identifier of the sending agent.
        receiver_agent: Name/Identifier of the intended receiving agent.
        message_type: Action or event identifier (A2AMessageType).
        payload: Structured dictionary containing domain data.
        timestamp: ISO 8601 UTC timestamp of message generation.
        correlation_id: Unique ID tracing a single emergency request across all agents.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_agent: str
    receiver_agent: str
    message_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str

    @classmethod
    def create(
        cls,
        sender_agent: str,
        receiver_agent: str,
        message_type: str,
        payload: Dict[str, Any],
        correlation_id: str,
        message_id: Optional[str] = None,
    ) -> "A2AMessage":
        """Convenience factory method to create an A2A message."""
        return cls(
            message_id=message_id or str(uuid.uuid4()),
            sender_agent=sender_agent,
            receiver_agent=receiver_agent,
            message_type=message_type,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=correlation_id,
        )

    def create_response(
        self,
        sender_agent: str,
        message_type: str,
        payload: Dict[str, Any],
    ) -> "A2AMessage":
        """Create a response message responding to this message, preserving correlation_id."""
        return A2AMessage(
            message_id=str(uuid.uuid4()),
            sender_agent=sender_agent,
            receiver_agent=self.sender_agent,
            message_type=message_type,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=self.correlation_id,
        )

    def create_error(
        self,
        sender_agent: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> "A2AMessage":
        """Create an A2A error response message preserving correlation_id."""
        return A2AMessage(
            message_id=str(uuid.uuid4()),
            sender_agent=sender_agent,
            receiver_agent=self.sender_agent,
            message_type=A2AMessageType.A2A_ERROR,
            payload={
                "error": error_message,
                "details": details or {},
                "original_message_id": self.message_id,
                "original_message_type": self.message_type,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=self.correlation_id,
        )
