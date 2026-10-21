"""FastAPI endpoints for the Communication Agent and interactive outreach."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.authorization import has_hospital_membership
from app.models.user import User, UserRole
from app.models.blood_request import BloodRequest
from app.schemas.communication import (
    CommunicationOutreachCreate,
    CommunicationResponseInput,
    CommunicationSessionResponse,
    EscalationTriggerResponse,
    CommunicationStatsResponse,
)
from app.agents.communication_agent import CommunicationAgent
from app.services.communication_service import CommunicationService

router = APIRouter(prefix="/communication", tags=["Communication Agent"])


@router.post(
    "/outreach",
    summary="Initiate interactive communication outreach",
    description="Dispatches emergency outreach to candidate blood sources and hospital with SLA deadline tracking.",
)
def initiate_outreach(
    payload: CommunicationOutreachCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Start interactive communication session for a blood request."""
    # Verify blood request exists
    req = db.query(BloodRequest).filter(BloodRequest.request_id == payload.request_id).first()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BloodRequest #{payload.request_id} not found.",
        )

    # Permission check: ADMIN or active hospital membership
    if current_user.role != UserRole.ADMIN and not has_hospital_membership(db, current_user.id, req.hospital_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to dispatch outreach for another hospital's request.",
        )

    plan = payload.fulfillment_plan or {"plan": [], "status": "PENDING", "total_units": req.units_required}
    agent = CommunicationAgent(db=db)
    result = agent.initiate_outreach(
        hospital_id=payload.hospital_id or req.hospital_id,
        request_id=payload.request_id,
        fulfillment_plan=plan,
        urgency=payload.urgency or str(req.urgency),
        hospital_name=payload.hospital_name,
        custom_message=payload.custom_message,
    )
    return result


@router.post(
    "/respond",
    summary="Record recipient response / RSVP",
    description="Receives donor or blood bank confirmation, decline, delay, or en-route update.",
)
def record_response(
    payload: CommunicationResponseInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record an interactive response for an outreach session."""
    agent = CommunicationAgent(db=db)
    try:
        return agent.record_response(
            session_id=payload.session_id,
            recipient_type=payload.recipient_type,
            recipient_id=payload.recipient_id,
            response_status=payload.response_status,
            response_notes=payload.response_notes,
            eta_minutes=payload.eta_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/sessions/{request_id}",
    response_model=CommunicationSessionResponse,
    summary="Get communication session by request ID",
    description="Returns real-time outreach status, message delivery logs, and recipient confirmations.",
)
def get_session(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve communication session and timeline of dispatched messages."""
    service = CommunicationService(db=db)
    session = service.get_session_by_request_id(request_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No communication session found for blood request #{request_id}.",
        )
    return session


@router.post(
    "/escalate/{session_id}",
    response_model=EscalationTriggerResponse,
    summary="Trigger SLA evaluation / emergency escalation",
    description="Checks SLA deadline breach or manually escalates an unresponsive outreach session.",
)
def escalate_session(
    session_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger SLA escalation for a specific communication session."""
    agent = CommunicationAgent(db=db)
    escalations = agent.evaluate_escalations(session_id=session_id, force=force)
    if not escalations:
        # Check if already escalated or not found
        service = CommunicationService(db=db)
        from app.models.communication import CommunicationSession
        sess = db.query(CommunicationSession).filter(CommunicationSession.session_id == session_id).first()
        if not sess:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        return {
            "session_id": session_id,
            "request_id": sess.request_id,
            "escalated": sess.is_escalated,
            "escalation_reason": sess.escalation_reason or "No escalation required at this time.",
            "unresponsive_recipients": [],
            "escalated_at": sess.updated_at,
        }
    item = escalations[0]
    return {
        "session_id": item["session_id"],
        "request_id": item["request_id"],
        "escalated": True,
        "escalation_reason": item.get("escalation_reason"),
        "unresponsive_recipients": item.get("unresponsive_recipients", []),
        "escalated_at": item.get("escalated_at"),
    }


@router.get(
    "/stats",
    response_model=CommunicationStatsResponse,
    summary="Get system-wide communication metrics",
    description="Aggregated confirmation rates, response latency, and escalation counts.",
)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve communication performance KPIs."""
    service = CommunicationService(db=db)
    return service.get_session_stats()
