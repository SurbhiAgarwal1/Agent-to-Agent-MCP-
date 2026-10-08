"""FastAPI router for hospital blood requests."""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.enums import RequestStatus
from app.schemas.blood_request import (
    BloodRequestCreate,
    BloodRequestStatusUpdate,
    BloodRequestResponse,
)
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent
from app.agents.coordinator_agent import CoordinatorAgent

router = APIRouter()


@router.post(
    "",
    response_model=BloodRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an emergency blood request",
    description=(
        "Enables a registered hospital to lodge an emergency blood request. "
        "Validates that the hospital exists, the blood group is valid, "
        "units required is greater than zero, and assigns an initial 'PENDING' status."
    ),
    responses={
        201: {"description": "Blood request created successfully."},
        404: {"description": "Referenced hospital ID does not exist."},
        422: {"description": "Validation error (invalid blood group, zero units, or invalid urgency)."},
    },
)
def create_blood_request(
    payload: BloodRequestCreate,
    db: Session = Depends(get_db),
):
    """Create a new blood request for a verified hospital."""
    # 1. Verify that the hospital exists in the database
    hospital = db.query(Hospital).filter(Hospital.hospital_id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {payload.hospital_id} not found.",
        )

    # 2. Persist the new blood request with initial status PENDING
    new_request = BloodRequest(
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group.value,
        units_required=payload.units_required,
        urgency=payload.urgency.value,
        status=RequestStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    # Record security & operations audit log (Part 15)
    from app.middleware.audit_log import record_audit_log
    record_audit_log(
        db=db,
        action="CREATE_REQUEST",
        resource="blood_request",
        resource_id=new_request.request_id,
        user_id=getattr(current_user, "id", None) if "current_user" in locals() else None,
        details={
            "hospital_id": payload.hospital_id,
            "blood_group": payload.blood_group.value,
            "units": payload.units_required,
        },
    )

    return new_request


@router.get(
    "",
    response_model=List[BloodRequestResponse],
    summary="List all blood requests",
    description="Retrieves a list of all emergency blood requests across all hospitals, ordered by creation time descending.",
)
def list_blood_requests(
    db: Session = Depends(get_db),
):
    """Retrieve all blood requests."""
    return db.query(BloodRequest).order_by(BloodRequest.created_at.desc()).all()


@router.get(
    "/{request_id}",
    response_model=BloodRequestResponse,
    summary="Get a blood request by ID",
    description="Fetches full details of a specific emergency blood request by its unique request ID.",
    responses={
        200: {"description": "Blood request retrieved successfully."},
        404: {"description": "Blood request not found."},
    },
)
def get_blood_request(
    request_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve an individual blood request by ID."""
    blood_request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if not blood_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blood request with ID {request_id} not found.",
        )

    return blood_request


@router.patch(
    "/{request_id}/status",
    response_model=BloodRequestResponse,
    summary="Update blood request status",
    description=(
        "Updates the lifecycle status of an existing blood request. "
        "Allowed statuses: PENDING, PROCESSING, PARTIALLY_FULFILLED, FULFILLED, CANCELLED."
    ),
    responses={
        200: {"description": "Status updated successfully."},
        404: {"description": "Blood request not found."},
        422: {"description": "Invalid status value."},
    },
)
def update_blood_request_status(
    request_id: int,
    status_update: BloodRequestStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update the status of an existing blood request."""
    blood_request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if not blood_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blood request with ID {request_id} not found.",
        )

    blood_request.status = status_update.status.value
    db.commit()
    db.refresh(blood_request)

    from app.middleware.audit_log import record_audit_log
    record_audit_log(
        db=db,
        action="UPDATE_STATUS",
        resource="blood_request",
        resource_id=blood_request.request_id,
        details={"new_status": status_update.status.value},
    )

    return blood_request


@router.get(
    "/{request_id}/matches",
    summary="Run multi-agent matching pipeline for a blood request",
    description="Executes Requirement Agent, Matching Agent, and Location Agent for the specified request.",
)
def get_request_matches(
    request_id: int,
    db: Session = Depends(get_db),
):
    """Execute end-to-end multi-agent matching pipeline for a blood request."""
    blood_request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if not blood_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blood request with ID {request_id} not found.",
        )

    hospital = db.query(Hospital).filter(Hospital.hospital_id == blood_request.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {blood_request.hospital_id} not found.",
        )

    # 1. Requirement Agent: validate and normalize
    req_agent = RequirementAgent(db=db)
    req_input = {
        "request_id": blood_request.request_id,
        "hospital_id": blood_request.hospital_id,
        "blood_group": blood_request.blood_group,
        "units_required": blood_request.units_required,
        "urgency": blood_request.urgency,
    }
    req_result = req_agent.process(req_input)

    # 2. Matching Agent: find compatible sources
    match_agent = MatchingAgent(db=db)
    match_result = match_agent.find_matches(req_result)

    # 3. Location Agent: compute straight-line distances and ETAs
    loc_agent = LocationAgent()
    enriched_matches = []
    for m in match_result["matches"]:
        source_type = m["source_type"]
        source_id = m["source_id"]
        source_bg = m["blood_group"]
        units = m["units_available"]

        if source_type == "BLOOD_BANK":
            bank = db.query(BloodBank).filter(BloodBank.bank_id == source_id).first()
            name = bank.name if bank else f"Blood Bank #{source_id}"
            address = bank.address if bank else "Central District"
            dest_lat = bank.latitude if bank else hospital.latitude
            dest_lon = bank.longitude if bank else hospital.longitude
        else:
            donor = db.query(Donor).filter(Donor.donor_id == source_id).first()
            name = donor.name if donor else f"Donor #{source_id}"
            address = "Voluntary Donor (Mobile Dispatch)"
            dest_lat = donor.latitude if donor else hospital.latitude
            dest_lon = donor.longitude if donor else hospital.longitude

        loc_info = loc_agent.calculate_distance(
            origin_lat=hospital.latitude,
            origin_lon=hospital.longitude,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            include_eta=True,
        )

        enriched_matches.append({
            "source_type": source_type,
            "source_id": source_id,
            "name": name,
            "address": address,
            "blood_group": source_bg,
            "units_available": units,
            "distance_km": loc_info["distance_km"],
            "estimated_time": loc_info["estimated_time"],
        })

    return {
        "request_id": blood_request.request_id,
        "status": blood_request.status,
        "hospital": {
            "hospital_id": hospital.hospital_id,
            "name": hospital.name,
            "latitude": hospital.latitude,
            "longitude": hospital.longitude,
            "address": hospital.address,
        },
        "requirement_validation": req_result,
        "matches_count": len(enriched_matches),
        "matches": enriched_matches,
    }


