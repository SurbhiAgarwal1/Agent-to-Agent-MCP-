"""Official A2A SDK server adapters for the existing agent business logic."""

import asyncio
from datetime import datetime, timezone
import json
import os
import time
import uuid
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part
from google.protobuf.json_format import MessageToDict
from opentelemetry import trace
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.observability.tracing import (
    AGENT_DURATION,
    AGENT_ERRORS,
    AGENT_REQUESTS,
    configure_telemetry,
    instrument_asgi,
)
from app.security.service_auth import ServiceAuthenticationMiddleware

_tracer = trace.get_tracer("app.agents.a2a.server")


async def _match_against_data_apis(call_remote_tool, requirement: dict) -> dict:
    """Discover component-specific synthetic stock and reviewed donors through MCP."""
    from app.services.compatibility import get_compatible_donor_groups
    component = requirement.get("component_type", "packed_red_blood_cells")
    groups = ([requirement["blood_group"]] if component == "whole_blood"
              else get_compatible_donor_groups(requirement["blood_group"]))
    if component not in {"whole_blood", "packed_red_blood_cells"}:
        raise ValueError("Unsupported blood component")
    inventory_rows, donor_rows, details = [], [], {}
    for group in groups:
        stocks = await call_remote_tool("search_blood_inventory", {
            "blood_group": group, "component_type": component,
            "minimum_available_units": 1, "availability_status": "available", "limit": 200, "offset": 0,
        })
        for row in stocks.get("items", []):
            bank = row.get("blood_bank", {})
            inventory_rows.append({"bank_id": row["blood_bank_id"], "blood_group": row["blood_group"], "component_type": row["component_type"], "units_available": row.get("units_available", max(0,row["available_units"]-row["reserved_units"])), "available_units": row["available_units"], "reserved_units": row["reserved_units"], "expiry_date": row.get("expiry_date")})
            details[("BLOOD_BANK", row["blood_bank_id"])] = {"name": bank.get("name"), "address": bank.get("city"), "latitude": bank.get("latitude"), "longitude": bank.get("longitude")}
        people = await call_remote_tool("search_donors", {
            "blood_group": group, "available": True, "verification_status": "verified",
            "eligibility_status": "eligible", "limit": 200, "offset": 0,
        })
        for row in people.get("items", []):
            donor_rows.append({"donor_id": row["id"], "blood_group": row["blood_group"], "available": row["available"], "last_donation_date": row.get("last_donation_date")})
            details[("DONOR", row["id"])] = {"name": row["name"], "address": row["city"], "latitude": row["latitude"], "longitude": row["longitude"]}
    result = await call_remote_tool("find_blood_sources", {
        "blood_group": requirement["blood_group"], "component_type": component, "request_id": requirement.get("request_id"),
        "inventories": inventory_rows, "donors": donor_rows,
    })
    for match in result.get("matches", []):
        match.update(details.get((match["source_type"], match["source_id"]), {}))
    result["data_source"] = "independent_synthetic_data_apis"
    return result


async def _coordinate_over_a2a(payload: dict, correlation_id: str | None = None) -> dict:
    """Run the established coordinator workflow with its remote A2A transport."""
    from app.agents.coordinator_agent import CoordinatorAgent
    from app.database.session import SessionLocal

    def run():
        db = SessionLocal()
        try:
            coordinator = CoordinatorAgent(db=db, network=True)
            persist = bool(payload.get("persist", False))
            if payload.get("mode") == "orchestrate" and payload.get("request_id") is not None:
                return coordinator.orchestrate(request_id=int(payload["request_id"]), persist=persist)
            if isinstance(payload.get("user_request"), str):
                allowed = payload.get("allowed_hospital_ids")
                allowed_set = set(allowed) if isinstance(allowed, list) else None
                return coordinator.coordinate_text(
                    payload["user_request"],
                    persist=persist,
                    request_id=payload.get("request_id"),
                    allowed_hospital_ids=allowed_set,
                    correlation_id=correlation_id,
                )
            request = payload.get("request_id") if (persist and payload.get("request_id") is not None) else (
                payload.get("request_id") if payload.get("request_id") is not None and "blood_group" not in payload else payload
            )
            return coordinator.coordinate(request_input=request, persist=persist, correlation_id=correlation_id)
        finally:
            db.close()

    return await asyncio.to_thread(run)


