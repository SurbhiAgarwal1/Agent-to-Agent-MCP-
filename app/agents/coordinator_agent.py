"""Coordinator Agent for Blood Donation Matching System (Part 9).

The CoordinatorAgent owns the end-to-end lifecycle for an emergency blood request:
Requirement -> Matching -> Location -> Final Ranked Result (distance ascending),
tracking the request through a formal state machine and persisting results to the database.
"""

import uuid
import asyncio
import os
import time
from contextvars import ContextVar
from contextlib import nullcontext
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from pydantic import ValidationError

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
from app.llm.client import record_usage
from app.llm.reasoners import (
    LLMReasoner,
    MockReasoner,
    ReasonerError,
    create_reasoner,
)
from app.llm.schemas import BloodRequestPlan
from opentelemetry import trace
from app.observability.tracing import (
    LLM_DURATION, LLM_ERRORS, LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS, LLM_REQUESTS,
    LLM_TOTAL_TOKENS, WORKFLOWS, WORKFLOW_DURATION, WORKFLOW_ERRORS,
)

_WORKFLOW_ACTIVE: ContextVar[bool] = ContextVar("workflow_active", default=False)
_TRACER = trace.get_tracer("app.coordinator")


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
        network: bool = False,
        reasoner: Optional[LLMReasoner] = None,
    ):
        """Initialize Coordinator Agent.
        
        Args:
            db: Optional SQLAlchemy Session.
            bus: Optional MessageBus instance for A2A communication.
        """
        self.db = db
        self.network = network
        self.reasoner = reasoner or create_reasoner()
        self._network_trace = {}
        self.bus = None if network else (bus or MessageBus(hub=COORDINATOR_NAME))
        if self.bus is not None:
            if self.bus.hub is None:
                self.bus.hub = COORDINATOR_NAME
            self.req_agent = RequirementAgent(db=self.db, bus=self.bus)
            self.match_agent = MatchingAgent(db=self.db, bus=self.bus)
            self.loc_agent = LocationAgent(bus=self.bus)
            self.notif_agent = NotificationAgent(bus=self.bus)
            self.bus.register_agent("RequirementAgent", self.req_agent.handle_a2a_message)
            self.bus.register_agent("MatchingAgent", self.match_agent.handle_a2a_message)
            self.bus.register_agent("LocationAgent", self.loc_agent.handle_a2a_message)
            self.bus.register_agent("NotificationAgent", self.notif_agent.handle_a2a_message)

    def generate_plan(self, user_request: str) -> tuple[BloodRequestPlan, Dict[str, Any]]:
        """Use the configured provider and validate its untrusted structured output."""
        started = time.perf_counter()
        provider = "mock" if isinstance(self.reasoner, MockReasoner) else "gemini"
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if provider == "gemini" else "deterministic-mock"
        attrs = {"provider": provider, "model": model}
        status = "error"
        with _TRACER.start_as_current_span("llm.generate", attributes=attrs, record_exception=False, set_status_on_exception=False) as span:
            try:
                result = self._generate_plan(user_request)
                status = "success"
                metadata = result[1]
                provider = str(metadata.get("provider", provider))
                model = str(metadata.get("model", model))
                attrs = {"provider": provider, "model": model}
                span.set_attribute("llm.provider", provider)
                span.set_attribute("llm.model", model)
                LLM_REQUESTS.add(1, {**attrs, "status": "success"})
                if metadata.get("fallback_used"):
                    failed_provider = "gemini" if provider == "mock" else "unknown"
                    LLM_REQUESTS.add(1, {"provider": failed_provider, "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "status": "error"})
                    LLM_ERRORS.add(1, {"provider": failed_provider, "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "status": "fallback"})
                usage = metadata.get("usage", {})
                if isinstance(usage, dict) and not usage.get("is_mock"):
                    for key, instrument in (("input_tokens", LLM_INPUT_TOKENS), ("output_tokens", LLM_OUTPUT_TOKENS), ("total_tokens", LLM_TOTAL_TOKENS)):
                        value = usage.get(key)
                        if isinstance(value, int) and value >= 0:
                            instrument.add(value, attrs)
                elif provider == "mock":
                    for instrument in (LLM_INPUT_TOKENS, LLM_OUTPUT_TOKENS, LLM_TOTAL_TOKENS):
                        instrument.add(0, attrs)
                return result
            except Exception as exc:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("error.type", type(exc).__name__)
                LLM_ERRORS.add(1, {**attrs, "status": "error"})
                LLM_REQUESTS.add(1, {**attrs, "status": "error"})
                raise
            finally:
                LLM_DURATION.record((time.perf_counter() - started) * 1000, {**attrs, "status": status})

    def _generate_plan(self, user_request: str) -> tuple[BloodRequestPlan, Dict[str, Any]]:
        try:
            generated = self.reasoner.generate_plan(user_request)
        except ReasonerError:
            fallback = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
            if fallback not in {"mock", "dummy"} or isinstance(self.reasoner, MockReasoner):
                raise
            generated = MockReasoner().generate_plan(user_request).model_copy(update={"fallback_used": True})

        record_usage(generated.usage)
        try:
            plan = BloodRequestPlan.model_validate(generated.plan)
        except ValidationError as exc:
            raise ValueError(f"LLM returned an invalid blood request plan: {exc}") from exc
        metadata = {
            "provider": generated.provider,
            "model": generated.model,
            "usage": generated.usage,
            "fallback_used": generated.fallback_used,
        }
        return plan, metadata

    def coordinate_text(
        self,
        user_request: str,
        *,
        persist: bool = False,
        request_id: Optional[int] = None,
        allowed_hospital_ids: Optional[set[int]] = None,
    ) -> Dict[str, Any]:
        """Plan a natural-language request, then execute only via the existing Coordinator workflow."""
        return self._run_workflow(lambda: self._coordinate_text(
            user_request, persist=persist, request_id=request_id, allowed_hospital_ids=allowed_hospital_ids
        ))

    def _coordinate_text(self, user_request: str, *, persist: bool, request_id: Optional[int],
                         allowed_hospital_ids: Optional[set[int]] = None) -> Dict[str, Any]:
        plan, _llm_metadata = self.generate_plan(user_request)
        missing = []
        if not plan.blood_group:
            missing.append("blood group")
        if not plan.units_required:
            missing.append("number of units")
        if not plan.location:
            missing.append("hospital or location")
        if missing:
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "missing_fields": missing,
                "clarification_question": "Please provide the " + " and ".join(missing) + ".",
                "plan": plan.model_dump(mode="json"),
            }

        hospital = None
        if self.db is not None:
            needle = f"%{plan.location}%"
            hospital = self.db.query(Hospital).filter(
                (Hospital.name.ilike(needle)) | (Hospital.address.ilike(needle))
            ).first()
        if hospital is None:
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "missing_fields": ["registered hospital matching the requested location"],
                "clarification_question": f"I couldn't match '{plan.location}' to a registered hospital. Please specify one.",
                "plan": plan.model_dump(mode="json"),
            }
        if allowed_hospital_ids is not None and hospital.hospital_id not in allowed_hospital_ids:
            return {"success": False, "status": "FORBIDDEN", "failed_at": "AUTHORIZATION",
                    "error": "Active membership in the requested hospital is required.",
                    "hospital_id": hospital.hospital_id}

        request_payload = {
            "request_id": request_id or 999,
            "hospital_id": hospital.hospital_id,
            "hospital_name": hospital.name,
            "hospital_address": hospital.address,
            "hospital_latitude": hospital.latitude,
            "hospital_longitude": hospital.longitude,
            "blood_group": plan.blood_group,
            "units_required": plan.units_required,
            "urgency": plan.urgency.value,
        }
        result = self.coordinate(request_payload, persist=persist)
        return {**result, "plan": plan.model_dump(mode="json")}

    def _ask(self, receiver: str, message_type: str, payload: Dict[str, Any], correlation_id: str):
        """Send a request to an agent over the A2A bus and return (reply_payload, error_reply).

        Exactly one of the two is None. Agent crashes and refusals arrive as A2A_ERROR replies.
        """
        if self.network:
            ports = {"RequirementAgent": 8101, "MatchingAgent": 8102, "LocationAgent": 8103, "NotificationAgent": 8104}
            try:
                from app.agents.a2a.client import call_remote_agent
                reply_payload = asyncio.run(call_remote_agent(receiver.upper(), payload, port=ports[receiver], operation=message_type))
                self._network_trace.setdefault(correlation_id, []).extend([
                    {"message_id": uuid.uuid4().hex, "sender": COORDINATOR_NAME, "receiver": receiver,
                     "type": message_type, "correlation_id": correlation_id, "timestamp": datetime.now(timezone.utc).isoformat()},
                    {"message_id": uuid.uuid4().hex, "sender": receiver, "receiver": COORDINATOR_NAME,
                     "type": message_type + ".response", "correlation_id": correlation_id, "timestamp": datetime.now(timezone.utc).isoformat()},
                ])
                if reply_payload.get("success") is False:
                    raise RuntimeError(reply_payload.get("error", f"{receiver} reported failure"))
                return reply_payload, None
            except Exception as exc:
                error = A2AMessage.create(sender_agent=receiver, receiver_agent=COORDINATOR_NAME,
                    message_type=A2AMessageType.A2A_ERROR, payload={"error": str(exc)}, correlation_id=correlation_id)
                return None, error
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
        if self.network:
            return self._network_trace.get(correlation_id, [])
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
        return self._run_workflow(lambda: self._coordinate_public(request_input, correlation_id, persist))

    def _coordinate_public(self, request_input, correlation_id, persist):
        guard = COORDINATION_LOCK if (persist and self.db is not None) else nullcontext()
        with guard:
            result = self._coordinate(request_input, correlation_id, persist)
        result["a2a_trace"] = self._trace(result.get("correlation_id"))
        return result

    def _run_workflow(self, operation):
        """Measure one logical workflow even when text planning calls coordinate()."""
        if _WORKFLOW_ACTIVE.get():
            return operation()
        token = _WORKFLOW_ACTIVE.set(True)
        started = time.perf_counter()
        status = "error"
        try:
            with _TRACER.start_as_current_span("workflow.coordinate", record_exception=False, set_status_on_exception=False) as span:
                try:
                    result = operation()
                    succeeded = isinstance(result, dict) and result.get("success") is True
                    status = "success" if succeeded else "error"
                    WORKFLOWS.add(1, {"status": status})
                    if not succeeded:
                        WORKFLOW_ERRORS.add(1, {"status": status})
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                    return result
                except Exception as exc:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    span.set_attribute("error.type", type(exc).__name__)
                    WORKFLOWS.add(1, {"status": "error"})
                    WORKFLOW_ERRORS.add(1, {"status": "error"})
                    raise
                finally:
                    WORKFLOW_DURATION.record((time.perf_counter() - started) * 1000, {"status": status})
        finally:
            _WORKFLOW_ACTIVE.reset(token)

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
