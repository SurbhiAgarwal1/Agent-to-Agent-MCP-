"""Modular helpers for CoordinatorAgent: hospital resolution, scoring, reservations, and Gateway-to-Coordinator A2A."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Coroutine, Dict, List, Optional, Tuple, TypeVar

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.blood_bank import BloodBank
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.enums import MatchSourceType, MatchStatus, RequestStatus
from app.models.hospital import Hospital
from app.models.match import Match
from app.services.fulfillment_service import refresh_request_status
from app.services.scarce_blood_policy import PENALTY_SCORE_POINTS, conservation_factor

T = TypeVar("T")


def is_in_memory_db(db: Optional[Session]) -> bool:
    """Return True if the SQLAlchemy session is bound to an in-memory SQLite database."""
    return bool(
        db is not None
        and getattr(db, "bind", None) is not None
        and ":memory:" in str(getattr(db.bind, "url", ""))
    )


def run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Execute an async coroutine safely from synchronous code even if an event loop is active."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def resolve_hospital_by_location(
    db: Optional[Session],
    location: Optional[str],
) -> Tuple[Optional[Hospital], List[Hospital]]:
    """Resolve a hospital from natural-language location text with exact-match priority and ambiguity detection.

    Returns:
        Tuple of (resolved_hospital_or_None, all_matching_hospitals).
        - (Hospital, [Hospital]) when uniquely resolved.
        - (None, [H1, H2, ...]) when multiple hospitals match ambiguously.
        - (None, []) when no hospital matches.
    """
    if db is None or not location or not location.strip():
        return None, []

    cleaned = location.strip()
    exact_matches = (
        db.query(Hospital)
        .filter(func.lower(Hospital.name) == cleaned.lower())
        .order_by(Hospital.hospital_id.asc())
        .all()
    )
    if len(exact_matches) == 1:
        return exact_matches[0], exact_matches
    if len(exact_matches) > 1:
        return None, exact_matches

    needle = f"%{cleaned}%"
    name_matches = (
        db.query(Hospital)
        .filter(Hospital.name.ilike(needle))
        .order_by(Hospital.hospital_id.asc())
        .all()
    )
    if len(name_matches) == 1:
        return name_matches[0], name_matches
    if len(name_matches) > 1:
        return None, name_matches

    address_matches = (
        db.query(Hospital)
        .filter(or_(Hospital.name.ilike(needle), Hospital.address.ilike(needle)))
        .order_by(Hospital.hospital_id.asc())
        .all()
    )
    if len(address_matches) == 1:
        return address_matches[0], address_matches
    return None, address_matches


def calculate_priority_score(
    distance_km: float,
    source_type: str,
    is_exact_match: bool,
    urgency: str,
    source_blood_group: Optional[str] = None,
    recipient_blood_group: Optional[str] = None,
) -> float:
    """Calculate composite priority score (0 to 100 points)."""
    proximity_score = max(0.0, 40.0 - (distance_km * 0.8))
    source_score = 25.0 if source_type == MatchSourceType.BLOOD_BANK.value else 15.0
    compat_score = 20.0 if is_exact_match else 10.0
    urgency_upper = (urgency or "").upper()
    if urgency_upper == "CRITICAL":
        urgency_score = 15.0
    elif urgency_upper == "HIGH":
        urgency_score = 12.0
    elif urgency_upper == "MEDIUM":
        urgency_score = 8.0
    else:
        urgency_score = 5.0
    total_score = proximity_score + source_score + compat_score + urgency_score
    total_score -= PENALTY_SCORE_POINTS * conservation_factor(
        source_blood_group, recipient_blood_group, urgency
    )
    return round(min(100.0, max(0.0, total_score)), 2)


def resolve_candidate_coordinates(
    db: Optional[Session],
    candidates: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Enrich candidate sources with coordinates, name, and address from the database when needed."""
    located_input: List[Dict[str, Any]] = []
    for cand in candidates:
        c_dict = dict(cand)
        dest_lat = c_dict.get("latitude")
        dest_lon = c_dict.get("longitude")

        if (dest_lat is None or dest_lon is None) and db is not None:
            s_type = c_dict["source_type"]
            s_id = c_dict["source_id"]
            if s_type == MatchSourceType.BLOOD_BANK.value:
                bank = db.query(BloodBank).filter(BloodBank.bank_id == s_id).first()
                if bank:
                    dest_lat = bank.latitude
                    dest_lon = bank.longitude
                    c_dict["name"] = bank.name
                    c_dict["address"] = bank.address
            else:
                donor = db.query(Donor).filter(Donor.donor_id == s_id).first()
                if donor:
                    dest_lat = donor.latitude
                    dest_lon = donor.longitude
                    c_dict["name"] = donor.name
                    c_dict["address"] = "Voluntary Donor (Mobile Dispatch)"

        if dest_lat is None or dest_lon is None:
            return [], f"Missing coordinates for candidate source {c_dict['source_type']} #{c_dict['source_id']}."

        c_dict["latitude"] = dest_lat
        c_dict["longitude"] = dest_lon
        located_input.append(c_dict)

    return located_input, None


