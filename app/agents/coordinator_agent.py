"""Coordinator Agent for Blood Donation Matching System (Part 9).

The CoordinatorAgent owns the end-to-end lifecycle for an emergency blood request:
Requirement -> Matching -> Location -> Final Ranked Result (distance ascending),
tracking the request through a formal state machine and persisting results to the database.
"""

import uuid
from contextlib import nullcontext
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
from app.agents.notification_agent import NotificationAgent

COORDINATOR_NAME = "CoordinatorAgent"
from app.services.fulfillment_service import COORDINATION_LOCK, refresh_request_status
from app.services.scarce_blood_policy import PENALTY_SCORE_POINTS, conservation_factor


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
        self.bus = bus or MessageBus(hub=COORDINATOR_NAME)
        if self.bus.hub is None:
            self.bus.hub = COORDINATOR_NAME  # agents may only talk to the Coordinator
        self.req_agent = RequirementAgent(db=self.db, bus=self.bus)
        self.match_agent = MatchingAgent(db=self.db, bus=self.bus)
        self.loc_agent = LocationAgent(bus=self.bus)
        self.notif_agent = NotificationAgent(bus=self.bus)
        self.bus.register_agent("RequirementAgent", self.req_agent.handle_a2a_message)
        self.bus.register_agent("MatchingAgent", self.match_agent.handle_a2a_message)
        self.bus.register_agent("LocationAgent", self.loc_agent.handle_a2a_message)
        self.bus.register_agent("NotificationAgent", self.notif_agent.handle_a2a_message)

    def _ask(self, receiver: str, message_type: str, payload: Dict[str, Any], correlation_id: str):
        """Send a request to an agent over the A2A bus and return (reply_payload, error_reply).

        Exactly one of the two is None. Agent crashes and refusals arrive as A2A_ERROR replies.
        """
        reply = self.bus.send(A2AMessage.create(
            sender_agent=COORDINATOR_NAME,
            receiver_agent=receiver,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
        ))
        if reply.message_type == A2AMessageType.A2A_ERROR:
            return None, reply
        return reply.payload, None

    def _trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Summaries of every A2A message exchanged for this correlation id."""
        return [
            {
                "message_id": m.message_id,
                "sender": m.sender_agent,
                "receiver": m.receiver_agent,
                "type": m.message_type,
                "correlation_id": m.correlation_id,
                "timestamp": m.timestamp,
            }
            for m in self.bus.get_messages_for_correlation_id(correlation_id)
        ]

    def calculate_priority_score(
        self,
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
        # Conserve scarce O- blood on routine requests
        total_score -= PENALTY_SCORE_POINTS * conservation_factor(
            source_blood_group, recipient_blood_group, urgency
        )
        return round(min(100.0, max(0.0, total_score)), 2)

    def orchestrate(
        self,
        request_id: int,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Run the coordination flow and return the allocation-oriented view of it.

        This is the same single pipeline as :meth:`coordinate` (validation, matching,
        distances, optimisation, reservation); it only reshapes the result into
        ``allocated_sources`` / ``standby_sources``. Raises ValueError when the
        request or its hospital does not exist.
        """
        if not self.db:
            raise ValueError("CoordinatorAgent requires an active database session for orchestration.")
        blood_request = self.db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
        if not blood_request:
            raise ValueError(f"Blood request #{request_id} not found.")
        hospital = self.db.query(Hospital).filter(Hospital.hospital_id == blood_request.hospital_id).first()
        if not hospital:
            raise ValueError(f"Hospital #{blood_request.hospital_id} referenced by request #{request_id} not found.")

        result = self.coordinate(request_input=request_id, persist=persist)
        hospital_info = {
            "hospital_id": hospital.hospital_id,
            "name": hospital.name,
            "address": hospital.address,
            "latitude": hospital.latitude,
            "longitude": hospital.longitude,
        }
        step_for_state = {
            "RECEIVED": "INIT", "VALIDATED": "REQUIREMENT_AGENT", "MATCHED": "MATCHING_AGENT",
            "LOCATED": "LOCATION_AND_RANKING", "COMPLETED": "ALLOCATION_ENGINE", "FAILED": "FAILED",
        }
        execution_log = [
            {"timestamp": h["timestamp"], "step": step_for_state.get(h["state"], h["state"]), "message": h["detail"]}
            for h in result.get("state_history", [])
        ]

        if not result.get("success"):
            if result.get("failed_at") == "MATCHING":
                # Nothing compatible exists: report an empty allocation rather than an error.
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
        by_key = {(c["source_type"], c["source_id"], c.get("blood_group")): c for c in result["ranked_matches"]}
        allocated, planned_keys = [], set()
        for entry in plan["plan"]:
            key = (entry["source_type"], entry["source_id"], entry.get("blood_group"))
            planned_keys.add(key)
            record = dict(by_key.get(key, entry))
            record["units_allocated"] = entry["units"]
            allocated.append(record)
        standby = [c for k, c in by_key.items() if k not in planned_keys]
        status = "FULFILLED" if plan["status"] == "FULLY_FULFILLED" else plan["status"]
        execution_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": "PERSISTENCE" if persist else "PERSISTENCE_SKIPPED",
            "message": f"{len(allocated)} source(s) reserved; request status '{result.get('request_status')}'."
                       if persist else "persist=False: nothing written.",
        })
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

    def coordinate(
        self,
        request_input: Union[int, Dict[str, Any], BloodRequest],
        correlation_id: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Coordinate a blood request end to end (the single coordination flow).

        When persisting, matching -> reservation runs under one lock so two requests
        cannot reserve the same units at the same moment.
        """
        guard = COORDINATION_LOCK if (persist and self.db is not None) else nullcontext()
        with guard:
            result = self._coordinate(request_input, correlation_id, persist)
        result["a2a_trace"] = self._trace(result.get("correlation_id"))
        return result

    def _coordinate(
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
            if req_id and self.db and persist:  # a preview must not attach to a real request that happens to share the id
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

        delivered_units = 0
        if blood_request_model is not None:
            if blood_request_model.status in (RequestStatus.FULFILLED.value, RequestStatus.CANCELLED.value):
                current_state = CoordinatorState.FAILED
                error_msg = f"Request #{req_id} is already {blood_request_model.status} and cannot be coordinated again."
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id, failed_at="STATE", error=error_msg,
                    state_history=state_history, correlation_id=corr_id,
                )
            if self.db is not None:
                delivered_units = sum(
                    m.units or 0 for m in self.db.query(Match).filter(
                        Match.request_id == blood_request_model.request_id,
                        Match.status == MatchStatus.COMPLETED.value)
                )

        # ---------------------------------------------------------------------
        # Step 2: State = VALIDATED (Requirement Agent)
        # ---------------------------------------------------------------------
        reply, error_reply = self._ask(
            "RequirementAgent", A2AMessageType.REQUIREMENT_VALIDATE_REQUEST, raw_payload, corr_id)
        if error_reply is not None:
            current_state = CoordinatorState.FAILED
            errors = (error_reply.payload.get("details") or {}).get("errors")
            if errors:
                error_msg = f"Requirement validation failed: {', '.join(errors)}"
            else:
                error_msg = error_reply.payload.get("error", "Requirement validation failed.")
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id,
                failed_at="VALIDATION",
                error=error_msg,
                details=errors,
                state_history=state_history,
                correlation_id=corr_id,
            )
        validation_result = reply["requirement"]

        current_state = CoordinatorState.VALIDATED
        log_transition(
            current_state,
            f"Requirement validated: {validation_result['units_required']} units of {validation_result['blood_group']}, Urgency: {validation_result['urgency']}."
        )

        # ---------------------------------------------------------------------
        # Step 3: State = MATCHED (Matching Agent)
        # ---------------------------------------------------------------------
        reply, error_reply = self._ask(
            "MatchingAgent",
            A2AMessageType.MATCHING_FIND_SOURCES_REQUEST,
            {
                "requirement": validation_result,
                "hospital_id": raw_payload.get("hospital_id"),
                "inventories": raw_payload.get("inventories"),
                "donors": raw_payload.get("donors"),
            },
            corr_id,
        )
        if error_reply is not None:
            current_state = CoordinatorState.FAILED
            error_msg = f"Matching failed: {error_reply.payload.get('error')}"
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id, failed_at="MATCHING", error=error_msg,
                state_history=state_history, correlation_id=corr_id,
            )
        matches_result = reply
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

        # Resolve each candidate's name and coordinates, then ask the LocationAgent for distances
        located_input = []
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
            c_dict["latitude"] = dest_lat
            c_dict["longitude"] = dest_lon
            located_input.append(c_dict)

        reply, error_reply = self._ask(
            "LocationAgent",
            A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST,
            {
                "hospital_id": hospital_id,
                "hospital_coords": {
                    "hospital_id": hospital_id, "name": hosp_name, "address": hosp_address,
                    "latitude": hosp_lat, "longitude": hosp_lon,
                },
                "candidates": located_input,
                "requirement": validation_result,
            },
            corr_id,
        )
        if error_reply is not None:
            current_state = CoordinatorState.FAILED
            error_msg = f"Location calculation failed: {error_reply.payload.get('error')}"
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id, failed_at="LOCATION", error=error_msg,
                state_history=state_history, correlation_id=corr_id,
            )

        annotated_candidates = []
        for c_dict in reply["candidates"]:
            if c_dict.get("distance_km") is None:
                current_state = CoordinatorState.FAILED
                error_msg = (
                    f"Location calculation failed for candidate #{c_dict['source_id']}: "
                    f"{c_dict.get('location_error', 'no distance returned')}"
                )
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id, failed_at="LOCATION", error=error_msg,
                    state_history=state_history, correlation_id=corr_id,
                )
            c_dict["is_exact_match"] = c_dict.get("blood_group") == validation_result["blood_group"]
            c_dict["priority_score"] = self.calculate_priority_score(
                distance_km=c_dict["distance_km"],
                source_type=c_dict["source_type"],
                is_exact_match=c_dict["is_exact_match"],
                urgency=validation_result["urgency"],
                source_blood_group=c_dict.get("blood_group"),
                recipient_blood_group=validation_result["blood_group"],
            )
            annotated_candidates.append(c_dict)

        # Rank candidates strictly by distance ascending
        annotated_candidates.sort(key=lambda c: c["distance_km"])

        current_state = CoordinatorState.LOCATED
        log_transition(
            current_state,
            f"Location Agent computed distances for {len(annotated_candidates)} candidates. Ranked nearest-first."
        )

        # ---------------------------------------------------------------------
        # Step 5: Allocation plan, reservation (holds) and persistence
        # ---------------------------------------------------------------------
        from app.services.optimization_service import OptimizationService
        units_still_needed = max(0, validation_result.get("units_required", 1) - delivered_units)
        fulfillment_plan = OptimizationService().optimize(
            request_id=req_id,
            units_required=units_still_needed,
            urgency=validation_result.get("urgency", "MEDIUM"),
            candidates=annotated_candidates,
            recipient_blood_group=validation_result.get("blood_group"),
        )
        # Fixed-size details for callers: the original need, not only what is left
        fulfillment_plan["details"]["units_delivered_already"] = delivered_units

        request_status = blood_request_model.status if blood_request_model else None
        if persist and self.db and blood_request_model:
            planned_units = {
                (p["source_type"], p["source_id"], p.get("blood_group")): p["units"]
                for p in fulfillment_plan["plan"]
            }
            # Release this request's previous proposals/holds; delivered and rejected rows are history.
            self.db.query(Match).filter(
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
                self.db.add(match_row)
                self.db.flush()
                cand["match_id"] = match_row.match_id
                cand["status"] = match_row.status
                if units:
                    cand["units_reserved"] = units
            for entry in fulfillment_plan["plan"]:
                for cand in annotated_candidates:
                    if (cand["source_type"], cand["source_id"], cand.get("blood_group")) == (
                            entry["source_type"], entry["source_id"], entry.get("blood_group")):
                        entry["match_id"] = cand["match_id"]

            request_status = refresh_request_status(self.db, blood_request_model.request_id)
            if request_status == RequestStatus.PROCESSING.value and fulfillment_plan["details"]["units_shortage"] > 0:
                blood_request_model.status = RequestStatus.PARTIALLY_FULFILLED.value
                request_status = blood_request_model.status
            self.db.commit()
            self.db.refresh(blood_request_model)

        current_state = CoordinatorState.COMPLETED
        log_transition(
            current_state,
            "Coordination completed successfully. "
            + ("Units reserved and results persisted." if persist else "Preview only; nothing persisted."),
        )

        # Alerts go out through the Notification Agent only once units are actually reserved
        notifications_result = {
            "success": True, "request_id": req_id, "dispatched_count": 0, "notifications": [],
            "skipped": "preview only; nothing was reserved",
        }
        if persist and self.db and blood_request_model:
            reply, error_reply = self._ask(
                "NotificationAgent",
                A2AMessageType.NOTIFICATION_DISPATCH_REQUEST,
                {
                    "hospital_id": hospital_id or 1,
                    "request_id": req_id,
                    "fulfillment_plan": fulfillment_plan,
                    "hospital_name": hosp_name,
                },
                corr_id,
            )
            if error_reply is not None:
                # The reservation is already saved; report the notification problem without failing it.
                notifications_result = {
                    "success": False, "request_id": req_id, "dispatched_count": 0, "notifications": [],
                    "error": error_reply.payload.get("error"),
                }
            else:
                notifications_result = reply

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
            "request_status": request_status,
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
