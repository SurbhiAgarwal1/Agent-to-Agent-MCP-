"""Official A2A SDK server adapters for the existing agent business logic."""

import json
import os
import time
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part
from opentelemetry import trace
from app.observability.tracing import (
    AGENT_DURATION, AGENT_ERRORS, AGENT_REQUESTS, configure_telemetry, instrument_asgi,
)
from starlette.applications import Starlette

_tracer = trace.get_tracer("app.agents.a2a.server")


async def _coordinate_over_a2a(payload: dict) -> dict:
    """Run the established coordinator workflow with its remote A2A transport."""
    from app.database.session import SessionLocal
    from app.agents.coordinator_agent import CoordinatorAgent

    def run():
        db = SessionLocal()
        try:
            coordinator = CoordinatorAgent(db=db, network=True)
            persist = bool(payload.get("persist", False))
            if isinstance(payload.get("user_request"), str):
                return coordinator.coordinate_text(
                    payload["user_request"],
                    persist=persist,
                    request_id=payload.get("request_id"),
                )
            request = payload.get("request_id") if persist else payload
            return coordinator.coordinate(request_input=request, persist=persist)
        finally:
            db.close()

    # Network calls are made by the synchronous domain coordinator; isolate them from
    # the A2A server event loop while preserving the existing allocation workflow.
    import asyncio
    return await asyncio.to_thread(run)


class DomainAgentExecutor(AgentExecutor):
    """Translate A2A message text into existing validated agent operations."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        agent = self.agent_name.removesuffix("Agent").lower()
        started = time.perf_counter()
        attrs = {"agent": agent}
        status = "error"
        with _tracer.start_as_current_span("agent.execute", attributes={"agent.name": agent}, record_exception=False, set_status_on_exception=False) as span:
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
        span = _tracer.start_span("agent.dispatch", attributes={"agent.name": self.agent_name.removesuffix("Agent").lower()})
        failed = False
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("A2A request must contain a JSON object")
            from app.mcp.client import call_remote_tool
            if self.agent_name == "RequirementAgent":
                validated = await call_remote_tool("validate_blood_request", payload)
                if not validated.get("valid"):
                    raise ValueError("Requirement validation failed: " + "; ".join(validated.get("errors", [])))
                result = {"requirement": validated}
            elif self.agent_name == "MatchingAgent":
                req = payload.get("requirement", payload)
                result = await call_remote_tool("find_blood_sources", {
                    "blood_group": req["blood_group"],
                    "request_id": req.get("request_id"),
                    "inventories": payload.get("inventories"),
                    "donors": payload.get("donors"),
                })
            elif self.agent_name == "LocationAgent":
                origin = payload.get("hospital_coords", payload)
                candidates = payload.get("candidates")
                if candidates is None:
                    result = await call_remote_tool("calculate_distance", payload)
                else:
                    located = []
                    for candidate in candidates:
                        lat, lon = candidate.get("latitude"), candidate.get("longitude")
                        if lat is None or lon is None:
                            located.append(candidate)
                            continue
                        distance = await call_remote_tool("calculate_distance", {
                            "origin_latitude": origin["latitude"], "origin_longitude": origin["longitude"],
                            "destination_latitude": lat, "destination_longitude": lon, "include_eta": True,
                        })
                        located.append({**candidate, **distance})
                    result = {"candidates": sorted(located, key=lambda item: item.get("distance_km", float("inf")))}
            elif self.agent_name == "NotificationAgent":
                result = await call_remote_tool("dispatch_notifications", payload)
            else:
                result = await _coordinate_over_a2a(payload)
            if isinstance(result, dict) and result.get("success") is False:
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
        )
        await event_queue.enqueue_event(response)
        return not failed

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None


def build_agent_app(agent_name: str, description: str, skills: list[str]) -> Starlette:
    """Build a JSON-RPC A2A service and its well-known Agent Card endpoint."""
    configure_telemetry(agent_name)
    card = AgentCard(
        name=agent_name,
        description=description,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(id=agent_name.lower(), name=agent_name, description=description, tags=skills, examples=[])],
        supported_interfaces=[AgentInterface(
            url=os.getenv(f"{agent_name.upper()}_A2A_URL", "http://localhost:8000/a2a"),
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )],
    )
    handler = DefaultRequestHandler(
        agent_executor=DomainAgentExecutor(agent_name),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = Starlette(routes=[])
    app.routes.extend(create_agent_card_routes(card))
    app.routes.extend(create_jsonrpc_routes(handler, rpc_url="/a2a"))
    return instrument_asgi(app, agent_name.removesuffix("Agent").lower())


AGENT_APPS = {
    "coordinator": build_agent_app("CoordinatorAgent", "Coordinates blood request validation, matching, and location workflows.", ["coordinate", "blood-donation"]),
    "requirement": build_agent_app("RequirementAgent", "Validates and normalizes blood requests.", ["validate-request", "blood-donation"]),
    "matching": build_agent_app("MatchingAgent", "Finds compatible eligible blood sources.", ["find-sources", "blood-donation"]),
    "location": build_agent_app("LocationAgent", "Calculates source distance and travel estimates.", ["calculate-distance", "blood-donation"]),
    "notification": build_agent_app("NotificationAgent", "Dispatches notifications for fulfillment plans.", ["notify", "blood-donation"]),
}