def persist_reservations(
    db: Session,
    blood_request_model: BloodRequest,
    annotated_candidates: List[Dict[str, Any]],
    fulfillment_plan: Dict[str, Any],
) -> str:
    """Persist Match proposals and unit holds (reservations) and refresh request status."""
    planned_units = {
        (p["source_type"], p["source_id"], p.get("blood_group")): p["units"]
        for p in fulfillment_plan["plan"]
    }
    db.query(Match).filter(
        Match.request_id == blood_request_model.request_id,
        Match.status.in_([MatchStatus.PROPOSED.value, MatchStatus.ACCEPTED.value]),
    ).delete(synchronize_session=False)

    for cand in annotated_candidates:
        units = planned_units.get((cand["source_type"], cand["source_id"], cand.get("blood_group")))
        match_row = Match(
            request_id=blood_request_model.request_id,
            source_type=cand["source_type"],
            source_id=cand["source_id"],
            distance_km=cand["distance_km"],
            estimated_time=cand.get("estimated_time"),
            priority_score=cand["priority_score"],
            blood_group=cand.get("blood_group"),
            units=units,
            status=MatchStatus.ACCEPTED.value if units else MatchStatus.PROPOSED.value,
        )
        db.add(match_row)
        db.flush()
        cand["match_id"] = match_row.match_id
        cand["status"] = match_row.status
        if units:
            cand["units_reserved"] = units

    for entry in fulfillment_plan["plan"]:
        for cand in annotated_candidates:
            if (cand["source_type"], cand["source_id"], cand.get("blood_group")) == (
                entry["source_type"],
                entry["source_id"],
                entry.get("blood_group"),
            ):
                entry["match_id"] = cand["match_id"]

    request_status = refresh_request_status(db, blood_request_model.request_id)
    if (
        request_status == RequestStatus.PROCESSING.value
        and fulfillment_plan["details"]["units_shortage"] > 0
    ):
        blood_request_model.status = RequestStatus.PARTIALLY_FULFILLED.value
        request_status = blood_request_model.status
    db.commit()
    db.refresh(blood_request_model)
    return request_status


