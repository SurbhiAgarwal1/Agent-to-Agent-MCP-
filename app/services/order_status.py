"""The hospital's view of a placed order: who confirmed, how many units, and when the blood should arrive."""
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.match import Match
from app.services import party_service as ps

URBAN_SPEED_KMH = 25.0   # used only when no routed travel time is on record for a source
POSITIVE = {"accepted", "partially_available"}


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _minutes(text: Optional[str]) -> Optional[int]:
    found = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|m\b)", text or "", re.IGNORECASE)
    return max(1, round(float(found.group(1)))) if found else None


def source_profile(source_type: str, source_id: int, cache: dict) -> dict:
    """Name and position of a notified blood bank or donor (cached; a failed lookup just means no name / ETA)."""
    key = (source_type, source_id)
    if key not in cache:
        try:
            if source_type == "BLOOD_BANK":
                d = ps.call("GET", f"{ps.bank_url()}/api/v1/blood-banks/{source_id}")
                cache[key] = {"name": d.get("name"), "latitude": d.get("latitude"), "longitude": d.get("longitude")}
            else:
                d = ps.call("GET", f"{ps.donor_url()}/api/v1/donors/{source_id}")
                cache[key] = {"name": d.get("name"), "latitude": d.get("latitude"), "longitude": d.get("longitude")}
        except HTTPException:
            cache[key] = {"name": None, "latitude": None, "longitude": None}
    return cache[key]


def enrich_matches(matches: list[dict]) -> list[dict]:
    """Replace placeholder source names ('DONOR #660') with the real data-service names (in place)."""
    cache: dict = {}
    for m in matches:
        st, sid = m.get("source_type"), m.get("source_id")
        if not st or sid is None:
            continue
        profile = source_profile(str(st).upper(), int(sid), cache)
        if profile.get("name"):
            m["name"] = profile["name"]
            m["source_name"] = profile["name"]
    return matches


def name_sources(rows: list[dict]) -> None:
    """Put the real name on each response row (in place)."""
    cache: dict = {}
    for row in rows:
        profile = source_profile(row["source_type"], row["source_id"], cache)
        row["source_name"] = profile["name"] or ("Blood bank" if row["source_type"] == "BLOOD_BANK" else "Donor") + f" #{row['source_id']}"


def build_order(db: Session, request: BloodRequest, summary: dict[str, Any]) -> dict[str, Any]:
    hospital = db.get(Hospital, request.hospital_id)
    matches = {(m.source_type, m.source_id): m for m in db.query(Match).filter(Match.request_id == request.request_id).all()}
    cache: dict = {}
    sources = []
    for row in summary.get("responses", []):
        profile = source_profile(row["source_type"], row["source_id"], cache)
        match = matches.get((row["source_type"], row["source_id"]))
        distance, eta = (match.distance_km if match else None), _minutes(match.estimated_time if match else None)
        if (distance is None or eta is None) and hospital and profile["latitude"] is not None and profile["longitude"] is not None:
            distance = round(_km(hospital.latitude, hospital.longitude, profile["latitude"], profile["longitude"]), 1)
            eta = max(1, round(distance / URBAN_SPEED_KMH * 60))
        status = row["response_status"]
        sources.append({
            "source_type": row["source_type"], "source_id": row["source_id"], "notification_id": row.get("notification_id"),
            "name": profile["name"] or ("Blood bank" if row["source_type"] == "BLOOD_BANK" else "Donor") + f" #{row['source_id']}",
            "state": "confirmed" if status in POSITIVE else "waiting" if status == "pending" else "declined",
            "units": row.get("units") if status in POSITIVE else None, "distance_km": distance, "eta_minutes": eta,
            "responded_at": row.get("responded_at"),
        })
    confirmed = [s for s in sources if s["state"] == "confirmed"]
    waiting = [s for s in sources if s["state"] == "waiting"]
    required, got = request.units_required, int(summary.get("confirmed_units", 0))
    etas = [s["eta_minutes"] for s in confirmed if s["eta_minutes"]]
    eta = max(etas) if etas else None                      # all confirmed units are there when the farthest source arrives
    near = min([s for s in waiting + confirmed if s["eta_minutes"]], key=lambda s: s["eta_minutes"], default=None)
    stamps = [datetime.fromisoformat(str(s["responded_at"]).replace("Z", "+00:00")) for s in confirmed if s["responded_at"]]
    anchor = max(stamps) if stamps else None
    if anchor is not None and anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    hosp_name = hospital.name if hospital else f"Hospital #{request.hospital_id}"
    if request.status == "CANCELLED":
        stage, headline = "cancelled", "This request was cancelled."
    elif request.status == "FULFILLED" and request.order_placed_at is not None:
        stage, headline = "delivered", f"Delivered: {got} unit(s) of {request.blood_group} received at {hosp_name}."
    elif request.order_placed_at is None:
        stage, headline = "not_placed", "Order not placed yet. Press Confirm Booking / Place Order to book the blood."
    elif got >= required:
        stage = "confirmed"
        headline = f"Order confirmed: {got} unit(s) of {request.blood_group} will reach {hosp_name} in about {eta} minutes." if eta else \
                   f"Order confirmed: {got} unit(s) of {request.blood_group} are secured for {hosp_name}."
    elif got > 0:
        stage = "partial"
        headline = f"Order placed: {got} of {required} unit(s) confirmed so far. Waiting for {len(waiting)} more source(s) to answer."
    elif waiting:
        stage = "waiting"
        headline = f"Order placed. Waiting for {len(waiting)} blood bank(s) and donor(s) to confirm." + \
                   (f" The nearest, {near['name']}, is about {near['eta_minutes']} min away." if near else "")
    elif not sources:
        stage, headline = "none", "Order placed, but no blood bank or donor has been notified yet. Try Find Available Blood."
    else:
        stage, headline = "declined", "Order placed, but everyone contacted declined. Try Find Available Blood to look for more sources."
    return {
        "request_id": request.request_id, "placed": request.order_placed_at is not None,
        "placed_at": request.order_placed_at.isoformat() if request.order_placed_at else None,
        "stage": stage, "headline": headline, "request_status": request.status,
        "hospital_name": hosp_name, "blood_group": request.blood_group, "units_required": required, "units_confirmed": got,
        "eta_minutes": eta, "nearest_eta_minutes": near["eta_minutes"] if near else None,
        "expected_arrival_at": (anchor + timedelta(minutes=eta)).isoformat() if anchor and eta else None,
        "eta_note": "Travel-time estimate from each source to the hospital; it starts when the last source confirms.",
        "sources": sources,
    }
