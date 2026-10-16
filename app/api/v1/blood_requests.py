"""FastAPI router for hospital blood requests."""

from datetime import datetime, timezone
from typing import List
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.hospital import Hospital
from app.models.blood_request import BloodRequest
from app.models.enums import RequestStatus
from app.models.user import User, UserRole
from app.models.membership import HospitalMembership
from app.schemas.blood_request import (
    BloodRequestCreate,
    BloodRequestStatusUpdate,
    BloodRequestResponse,
)
from app.agents.coordinator_agent import CoordinatorAgent
from app.auth.dependencies import get_current_user, require_role
from app.auth.authorization import has_hospital_membership

router = APIRouter()


def _get_authorized_request(db: Session, request_id: int, user: User) -> BloodRequest:
    """Load a request and require active membership in its owning hospital."""
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if user.role != UserRole.ADMIN and not has_hospital_membership(db, user.id, request.hospital_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hospital membership is required.")
    return request


class RejectMatchBody(BaseModel):
    """Optional reason recorded in the audit log when a source is rejected."""
    reason: Optional[str] = Field(default=None, max_length=300)


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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Create a new blood request for a verified hospital."""
    # 1. Verify that the hospital exists in the database
    hospital = db.query(Hospital).filter(Hospital.hospital_id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {payload.hospital_id} not found.",
        )
    if current_user.role != UserRole.ADMIN and not has_hospital_membership(db, current_user.id, hospital.hospital_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active membership in this hospital is required.")

    # 2. Persist the new blood request with initial status PENDING
    new_request = BloodRequest(
        hospital_id=payload.hospital_id,
        created_by_user_id=current_user.id,
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
    from app.services.audit import record_audit_log
    record_audit_log(
        db=db,
        action="CREATE_REQUEST",
        resource="blood_request",
        resource_id=new_request.request_id,
        user_id=current_user.id,
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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Retrieve requests in the caller's permitted scope."""
    query = db.query(BloodRequest)
    if current_user.role != UserRole.ADMIN:
        query = query.join(HospitalMembership, HospitalMembership.hospital_id == BloodRequest.hospital_id).filter(
            HospitalMembership.user_id == current_user.id,
            HospitalMembership.is_active.is_(True),
        )
    return query.order_by(BloodRequest.created_at.desc()).all()


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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Retrieve an individual blood request by ID."""
    blood_request = _get_authorized_request(db, request_id, current_user)

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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Update the status of an existing blood request."""
    blood_request = _get_authorized_request(db, request_id, current_user)

    blood_request.status = status_update.status.value
    db.commit()
    db.refresh(blood_request)

    from app.services.audit import record_audit_log
    record_audit_log(
        db=db,
        action="UPDATE_STATUS",
        resource="blood_request",
        resource_id=blood_request.request_id,
        user_id=current_user.id,
        details={"new_status": status_update.status.value},
    )

    return blood_request


@router.get(
    "/{request_id}/matches",
    summary="Run multi-agent matching pipeline for a blood request",
    description=(
        "Runs the Coordinator preview workflow through the remote Requirement, Matching, and Location agents. "
        "No allocation or notification is persisted for this preview."
    ),
)
def get_request_matches(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Execute end-to-end multi-agent matching pipeline for a blood request."""
    from app.agents.coordinator_helpers import invoke_coordinator_from_gateway

    blood_request = _get_authorized_request(db, request_id, current_user)
    result = invoke_coordinator_from_gateway(db, request_id=request_id, persist=False, mode="coordinate")
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Coordinator could not complete the matching workflow.",
        )
    matches = result["ranked_matches"]

    return {
        "request_id": blood_request.request_id,
        "status": blood_request.status,
        "hospital": result["hospital"],
        "requirement_validation": result["requirement"],
        "matches_count": len(matches),
        "matches": matches,
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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Execute CoordinatorAgent to autonomously orchestrate, allocate, and persist blood request matches."""
    from app.agents.coordinator_helpers import invoke_coordinator_from_gateway

    _get_authorized_request(db, request_id, current_user)
    try:
        result = invoke_coordinator_from_gateway(db, request_id=request_id, persist=True, mode="orchestrate")
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        )
    except Exception as exc:
        import logging
        logging.getLogger("app.errors").error("Orchestration failed", extra={"error_type": type(exc).__name__})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration could not be completed.",
        )
    if not result.get("success"):
        if result.get("failed_at") == "STATE":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request state does not allow orchestration.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Orchestration could not complete its agent workflow.")
    return result


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
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Execute CoordinatorAgent to process, state-track, rank, and persist candidate matches."""
    from app.agents.coordinator_helpers import invoke_coordinator_from_gateway

    _get_authorized_request(db, request_id, current_user)
    result = invoke_coordinator_from_gateway(db, request_id=request_id, persist=True, mode="coordinate")
    from app.services.audit import record_audit_log
    record_audit_log(
        db=db,
        action="COORDINATE",
        resource="blood_request",
        resource_id=request_id,
        user_id=current_user.id,
        details={"status": result.get("current_state"), "candidates_count": result.get("candidates_count"),
                 "success": bool(result.get("success"))},
    )
    if not result.get("success"):
        failed_at = result.get("failed_at", "UNKNOWN")
        if failed_at == "RECEIVED":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Blood request not found.",
            )
        if failed_at == "STATE":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request state does not allow coordination.")
        if failed_at == "VALIDATION":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Blood request validation failed.")
        if failed_at == "MATCHING" and "No compatible blood sources found" in str(result.get("error", "")):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No compatible blood sources are available.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Coordinator could not complete its agent workflow.",
        )

    return result


def _match_action(db, current_user, request_id, match_id, action, audit_name, details=None, **kwargs):
    """Run a match lifecycle action, translating service errors to HTTP errors and auditing success."""
    from app.services import fulfillment_service as fs
    from app.services.audit import record_audit_log
    _get_authorized_request(db, request_id, current_user)
    try:
        result = action(db, request_id, match_id, **kwargs)
    except fs.MatchNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (fs.InvalidMatchState, fs.InsufficientStock) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    record_audit_log(
        db=db,
        action=audit_name,
        resource="match",
        resource_id=match_id,
        user_id=current_user.id,
        details={"request_id": request_id, "request_status": result.get("request_status"), **(details or {})},
    )
    return result


@router.post(
    "/{request_id}/matches/{match_id}/complete",
    summary="Confirm that a reserved match was delivered",
    description=(
        "Marks an ACCEPTED (reserved) match COMPLETED. Blood bank stock is reduced "
        "(earliest-expiring batches first) or the donor starts their donation cool-down, "
        "and the request becomes PARTIALLY_FULFILLED or FULFILLED."
    ),
    responses={404: {"description": "Match not found for this request."},
               409: {"description": "Match is not in a completable state, or stock is no longer sufficient."}},
)
def complete_blood_match(
    request_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    from app.services.fulfillment_service import complete_match
    return _match_action(db, current_user, request_id, match_id, complete_match, "COMPLETE_MATCH")


@router.post(
    "/{request_id}/matches/{match_id}/reject",
    summary="Reject a proposed or reserved match",
    description="Releases the reserved units. The rejected source is not offered again for this request.",
    responses={404: {"description": "Match not found for this request."},
               409: {"description": "Match can no longer be rejected."}},
)
def reject_blood_match(
    request_id: int,
    match_id: int,
    body: Optional[RejectMatchBody] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    from app.services.fulfillment_service import reject_match
    reason = body.reason if body else None
    return _match_action(db, current_user, request_id, match_id, reject_match, "REJECT_MATCH",
                         details={"reason": reason}, reason=reason)
