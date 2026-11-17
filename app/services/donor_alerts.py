"""Alert the nearest eligible, blood-compatible donors about a request (they answer in their dashboard)."""
from fastapi import HTTPException

from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.services import party_service as ps
from app.services.compatibility import get_compatible_donor_groups


def candidates(db, request: BloodRequest, hospital, radius_km: float, limit: int) -> list[dict]:
    """Compatible, available donors near the hospital. Donors who have a login come first (their dashboard can answer), then nearest."""
    from app.models.party_link import PartyLink
    registered = {l.external_id for l in db.query(PartyLink).filter(PartyLink.kind == "donor").all()}
    found: dict[int, dict] = {}
    for group in get_compatible_donor_groups(request.blood_group):
        data = ps.call("GET", ps.donor_url() + "/api/v1/donors/nearby", params={
            "latitude": hospital.latitude, "longitude": hospital.longitude, "radius_km": radius_km,
            "blood_group": group, "available": True, "limit": 200})
        for d in data.get("items", []):
            d["has_login"] = int(d["id"]) in registered
            found.setdefault(int(d["id"]), d)
    return sorted(found.values(), key=lambda d: (not d["has_login"], d.get("distance_km") or 0))[:limit]


def alert_donors(db, request: BloodRequest, *, limit: int = 10, radius_km: float = 50) -> dict:
    hospital = db.get(Hospital, request.hospital_id)
    if hospital is None or hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(422, "The hospital has no location, so nearby donors cannot be found.")
    ranked = candidates(db, request, hospital, radius_km, limit)
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
    return {"request_id": request.request_id, "donors_found": len(ranked), "notified": sent,
            "message": f"Alerted {sent} nearby donor(s)." if sent else "No eligible donors were found nearby."}
