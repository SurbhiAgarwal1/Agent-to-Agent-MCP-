"""A2A SDK client helper with Agent Card skill discovery, service auth, bounded retries, and timeouts."""

import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import Message, Part, SendMessageRequest
from opentelemetry import trace

from app.agents.a2a.discovery import (
    card_matches_skill,
    default_skill_for_agent,
    discover_agent_by_skill,
    normalize_agent_key,
    resolve_agent_base_url,
)
from app.observability.tracing import (
    A2A_DURATION,
    A2A_ERRORS,
    A2A_REQUESTS,
    configure_telemetry,
    instrument_http_client,
)
from app.security.service_auth import service_auth_headers

tracer = trace.get_tracer("app.agents.a2a.client")

_ALLOWED_OPERATIONS = {
    "message",
    "REQUIREMENT_VALIDATE_REQUEST",
    "MATCHING_FIND_SOURCES_REQUEST",
    "LOCATION_CALCULATE_DISTANCES_REQUEST",
    "NOTIFICATION_DISPATCH_REQUEST",
    "EMERGENCY_PRIORITY_EVALUATE_REQUEST",
    "COORDINATE_REQUEST",
}


async def call_remote_agent_by_skill(
    skill: str,
    payload: Dict[str, Any],
    *,
    operation: str = "message",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Discover an A2A agent by advertised capability and send a JSON task."""
    import inspect
    kwargs: Dict[str, Any] = {"skill": skill, "operation": operation}
    sig = inspect.signature(call_remote_agent)
    if "correlation_id" in sig.parameters:
        kwargs["correlation_id"] = correlation_id
    return await call_remote_agent(
        skill,
        payload,
        **kwargs,
    )


async def call_remote_agent(
    agent: str,
    payload: Dict[str, Any],
    *,
    port: Optional[int] = None,
    skill: Optional[str] = None,
    operation: str = "message",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Discover an agent card and send a JSON task using the official A2A client."""
    source = os.getenv("OTEL_SERVICE_NAME", os.getenv("A2A_AGENT", "coordinator")).lower()
    target = normalize_agent_key(agent) or str(agent)
    if operation not in _ALLOWED_OPERATIONS:
        operation = "other"
    attrs = {"source_agent": source, "target_agent": target, "operation": operation}
    started = time.perf_counter()
    status = "error"
    configure_telemetry(source)
    instrument_http_client()
    with tracer.start_as_current_span(
        "a2a.request",
        attributes={
            "a2a.source_agent": source,
            "a2a.target_agent": target,
            "a2a.operation": operation,
        },
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            result = await _call_remote_agent(agent, payload, port=port, skill=skill, operation=operation, correlation_id=correlation_id)
            status = "success"
            span.set_attribute("a2a.status", "success")
            A2A_REQUESTS.add(1, {**attrs, "status": "success"})
            return result
        except Exception as exc:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.set_attribute("error.type", type(exc).__name__)
            A2A_ERRORS.add(1, {**attrs, "status": "error"})
            A2A_REQUESTS.add(1, {**attrs, "status": "error"})
            raise
        finally:
            A2A_DURATION.record((time.perf_counter() - started) * 1000, {**attrs, "status": status})


async def _call_remote_agent(
    agent: Optional[str],
    payload: Dict[str, Any],
    *,
    port: Optional[int] = None,
    skill: Optional[str] = None,
    operation: str = "message",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    required_skill = skill or (default_skill_for_agent(agent) if agent else None)
    if not required_skill:
        raise ValueError("A capability is required for A2A agent selection")
    timeout = float(os.getenv("A2A_TIMEOUT_SECONDS", "20"))
    attempts = max(1, int(os.getenv("A2A_MAX_RETRIES", "2")) + 1)
    headers = service_auth_headers()
    last_error: Optional[Exception] = None
    task_id = str(uuid.uuid4())
    context_id = correlation_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    request_metadata = {"taskId": task_id, "correlationId": context_id, "capability": required_skill, "operation": operation}
    selected_agent_id = required_skill

    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as http_client:
                base, card = await discover_agent_by_skill(
                    required_skill,
                    preferred_agent=agent,
                    port=port,
                    http_client=http_client,
                    timeout=timeout,
                )
                selected_agent_id = str(card.get("agentId") or required_skill)
                if not card_matches_skill(card, required_skill):
                    raise RuntimeError(f"Selected agent does not advertise capability '{required_skill}'")

                factory = ClientFactory(
                    ClientConfig(
                        httpx_client=http_client,
                        accepted_output_modes=["application/json", "text/plain"],
                    )
                )
                # The official SDK resolves the standard Agent Card path itself.
                client = await factory.create_from_url(base.rstrip("/"))
                request = SendMessageRequest(
                    message=Message(
                        message_id=message_id,
                        context_id=context_id,
                        role="ROLE_USER",
                        parts=[Part(text=json.dumps(payload, default=str))],
                        metadata=request_metadata,
                    )
                )
                async for response in client.send_message(request):
                    with tracer.start_as_current_span(
                        "a2a.response",
                        attributes={"a2a.target_agent": normalize_agent_key(agent)},
                        record_exception=False,
                        set_status_on_exception=False,
                    ):
                        if response.message:
                            for part in response.message.parts:
                                if part.text:
                                    decoded = json.loads(part.text)
                                    if isinstance(decoded, dict):
                                        if "error" in decoded:
                                            error = decoded["error"]
                                            raise RuntimeError(error if isinstance(error, str) else str(error))
                                        response_metadata = dict(response.message.metadata) if response.message.metadata else {}
                                        decoded["_a2a"] = {
                                            "task_id": response_metadata.get("taskId") or response.message.task_id or task_id,
                                            "context_id": response.message.context_id or context_id,
                                            "correlation_id": response_metadata.get("correlationId") or context_id,
                                            "agent_id": response_metadata.get("agentId") or selected_agent_id,
                                            "capability": required_skill,
                                            "operation": operation,
                                        }
                                        return decoded
            raise RuntimeError(f"A2A agent '{agent}' returned no message")
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(min(0.2 * (attempt + 1), timeout / 2))
    label = agent or required_skill
    if agent and agent != required_skill:
        message = f"A2A call to '{agent}' failed after {attempts} attempt(s): {last_error}"
    else:
        message = f"A2A call for capability '{required_skill}' failed after {attempts} attempt(s): {last_error}"
    raise RuntimeError(message) from last_error
