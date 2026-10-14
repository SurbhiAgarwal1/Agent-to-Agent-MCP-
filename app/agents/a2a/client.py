"""A2A SDK client helper with bounded retries and request timeouts."""

import json
import os
import asyncio
import uuid
import time

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import Message, Part, SendMessageRequest
from opentelemetry import trace
from app.observability.tracing import A2A_DURATION, A2A_ERRORS, A2A_REQUESTS, configure_telemetry, instrument_http_client

tracer = trace.get_tracer("app.agents.a2a.client")


async def call_remote_agent(agent: str, payload: dict, *, port: int, operation: str = "message") -> dict:
    """Discover an agent card and send a JSON task using the official A2A client."""
    source = os.getenv("OTEL_SERVICE_NAME", os.getenv("A2A_AGENT", "coordinator")).lower()
    target = agent.removesuffix("Agent").lower()
    if operation not in {"message", "REQUIREMENT_VALIDATE_REQUEST", "MATCHING_FIND_SOURCES_REQUEST", "LOCATION_CALCULATE_DISTANCES_REQUEST", "NOTIFICATION_DISPATCH_REQUEST", "COORDINATE_REQUEST"}:
        operation = "other"
    attrs = {"source_agent": source, "target_agent": target, "operation": operation}
    started = time.perf_counter()
    status = "error"
    configure_telemetry(source)
    instrument_http_client()
    with tracer.start_as_current_span("a2a.request", attributes={"a2a.source_agent": source, "a2a.target_agent": target, "a2a.operation": operation}, record_exception=False, set_status_on_exception=False) as span:
        try:
            result = await _call_remote_agent(agent, payload, port=port)
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


async def _call_remote_agent(agent: str, payload: dict, *, port: int) -> dict:
    base = os.getenv(f"{agent.upper()}_BASE_URL", f"http://127.0.0.1:{port}")
    timeout = float(os.getenv("A2A_TIMEOUT_SECONDS", "20"))
    attempts = max(1, int(os.getenv("A2A_MAX_RETRIES", "2")) + 1)
    last_error = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                factory = ClientFactory(ClientConfig(httpx_client=http_client, accepted_output_modes=["application/json", "text/plain"]))
                # The official SDK resolves the standard Agent Card path itself.
                client = await factory.create_from_url(base.rstrip("/"))
                request = SendMessageRequest(message=Message(
                    message_id=str(uuid.uuid4()),
                    role="ROLE_USER",
                    parts=[Part(text=json.dumps(payload, default=str))],
                ))
                async for response in client.send_message(request):
                    with tracer.start_as_current_span("a2a.response", attributes={"a2a.target_agent": agent.removesuffix("Agent").lower()}, record_exception=False, set_status_on_exception=False):
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
                await asyncio.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"A2A call to '{agent}' failed after {attempts} attempt(s): {last_error}") from last_error