async def _collaborate_matching_to_location(
    matches: list[dict[str, Any]],
    payload: dict[str, Any],
    req: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Peer-to-peer A2A collaboration: MatchingAgent discovers and invokes LocationAgent directly."""
    from app.agents.a2a.client import call_remote_agent
    from app.agents.coordinator_helpers import resolve_candidate_coordinates
    from app.database.session import SessionLocal

    def _enrich():
        db = SessionLocal()
        try:
            return resolve_candidate_coordinates(db, matches)
        finally:
            db.close()

    located_input, coord_err = await asyncio.to_thread(_enrich)
    if coord_err or not located_input:
        return None, []

    corr_id = payload.get("correlation_id") or f"p2p-{uuid.uuid4().hex[:8]}"
    loc_payload = {
        "hospital_id": payload.get("hospital_id"),
        "hospital_coords": payload["hospital_coords"],
        "candidates": located_input,
        "requirement": req,
    }
    loc_reply = await call_remote_agent(
        "LOCATIONAGENT",
        loc_payload,
        skill="calculate-distance",
        operation="LOCATION_CALCULATE_DISTANCES_REQUEST",
    )
    peer_trace = [
        {
            "message_id": uuid.uuid4().hex,
            "sender": "MatchingAgent",
            "receiver": "LocationAgent",
            "type": "LOCATION_CALCULATE_DISTANCES_REQUEST",
            "correlation_id": corr_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "message_id": uuid.uuid4().hex,
            "sender": "LocationAgent",
            "receiver": "MatchingAgent",
            "type": "LOCATION_CALCULATE_DISTANCES_REQUEST.response",
            "correlation_id": corr_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    ]
    return loc_reply.get("candidates"), peer_trace


class DomainAgentExecutor(AgentExecutor):
    """Translate A2A message text into existing validated agent operations."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        agent = self.agent_name.removesuffix("Agent").lower()
        started = time.perf_counter()
        attrs = {"agent": agent}
        status = "error"
        with _tracer.start_as_current_span(
            "agent.execute",
            attributes={"agent.name": agent},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                succeeded = await self._execute(context, event_queue)
                if succeeded:
                    status = "success"
                    AGENT_REQUESTS.add(1, {**attrs, "status": "success"})
                else:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    AGENT_ERRORS.add(1, {**attrs, "status": "error"})
                    AGENT_REQUESTS.add(1, {**attrs, "status": "error"})
            except Exception as exc:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("error.type", type(exc).__name__)
                AGENT_ERRORS.add(1, {**attrs, "status": "error"})
                AGENT_REQUESTS.add(1, {**attrs, "status": "error"})
                raise
            finally:
                AGENT_DURATION.record((time.perf_counter() - started) * 1000, {**attrs, "status": status})

    async def _execute(self, context: RequestContext, event_queue: EventQueue) -> bool:
        msg = context.message
        text = "\n".join(part.text for part in msg.parts if part.text)
        span = _tracer.start_span(
            "agent.dispatch",
            attributes={"agent.name": self.agent_name.removesuffix("Agent").lower()},
        )
        failed = False
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("A2A request must contain a JSON object")
            from app.mcp.client import call_remote_tool

            task_metadata = dict(msg.metadata) if msg.metadata else {}
            correlation_id = task_metadata.get("correlationId") or context.context_id
            if self.agent_name == "EmergencyPriorityAgent":
                from app.agents.emergency_priority_agent import EmergencyPriorityAgent
                result = EmergencyPriorityAgent().evaluate(payload)
            elif self.agent_name == "RequirementAgent":
                validated = await call_remote_tool("validate_blood_request", payload)
                if not validated.get("valid"):
                    raise ValueError("Requirement validation failed: " + "; ".join(validated.get("errors", [])))
                result = {"requirement": validated}
            elif self.agent_name == "MatchingAgent":
                req = payload.get("requirement", payload)
                if os.getenv("DATA_APIS_ENABLED", "false").lower() == "true" and payload.get("inventories") is None and payload.get("donors") is None:
                    result = await _match_against_data_apis(call_remote_tool, req)
                else:
                    result = await call_remote_tool(
                        "find_blood_sources",
                        {"blood_group": req["blood_group"], "request_id": req.get("request_id"), "inventories": payload.get("inventories"), "donors": payload.get("donors")},
                    )
                if (
                    payload.get("collaborate_location")
                    and isinstance(payload.get("hospital_coords"), dict)
                    and result.get("matches")
                ):
                    try:
                        located_candidates, peer_trace = await _collaborate_matching_to_location(
                            result["matches"], payload, req
                        )
                        if located_candidates is not None:
                            result["located_candidates"] = located_candidates
                            result["peer_trace"] = peer_trace
                    except Exception:
                        # Fall back to Coordinator-driven LocationAgent call if peer-to-peer fails
                        pass
            elif self.agent_name == "LocationAgent":
                origin = payload.get("hospital_coords", payload)
                candidates = payload.get("candidates")
                if candidates is None:
                    result = await call_remote_tool("calculate_distance", payload)
                else:
                    located = []
                    nearby_distances = {}
                    if os.getenv("DATA_APIS_ENABLED", "false").lower() == "true":
                        for source_type, tool_name in (("BLOOD_BANK", "find_nearby_blood_banks"), ("DONOR", "find_nearby_donors")):
                            nearby = await call_remote_tool(tool_name, {"latitude": origin["latitude"], "longitude": origin["longitude"], "radius_km": 500, "limit": 200})
                            for item in nearby.get("items", []): nearby_distances[(source_type, item["id"])] = item.get("distance_km")
                    for candidate in candidates:
                        lat, lon = candidate.get("latitude"), candidate.get("longitude")
                        if lat is None or lon is None:
                            located.append(candidate)
                            continue
                        distance = await call_remote_tool(
                            "calculate_distance",
                            {
                                "origin_latitude": origin["latitude"],
                                "origin_longitude": origin["longitude"],
                                "destination_latitude": lat,
                                "destination_longitude": lon,
                                "include_eta": True,
                            },
                        )
                        api_distance = nearby_distances.get((candidate.get("source_type"), candidate.get("source_id")))
                        if api_distance is not None: distance["distance_km"] = api_distance
                        located.append({**candidate, **distance})
                    result = {
                        "candidates": sorted(
                            located, key=lambda item: item.get("distance_km", float("inf"))
                        )
                    }
            elif self.agent_name == "NotificationAgent":
                notification_payload = dict(payload)
                attempts = []
                if os.getenv("DATA_APIS_ENABLED", "false").lower() == "true":
                    plan = dict(payload.get("fulfillment_plan") or {})
                    for entry in plan.get("plan", []):
                        if entry.get("source_type") == "BLOOD_BANK":
                            component=entry.get("component_type",payload.get("component_type","packed_red_blood_cells"))
                            group=payload.get("blood_group")
                            inventory_group=entry.get("blood_group",group)
                            if not group or not inventory_group or not component:
                                continue
                            try:
                                attempts.append(await call_remote_tool("send_blood_bank_notification", {
                                    "blood_bank_id":entry["source_id"],"blood_request_id":payload["request_id"],
                                    "blood_group":group,"inventory_blood_group":inventory_group,
                                    "component_type":component,"required_units":entry.get("units",1),
                                    "channel":os.getenv("NOTIFICATION_CHANNEL","console"),
                                    "message":f"Hospital {payload.get('hospital_name','')} requests {entry.get('units',1)} units of {group} {component}.",
                                    "idempotency_key":f"bank:{payload['request_id']}:{entry['source_id']}:{component}:{group}",
                                }))
                            except Exception as exc:
                                attempts.append({"recipient_type":"BLOOD_BANK","recipient_id":entry["source_id"],"delivery_status":"failed","error_details":str(exc)})
                            continue
                        if entry.get("source_type") != "DONOR":
                            continue
                        donor = await call_remote_tool("get_donor_details", {"donor_id": entry["source_id"]})
                        if not donor.get("notification_consent"):
                            continue
                        if (not donor.get("available") or donor.get("verification_status") != "verified"
                                or donor.get("eligibility_status") != "eligible"):
                            continue
                        coords=payload.get("hospital_coords") or {}
                        if coords.get("latitude") is None or coords.get("longitude") is None:
                            continue
                        channel=donor.get("preferred_contact_method","email")
                        if channel=="phone":channel="sms"
                        component=entry.get("component_type",payload.get("component_type","packed_red_blood_cells"))
                        group=payload.get("blood_group")
                        try:
                            attempts.append(await call_remote_tool("send_donor_notification", {
                                "donor_id":donor["id"],"blood_request_id":payload["request_id"],"blood_group":group,
                                "component_type":component,"channel":channel,
                                "message":f"A hospital near you requests {entry.get('units',1)} donation unit(s) of {group} blood.",
                                "hospital_latitude":coords["latitude"],"hospital_longitude":coords["longitude"],
                                "idempotency_key":f"donor:{payload['request_id']}:{donor['id']}:{component}:{group}",
                            }))
                        except Exception as exc:
                            attempts.append({"recipient_type":"DONOR","recipient_id":donor["id"],"delivery_status":"failed","error_details":str(exc)})
                    # The existing generic dispatcher still notifies the requesting hospital,
                    # but its source list is emptied to prevent duplicate bank/donor sends.
                    hospital_payload=dict(notification_payload)
                    hospital_plan=dict(payload.get("fulfillment_plan") or {});hospital_plan["plan"]=[]
                    hospital_payload["fulfillment_plan"]=hospital_plan
                    result=await call_remote_tool("dispatch_notifications",hospital_payload)
                    result["recipient_notifications"]=attempts
                else:
                    result = await call_remote_tool("dispatch_notifications", notification_payload)
            elif self.agent_name in ("CommunicationAgent", "CallingAgent"):
                result = await call_remote_tool("dispatch_notifications", payload)
            else:
                result = await _coordinate_over_a2a(payload, correlation_id=correlation_id)
            if (
                isinstance(result, dict)
                and result.get("success") is False
                and not payload.get("return_structured_failure")
            ):
                raise ValueError(result.get("error", "Agent could not complete request"))
            answer = json.dumps(result, default=str)
        except Exception as exc:
            failed = True
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            error = exc.as_dict() if hasattr(exc, "as_dict") else {"error": str(exc)}
            answer = json.dumps({**error, "agent": self.agent_name})
        finally:
            span.end()
        response = Message(
            role="ROLE_AGENT",
            parts=[Part(text=answer)],
            message_id=f"{context.task_id or 'request'}-result",
            context_id=context.context_id,
            task_id=context.task_id,
            metadata={
                "taskId": context.task_id,
                "correlationId": correlation_id if "correlation_id" in locals() else context.context_id,
                "agentId": os.getenv("A2A_AGENT_ID", self.agent_name.removesuffix("Agent").lower()),
            },
        )
        await event_queue.enqueue_event(response)
        return not failed

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None


def build_agent_app(agent_name: str, description: str, skills: list[str]) -> Any:
    """Build a JSON-RPC A2A service, its well-known Agent Card endpoint, and /a2a service auth."""
    configure_telemetry(agent_name)
    agent_id = os.getenv("A2A_AGENT_ID", agent_name.removesuffix("Agent").lower())
    input_modes = ["application/json", "text/plain"]
    output_modes = ["application/json"]
    card = AgentCard(
        name=agent_name,
        description=description,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(
            id=skill,
            name=skill.replace("-", " ").title(),
            description=description,
            tags=[skill, "blood-donation"],
            examples=[],
            input_modes=input_modes,
            output_modes=output_modes,
        ) for skill in skills],
        supported_interfaces=[
            AgentInterface(
                url=os.getenv(f"{agent_id.replace('-', '_').upper()}AGENT_A2A_URL", os.getenv("A2A_PUBLIC_URL", "http://localhost:8000/a2a")),
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=DomainAgentExecutor(agent_name),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = Starlette(routes=[])
    async def card_response(request: Request):
        data = MessageToDict(card, preserving_proto_field_name=False)
        origin = str(request.base_url).rstrip("/")
        data["agentId"] = agent_id
        data["metadata"] = {
            "agentId": agent_id,
            "availability": "available",
            "healthUrl": f"{origin}/health",
        }
        return JSONResponse(data)

    async def health_response(request: Request):
        return JSONResponse({"status": "healthy", "agent_id": agent_id, "agent": agent_name})

    app.routes.append(Route("/.well-known/agent-card.json", card_response, methods=["GET"]))
    app.routes.append(Route("/health", health_response, methods=["GET"]))
    app.routes.extend(create_jsonrpc_routes(handler, rpc_url="/a2a"))
    secured = ServiceAuthenticationMiddleware(app, protected_prefix="/a2a")
    return instrument_asgi(secured, agent_name.removesuffix("Agent").lower())


AGENT_APPS = {
    "coordinator": build_agent_app(
        "CoordinatorAgent",
        "Coordinates blood request validation, matching, and location workflows.",
        ["coordinate", "coordinate-blood-request", "blood-donation"],
    ),
    "requirement": build_agent_app(
        "RequirementAgent",
        "Validates and normalizes blood requests.",
        ["validate-request", "validate-blood-request", "blood-donation"],
    ),
    "matching": build_agent_app(
        "MatchingAgent",
        "Finds compatible eligible blood sources.",
        ["find-sources", "find-compatible-blood-sources", "blood-donation"],
    ),
    "location": build_agent_app(
        "LocationAgent",
        "Calculates source distance and travel estimates.",
        ["calculate-distance", "calculate-source-distance", "blood-donation"],
    ),
    "notification": build_agent_app(
        "NotificationAgent",
        "Dispatches notifications for fulfillment plans.",
        ["notify", "dispatch-fulfillment-notifications", "blood-donation"],
    ),
    "communication": build_agent_app(
        "CommunicationAgent",
        "Orchestrates interactive outreach, donor RSVPs, and emergency SLA escalations.",
        ["communicate", "blood-donation"],
    ),
    "calling": build_agent_app(
        "CallingAgent",
        "Dispatches automated outbound emergency voice calls and processes IVR touch-tone responses.",
        ["call", "blood-donation"],
    ),
    "pharmacy": build_agent_app(
        "PharmacyAgent",
        "Fulfills medicine orders through validated local pharmacy inventory.",
        ["fulfill-pharmacy-order", "medicine-delivery"],
    ),
    "emergency-priority": build_agent_app(
        "EmergencyPriorityAgent",
        "Evaluates request priority, recommends escalation, and prioritizes critical requests.",
        ["evaluate-emergency-priority", "recommend-emergency-escalation", "prioritize-critical-requests"],
    ),
}
