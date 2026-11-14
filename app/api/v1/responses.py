"""Hospital-facing view of blood bank and donor responses (acceptance flowing back to staff)."""
import hmac
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.authorization import has_hospital_membership
from app.auth.dependencies import require_role
from app.database.session import get_db
from app.models.blood_request import BloodRequest
from app.models.hospital_alert import HospitalAlert
from app.models.membership import HospitalMembership
from app.models.user import User, UserRole
from app.services import response_sync

router = APIRouter()
STAFF = [UserRole.HOSPITAL_STAFF, UserRole.ADMIN]


class ResponseEvent(BaseModel):
    blood_request_id: int
    source_type: str          # BLOOD_BANK | DONOR
    source_id: int
    notification_id: int
    response_status: str
    confirmed_units: Optional[int] = None
    reason: Optional[str] = None
    source_name: Optional[str] = None


def _alert_dict(a: HospitalAlert) -> dict:
    return {"alert_id": a.alert_id, "hospital_id": a.hospital_id, "request_id": a.request_id, "source_type": a.source_type,
            "source_id": a.source_id, "source_name": a.source_name, "response_status": a.response_status,
            "confirmed_units": a.confirmed_units, "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None, "read": a.read_at is not None}


def _require_service_token(authorization: Optional[str]) -> None:
    expected = os.getenv("SERVICE_TO_SERVICE_TOKEN", "").strip()
    if not expected:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service authentication is not configured.")
        return  # local development only
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Internal service authentication required.")


@router.post("/internal/response-events", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
def receive_response_event(event: ResponseEvent, authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    """Called by the blood bank / donor data APIs the moment a recipient answers."""
    _require_service_token(authorization)
    alert, created = response_sync.ingest_response(
        db, request_id=event.blood_request_id, source_type=event.source_type, source_id=event.source_id,
        notification_id=event.notification_id, response_status=event.response_status,
        confirmed_units=event.confirmed_units, reason=event.reason, source_name=event.source_name,
    )
    return {"accepted": alert is not None, "created": created}


@router.get("/blood-requests/{request_id}/responses", tags=["Blood Requests"])
def request_responses(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    """Everything blood banks and donors answered for this request, with how many units are confirmed."""
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blood request not found.")
    if user.role != UserRole.ADMIN and not has_hospital_membership(db, user.id, request.hospital_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital membership is required.")
    return response_sync.summarize(db, request, response_sync.fetch_notifications(request_id))


@router.get("/hospital-alerts", tags=["Hospital Alerts"])
def list_alerts(unread_only: bool = False, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                user: User = Depends(require_role(STAFF))):
    """Alerts for the hospitals this user belongs to (admins see all), newest first."""
    query = db.query(HospitalAlert)
    if user.role != UserRole.ADMIN:
        ids = [m.hospital_id for m in db.query(HospitalMembership).filter(HospitalMembership.user_id == user.id)]
        query = query.filter(HospitalAlert.hospital_id.in_(ids or [-1]))
    if unread_only:
        query = query.filter(HospitalAlert.read_at.is_(None))
    unread = query.filter(HospitalAlert.read_at.is_(None)).count()
    items = query.order_by(HospitalAlert.created_at.desc(), HospitalAlert.alert_id.desc()).limit(limit).all()
    return {"unread": unread, "items": [_alert_dict(a) for a in items]}


@router.post("/hospital-alerts/{alert_id}/read", tags=["Hospital Alerts"])
def mark_read(alert_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    alert = db.get(HospitalAlert, alert_id)
    if alert is None or (user.role != UserRole.ADMIN and not has_hospital_membership(db, user.id, alert.hospital_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found.")
    if alert.read_at is None:
        alert.read_at = datetime.now(timezone.utc)
        db.commit()
    return _alert_dict(alert)
