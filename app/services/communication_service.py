"""Communication Service managing interactive outreach, donor RSVPs, and SLA escalation."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.communication import CommunicationSession, CommunicationMessage
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.donor import Donor
from app.models.blood_bank import BloodBank
from app.services.notification_providers import BaseNotificationProvider
from app.services.notification_providers.console_provider import ConsoleNotificationProvider
from app.services.notification_providers.sms_provider import SMSNotificationProvider
from app.services.notification_providers.email_provider import EmailNotificationProvider

logger = logging.getLogger("CommunicationService")

# Urgency SLA definitions in minutes
URGENCY_SLA_MINUTES: Dict[str, int] = {
    "CRITICAL": 15,
    "HIGH": 30,
    "MEDIUM": 60,
    "LOW": 120,
}


class CommunicationService:
    """Service orchestrating multi-channel outreach, donor acknowledgments, and emergency escalations."""

    def __init__(
        self,
        db: Optional[Session] = None,
        provider: Optional[BaseNotificationProvider] = None,
    ):
        self.db = db
        self.provider = provider or ConsoleNotificationProvider()
        self.sms_provider = SMSNotificationProvider()
        self.email_provider = EmailNotificationProvider()

    def calculate_sla_deadline(self, urgency: str) -> tuple[int, datetime]:
        """Calculate SLA response window based on clinical urgency."""
        sla_min = URGENCY_SLA_MINUTES.get((urgency or "MEDIUM").upper(), 60)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=sla_min)
        return sla_min, expires_at

    def select_channels_for_urgency(self, urgency: str) -> List[str]:
        """Determine dispatch channels adapted to request criticality."""
        urg = (urgency or "MEDIUM").upper()
        if urg in ("CRITICAL", "HIGH"):
            return ["SMS", "CONSOLE"]
        return ["EMAIL", "CONSOLE"]

    def initiate_outreach_session(
        self,
        request_id: int,
        hospital_id: Optional[int],
        fulfillment_plan: Dict[str, Any],
        urgency: str = "MEDIUM",
        hospital_name: Optional[str] = None,
        custom_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start an interactive communication session, alerting all matched parties and tracking responses."""
        urgency = (urgency or "MEDIUM").upper()
        sla_minutes, sla_expires = self.calculate_sla_deadline(urgency)
        session_id = str(uuid.uuid4())
        hosp_display = hospital_name or f"Hospital #{hospital_id or 'Unknown'}"
        plan_items = fulfillment_plan.get("plan", [])
        total_targets = len(plan_items) + (1 if hospital_id else 0)

        session_model = None
        if self.db:
            session_model = CommunicationSession(
                session_id=session_id,
                request_id=request_id,
                hospital_id=hospital_id,
                urgency=urgency,
                status="ACTIVE",
                total_targets=total_targets,
                confirmed_count=0,
                declined_count=0,
                pending_count=len(plan_items),
                sla_minutes=sla_minutes,
                sla_expires_at=sla_expires,
                is_escalated=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(session_model)
            self.db.commit()

        channels = self.select_channels_for_urgency(urgency)
        dispatched_messages: List[Dict[str, Any]] = []

        # 1. Hospital confirmation notice
        status = fulfillment_plan.get("status", "UNFULFILLED")
        total_units = fulfillment_plan.get("total_units", 0)
        hosp_title = f"[{urgency}] Blood Request #{request_id} Active Outreach"
        hosp_body = (
            f"Emergency blood coordination initiated for {hosp_display}. "
            f"Securing {total_units} unit(s). Expected confirmation SLA: {sla_minutes} minutes."
        )
        if custom_message:
            hosp_body += f" Clinical note: {custom_message}"

        hosp_notif = self.provider.send_notification(
            recipient_type="HOSPITAL",
            recipient_id=hospital_id or 0,
            title=hosp_title,
            message=hosp_body,
            metadata={
                "session_id": session_id,
                "request_id": request_id,
                "urgency": urgency,
                "sla_minutes": sla_minutes,
            },
        )
        dispatched_messages.append(hosp_notif)

        if self.db and session_model:
            msg_model = CommunicationMessage(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                recipient_type="HOSPITAL",
                recipient_id=hospital_id or 0,
                channel="CONSOLE",
                title=hosp_title,
                body=hosp_body,
                units_requested=total_units,
                delivery_status="DELIVERED",
                response_status="CONFIRMED",
                sent_at=datetime.now(timezone.utc),
                responded_at=datetime.now(timezone.utc),
                metadata_json={"role": "REQUESTER"},
            )
            self.db.add(msg_model)
            self.db.commit()

        # 2. Targeted source outreach (Donors & Blood Banks)
        for item in plan_items:
            s_type = item.get("source_type", "BLOOD_BANK")
            s_id = item.get("source_id", 0)
            units = item.get("units", 1)
            dist_km = item.get("distance_km", 0.0)
            eta = item.get("estimated_time", f"{dist_km} km")

            channel_chosen = channels[0]
            src_title = f"[{urgency}] Urgent Blood Donation Request: {units} unit(s)"
            src_body = (
                f"Immediate emergency dispatch for {units} unit(s) to {hosp_display} ({dist_km} km away, ETA {eta}). "
                f"Please reply within {sla_minutes} mins to CONFIRM or DECLINE."
            )

            # Dispatch via configured provider
            notif_res = self.provider.send_notification(
                recipient_type=s_type,
                recipient_id=s_id,
                title=src_title,
                message=src_body,
                metadata={
                    "session_id": session_id,
                    "request_id": request_id,
                    "units": units,
                    "distance_km": dist_km,
                    "sla_expires": sla_expires.isoformat(),
                },
            )
            dispatched_messages.append(notif_res)

            if self.db and session_model:
                item_msg = CommunicationMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    recipient_type=s_type,
                    recipient_id=s_id,
                    channel=channel_chosen,
                    title=src_title,
                    body=src_body,
                    units_requested=units,
                    delivery_status="DELIVERED",
                    response_status="PENDING",
                    sent_at=datetime.now(timezone.utc),
                    metadata_json=item,
                )
                self.db.add(item_msg)
                self.db.commit()

        return {
            "success": True,
            "session_id": session_id,
            "request_id": request_id,
            "urgency": urgency,
            "sla_minutes": sla_minutes,
            "sla_expires_at": sla_expires.isoformat(),
            "status": "ACTIVE",
            "total_targets": total_targets,
            "dispatched_count": len(dispatched_messages),
            "dispatched_messages": dispatched_messages,
        }

    def record_response(
        self,
        session_id: str,
        recipient_type: str,
        recipient_id: int,
        response_status: str,
        response_notes: Optional[str] = None,
        eta_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record an interactive reply from a donor or blood bank and update session health."""
        status_upper = (response_status or "PENDING").upper()
        if status_upper not in ("CONFIRMED", "DECLINED", "DELAYED", "EN_ROUTE", "TIMEOUT"):
            raise ValueError(f"Invalid response_status '{response_status}'. Must be CONFIRMED, DECLINED, DELAYED, or EN_ROUTE.")

        session_model = None
        updated_message = None

        if self.db:
            session_model = (
                self.db.query(CommunicationSession)
                .filter(CommunicationSession.session_id == session_id)
                .first()
            )
            if not session_model:
                raise ValueError(f"Communication session '{session_id}' not found.")

            msg = (
                self.db.query(CommunicationMessage)
                .filter(
                    CommunicationMessage.session_id == session_id,
                    CommunicationMessage.recipient_type == recipient_type.upper(),
                    CommunicationMessage.recipient_id == recipient_id,
                )
                .first()
            )
            if msg:
                msg.response_status = status_upper
                msg.response_notes = response_notes
                msg.eta_minutes = eta_minutes
                msg.responded_at = datetime.now(timezone.utc)
                updated_message = msg

                # Recalculate session aggregates
                all_msgs = (
                    self.db.query(CommunicationMessage)
                    .filter(CommunicationMessage.session_id == session_id)
                    .all()
                )
                # Count non-requester messages
                source_msgs = [m for m in all_msgs if m.recipient_type != "HOSPITAL"]
                confirmed = sum(1 for m in source_msgs if m.response_status in ("CONFIRMED", "EN_ROUTE"))
                declined = sum(1 for m in source_msgs if m.response_status in ("DECLINED", "TIMEOUT"))
                pending = sum(1 for m in source_msgs if m.response_status == "PENDING")

                session_model.confirmed_count = confirmed
                session_model.declined_count = declined
                session_model.pending_count = pending
                session_model.updated_at = datetime.now(timezone.utc)

                if pending == 0 and confirmed > 0:
                    session_model.status = "ALL_CONFIRMED"
                elif confirmed > 0 and (declined > 0 or pending > 0):
                    session_model.status = "PARTIALLY_CONFIRMED"
                elif declined == len(source_msgs) and len(source_msgs) > 0:
                    session_model.status = "ESCALATED"
                    session_model.is_escalated = True
                    session_model.escalation_reason = "All prospective sources declined."

                self.db.commit()

        return {
            "success": True,
            "session_id": session_id,
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "response_status": status_upper,
            "response_notes": response_notes,
            "eta_minutes": eta_minutes,
            "session_status": session_model.status if session_model else "ACTIVE",
            "confirmed_count": session_model.confirmed_count if session_model else 1,
            "pending_count": session_model.pending_count if session_model else 0,
        }

    def evaluate_and_escalate(
        self,
        session_id: Optional[str] = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """Scan active sessions for SLA breaches or negative responses and trigger emergency escalation."""
        if not self.db:
            return []

        now = datetime.now(timezone.utc)
        query = self.db.query(CommunicationSession).filter(
            CommunicationSession.status.in_(["ACTIVE", "PARTIALLY_CONFIRMED"]),
            CommunicationSession.is_escalated == False,
        )
        if session_id:
            query = query.filter(CommunicationSession.session_id == session_id)

        candidates = query.all()
        escalated_records = []

        for sess in candidates:
            # Check SLA expiration or force
            is_breached = False
            if sess.sla_expires_at is not None:
                exp = sess.sla_expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                is_breached = exp < now
            has_pending = sess.pending_count > 0

            if is_breached or force or (sess.declined_count > 0 and sess.confirmed_count == 0):
                sess.is_escalated = True
                sess.status = "ESCALATED"
                sess.escalation_reason = (
                    "SLA timeout reached without sufficient confirmations"
                    if is_breached
                    else "Emergency manual escalation or all initial matches declined."
                )
                sess.updated_at = now

                # Mark timed out pending messages
                pending_msgs = (
                    self.db.query(CommunicationMessage)
                    .filter(
                        CommunicationMessage.session_id == sess.session_id,
                        CommunicationMessage.response_status == "PENDING",
                    )
                    .all()
                )
                unresponsive = []
                for p in pending_msgs:
                    p.response_status = "TIMEOUT"
                    p.responded_at = now
                    unresponsive.append({"recipient_type": p.recipient_type, "recipient_id": p.recipient_id})

                self.db.commit()

                # Dispatch high-priority escalation notice to Hospital
                esc_title = f"[EMERGENCY ESCALATION] Blood Request #{sess.request_id} SLA Breach"
                esc_body = (
                    f"Outreach session {sess.session_id} has exceeded its SLA ({sess.sla_minutes} mins). "
                    f"Remaining pending targets: {len(unresponsive)}. Escalating to regional standby donor network."
                )
                self.provider.send_notification(
                    recipient_type="HOSPITAL",
                    recipient_id=sess.hospital_id or 0,
                    title=esc_title,
                    message=esc_body,
                    metadata={
                        "session_id": sess.session_id,
                        "escalation": True,
                        "reason": sess.escalation_reason,
                    },
                )

                escalated_records.append({
                    "session_id": sess.session_id,
                    "request_id": sess.request_id,
                    "escalated": True,
                    "escalation_reason": sess.escalation_reason,
                    "unresponsive_recipients": unresponsive,
                    "escalated_at": now.isoformat(),
                })

        return escalated_records

    def get_session_by_request_id(self, request_id: int) -> Optional[CommunicationSession]:
        """Fetch communication session and nested message logs by blood request ID."""
        if not self.db:
            return None
        return (
            self.db.query(CommunicationSession)
            .filter(CommunicationSession.request_id == request_id)
            .order_by(CommunicationSession.created_at.desc())
            .first()
        )

    def get_session_stats(self) -> Dict[str, Any]:
        """Compute system-wide KPIs for the Communication Agent."""
        if not self.db:
            return {
                "total_sessions": 0,
                "active_sessions": 0,
                "fully_confirmed_sessions": 0,
                "escalated_sessions": 0,
                "total_messages_dispatched": 0,
                "confirmed_responses": 0,
                "declined_responses": 0,
                "pending_responses": 0,
                "confirmation_rate_pct": 0.0,
                "escalation_rate_pct": 0.0,
            }

        total_sessions = self.db.query(func.count(CommunicationSession.session_id)).scalar() or 0
        active_sessions = (
            self.db.query(func.count(CommunicationSession.session_id))
            .filter(CommunicationSession.status == "ACTIVE")
            .scalar()
            or 0
        )
        confirmed_sessions = (
            self.db.query(func.count(CommunicationSession.session_id))
            .filter(CommunicationSession.status == "ALL_CONFIRMED")
            .scalar()
            or 0
        )
        escalated_sessions = (
            self.db.query(func.count(CommunicationSession.session_id))
            .filter(CommunicationSession.is_escalated == True)
            .scalar()
            or 0
        )

        total_messages = self.db.query(func.count(CommunicationMessage.message_id)).scalar() or 0
        confirmed_msgs = (
            self.db.query(func.count(CommunicationMessage.message_id))
            .filter(CommunicationMessage.response_status.in_(["CONFIRMED", "EN_ROUTE"]))
            .scalar()
            or 0
        )
        declined_msgs = (
            self.db.query(func.count(CommunicationMessage.message_id))
            .filter(CommunicationMessage.response_status.in_(["DECLINED", "TIMEOUT"]))
            .scalar()
            or 0
        )
        pending_msgs = (
            self.db.query(func.count(CommunicationMessage.message_id))
            .filter(CommunicationMessage.response_status == "PENDING")
            .scalar()
            or 0
        )

        conf_rate = round((confirmed_msgs / total_messages * 100), 1) if total_messages > 0 else 0.0
        esc_rate = round((escalated_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0.0

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "fully_confirmed_sessions": confirmed_sessions,
            "escalated_sessions": escalated_sessions,
            "total_messages_dispatched": total_messages,
            "confirmed_responses": confirmed_msgs,
            "declined_responses": declined_msgs,
            "pending_responses": pending_msgs,
            "confirmation_rate_pct": conf_rate,
            "escalation_rate_pct": esc_rate,
        }
