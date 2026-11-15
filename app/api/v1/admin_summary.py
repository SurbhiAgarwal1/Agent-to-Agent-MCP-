"""Admin front-page overview: who requested blood, how much, and how much has been secured."""
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_role
from app.database.session import get_db
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.match import Match
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin", tags=["Admin Overview"])

SECURED = ("ACCEPTED", "COMPLETED")


@router.get("/request-summary")
def request_summary(db: Session = Depends(get_db), _: User = Depends(require_role([UserRole.ADMIN]))):
    """Per hospital: requests, units asked for, units secured (accepted or completed matches, capped at what was asked)."""
    secured = dict(
        db.query(Match.request_id, func.coalesce(func.sum(Match.units), 0))
        .filter(Match.status.in_(SECURED)).group_by(Match.request_id).all()
    )
    rows = (
        db.query(BloodRequest, Hospital.name)
        .join(Hospital, Hospital.hospital_id == BloodRequest.hospital_id)
        .order_by(BloodRequest.created_at.desc(), BloodRequest.request_id.desc())
        .all()
    )
    per_hospital: dict[int, dict] = {}
    recent = []
    for request, hospital_name in rows:
        got = min(int(secured.get(request.request_id, 0) or 0), request.units_required)
        h = per_hospital.setdefault(request.hospital_id, {
            "hospital_id": request.hospital_id, "hospital_name": hospital_name, "requests": 0,
            "units_requested": 0, "units_secured": 0, "fulfilled_requests": 0, "last_request_at": None})
        h["requests"] += 1
        h["units_requested"] += request.units_required
        h["units_secured"] += got
        h["fulfilled_requests"] += 1 if request.status == "FULFILLED" else 0
        h["last_request_at"] = h["last_request_at"] or (request.created_at.isoformat() if request.created_at else None)
        if len(recent) < 100:
            recent.append({"request_id": request.request_id, "hospital_id": request.hospital_id, "hospital_name": hospital_name,
                           "blood_group": request.blood_group, "units_requested": request.units_required, "units_secured": got,
                           "urgency": request.urgency, "status": request.status,
                           "created_at": request.created_at.isoformat() if request.created_at else None})
    hospitals = sorted(per_hospital.values(), key=lambda h: (-h["requests"], h["hospital_name"]))
    totals = {
        "requests": sum(h["requests"] for h in hospitals), "hospitals": len(hospitals),
        "units_requested": sum(h["units_requested"] for h in hospitals), "units_secured": sum(h["units_secured"] for h in hospitals),
        "fulfilled_requests": sum(h["fulfilled_requests"] for h in hospitals),
    }
    return {"totals": totals, "hospitals": hospitals, "recent": recent}
