"""FastAPI endpoints for the Calling Agent automated voice dispatch and IVR telephony."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.authorization import has_hospital_membership
from app.models.user import User, UserRole
from app.models.blood_request import BloodRequest
from app.schemas.calling import (
    VoiceCallCreate,
    VoiceCallWebhookInput,
    CallSessionResponse,
    CallingStatsResponse,
)
from app.agents.calling_agent import CallingAgent
from app.services.calling_service import CallingService

router = APIRouter(prefix="/calling", tags=["Calling Agent"])


@router.post(
    "/dispatch",
    summary="Dispatch emergency voice call",
    description="Initiates an automated outbound phone call with synthesized TTS emergency prompt to donor or blood bank.",
)
def dispatch_emergency_call(
    payload: VoiceCallCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Dispatch an automated voice call for an emergency blood request."""
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
            detail="You are not authorized to dispatch voice calls for another hospital's request.",
        )

    agent = CallingAgent(db=db)
    result = agent.dispatch_call(
        request_id=payload.request_id,
        recipient_type=payload.recipient_type,
        recipient_id=payload.recipient_id,
        recipient_phone=payload.recipient_phone,
        recipient_name=payload.recipient_name,
        hospital_id=payload.hospital_id or req.hospital_id,
        hospital_name=payload.hospital_name,
        blood_group=payload.blood_group or req.blood_group,
        units_required=payload.units_required or req.units_required,
        urgency=payload.urgency or str(req.urgency),
        custom_prompt=payload.custom_prompt,
    )
    return result


@router.post(
    "/webhook",
    summary="Telephony IVR touch-tone webhook callback",
    description="Processes carrier status callbacks and DTMF keypresses (1=Confirm, 2=Decline, 3=Delay).",
)
def telephony_webhook(
    payload: VoiceCallWebhookInput,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Process carrier callback with touchtone DTMF digits."""
    agent = CallingAgent(db=db)
    result = agent.process_callback(
        call_id=payload.call_id,
        call_status=payload.call_status,
        digits_pressed=payload.digits_pressed,
        duration_seconds=payload.duration_seconds or 0,
    )
    return result


@router.get(
    "/logs/{request_id}",
    response_model=List[CallSessionResponse],
    summary="Get voice call logs for blood request",
    description="Retrieves history of all voice calls dispatched for a specific emergency request.",
)
def get_call_logs(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve call session history for a blood request."""
    # Verify blood request exists
    req = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BloodRequest #{request_id} not found.",
        )

    if current_user.role != UserRole.ADMIN and not has_hospital_membership(db, current_user.id, req.hospital_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access call logs for another hospital's request.",
        )

    service = CallingService(db=db)
    return service.get_calls_by_request_id(request_id)


@router.get(
    "/stats",
    response_model=CallingStatsResponse,
    summary="Get telephony KPIs and performance metrics",
    description="Computes system-wide voice call metrics, DTMF confirmation rate, and average duration.",
)
def get_calling_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve aggregated telephony KPIs."""
    service = CallingService(db=db)
    return service.get_telephony_stats()
