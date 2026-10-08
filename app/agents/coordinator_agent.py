"""Coordinator Agent for Blood Donation Matching System (Part 9).

The CoordinatorAgent owns the end-to-end lifecycle for an emergency blood request:
Requirement -> Matching -> Location -> Final Ranked Result (distance ascending),
tracking the request through a formal state machine and persisting results to the database.
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.match import Match
from app.models.enums import RequestStatus, MatchStatus, MatchSourceType
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent
from app.agents.a2a.bus import MessageBus
from app.agents.a2a.message import A2AMessage, A2AMessageType


class CoordinatorState(str, Enum):
    """Lifecycle states of a request within the Coordinator Agent."""
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    MATCHED = "MATCHED"
    LOCATED = "LOCATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CoordinatorAgent:
    """Coordinator Agent managing end-to-end multi-agent execution, state machine, and persistence."""

    def __init__(
        self,
        db: Optional[Session] = None,
        bus: Optional[MessageBus] = None,
    ):
        """Initialize Coordinator Agent.
        
        Args:
            db: Optional SQLAlchemy Session.
            bus: Optional MessageBus instance for A2A communication.
        """
        self.db = db
        self.bus = bus or MessageBus()
        self.req_agent = RequirementAgent(db=self.db, bus=self.bus)
        self.match_agent = MatchingAgent(db=self.db, bus=self.bus)
        self.loc_agent = LocationAgent(bus=self.bus)

    def calculate_priority_score(
        self,
        distance_km: float,
        source_type: str,
        is_exact_match: bool,
        urgency: str,
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
        return round(min(100.0, max(0.0, total_score)), 2)

    def orchestrate(
        self,
        request_id: int,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Execute end-to-end orchestration for an emergency blood request."""
        if not self.db:
            raise ValueError("CoordinatorAgent requires an active database session for orchestration.")

        execution_log = []
        now_str = datetime.now(timezone.utc).isoformat()

        # Step 1: Fetch Blood Request & Hospital
        blood_request = self.db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
        if not blood_request:
            raise ValueError(f"Blood request #{request_id} not found.")

        hospital = self.db.query(Hospital).filter(Hospital.hospital_id == blood_request.hospital_id).first()
        if not hospital:
            raise ValueError(f"Hospital #{blood_request.hospital_id} referenced by request #{request_id} not found.")

        execution_log.append({
            "timestamp": now_str,
            "step": "INIT",
            "message": f"Orchestrator initiated for Request #{request_id} from Hospital '{hospital.name}' ({blood_request.units_required} units of {blood_request.blood_group}, Urgency: {blood_request.urgency}).",
        })

        # Step 2: Requirement Agent Validation & Normalization
        req_agent = RequirementAgent(db=self.db)
        req_input = {
            "request_id": blood_request.request_id,
            "hospital_id": blood_request.hospital_id,
            "blood_group": blood_request.blood_group,
            "units_required": blood_request.units_required,
            "urgency": blood_request.urgency,
        }
        req_result = req_agent.process(req_input)

        if not req_result.get("valid"):
            execution_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": "REQUIREMENT_VALIDATION_FAILED",
                "message": f"Requirement validation failed: {req_result.get('errors')}",
            })
            return {
                "success": False,
                "request_id": request_id,
                "error": "Requirement validation failed",
                "details": req_result.get("errors"),
                "execution_log": execution_log,
            }

        execution_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "REQUIREMENT_AGENT",
            "message": f"Requirement normalized and validated: Blood Group {req_result['blood_group']}, {req_result['units_required']} units.",
        })

        # Step 3: Matching Agent - Candidate Discovery
        match_agent = MatchingAgent(db=self.db)
        match_result = match_agent.find_matches(req_result)
        raw_candidates = match_result.get("matches", [])

        execution_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "MATCHING_AGENT",
            "message": f"Matching Agent identified {len(raw_candidates)} compatible candidates ({len(match_result.get('compatible_groups', []))} compatible blood groups).",
        })

        # Step 4: Location Agent - Distance, ETA & Composite Scoring
        loc_agent = LocationAgent()
        enriched_candidates = []
        for cand in raw_candidates:
            source_type = cand["source_type"]
            source_id = cand["source_id"]
            source_bg = cand["blood_group"]
            avail_units = cand["units_available"]

            if source_type == MatchSourceType.BLOOD_BANK.value:
                bank = self.db.query(BloodBank).filter(BloodBank.bank_id == source_id).first()
                name = bank.name if bank else f"Blood Bank #{source_id}"
                address = bank.address if bank else "Central District"
                dest_lat = bank.latitude if bank else hospital.latitude
                dest_lon = bank.longitude if bank else hospital.longitude
            else:
                donor = self.db.query(Donor).filter(Donor.donor_id == source_id).first()
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

            is_exact = (source_bg == req_result["blood_group"])
            dist_km = loc_info["distance_km"]
            score = self.calculate_priority_score(
                distance_km=dist_km,
                source_type=source_type,
                is_exact_match=is_exact,
                urgency=req_result["urgency"],
            )

            enriched_candidates.append({
                "source_type": source_type,
                "source_id": source_id,
                "name": name,
                "address": address,
                "blood_group": source_bg,
                "is_exact_match": is_exact,
                "units_available": avail_units,
                "distance_km": dist_km,
                "estimated_time": loc_info["estimated_time"],
                "priority_score": score,
            })

        enriched_candidates.sort(key=lambda x: (-x["priority_score"], x["distance_km"]))

        execution_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "LOCATION_AND_RANKING",
            "message": f"Calculated ETAs and prioritized {len(enriched_candidates)} candidates via multi-criteria composite scoring.",
        })

        # Step 5: Resource Allocation Planning
        units_needed = req_result["units_required"]
        remaining = units_needed
        allocated_sources = []
        standby_sources = []

        for cand in enriched_candidates:
            if remaining > 0:
                units_allocated = min(cand["units_available"], remaining)
                remaining -= units_allocated
                allocated_record = dict(cand)
                allocated_record["units_allocated"] = units_allocated
                allocated_sources.append(allocated_record)
            else:
                standby_sources.append(cand)

        total_allocated = units_needed - remaining
        if total_allocated >= units_needed:
            fulfillment_status = "FULFILLED"
        elif total_allocated > 0:
            fulfillment_status = "PARTIALLY_FULFILLED"
        else:
            fulfillment_status = "UNFULFILLED"

        execution_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "ALLOCATION_ENGINE",
            "message": f"Resource Allocation Plan formulated: {total_allocated}/{units_needed} units allocated across {len(allocated_sources)} source(s). Status: {fulfillment_status}.",
        })

        # Step 6: Database Persistence
        if persist:
            self.db.query(Match).filter(Match.request_id == request_id).delete()
            for item in allocated_sources:
                match_entry = Match(
                    request_id=request_id,
                    source_type=item["source_type"],
                    source_id=item["source_id"],
                    distance_km=item["distance_km"],
                    estimated_time=item["estimated_time"],
                    priority_score=item["priority_score"],
                    status=MatchStatus.ACCEPTED.value,
                )
                self.db.add(match_entry)
                self.db.flush()
                item["match_id"] = match_entry.match_id

            for item in standby_sources:
                match_entry = Match(
                    request_id=request_id,
                    source_type=item["source_type"],
                    source_id=item["source_id"],
                    distance_km=item["distance_km"],
                    estimated_time=item["estimated_time"],
                    priority_score=item["priority_score"],
                    status=MatchStatus.PROPOSED.value,
                )
                self.db.add(match_entry)
                self.db.flush()
                item["match_id"] = match_entry.match_id

            if fulfillment_status == "FULFILLED":
                blood_request.status = RequestStatus.FULFILLED.value
            elif fulfillment_status == "PARTIALLY_FULFILLED":
                blood_request.status = RequestStatus.PARTIALLY_FULFILLED.value
            else:
                blood_request.status = RequestStatus.PROCESSING.value

            self.db.commit()
            self.db.refresh(blood_request)

            execution_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": "PERSISTENCE",
                "message": f"Committed {len(allocated_sources)} accepted matches and updated BloodRequest #{request_id} to '{blood_request.status}'.",
            })

        return {
            "success": True,
            "request_id": request_id,
            "fulfillment_status": fulfillment_status,
            "units_required": units_needed,
            "units_allocated": total_allocated,
            "hospital": {
                "hospital_id": hospital.hospital_id,
                "name": hospital.name,
                "address": hospital.address,
                "latitude": hospital.latitude,
                "longitude": hospital.longitude,
            },
            "allocated_sources": allocated_sources,
            "standby_sources": standby_sources,
            "execution_log": execution_log,
        }

    def coordinate(
        self,
        request_input: Union[int, Dict[str, Any], BloodRequest],
        correlation_id: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Execute end-to-end coordination workflow for a blood request.
        
        State machine:
            RECEIVED -> VALIDATED -> MATCHED -> LOCATED -> COMPLETED (or FAILED)
            
        Args:
            request_input: Blood request ID, dictionary, or BloodRequest instance.
            correlation_id: Optional correlation ID for message bus tracing.
            persist: Whether to commit candidate matches to the SQLite database.
            
        Returns:
            Dictionary containing state machine transitions, ranked candidate matches, and status.
        """
        state_history = []
        now_iso = lambda: datetime.now(timezone.utc).isoformat()

        def log_transition(state: CoordinatorState, detail: str):
            state_history.append({
                "state": state.value,
                "timestamp": now_iso(),
                "detail": detail,
            })

        # ---------------------------------------------------------------------
        # Step 1: State = RECEIVED
        # ---------------------------------------------------------------------
        current_state = CoordinatorState.RECEIVED
        log_transition(current_state, "Blood request received by Coordinator Agent.")

        blood_request_model: Optional[BloodRequest] = None
        raw_payload: Dict[str, Any] = {}

        if isinstance(request_input, int):
            if not self.db:
                current_state = CoordinatorState.FAILED
                log_transition(current_state, "Database session required when providing request_id as integer.")
                return self._failure_response(
                    request_id=request_input,
                    failed_at="RECEIVED",
                    error="Database session required to fetch request by ID.",
                    state_history=state_history,
                )
            blood_request_model = self.db.query(BloodRequest).filter(BloodRequest.request_id == request_input).first()
            if not blood_request_model:
                current_state = CoordinatorState.FAILED
                log_transition(current_state, f"BloodRequest #{request_input} not found in database.")
                return self._failure_response(
                    request_id=request_input,
                    failed_at="RECEIVED",
                    error=f"BloodRequest #{request_input} not found.",
                    state_history=state_history,
                )
            raw_payload = {
                "request_id": blood_request_model.request_id,
                "hospital_id": blood_request_model.hospital_id,
                "blood_group": blood_request_model.blood_group,
                "units_required": blood_request_model.units_required,
                "urgency": blood_request_model.urgency,
            }
        elif isinstance(request_input, BloodRequest):
            blood_request_model = request_input
            raw_payload = {
                "request_id": request_input.request_id,
                "hospital_id": request_input.hospital_id,
                "blood_group": request_input.blood_group,
                "units_required": request_input.units_required,
                "urgency": request_input.urgency,
            }
        elif isinstance(request_input, dict):
            raw_payload = dict(request_input)
            req_id = raw_payload.get("request_id")
            if req_id and self.db:
                blood_request_model = self.db.query(BloodRequest).filter(BloodRequest.request_id == req_id).first()
        else:
            current_state = CoordinatorState.FAILED
            log_transition(current_state, f"Invalid request input type: {type(request_input).__name__}")
            return self._failure_response(
                request_id=None,
                failed_at="RECEIVED",
                error="Invalid input format.",
                state_history=state_history,
            )

        req_id = raw_payload.get("request_id", 1)
        corr_id = correlation_id or f"coord-{req_id}-{uuid.uuid4().hex[:8]}"

        # ---------------------------------------------------------------------
        # Step 2: State = VALIDATED (Requirement Agent)
        # ---------------------------------------------------------------------
        validation_result = self.req_agent.process(raw_payload)
        if not validation_result.get("valid"):
            current_state = CoordinatorState.FAILED
            error_msg = f"Requirement validation failed: {', '.join(validation_result.get('errors', []))}"
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id,
                failed_at="VALIDATION",
                error=error_msg,
                details=validation_result.get("errors"),
                state_history=state_history,
                correlation_id=corr_id,
            )

        current_state = CoordinatorState.VALIDATED
        log_transition(
            current_state,
            f"Requirement validated: {validation_result['units_required']} units of {validation_result['blood_group']}, Urgency: {validation_result['urgency']}."
        )

        # ---------------------------------------------------------------------
        # Step 3: State = MATCHED (Matching Agent)
        # ---------------------------------------------------------------------
        matches_result = self.match_agent.find_matches(
            request_data=validation_result,
            inventories=raw_payload.get("inventories"),
            donors=raw_payload.get("donors"),
        )
        candidates = matches_result.get("matches", [])
        if not candidates:
            current_state = CoordinatorState.FAILED
            error_msg = f"No compatible blood sources found for blood group '{validation_result['blood_group']}'."
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id,
                failed_at="MATCHING",
                error=error_msg,
                state_history=state_history,
                correlation_id=corr_id,
            )

        current_state = CoordinatorState.MATCHED
        log_transition(current_state, f"Matching Agent identified {len(candidates)} compatible candidate source(s).")

        # ---------------------------------------------------------------------
        # Step 4: State = LOCATED (Location Agent)
        # ---------------------------------------------------------------------
        hospital_id = raw_payload.get("hospital_id")
        hosp_lat = raw_payload.get("hospital_latitude")
        hosp_lon = raw_payload.get("hospital_longitude")
        hosp_name = "Emergency Facility"
        hosp_address = "Medical District"

        if (hosp_lat is None or hosp_lon is None) and self.db and hospital_id:
            hosp_record = self.db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()
            if hosp_record:
                hosp_lat = hosp_record.latitude
                hosp_lon = hosp_record.longitude
                hosp_name = hosp_record.name
                hosp_address = hosp_record.address

        if hosp_lat is None or hosp_lon is None:
            current_state = CoordinatorState.FAILED
            error_msg = f"Hospital coordinates unavailable for hospital #{hospital_id}."
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id,
                failed_at="LOCATION",
                error=error_msg,
                state_history=state_history,
                correlation_id=corr_id,
            )

        annotated_candidates = []
        for cand in candidates:
            c_dict = dict(cand)
            dest_lat = c_dict.get("latitude")
            dest_lon = c_dict.get("longitude")

            if (dest_lat is None or dest_lon is None) and self.db:
                s_type = c_dict["source_type"]
                s_id = c_dict["source_id"]
                if s_type == MatchSourceType.BLOOD_BANK.value:
                    bank = self.db.query(BloodBank).filter(BloodBank.bank_id == s_id).first()
                    if bank:
                        dest_lat = bank.latitude
                        dest_lon = bank.longitude
                        c_dict["name"] = bank.name
                        c_dict["address"] = bank.address
                else:
                    donor = self.db.query(Donor).filter(Donor.donor_id == s_id).first()
                    if donor:
                        dest_lat = donor.latitude
                        dest_lon = donor.longitude
                        c_dict["name"] = donor.name
                        c_dict["address"] = "Voluntary Donor (Mobile Dispatch)"

            if dest_lat is None or dest_lon is None:
                current_state = CoordinatorState.FAILED
                error_msg = f"Missing coordinates for candidate source {c_dict['source_type']} #{c_dict['source_id']}."
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id,
                    failed_at="LOCATION",
                    error=error_msg,
                    state_history=state_history,
                    correlation_id=corr_id,
                )

            try:
                dist_info = self.loc_agent.calculate_distance(
                    origin_lat=float(hosp_lat),
                    origin_lon=float(hosp_lon),
                    dest_lat=float(dest_lat),
                    dest_lon=float(dest_lon),
                    include_eta=True,
                )
                c_dict["distance_km"] = dist_info["distance_km"]
                c_dict["estimated_time"] = dist_info["estimated_time"]
                annotated_candidates.append(c_dict)
            except Exception as loc_err:
                current_state = CoordinatorState.FAILED
                error_msg = f"Location calculation failed for candidate #{c_dict['source_id']}: {loc_err}"
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id,
                    failed_at="LOCATION",
                    error=error_msg,
                    state_history=state_history,
                    correlation_id=corr_id,
                )

        # Rank candidates strictly by distance ascending
        annotated_candidates.sort(key=lambda c: c["distance_km"])

        current_state = CoordinatorState.LOCATED
        log_transition(
            current_state,
            f"Location Agent computed distances for {len(annotated_candidates)} candidates. Ranked nearest-first."
        )

        # ---------------------------------------------------------------------
        # Step 5: State = COMPLETED & Database Persistence
        # ---------------------------------------------------------------------
        if persist and self.db and blood_request_model:
            # Clean existing provisional matches for this request
            self.db.query(Match).filter(Match.request_id == blood_request_model.request_id).delete()

            for cand in annotated_candidates:
                match_row = Match(
                    request_id=blood_request_model.request_id,
                    source_type=cand["source_type"],
                    source_id=cand["source_id"],
                    distance_km=cand["distance_km"],
                    estimated_time=cand.get("estimated_time"),
                    priority_score=round(cand["distance_km"], 2),
                    status=MatchStatus.PROPOSED.value,
                )
                self.db.add(match_row)
                self.db.flush()
                cand["match_id"] = match_row.match_id

            blood_request_model.status = RequestStatus.PROCESSING.value
            self.db.commit()
            self.db.refresh(blood_request_model)

        current_state = CoordinatorState.COMPLETED
        log_transition(current_state, "Coordination completed successfully. Results ranked and persisted.")

        # Generate multi-source fulfillment plan using Optimization Engine (Part 10)
        from app.services.optimization_service import OptimizationService
        opt_service = OptimizationService()
        fulfillment_plan = opt_service.optimize(
            request_id=req_id,
            units_required=validation_result.get("units_required", 1),
            urgency=validation_result.get("urgency", "MEDIUM"),
            candidates=annotated_candidates,
        )

        # Dispatch alerts via Notification Agent (Part 12)
        from app.agents.notification_agent import NotificationAgent
        notif_agent = NotificationAgent()
        notifications_result = notif_agent.notify_plan(
            hospital_id=hospital_id or 1,
            request_id=req_id,
            fulfillment_plan=fulfillment_plan,
            hospital_name=hosp_name,
        )

        return {
            "success": True,
            "current_state": current_state.value,
            "correlation_id": corr_id,
            "request_id": req_id,
            "hospital": {
                "hospital_id": hospital_id,
                "name": hosp_name,
                "address": hosp_address,
                "latitude": hosp_lat,
                "longitude": hosp_lon,
            },
            "requirement": validation_result,
            "candidates_count": len(annotated_candidates),
            "ranked_matches": annotated_candidates,
            "fulfillment_plan": fulfillment_plan,
            "notifications": notifications_result,
            "state_history": state_history,
        }

    @staticmethod
    def _failure_response(
        request_id: Optional[int],
        failed_at: str,
        error: str,
        state_history: List[Dict[str, Any]],
        details: Optional[Any] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate structured error response halting coordination gracefully."""
        return {
            "success": False,
            "current_state": CoordinatorState.FAILED.value,
            "correlation_id": correlation_id or f"err-{uuid.uuid4().hex[:8]}",
            "request_id": request_id,
            "failed_at": failed_at,
            "error": error,
            "details": details,
            "state_history": state_history,
        }
