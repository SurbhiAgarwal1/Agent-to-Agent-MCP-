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
from app.services import donor_alerts, order_status, response_sync

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
    summary = response_sync.summarize(db, request, response_sync.fetch_notifications(request_id))
    order_status.name_sources(summary["responses"])
    summary["accepted"] = [row for row in summary["responses"] if row["response_status"] in response_sync.POSITIVE]
    return summary


@router.get("/blood-requests/{request_id}/order", tags=["Blood Requests"])
def request_order(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    """The placed order: who confirmed, how many units, and the estimated arrival time at the hospital."""
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blood request not found.")
    if user.role != UserRole.ADMIN and not has_hospital_membership(db, user.id, request.hospital_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital membership is required.")
    summary = response_sync.summarize(db, request, response_sync.fetch_notifications(request_id))
    return order_status.build_order(db, request, summary)


def _own_request(db: Session, user: User, request_id: int) -> BloodRequest:
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blood request not found.")
    if user.role != UserRole.ADMIN and not has_hospital_membership(db, user.id, request.hospital_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital membership is required.")
    return request


def _hospital_with_location(db: Session, request: BloodRequest):
    from app.models.hospital import Hospital
    hospital = db.get(Hospital, request.hospital_id)
    if hospital is None or hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The hospital has no location, so nearby donors cannot be found.")
    return hospital


@router.get("/blood-requests/{request_id}/donor-candidates", tags=["Blood Requests"])
def donor_candidates(request_id: int, radius_km: float = Query(50, gt=0, le=200), limit: int = Query(12, ge=1, le=50),
                     db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    """Compatible donors near the hospital, each with whether they were already alerted and what they answered."""
    request = _own_request(db, user, request_id)
    hospital = _hospital_with_location(db, request)
    fetched = response_sync.fetch_notifications(request_id)
    state = {int(n["donor_id"]): n.get("response_status", "pending") for n in fetched["donors"]}
    out = []
    for d in donor_alerts.candidates(db, request, hospital, radius_km, limit):
        km = d.get("distance_km")
        out.append({"donor_id": int(d["id"]), "name": d.get("name"), "blood_group": d.get("blood_group"), "city": d.get("city"),
                    "distance_km": km, "has_login": d.get("has_login", False), "eta_minutes": round((km or 0) / 25 * 60) + 1 if km is not None else None,
                    "state": state.get(int(d["id"]), "not_notified")})
    return {"request_id": request_id, "units_required": request.units_required, "donors": out}


class AlertDonors(BaseModel):
    donor_ids: list[int] | None = None


@router.post("/blood-requests/{request_id}/alert-donors", tags=["Blood Requests"])
def alert_nearby_donors(request_id: int, body: AlertDonors | None = None, radius_km: float = Query(50, gt=0, le=200),
                        limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    """Alert the chosen donors (or, with no list, the nearest ones); they answer in their own dashboard."""
    from app.services import party_service as ps
    request = _own_request(db, user, request_id)
    hospital = _hospital_with_location(db, request)
    ranked = donor_alerts.candidates(db, request, hospital, radius_km, max(limit, 100 if body and body.donor_ids else limit))
    if body and body.donor_ids:
        wanted = set(body.donor_ids)
        ranked = [d for d in ranked if int(d["id"]) in wanted]
    else:
        ranked = ranked[:limit]
    sent = 0
    for d in ranked:
        try:
            ps.call("POST", ps.donor_url() + "/api/v1/donor-notifications/send", json={
                "donor_id": int(d["id"]), "channel": "console", "blood_request_id": request.request_id,
                "blood_group": request.blood_group,
                "message": f"{hospital.name} urgently needs {request.units_required} unit(s) of {request.blood_group}. Open your dashboard to accept or decline.",
                "idempotency_key": f"alert-{request.request_id}-{d['id']}",
                "hospital_latitude": hospital.latitude, "hospital_longitude": hospital.longitude,
                "max_distance_km": max(radius_km, 1)})
            sent += 1
        except HTTPException:
            continue
    return {"request_id": request_id, "donors_found": len(ranked), "notified": sent,
            "message": f"Alerted {sent} donor(s)." if sent else "No eligible donors were found nearby."}


@router.post("/blood-requests/{request_id}/confirm-delivery", tags=["Blood Requests"])
def confirm_delivery(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(STAFF))):
    """The hospital confirms the confirmed blood has arrived; the request is closed as fulfilled."""
    request = _own_request(db, user, request_id)
    summary = response_sync.summarize(db, request, response_sync.fetch_notifications(request_id))
    if request.order_placed_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The order has not been placed yet.")
    if not summary.get("confirmed_units"):
        raise HTTPException(status.HTTP_409_CONFLICT, "No blood bank or donor has confirmed yet, so there is nothing to receive.")
    request.status = "FULFILLED"
    db.commit()
    from app.services.audit import record_audit_log
    record_audit_log(db=db, action="CONFIRM_DELIVERY", resource="blood_request", resource_id=request.request_id,
                     user_id=user.id, details={"units_confirmed": summary.get("confirmed_units")})
    return order_status.build_order(db, request, summary)


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
