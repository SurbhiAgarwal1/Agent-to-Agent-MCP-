"""Coordinator Agent for Blood Donation Matching System (Part 9).

The CoordinatorAgent owns the end-to-end lifecycle for an emergency blood request:
Requirement -> Matching -> Location -> Final Ranked Result (distance ascending),
tracking the request through a formal state machine and persisting results to the database.
"""

import asyncio
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
import os
import time
from typing import Any, Dict, List, Optional, Union
import uuid

from opentelemetry import trace
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.a2a.bus import MessageBus
from app.agents.a2a.discovery import default_skill_for_agent
from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.agents.coordinator_helpers import (
    calculate_priority_score as _calc_priority_score,
    format_orchestration_view,
    is_in_memory_db,
    persist_reservations,
    resolve_candidate_coordinates,
    resolve_hospital_by_location,
    run_coro_sync,
)
from app.agents.location_agent import LocationAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.notification_agent import NotificationAgent
from app.agents.requirement_agent import RequirementAgent
from app.llm.client import record_usage
from app.llm.reasoners import (
    LLMReasoner,
    MockReasoner,
    ReasonerError,
    create_reasoner,
)
from app.llm.schemas import BloodRequestPlan
from app.models.blood_request import BloodRequest
from app.models.enums import MatchStatus, RequestStatus
from app.models.hospital import Hospital
from app.models.match import Match
from app.observability.tracing import (
    LLM_DURATION,
    LLM_ERRORS,
    LLM_INPUT_TOKENS,
    LLM_OUTPUT_TOKENS,
    LLM_REQUESTS,
    LLM_TOTAL_TOKENS,
    WORKFLOW_DURATION,
    WORKFLOW_ERRORS,
    WORKFLOWS,
)
from app.services.fulfillment_service import COORDINATION_LOCK

