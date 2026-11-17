"""Alert the nearest eligible, blood-compatible donors about a request (they answer in their dashboard)."""
from fastapi import HTTPException

from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.services import party_service as ps
from app.services.compatibility import get_compatible_donor_groups


def alert_donors(db, request: BloodRequest, *, limit: int = 10, radius_km: float = 30) -> dict:
    hospital = db.get(Hospital, request.hospital_id)
    if hospital is None or hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(422, "The hospital has no location, so nearby donors cannot be found.")
    found: dict[int, dict] = {}
    for group in get_compatible_donor_groups(request.blood_group):
        data = ps.call("GET", ps.donor_url() + "/api/v1/donors/nearby", params={
            "latitude": hospital.latitude, "longitude": hospital.longitude, "radius_km": radius_km,
            "blood_group": group, "available": True, "limit": limit})
        for d in data.get("items", []):
            found.setdefault(int(d["id"]), d)
    ranked = sorted(found.values(), key=lambda d: d.get("distance_km") or 0)[:limit]
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
