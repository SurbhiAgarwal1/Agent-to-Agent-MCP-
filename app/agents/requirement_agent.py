"""Requirement Agent for Blood Donation Matching System.

Responsible for receiving structured blood requests, validating all parameters,
and normalizing data (e.g. blood group casing, urgency casing) into a clean,
consistent specification ready for subsequent coordination and matching agents.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.enums import BloodGroup, UrgencyLevel
from app.models.hospital import Hospital


class RequirementAgent:
    """Validates and normalizes emergency blood requests.
    
    This agent acts as the first gatekeeper in the multi-agent pipeline:
    1. Ensures blood groups and urgency levels match medical standards.
    2. Validates positive non-zero quantities.
    3. Verifies that request ID and hospital ID exist.
    4. Normalizes casing and formatting into standardized strings.
    """

    # Supported medical blood groups
    VALID_BLOOD_GROUPS = {bg.value for bg in BloodGroup}
    # Supported urgency levels
    VALID_URGENCIES = {u.value for u in UrgencyLevel}

    def __init__(self, db: Optional[Session] = None, bus: Optional[Any] = None):
        """Initialize the Requirement Agent with an optional database session and A2A message bus."""
        self.db = db
        self.bus = bus

    def handle_a2a_message(self, message: Any) -> Any:
        """Handle incoming A2A message for requirement validation.
        
        Validates the incoming message envelope and payload. If valid and connected to
        the message bus, dispatches an A2A message to MatchingAgent.
        """
        from app.agents.a2a.message import A2AMessage, A2AMessageType

        if not hasattr(message, "payload") or not isinstance(message.payload, dict):
            return message.create_error(
                sender_agent="RequirementAgent",
                error_message="Malformed message: payload must be a dictionary.",
            )

        if getattr(message, "message_type", None) != A2AMessageType.REQUIREMENT_VALIDATE_REQUEST:
            return message.create_error(
                sender_agent="RequirementAgent",
                error_message=f"Unsupported message_type '{getattr(message, 'message_type', None)}'. Expected '{A2AMessageType.REQUIREMENT_VALIDATE_REQUEST}'.",
            )

        # Execute direct domain validation
        req_result = self.process(message.payload)
        if not req_result.get("valid"):
            return message.create_error(
                sender_agent="RequirementAgent",
                error_message="Requirement validation failed.",
                details={"errors": req_result.get("errors", [])},
            )

        # If connected to an A2A message bus, forward to MatchingAgent
        if self.bus:
            next_payload = {
                "requirement": req_result,
                "hospital_id": message.payload.get("hospital_id"),
            }
            next_msg = A2AMessage.create(
                sender_agent="RequirementAgent",
                receiver_agent="MatchingAgent",
                message_type=A2AMessageType.MATCHING_FIND_SOURCES_REQUEST,
                payload=next_payload,
                correlation_id=message.correlation_id,
            )
            return self.bus.send(next_msg)

        # Standalone response
        return message.create_response(
            sender_agent="RequirementAgent",
            message_type=A2AMessageType.REQUIREMENT_VALIDATED_EVENT,
            payload={"requirement": req_result},
        )

    def process(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize a structured blood request.
        
        Args:
            request_data: Dictionary containing:
                - request_id: int
                - hospital_id: int
                - blood_group: str (e.g. "o+", "A-")
                - units_required: int (must be > 0)
                - urgency: str (e.g. "critical", "MEDIUM")
                
        Returns:
            Dictionary containing:
                If valid:
                    - request_id: int
                    - blood_group: str (normalized, e.g. "O+")
                    - units_required: int
                    - urgency: str (normalized, e.g. "CRITICAL")
                    - valid: True
                If invalid:
                    - request_id: Optional[int]
                    - valid: False
                    - errors: List[str]
        """
        errors: List[str] = []

        if not isinstance(request_data, dict):
            return {
                "request_id": None,
                "valid": False,
                "errors": ["Request data must be a valid dictionary."],
            }

        # 1. Validate & extract request_id
        raw_request_id = request_data.get("request_id")
        if raw_request_id is None:
            errors.append("request_id is required.")
            request_id = None
        elif not isinstance(raw_request_id, int) or raw_request_id <= 0:
            errors.append("request_id must be a positive integer.")
            request_id = raw_request_id
        else:
            request_id = raw_request_id

        # 2. Validate hospital_id & check database existence if db session is available
        raw_hospital_id = request_data.get("hospital_id")
        if raw_hospital_id is None:
            errors.append("hospital_id is required.")
        elif not isinstance(raw_hospital_id, int) or raw_hospital_id <= 0:
            errors.append("hospital_id must be a positive integer.")
        elif self.db is not None:
            hospital = self.db.query(Hospital).filter(Hospital.hospital_id == raw_hospital_id).first()
            if not hospital:
                errors.append(f"Hospital with ID {raw_hospital_id} does not exist.")

        # 3. Validate & normalize blood_group
        raw_blood_group = request_data.get("blood_group")
        normalized_blood_group: Optional[str] = None
        if not raw_blood_group or not isinstance(raw_blood_group, str):
            errors.append("blood_group is required and must be a string.")
        else:
            clean_bg = raw_blood_group.strip().upper()
            if clean_bg in self.VALID_BLOOD_GROUPS:
                normalized_blood_group = clean_bg
            else:
                errors.append(
                    f"Unsupported blood group '{raw_blood_group}'. Supported groups are: {sorted(list(self.VALID_BLOOD_GROUPS))}."
                )

        # 4. Validate units_required
        raw_units = request_data.get("units_required")
        units_required: Optional[int] = None
        if raw_units is None:
            errors.append("units_required is required.")
        elif not isinstance(raw_units, int):
            errors.append("units_required must be an integer.")
        elif raw_units <= 0:
            errors.append("units_required must be greater than zero.")
        else:
            units_required = raw_units

        # 5. Validate & normalize urgency
        raw_urgency = request_data.get("urgency")
        normalized_urgency: Optional[str] = None
        if not raw_urgency or not isinstance(raw_urgency, str):
            errors.append("urgency is required and must be a string.")
        else:
            clean_urgency = raw_urgency.strip().upper()
            if clean_urgency in self.VALID_URGENCIES:
                normalized_urgency = clean_urgency
            else:
                errors.append(
                    f"Unsupported urgency level '{raw_urgency}'. Supported levels are: {sorted(list(self.VALID_URGENCIES))}."
                )

        # If any validation errors occurred, return invalid response with errors
        if errors:
            return {
                "request_id": request_id,
                "valid": False,
                "errors": errors,
            }

        # Return clean, validated, and normalized requirement
        return {
            "request_id": request_id,
            "blood_group": normalized_blood_group,
            "units_required": units_required,
            "urgency": normalized_urgency,
            "valid": True,
        }