def format_orchestration_view(
    request_id: int,
    blood_request: BloodRequest,
    hospital: Hospital,
    result: Dict[str, Any],
    persist: bool,
) -> Dict[str, Any]:
    """Reshape a CoordinatorAgent.coordinate result into the allocation-oriented orchestration view."""
    hospital_info = {
        "hospital_id": hospital.hospital_id,
        "name": hospital.name,
        "address": hospital.address,
        "latitude": hospital.latitude,
        "longitude": hospital.longitude,
    }
    step_for_state = {
        "RECEIVED": "INIT",
        "VALIDATED": "REQUIREMENT_AGENT",
        "MATCHED": "MATCHING_AGENT",
        "LOCATED": "LOCATION_AND_RANKING",
        "COMPLETED": "ALLOCATION_ENGINE",
        "FAILED": "FAILED",
    }
    execution_log = [
        {
            "timestamp": h["timestamp"],
            "step": step_for_state.get(h["state"], h["state"]),
            "message": h["detail"],
        }
        for h in result.get("state_history", [])
    ]

    if not result.get("success"):
        if result.get("failed_at") == "MATCHING":
            return {
                "success": True,
                "request_id": request_id,
                "fulfillment_status": "UNFULFILLED",
                "units_required": blood_request.units_required,
                "units_allocated": 0,
                "hospital": hospital_info,
                "allocated_sources": [],
                "standby_sources": [],
                "execution_log": execution_log,
            }
        return {
            "success": False,
            "request_id": request_id,
            "failed_at": result.get("failed_at"),
            "error": result.get("error"),
            "details": result.get("details"),
            "execution_log": execution_log,
            "a2a_trace": result.get("a2a_trace", []),
        }

    plan = result["fulfillment_plan"]
    by_key = {
        (c["source_type"], c["source_id"], c.get("blood_group")): c
        for c in result["ranked_matches"]
    }
    allocated, planned_keys = [], set()
    for entry in plan["plan"]:
        key = (entry["source_type"], entry["source_id"], entry.get("blood_group"))
        planned_keys.add(key)
        record = dict(by_key.get(key, entry))
        record["units_allocated"] = entry["units"]
        allocated.append(record)
    standby = [c for k, c in by_key.items() if k not in planned_keys]
    status = "FULFILLED" if plan["status"] == "FULLY_FULFILLED" else plan["status"]
    execution_log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "PERSISTENCE" if persist else "PERSISTENCE_SKIPPED",
            "message": (
                f"{len(allocated)} source(s) reserved; request status '{result.get('request_status')}'."
                if persist
                else "persist=False: nothing written."
            ),
        }
    )
    return {
        "success": True,
        "request_id": request_id,
        "fulfillment_status": status,
        "request_status": result.get("request_status"),
        "units_required": result["requirement"]["units_required"],
        "units_allocated": plan["total_units"],
        "hospital": hospital_info,
        "allocated_sources": allocated,
        "standby_sources": standby,
        "execution_log": execution_log,
        "a2a_trace": result.get("a2a_trace", []),
    }


def should_call_coordinator_over_a2a(db: Optional[Session]) -> bool:
    """Return True when the Gateway should invoke the Coordinator Agent over A2A HTTP."""
    import os

    if is_in_memory_db(db):
        return False
    if os.getenv("COORDINATOR_IN_PROCESS", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return bool(
        os.getenv("COORDINATORAGENT_BASE_URL", "").strip()
        or os.getenv("COORDINATORAGENT_A2A_URL", "").strip()
        or os.getenv("COORDINATOR_USE_A2A", "").strip().lower() in {"1", "true", "yes"}
    )


def invoke_coordinator_from_gateway(
    db: Session,
    *,
    request_id: int,
    persist: bool = True,
    mode: str = "coordinate",
) -> Dict[str, Any]:
    """Invoke Coordinator over A2A when configured, with seamless local CoordinatorAgent fallback."""
    import os
    from app.agents.coordinator_agent import CoordinatorAgent

    if should_call_coordinator_over_a2a(db):
        from app.agents.a2a.client import call_remote_agent

        payload: Dict[str, Any] = {
            "request_id": request_id,
            "persist": persist,
            "mode": mode,
            "return_structured_failure": True,
        }
        try:
            result = run_coro_sync(
                call_remote_agent(
                    "COORDINATORAGENT",
                    payload,
                    skill="coordinate",
                    operation="COORDINATE_REQUEST",
                )
            )
            db.expire_all()
            return result
        except Exception:
            if os.getenv("COORDINATOR_REQUIRE_A2A", "").strip().lower() in {"1", "true", "yes"}:
                raise

    coordinator = CoordinatorAgent(db=db, network=True)
    if mode == "orchestrate":
        return coordinator.orchestrate(request_id=request_id, persist=persist)
    return coordinator.coordinate(request_input=request_id, persist=persist)

