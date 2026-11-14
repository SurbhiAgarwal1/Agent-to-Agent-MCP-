"""Bring blood bank / donor responses back to the hospital that asked.

Responses are stored by the independent data APIs. They reach the hospital two ways:
  * push - the data API calls ``POST /api/v1/internal/response-events`` right after a response;
  * pull - ``GET /api/v1/blood-requests/{id}/responses`` re-reads the data APIs (covers a missed push).
Both paths go through ``ingest_response`` so an alert is created exactly once per notification.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.blood_request import BloodRequest
from app.models.hospital_alert import HospitalAlert
from app.security.service_auth import service_auth_headers

ANSWERED = {"accepted", "partially_available", "rejected", "unavailable", "declined"}
POSITIVE = {"accepted", "partially_available"}


def _describe(source_type: str, name: str | None, status: str, units: int | None, reason: str | None) -> str:
    who = name or ("A blood bank" if source_type == "BLOOD_BANK" else "A donor")
    if status == "accepted":
        return f"{who} accepted" + (f" and confirmed {units} unit(s)." if units else " the request.")
    if status == "partially_available":
        return f"{who} can supply {units} unit(s) only."
    return f"{who} could not help" + (f": {reason}" if reason else ".")


def ingest_response(
    db: Session, *, request_id: int, source_type: str, source_id: int, notification_id: int,
    response_status: str, confirmed_units: int | None = None, reason: str | None = None, source_name: str | None = None,
) -> tuple[HospitalAlert | None, bool]:
    """Create the alert for one response. Returns (alert, created); (None, False) if it is not actionable."""
    if response_status not in ANSWERED:
        return None, False
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None:
        return None, False
    existing = db.query(HospitalAlert).filter_by(source_type=source_type, notification_id=notification_id).first()
    if existing:
        return existing, False
    alert = HospitalAlert(
        hospital_id=request.hospital_id, request_id=request_id, source_type=source_type, source_id=source_id,
        source_name=source_name, notification_id=notification_id, response_status=response_status,
        confirmed_units=confirmed_units, message=_describe(source_type, source_name, response_status, confirmed_units, reason),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert, True


def _fetch(base: str, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    response = httpx.get(base.rstrip("/") + path, params=params, headers=service_auth_headers(), timeout=float(os.getenv("DATA_API_TIMEOUT_SECONDS", "8")))
    response.raise_for_status()
    return response.json().get("items", [])


def fetch_notifications(request_id: int) -> dict[str, Any]:
    """Read every notification (and its response) for a request from the two data APIs."""
    bank_url = os.getenv("BLOOD_BANK_API_URL", "http://127.0.0.1:8105")
    donor_url = os.getenv("DONOR_API_URL", "http://127.0.0.1:8106")
    out: dict[str, Any] = {"banks": [], "donors": [], "errors": []}
    try:
        out["banks"] = _fetch(bank_url, "/api/v1/blood-bank-notifications", {"blood_request_id": request_id, "limit": 500})
    except (httpx.HTTPError, ValueError) as exc:
        out["errors"].append(f"blood bank data API unavailable: {type(exc).__name__}")
    try:
        out["donors"] = _fetch(donor_url, "/api/v1/donor-notifications", {"blood_request_id": request_id, "limit": 500})
    except (httpx.HTTPError, ValueError) as exc:
        out["errors"].append(f"donor data API unavailable: {type(exc).__name__}")
    return out


def summarize(db: Session, request: BloodRequest, fetched: dict[str, Any]) -> dict[str, Any]:
    """Sync alerts from fetched notifications and return the hospital's view of all responses."""
    rows: list[dict[str, Any]] = []
    for item in fetched["banks"]:
        rows.append({"source_type": "BLOOD_BANK", "source_id": item["blood_bank_id"], "notification_id": item["id"],
                     "response_status": item.get("response_status", "pending"), "units": item.get("confirmed_available_units"),
                     "reason": item.get("rejection_reason"), "responded_at": item.get("response_at")})
    for item in fetched["donors"]:
        rows.append({"source_type": "DONOR", "source_id": item["donor_id"], "notification_id": item["id"],
                     "response_status": item.get("response_status", "pending"), "units": 1 if item.get("response_status") == "accepted" else None,
                     "reason": None, "responded_at": item.get("response_at")})
    for row in rows:
        ingest_response(db, request_id=request.request_id, source_type=row["source_type"], source_id=row["source_id"],
                        notification_id=row["notification_id"], response_status=row["response_status"],
                        confirmed_units=row["units"], reason=row["reason"])
    accepted = [r for r in rows if r["response_status"] in POSITIVE]
    confirmed_units = sum(int(r["units"] or 0) for r in accepted)
    return {
        "request_id": request.request_id,
        "units_required": request.units_required,
        "confirmed_units": confirmed_units,
        "is_covered": confirmed_units >= request.units_required,
        "counts": {
            "notified": len(rows),
            "pending": sum(r["response_status"] == "pending" for r in rows),
            "accepted": sum(r["response_status"] == "accepted" for r in rows),
            "partially_available": sum(r["response_status"] == "partially_available" for r in rows),
            "declined_or_unavailable": sum(r["response_status"] in {"rejected", "unavailable", "declined"} for r in rows),
        },
        "accepted": accepted,
        "responses": rows,
        "warnings": fetched["errors"],
    }
