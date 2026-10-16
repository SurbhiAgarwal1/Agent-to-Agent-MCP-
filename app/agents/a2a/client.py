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
    AGENT_BY_SKILL,
    agent_env_prefix,
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
    "COORDINATE_REQUEST",
}


async def call_remote_agent_by_skill(
    skill: str,
    payload: Dict[str, Any],
    *,
    preferred_agent: Optional[str] = None,
    operation: str = "message",
) -> Dict[str, Any]:
    """Discover an A2A agent by advertised AgentCard skill and send a JSON task."""
    agent_hint = preferred_agent or AGENT_BY_SKILL.get(skill, skill)
    return await call_remote_agent(
        agent_hint,
        payload,
        skill=skill,
        operation=operation,
    )


async def call_remote_agent(
    agent: str,
    payload: Dict[str, Any],
    *,
    port: Optional[int] = None,
    skill: Optional[str] = None,
    operation: str = "message",
) -> Dict[str, Any]:
    """Discover an agent card and send a JSON task using the official A2A client."""
    source = os.getenv("OTEL_SERVICE_NAME", os.getenv("A2A_AGENT", "coordinator")).lower()
    target = normalize_agent_key(agent) or agent.removesuffix("Agent").lower()
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
            result = await _call_remote_agent(agent, payload, port=port, skill=skill)
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
    agent: str,
    payload: Dict[str, Any],
    *,
    port: Optional[int] = None,
    skill: Optional[str] = None,
) -> Dict[str, Any]:
    prefix = agent_env_prefix(agent)
    explicit_agent_url = os.getenv(f"{prefix}_BASE_URL", "").strip() or os.getenv(f"{prefix}_A2A_URL", "").strip()
    required_skill = skill or default_skill_for_agent(agent)
    timeout = float(os.getenv("A2A_TIMEOUT_SECONDS", "20"))
    attempts = max(1, int(os.getenv("A2A_MAX_RETRIES", "2")) + 1)
    headers = service_auth_headers()
    last_error: Optional[Exception] = None

    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as http_client:
                if explicit_agent_url or port is not None or not required_skill:
                    base = resolve_agent_base_url(agent, port=port)
                else:
                    base, card = await discover_agent_by_skill(
                        required_skill,
                        preferred_agent=agent,
                        port=port,
                        http_client=http_client,
                        timeout=timeout,
                    )
                    if not card_matches_skill(card, required_skill):
                        raise RuntimeError(f"Agent at {base} does not advertise skill '{required_skill}'")

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
                        message_id=str(uuid.uuid4()),
                        role="ROLE_USER",
                        parts=[Part(text=json.dumps(payload, default=str))],
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
                                            raise RuntimeError(decoded["error"])
                                        return decoded
            raise RuntimeError(f"A2A agent '{agent}' returned no message")
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(min(0.2 * (attempt + 1), timeout / 2))
    raise RuntimeError(f"A2A call to '{agent}' failed after {attempts} attempt(s): {last_error}") from last_error