@router.post(
    "/{request_id}/orchestrate",
    summary="Trigger Coordinator/Orchestrator Agent for automated blood allocation",
    description=(
        "Executes the autonomous CoordinatorAgent orchestration pipeline: "
        "validates requirements, identifies compatible blood banks/donors, computes proximity and ETAs, "
        "calculates composite multi-criteria priority scores, allocates units to meet requested quota, "
        "persists Match records in the database, and transitions request lifecycle status."
    ),
)
def orchestrate_blood_request(
    request_id: int,
    db: Session = Depends(get_db),
):
    """Execute CoordinatorAgent to autonomously orchestrate, allocate, and persist blood request matches."""
    coordinator = CoordinatorAgent(db=db)
    try:
        result = coordinator.orchestrate(request_id=request_id, persist=True)
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration execution failed: {str(exc)}",
        )


@router.post(
    "/{request_id}/coordinate",
    summary="Coordinate an emergency blood request through the full Coordinator Agent lifecycle",
    description=(
        "Part 9 Coordinator Agent execution: owns the full end-to-end flow "
        "(Requirement -> Matching -> Location -> ranked result), "
        "tracking the request through a formal state machine (RECEIVED -> VALIDATED -> MATCHED -> LOCATED -> COMPLETED) "
        "and persisting candidate matches to the database."
    ),
)
def coordinate_blood_request(
    request_id: int,
    db: Session = Depends(get_db),
):
    """Execute CoordinatorAgent to process, state-track, rank, and persist candidate matches."""
    coordinator = CoordinatorAgent(db=db)
    result = coordinator.coordinate(request_input=request_id, persist=True)
    if not result.get("success"):
        failed_at = result.get("failed_at", "UNKNOWN")
        error_msg = result.get("error", "Coordination failed.")
        if failed_at == "RECEIVED":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coordination halted at {failed_at}: {error_msg}",
        )

    from app.middleware.audit_log import record_audit_log
    record_audit_log(
        db=db,
        action="COORDINATE",
        resource="blood_request",
        resource_id=request_id,
        details={"status": result.get("current_state"), "candidates_count": result.get("candidates_count")},
    )

    return result

