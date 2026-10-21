"""Calling Service managing automated outbound emergency voice calls and IVR processing."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.calling import CallSession
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.donor import Donor
from app.models.blood_bank import BloodBank
from app.services.voice_providers import BaseVoiceProvider, ConsoleVoiceProvider, TwilioVoiceProvider
from app.services.communication_service import CommunicationService

logger = logging.getLogger("CallingService")


class CallingService:
    """Service orchestrating emergency voice dispatch, Text-to-Speech synthesis, and IVR keypresses."""

    def __init__(
        self,
        db: Optional[Session] = None,
        voice_provider: Optional[BaseVoiceProvider] = None,
    ):
        self.db = db
        self.provider = voice_provider or ConsoleVoiceProvider()

    def generate_tts_script(
        self,
        hospital_name: Optional[str],
        blood_group: str,
        units: int,
        urgency: str = "CRITICAL",
        recipient_name: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Synthesize interactive IVR voice prompt script."""
        if custom_prompt:
            return custom_prompt

        hosp = hospital_name or "the requesting emergency trauma center"
        greeting = f"Hello {recipient_name}, " if recipient_name else "Emergency Alert. "
        script = (
            f"{greeting}this is an automated urgent blood coordination call on behalf of {hosp}. "
            f"There is a {urgency} clinical requirement for {units} unit(s) of {blood_group} blood. "
            f"Please listen carefully to the following options: "
            f"Press 1 to CONFIRM you can donate and proceed to the facility. "
            f"Press 2 to DECLINE if you are unable to donate today. "
            f"Press 3 if you can donate but with a DELAY. "
            f"Thank you for supporting emergency lifesaving medical care."
        )
        return script

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
        """Initiate outbound voice call to a prospective donor or blood bank."""
        call_id = str(uuid.uuid4())
        tts_script = self.generate_tts_script(
            hospital_name=hospital_name,
            blood_group=blood_group,
            units=units_required,
            urgency=urgency,
            recipient_name=recipient_name,
            custom_prompt=custom_prompt,
        )

        # Trigger telephony provider
        telephony_res = self.provider.initiate_call(
            to_phone=recipient_phone,
            tts_script=tts_script,
            callback_url=callback_url,
            metadata={"call_id": call_id, "request_id": request_id},
        )

        call_record = None
        if self.db:
            call_record = CallSession(
                call_id=call_id,
                request_id=request_id,
                hospital_id=hospital_id,
                recipient_type=recipient_type.upper(),
                recipient_id=recipient_id,
                recipient_phone=recipient_phone,
                recipient_name=recipient_name,
                status="INITIATED",
                duration_seconds=0,
                dtmf_input=None,
                response_status="NO_RESPONSE",
                tts_script=tts_script,
                telephony_provider=telephony_res.get("provider", "CONSOLE_MOCK"),
                call_sid=telephony_res.get("call_sid"),
                initiated_at=datetime.now(timezone.utc),
            )
            self.db.add(call_record)
            self.db.commit()

        return {
            "success": True,
            "call_id": call_id,
            "request_id": request_id,
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "recipient_phone": recipient_phone,
            "recipient_name": recipient_name,
            "status": "INITIATED",
            "provider": telephony_res.get("provider", "CONSOLE_MOCK"),
            "call_sid": telephony_res.get("call_sid"),
            "tts_script": tts_script,
        }

    def process_call_callback(
        self,
        call_id: str,
        call_status: str = "COMPLETED",
        digits_pressed: Optional[str] = None,
        duration_seconds: int = 0,
    ) -> Dict[str, Any]:
        """Process carrier IVR status update and DTMF keypress (1=Confirm, 2=Decline, 3=Delay)."""
        # Map touch-tone digits to clinical response status
        response_map = {
            "1": "CONFIRMED",
            "2": "DECLINED",
            "3": "DELAYED",
        }
        resp_status = response_map.get(str(digits_pressed).strip(), "NO_RESPONSE") if digits_pressed else "NO_RESPONSE"

        call_model = None
        if self.db:
            call_model = self.db.query(CallSession).filter(CallSession.call_id == call_id).first()
            if call_model:
                call_model.status = (call_status or "COMPLETED").upper()
                call_model.dtmf_input = str(digits_pressed) if digits_pressed else None
                call_model.response_status = resp_status
                call_model.duration_seconds = max(0, duration_seconds)
                call_model.completed_at = datetime.now(timezone.utc)
                self.db.commit()

                # If an active communication session exists for this blood request, bridge the RSVP
                if resp_status in ("CONFIRMED", "DECLINED", "DELAYED"):
                    comm_service = CommunicationService(db=self.db)
                    comm_session = comm_service.get_session_by_request_id(call_model.request_id)
                    if comm_session:
                        try:
                            comm_service.record_response(
                                session_id=comm_session.session_id,
                                recipient_type=call_model.recipient_type,
                                recipient_id=call_model.recipient_id,
                                response_status=resp_status,
                                response_notes=f"Voice call IVR keypress: DTMF '{digits_pressed}'",
                            )
                        except Exception as exc:
                            logger.warning(f"Could not sync voice response to communication session: {exc}")

        return {
            "success": True,
            "call_id": call_id,
            "call_status": (call_status or "COMPLETED").upper(),
            "digits_pressed": digits_pressed,
            "response_status": resp_status,
            "duration_seconds": duration_seconds,
        }

    def get_calls_by_request_id(self, request_id: int) -> List[CallSession]:
        """Fetch all call logs associated with an emergency request."""
        if not self.db:
            return []
        return (
            self.db.query(CallSession)
            .filter(CallSession.request_id == request_id)
            .order_by(CallSession.initiated_at.desc())
            .all()
        )

    def get_telephony_stats(self) -> Dict[str, Any]:
        """Compute system-wide voice dispatch KPIs."""
        if not self.db:
            return {
                "total_calls": 0,
                "completed_calls": 0,
                "confirmed_count": 0,
                "declined_count": 0,
                "no_answer_count": 0,
                "avg_duration_seconds": 0.0,
                "voice_confirmation_rate_pct": 0.0,
            }

        total = self.db.query(func.count(CallSession.call_id)).scalar() or 0
        completed = (
            self.db.query(func.count(CallSession.call_id))
            .filter(CallSession.status == "COMPLETED")
            .scalar()
            or 0
        )
        confirmed = (
            self.db.query(func.count(CallSession.call_id))
            .filter(CallSession.response_status == "CONFIRMED")
            .scalar()
            or 0
        )
        declined = (
            self.db.query(func.count(CallSession.call_id))
            .filter(CallSession.response_status == "DECLINED")
            .scalar()
            or 0
        )
        no_ans = (
            self.db.query(func.count(CallSession.call_id))
            .filter(CallSession.status.in_(["NO_ANSWER", "BUSY", "FAILED"]))
            .scalar()
            or 0
        )
        avg_dur = (
            self.db.query(func.avg(CallSession.duration_seconds))
            .filter(CallSession.status == "COMPLETED")
            .scalar()
            or 0.0
        )

        conf_rate = round((confirmed / completed * 100), 1) if completed > 0 else 0.0

        return {
            "total_calls": total,
            "completed_calls": completed,
            "confirmed_count": confirmed,
            "declined_count": declined,
            "no_answer_count": no_ans,
            "avg_duration_seconds": round(float(avg_dur), 1),
            "voice_confirmation_rate_pct": conf_rate,
        }
