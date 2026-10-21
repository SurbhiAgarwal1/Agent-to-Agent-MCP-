"""Calling Agent for Emergency Blood Donation & Automated IVR Voice Dispatch.

The CallingAgent handles outbound emergency phone calls, Text-to-Speech (TTS)
synthesis, interactive touch-tone (DTMF) keypress processing, and real-time
telephony status monitoring for critical blood coordination.
"""

from typing import Any, Dict, List, Optional
import logging
from sqlalchemy.orm import Session

from app.services.voice_providers import BaseVoiceProvider, ConsoleVoiceProvider
from app.services.calling_service import CallingService

logger = logging.getLogger("CallingAgent")


class CallingAgent:
    """Agent orchestrating outbound voice calls, speech synthesis, and IVR responses."""

    def __init__(
        self,
        db: Optional[Session] = None,
        voice_provider: Optional[BaseVoiceProvider] = None,
        bus: Optional[Any] = None,
    ):
        self.db = db
        self.provider = voice_provider or ConsoleVoiceProvider()
        self.bus = bus
        self.service = CallingService(db=self.db, voice_provider=self.provider)

    def dispatch_call(
        self,
        request_id: int,
        recipient_type: str,
        recipient_id: int,
        recipient_phone: str,
        recipient_name: Optional[str] = None,
        hospital_id: Optional[int] = None,
        hospital_name: Optional[str] = None,
        blood_group: str = "O+",
        units_required: int = 1,
        urgency: str = "CRITICAL",
        custom_prompt: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch an automated voice call to a donor or blood bank."""
        return self.service.dispatch_call(
            request_id=request_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            recipient_phone=recipient_phone,
            recipient_name=recipient_name,
            hospital_id=hospital_id,
            hospital_name=hospital_name,
            blood_group=blood_group,
            units_required=units_required,
            urgency=urgency,
            custom_prompt=custom_prompt,
            callback_url=callback_url,
        )

    def process_callback(
        self,
        call_id: str,
        call_status: str = "COMPLETED",
        digits_pressed: Optional[str] = None,
        duration_seconds: int = 0,
    ) -> Dict[str, Any]:
        """Process telephony callback with touch-tone (DTMF) input."""
        return self.service.process_call_callback(
            call_id=call_id,
            call_status=call_status,
            digits_pressed=digits_pressed,
            duration_seconds=duration_seconds,
        )

    def get_logs(self, request_id: int) -> List[Dict[str, Any]]:
        """Retrieve call records for a blood request."""
        records = self.service.get_calls_by_request_id(request_id)
        return [
            {
                "call_id": r.call_id,
                "request_id": r.request_id,
                "recipient_type": r.recipient_type,
                "recipient_id": r.recipient_id,
                "recipient_phone": r.recipient_phone,
                "recipient_name": r.recipient_name,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "dtmf_input": r.dtmf_input,
                "response_status": r.response_status,
                "telephony_provider": r.telephony_provider,
                "initiated_at": r.initiated_at.isoformat() if r.initiated_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in records
        ]

    def handle_a2a_message(self, message: Any) -> Any:
        """Process incoming A2A messages for voice dispatch and status polling."""
        from app.agents.a2a.message import A2AMessageType

        mtype = getattr(message, "message_type", None)
        payload = message.payload if isinstance(message.payload, dict) else {}

        # 1. Outbound Emergency Voice Call Request
        if mtype == A2AMessageType.CALLING_DISPATCH_REQUEST:
            for req in ("request_id", "recipient_type", "recipient_id", "recipient_phone"):
                if req not in payload:
                    return message.create_error(
                        sender_agent="CallingAgent",
                        error_message=f"Missing required field '{req}' for voice dispatch.",
                    )
            result = self.dispatch_call(
                request_id=int(payload["request_id"]),
                recipient_type=str(payload["recipient_type"]),
                recipient_id=int(payload["recipient_id"]),
                recipient_phone=str(payload["recipient_phone"]),
                recipient_name=payload.get("recipient_name"),
                hospital_id=payload.get("hospital_id"),
                hospital_name=payload.get("hospital_name"),
                blood_group=payload.get("blood_group", "O+"),
                units_required=int(payload.get("units_required", 1)),
                urgency=payload.get("urgency", "CRITICAL"),
                custom_prompt=payload.get("custom_prompt"),
                callback_url=payload.get("callback_url"),
            )
            return message.create_response(
                sender_agent="CallingAgent",
                message_type=A2AMessageType.CALLING_DISPATCH_RESULT,
                payload=result,
            )

        # 2. Telephony Callback Event (DTMF touch-tone processed)
        elif mtype == A2AMessageType.CALLING_CALLBACK_EVENT:
            if "call_id" not in payload:
                return message.create_error(
                    sender_agent="CallingAgent",
                    error_message="'call_id' is required for CALLING_CALLBACK_EVENT.",
                )
            res = self.process_callback(
                call_id=str(payload["call_id"]),
                call_status=payload.get("call_status", "COMPLETED"),
                digits_pressed=payload.get("digits_pressed"),
                duration_seconds=int(payload.get("duration_seconds", 0)),
            )
            return message.create_response(
                sender_agent="CallingAgent",
                message_type="CALLING_STATUS_UPDATED",
                payload=res,
            )

        # 3. Status Poll
        elif mtype == A2AMessageType.CALLING_STATUS_POLL:
            req_id = payload.get("request_id")
            if req_id is None:
                return message.create_error(
                    sender_agent="CallingAgent",
                    error_message="'request_id' is required for CALLING_STATUS_POLL.",
                )
            logs = self.get_logs(request_id=int(req_id))
            return message.create_response(
                sender_agent="CallingAgent",
                message_type="CALLING_STATUS_REPORT",
                payload={"request_id": req_id, "call_count": len(logs), "calls": logs},
            )

        return message.create_error(
            sender_agent="CallingAgent",
            error_message=f"Unsupported message_type '{mtype}' for CallingAgent.",
        )
