"""Communication Agent for Emergency Blood Donation & A2A Interactive Outreach.

The CommunicationAgent handles bidirectional multi-channel communication,
donor acknowledgments / RSVPs, urgency-adaptive dispatch, SLA timeout tracking,
and automated escalation to regional standby networks.
"""

from typing import Any, Dict, List, Optional
import logging
from sqlalchemy.orm import Session

from app.services.communication_service import CommunicationService
from app.services.notification_providers import BaseNotificationProvider
from app.services.notification_providers.console_provider import ConsoleNotificationProvider

logger = logging.getLogger("CommunicationAgent")


class CommunicationAgent:
    """Agent orchestrating interactive communication, donor confirmations, and SLA escalations."""

    def __init__(
        self,
        db: Optional[Session] = None,
        provider: Optional[BaseNotificationProvider] = None,
        bus: Optional[Any] = None,
    ):
        self.db = db
        self.provider = provider or ConsoleNotificationProvider()
        self.bus = bus
        self.service = CommunicationService(db=self.db, provider=self.provider)

    def initiate_outreach(
        self,
        hospital_id: int,
        request_id: int,
        fulfillment_plan: Dict[str, Any],
        urgency: str = "MEDIUM",
        hospital_name: Optional[str] = None,
        custom_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate an interactive outreach session for matched blood sources."""
        return self.service.initiate_outreach_session(
            request_id=request_id,
            hospital_id=hospital_id,
            fulfillment_plan=fulfillment_plan,
            urgency=urgency,
            hospital_name=hospital_name,
            custom_message=custom_message,
        )

    def record_response(
        self,
        session_id: str,
        recipient_type: str,
        recipient_id: int,
        response_status: str,
        response_notes: Optional[str] = None,
        eta_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record donor or blood bank RSVP response (CONFIRMED, DECLINED, DELAYED, EN_ROUTE)."""
        return self.service.record_response(
            session_id=session_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            response_status=response_status,
            response_notes=response_notes,
            eta_minutes=eta_minutes,
        )

    def evaluate_escalations(
        self,
        session_id: Optional[str] = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """Evaluate active sessions for SLA timeout and trigger escalation alert."""
        return self.service.evaluate_and_escalate(session_id=session_id, force=force)

    def get_status(self, request_id: int) -> Dict[str, Any]:
        """Query live communication status and response statistics for a blood request."""
        session = self.service.get_session_by_request_id(request_id)
        if not session:
            return {"found": False, "request_id": request_id}

        return {
            "found": True,
            "session_id": session.session_id,
            "request_id": session.request_id,
            "urgency": session.urgency,
            "status": session.status,
            "total_targets": session.total_targets,
            "confirmed_count": session.confirmed_count,
            "declined_count": session.declined_count,
            "pending_count": session.pending_count,
            "is_escalated": session.is_escalated,
            "escalation_reason": session.escalation_reason,
            "sla_minutes": session.sla_minutes,
            "sla_expires_at": session.sla_expires_at.isoformat() if session.sla_expires_at else None,
            "messages_count": len(session.messages),
        }

    def notify_plan(
        self,
        hospital_id: int,
        request_id: int,
        fulfillment_plan: Dict[str, Any],
        hospital_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible helper method mimicking NotificationAgent's notify_plan."""
        urgency = fulfillment_plan.get("details", {}).get("urgency", "MEDIUM")
        outreach = self.initiate_outreach(
            hospital_id=hospital_id,
            request_id=request_id,
            fulfillment_plan=fulfillment_plan,
            urgency=urgency,
            hospital_name=hospital_name,
        )
        return {
            "success": outreach.get("success", True),
            "request_id": request_id,
            "dispatched_count": outreach.get("dispatched_count", 0),
            "notifications": outreach.get("dispatched_messages", []),
            "session_id": outreach.get("session_id"),
        }

    def handle_a2a_message(self, message: Any) -> Any:
        """Process incoming A2A messages according to standard protocol envelope."""
        from app.agents.a2a.message import A2AMessageType

        mtype = getattr(message, "message_type", None)
        payload = message.payload if isinstance(message.payload, dict) else {}

        # 1. Interactive Communication Outreach Request
        if mtype == A2AMessageType.COMMUNICATION_OUTREACH_REQUEST:
            plan = payload.get("fulfillment_plan")
            if not isinstance(plan, dict) or payload.get("request_id") is None:
                return message.create_error(
                    sender_agent="CommunicationAgent",
                    error_message="Malformed payload: 'request_id' and 'fulfillment_plan' are required.",
                )
            result = self.initiate_outreach(
                hospital_id=payload.get("hospital_id") or 0,
                request_id=payload["request_id"],
                fulfillment_plan=plan,
                urgency=payload.get("urgency", "MEDIUM"),
                hospital_name=payload.get("hospital_name"),
                custom_message=payload.get("custom_message"),
            )
            return message.create_response(
                sender_agent="CommunicationAgent",
                message_type=A2AMessageType.COMMUNICATION_OUTREACH_DISPATCHED,
                payload=result,
            )

        # 2. Donor/Source Response Received
        elif mtype == A2AMessageType.COMMUNICATION_RESPONSE_RECEIVED:
            required = ("session_id", "recipient_type", "recipient_id", "response_status")
            missing = [k for k in required if k not in payload]
            if missing:
                return message.create_error(
                    sender_agent="CommunicationAgent",
                    error_message=f"Missing fields for response: {', '.join(missing)}",
                )
            try:
                res = self.record_response(
                    session_id=payload["session_id"],
                    recipient_type=payload["recipient_type"],
                    recipient_id=payload["recipient_id"],
                    response_status=payload["response_status"],
                    response_notes=payload.get("response_notes"),
                    eta_minutes=payload.get("eta_minutes"),
                )
                return message.create_response(
                    sender_agent="CommunicationAgent",
                    message_type=A2AMessageType.COMMUNICATION_RESPONSE_RECORDED,
                    payload=res,
                )
            except Exception as exc:
                return message.create_error(
                    sender_agent="CommunicationAgent",
                    error_message=str(exc),
                )

        # 3. Escalation Check or Alert
        elif mtype == A2AMessageType.COMMUNICATION_ESCALATION_ALERT:
            session_id = payload.get("session_id")
            force = bool(payload.get("force", False))
            escalations = self.evaluate_escalations(session_id=session_id, force=force)
            return message.create_response(
                sender_agent="CommunicationAgent",
                message_type=A2AMessageType.COMMUNICATION_ESCALATED_EVENT,
                payload={"escalations": escalations, "count": len(escalations)},
            )

        # 4. Status Poll
        elif mtype == A2AMessageType.COMMUNICATION_STATUS_POLL:
            req_id = payload.get("request_id")
            if req_id is None:
                return message.create_error(
                    sender_agent="CommunicationAgent",
                    error_message="'request_id' is required for COMMUNICATION_STATUS_POLL",
                )
            status = self.get_status(request_id=int(req_id))
            return message.create_response(
                sender_agent="CommunicationAgent",
                message_type="COMMUNICATION_STATUS_REPORT",
                payload=status,
            )

        # 5. Legacy Notification Request (Backwards-compatibility)
        elif mtype == A2AMessageType.NOTIFICATION_DISPATCH_REQUEST:
            plan = payload.get("fulfillment_plan")
            if not isinstance(plan, dict) or payload.get("request_id") is None:
                return message.create_error(
                    sender_agent="CommunicationAgent",
                    error_message="Malformed payload: 'request_id' and 'fulfillment_plan' are required.",
                )
            result = self.notify_plan(
                hospital_id=payload.get("hospital_id") or 0,
                request_id=payload["request_id"],
                fulfillment_plan=plan,
                hospital_name=payload.get("hospital_name"),
            )
            return message.create_response(
                sender_agent="CommunicationAgent",
                message_type=A2AMessageType.NOTIFICATION_DISPATCHED_EVENT,
                payload=result,
            )

        return message.create_error(
            sender_agent="CommunicationAgent",
            error_message=f"Unsupported message_type '{mtype}' for CommunicationAgent.",
        )