COORDINATOR_NAME = "CoordinatorAgent"

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
        peer_to_peer: bool = False,
    ):
        """Initialize Coordinator Agent."""
        self.db = db
        self.network = bool(network and not is_in_memory_db(db))
        self.peer_to_peer = peer_to_peer
        self.reasoner = reasoner or create_reasoner()
        self._network_trace: Dict[str, List[Dict[str, Any]]] = {}
        default_hub = None if peer_to_peer else COORDINATOR_NAME
        self.bus = None if self.network else (bus or MessageBus(hub=default_hub))
        if self.bus is not None:
            if self.bus.hub is None and not peer_to_peer:
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
        with _TRACER.start_as_current_span(
            "llm.generate",
            attributes=attrs,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
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
                    failed_attrs = {
                        "provider": failed_provider,
                        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    }
                    LLM_REQUESTS.add(1, {**failed_attrs, "status": "error"})
                    LLM_ERRORS.add(1, {**failed_attrs, "status": "fallback"})
                usage = metadata.get("usage", {})
                if isinstance(usage, dict) and not usage.get("is_mock"):
                    for key, instrument in (
                        ("input_tokens", LLM_INPUT_TOKENS),
                        ("output_tokens", LLM_OUTPUT_TOKENS),
                        ("total_tokens", LLM_TOTAL_TOKENS),
                    ):
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
        """Plan a natural-language request, then execute only via the Coordinator workflow."""
        return self._run_workflow(
            lambda: self._coordinate_text(
                user_request,
                persist=persist,
                request_id=request_id,
                allowed_hospital_ids=allowed_hospital_ids,
            )
        )

    async def acoordinate_text(
        self,
        user_request: str,
        *,
        persist: bool = False,
        request_id: Optional[int] = None,
        allowed_hospital_ids: Optional[set[int]] = None,
    ) -> Dict[str, Any]:
        """Async entrypoint for natural-language request planning and coordination."""
        return await asyncio.to_thread(
            self.coordinate_text,
            user_request,
            persist=persist,
            request_id=request_id,
            allowed_hospital_ids=allowed_hospital_ids,
        )

    def _coordinate_text(
        self,
        user_request: str,
        *,
        persist: bool,
        request_id: Optional[int],
        allowed_hospital_ids: Optional[set[int]] = None,
    ) -> Dict[str, Any]:
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

        hospital, matches = resolve_hospital_by_location(self.db, plan.location)
        if len(matches) > 1 and hospital is None:
            names = ", ".join(h.name for h in matches)
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "missing_fields": ["unambiguous hospital name"],
                "clarification_question": (
                    f"Multiple hospitals matched '{plan.location}' ({names}). Please specify which hospital."
                ),
                "plan": plan.model_dump(mode="json"),
            }
        if hospital is None:
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "missing_fields": ["registered hospital matching the requested location"],
                "clarification_question": f"I couldn't match '{plan.location}' to a registered hospital. Please specify one.",
                "plan": plan.model_dump(mode="json"),
            }
        if allowed_hospital_ids is not None and hospital.hospital_id not in allowed_hospital_ids:
            return {
                "success": False,
                "status": "FORBIDDEN",
                "failed_at": "AUTHORIZATION",
                "error": "Active membership in the requested hospital is required.",
                "hospital_id": hospital.hospital_id,
            }

        effective_request_id = request_id
        if effective_request_id is None and persist and self.db is not None:
            new_req = BloodRequest(
                hospital_id=hospital.hospital_id,
                blood_group=plan.blood_group,
                units_required=plan.units_required,
                urgency=plan.urgency.value,
                status=RequestStatus.PENDING.value,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(new_req)
            self.db.commit()
            self.db.refresh(new_req)
            effective_request_id = new_req.request_id

        request_payload: Dict[str, Any] = {
            "request_id": effective_request_id,
            "is_preview": not persist and effective_request_id is None,
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
        """Send a request to an agent over A2A (via Agent Card skill discovery in network mode or MessageBus)."""
        if self.network:
            try:
                from app.agents.a2a.client import call_remote_agent

                skill = default_skill_for_agent(receiver)
                reply_payload = run_coro_sync(
                    call_remote_agent(
                        receiver.upper(),
                        payload,
                        skill=skill,
                        operation=message_type,
                    )
                )
                self._network_trace.setdefault(correlation_id, []).extend(
                    [
                        {
                            "message_id": uuid.uuid4().hex,
                            "sender": COORDINATOR_NAME,
                            "receiver": receiver,
                            "type": message_type,
                            "correlation_id": correlation_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        {
                            "message_id": uuid.uuid4().hex,
                            "sender": receiver,
                            "receiver": COORDINATOR_NAME,
                            "type": message_type + ".response",
                            "correlation_id": correlation_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ]
                )
                if reply_payload.get("success") is False:
                    raise RuntimeError(reply_payload.get("error", f"{receiver} reported failure"))
                return reply_payload, None
            except Exception as exc:
                error = A2AMessage.create(
                    sender_agent=receiver,
                    receiver_agent=COORDINATOR_NAME,
                    message_type=A2AMessageType.A2A_ERROR,
                    payload={"error": str(exc)},
                    correlation_id=correlation_id,
                )
                return None, error
        reply = self.bus.send(
            A2AMessage.create(
                sender_agent=COORDINATOR_NAME,
                receiver_agent=receiver,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
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
        return _calc_priority_score(
            distance_km=distance_km,
            source_type=source_type,
            is_exact_match=is_exact_match,
            urgency=urgency,
            source_blood_group=source_blood_group,
            recipient_blood_group=recipient_blood_group,
        )

    def orchestrate(self, request_id: int, persist: bool = True) -> Dict[str, Any]:
        """Run the coordination flow and return the allocation-oriented view of it."""
        if not self.db:
            raise ValueError("CoordinatorAgent requires an active database session for orchestration.")
        blood_request = self.db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
        if not blood_request:
            raise ValueError(f"Blood request #{request_id} not found.")
        hospital = self.db.query(Hospital).filter(Hospital.hospital_id == blood_request.hospital_id).first()
        if not hospital:
            raise ValueError(f"Hospital #{blood_request.hospital_id} referenced by request #{request_id} not found.")

        result = self.coordinate(request_input=request_id, persist=persist)
        return format_orchestration_view(request_id, blood_request, hospital, result, persist)

    def coordinate(
        self,
        request_input: Union[int, Dict[str, Any], BloodRequest],
        correlation_id: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Coordinate a blood request end to end (the single coordination flow)."""
        return self._run_workflow(lambda: self._coordinate_public(request_input, correlation_id, persist))

    async def acoordinate(
        self,
        request_input: Union[int, Dict[str, Any], BloodRequest],
        correlation_id: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Async entrypoint for coordinating a blood request."""
        return await asyncio.to_thread(self.coordinate, request_input, correlation_id, persist)

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
            with _TRACER.start_as_current_span(
                "workflow.coordinate",
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
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
        """Execute end-to-end coordination workflow for a blood request."""
        state_history = []
        now_iso = lambda: datetime.now(timezone.utc).isoformat()

        def log_transition(state: CoordinatorState, detail: str):
            state_history.append({"state": state.value, "timestamp": now_iso(), "detail": detail})

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
            if req_id and self.db and persist:
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

        req_id = raw_payload.get("request_id") if "request_id" in raw_payload else 1
        corr_id = correlation_id or f"coord-{req_id or 'preview'}-{uuid.uuid4().hex[:8]}"

        delivered_units = 0
        if blood_request_model is not None:
            if blood_request_model.status in (RequestStatus.FULFILLED.value, RequestStatus.CANCELLED.value):
                current_state = CoordinatorState.FAILED
                error_msg = f"Request #{req_id} is already {blood_request_model.status} and cannot be coordinated again."
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id,
                    failed_at="STATE",
                    error=error_msg,
                    state_history=state_history,
                    correlation_id=corr_id,
                )
            if self.db is not None:
                delivered_units = sum(
                    m.units or 0
                    for m in self.db.query(Match).filter(
                        Match.request_id == blood_request_model.request_id,
                        Match.status == MatchStatus.COMPLETED.value,
                    )
                )

        # Step 2: VALIDATED (RequirementAgent)
        reply, error_reply = self._ask(
            "RequirementAgent", A2AMessageType.REQUIREMENT_VALIDATE_REQUEST, raw_payload, corr_id
        )
        if error_reply is not None:
            current_state = CoordinatorState.FAILED
            errors = (error_reply.payload.get("details") or {}).get("errors")
            error_msg = (
                f"Requirement validation failed: {', '.join(errors)}"
                if errors
                else error_reply.payload.get("error", "Requirement validation failed.")
            )
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
            f"Requirement validated: {validation_result['units_required']} units of "
            f"{validation_result['blood_group']}, Urgency: {validation_result['urgency']}.",
        )

        # Resolve hospital coordinates so MatchingAgent can optionally collaborate peer-to-peer with LocationAgent
        hospital_id = raw_payload.get("hospital_id")
        hosp_lat = raw_payload.get("hospital_latitude")
        hosp_lon = raw_payload.get("hospital_longitude")
        hosp_name = raw_payload.get("hospital_name") or "Emergency Facility"
        hosp_address = raw_payload.get("hospital_address") or "Medical District"
        if (hosp_lat is None or hosp_lon is None) and self.db and hospital_id:
            hosp_record = self.db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()
            if hosp_record:
                hosp_lat = hosp_record.latitude
                hosp_lon = hosp_record.longitude
                hosp_name = hosp_record.name
                hosp_address = hosp_record.address

        enable_p2p = (self.network or self.peer_to_peer) and hosp_lat is not None and hosp_lon is not None
        matching_payload: Dict[str, Any] = {
            "requirement": validation_result,
            "hospital_id": hospital_id,
            "inventories": raw_payload.get("inventories"),
            "donors": raw_payload.get("donors"),
        }
        if enable_p2p:
            matching_payload["collaborate_location"] = True
            matching_payload["correlation_id"] = corr_id
            matching_payload["hospital_coords"] = {
                "hospital_id": hospital_id,
                "name": hosp_name,
                "address": hosp_address,
                "latitude": hosp_lat,
                "longitude": hosp_lon,
            }

        # Step 3: MATCHED (MatchingAgent)
        reply, error_reply = self._ask(
            "MatchingAgent",
            A2AMessageType.MATCHING_FIND_SOURCES_REQUEST,
            matching_payload,
            corr_id,
        )
        if error_reply is not None:
            current_state = CoordinatorState.FAILED
            error_msg = f"Matching failed: {error_reply.payload.get('error')}"
            log_transition(current_state, error_msg)
            return self._failure_response(
                request_id=req_id,
                failed_at="MATCHING",
                error=error_msg,
                state_history=state_history,
                correlation_id=corr_id,
            )
        matches_result = reply
        if self.network and isinstance(matches_result.get("peer_trace"), list):
            self._network_trace.setdefault(corr_id, []).extend(matches_result["peer_trace"])
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

        # Step 4: LOCATED (LocationAgent — either via peer-to-peer MatchingAgent->LocationAgent or Coordinator)
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

        located_candidates = matches_result.get("located_candidates")
        if not isinstance(located_candidates, list):
            located_input, coord_err = resolve_candidate_coordinates(self.db, candidates)
            if coord_err:
                current_state = CoordinatorState.FAILED
                log_transition(current_state, coord_err)
                return self._failure_response(
                    request_id=req_id,
                    failed_at="LOCATION",
                    error=coord_err,
                    state_history=state_history,
                    correlation_id=corr_id,
                )
            reply, error_reply = self._ask(
                "LocationAgent",
                A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST,
                {
                    "hospital_id": hospital_id,
                    "hospital_coords": {
                        "hospital_id": hospital_id,
                        "name": hosp_name,
                        "address": hosp_address,
                        "latitude": hosp_lat,
                        "longitude": hosp_lon,
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
                    request_id=req_id,
                    failed_at="LOCATION",
                    error=error_msg,
                    state_history=state_history,
                    correlation_id=corr_id,
                )
            located_candidates = reply["candidates"]

        annotated_candidates = []
        for c_dict in located_candidates:
            if c_dict.get("distance_km") is None:
                current_state = CoordinatorState.FAILED
                error_msg = (
                    f"Location calculation failed for candidate #{c_dict['source_id']}: "
                    f"{c_dict.get('location_error', 'no distance returned')}"
                )
                log_transition(current_state, error_msg)
                return self._failure_response(
                    request_id=req_id,
                    failed_at="LOCATION",
                    error=error_msg,
                    state_history=state_history,
                    correlation_id=corr_id,
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

        annotated_candidates.sort(key=lambda c: c["distance_km"])
        current_state = CoordinatorState.LOCATED
        log_transition(
            current_state,
            f"Location Agent computed distances for {len(annotated_candidates)} candidates. Ranked nearest-first.",
        )

        # Step 5: Allocation plan, reservation (holds) and persistence
        from app.services.optimization_service import OptimizationService

        units_still_needed = max(0, validation_result.get("units_required", 1) - delivered_units)
        fulfillment_plan = OptimizationService().optimize(
            request_id=req_id or 0,
            units_required=units_still_needed,
            urgency=validation_result.get("urgency", "MEDIUM"),
            candidates=annotated_candidates,
            recipient_blood_group=validation_result.get("blood_group"),
        )
        fulfillment_plan["details"]["units_delivered_already"] = delivered_units

        request_status = blood_request_model.status if blood_request_model else None
        if persist and self.db and blood_request_model:
            request_status = persist_reservations(
                self.db, blood_request_model, annotated_candidates, fulfillment_plan
            )

        current_state = CoordinatorState.COMPLETED
        log_transition(
            current_state,
            "Coordination completed successfully. "
            + ("Units reserved and results persisted." if persist else "Preview only; nothing persisted."),
        )

        notifications_result = {
            "success": True,
            "request_id": req_id,
            "dispatched_count": 0,
            "notifications": [],
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
                notifications_result = {
                    "success": False,
                    "request_id": req_id,
                    "dispatched_count": 0,
                    "notifications": [],
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
