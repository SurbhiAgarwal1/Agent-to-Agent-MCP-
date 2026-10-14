"""OpenTelemetry setup and privacy-safe HTTP instrumentation."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from opentelemetry import metrics, propagate, trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace import SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_lock = threading.Lock()
_configured = False
_http_instrumented = False
_scrape_server_started = False
_service_name = "unknown"
_meter = metrics.get_meter("blood-donation.observability")
_HTTP_TRACER = trace.get_tracer("blood-donation.http")
HTTP_REQUESTS = _meter.create_counter("http.server.request.count", description="HTTP server requests")
HTTP_ERRORS = _meter.create_counter("http.server.error.count", description="HTTP server errors")
HTTP_DURATION = _meter.create_histogram("http.server.request.duration", unit="ms", description="HTTP server request duration")
A2A_REQUESTS = _meter.create_counter("a2a.requests", description="A2A requests")
A2A_ERRORS = _meter.create_counter("a2a.errors", description="A2A request errors")
A2A_DURATION = _meter.create_histogram("a2a.request.duration", unit="ms", description="A2A request duration")
MCP_DISCOVERIES = _meter.create_counter("mcp.tool.discovery", description="MCP tool discovery operations")
MCP_CALLS = _meter.create_counter("mcp.tool.calls", description="MCP tool calls")
MCP_ERRORS = _meter.create_counter("mcp.tool.errors", description="MCP tool errors")
MCP_DURATION = _meter.create_histogram("mcp.tool.duration", unit="ms", description="MCP tool call duration")
LLM_REQUESTS = _meter.create_counter("llm.requests", description="LLM planner requests")
LLM_ERRORS = _meter.create_counter("llm.errors", description="LLM planner errors")
LLM_DURATION = _meter.create_histogram("llm.request.duration", unit="ms", description="LLM planner request duration")
LLM_INPUT_TOKENS = _meter.create_counter("llm.input.tokens", unit="{token}", description="Provider-reported input tokens")
LLM_OUTPUT_TOKENS = _meter.create_counter("llm.output.tokens", unit="{token}", description="Provider-reported output tokens")
LLM_TOTAL_TOKENS = _meter.create_counter("llm.total.tokens", unit="{token}", description="Provider-reported total tokens")
WORKFLOWS = _meter.create_counter("workflow.requests", description="Coordinator workflows")
WORKFLOW_ERRORS = _meter.create_counter("workflow.errors", description="Failed coordinator workflows")
WORKFLOW_DURATION = _meter.create_histogram("workflow.duration", unit="ms", description="Coordinator workflow duration")
AGENT_REQUESTS = _meter.create_counter("agent.requests", description="Specialized agent executions")
AGENT_ERRORS = _meter.create_counter("agent.errors", description="Failed specialized agent executions")
AGENT_DURATION = _meter.create_histogram("agent.duration", unit="ms", description="Specialized agent execution duration")


class _JsonFormatter(logging.Formatter):
    """Emit structured logs with current trace context, without exception payloads."""

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "service": os.getenv("OTEL_SERVICE_NAME", _service_name),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if span_context.is_valid:
            data["trace_id"] = f"{span_context.trace_id:032x}"
            data["span_id"] = f"{span_context.span_id:016x}"
        return json.dumps(data, ensure_ascii=False, default=str)


def _configure_json_logging(service_name: str) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        root.addHandler(handler)
    for handler in root.handlers:
        handler.setFormatter(_JsonFormatter())
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def configure_telemetry(service_name: str) -> None:
    """Configure no-throw SDK exporters. The business service works when disabled or unavailable."""
    global _configured, _service_name, _scrape_server_started
    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)
    _service_name = service_name
    _configure_json_logging(service_name)
    set_global_textmap(TraceContextTextMapPropagator())
    if os.getenv("OBSERVABILITY_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return
    with _lock:
        if _configured:
            return
        resource = None
        try:
            from opentelemetry.sdk.resources import Resource
            resource = Resource.create({"service.name": service_name})
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            if not isinstance(trace.get_tracer_provider(), TracerProvider):
                provider = TracerProvider(resource=resource)
                endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
                protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").lower()
                if os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower() == "otlp":
                    if protocol == "grpc":
                        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                        exporter = OTLPSpanExporter(endpoint=endpoint)
                    else:
                        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                        exporter = OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
                    provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(provider)
            if os.getenv("OTEL_METRICS_EXPORTER", "prometheus").lower() == "prometheus":
                from opentelemetry.exporter.prometheus import PrometheusMetricReader
                from opentelemetry.sdk.metrics import MeterProvider
                if not isinstance(metrics.get_meter_provider(), MeterProvider):
                    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[PrometheusMetricReader()]))
                if not _scrape_server_started:
                    from prometheus_client import start_http_server
                    start_http_server(port=int(os.getenv("OBSERVABILITY_METRICS_PORT", "9464")), addr="0.0.0.0")
                    _scrape_server_started = True
            _configured = True
        except Exception as exc:
            # Exporter/backend setup is operationally optional and must never stop service startup.
            logging.getLogger(__name__).warning("OpenTelemetry initialization unavailable (%s)", type(exc).__name__)


def instrument_http_client() -> None:
    """Enable W3C context propagation for HTTPX A2A and MCP network calls."""
    global _http_instrumented
    if _http_instrumented or os.getenv("OBSERVABILITY_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        _http_instrumented = True
    except Exception as exc:
        logging.getLogger(__name__).warning("HTTP client tracing unavailable (%s)", type(exc).__name__)


class _HTTPMetricsMiddleware:
    """ASGI metrics with normalized route labels; raw URLs and query values are excluded."""

    def __init__(self, app, service_name: str):
        self.app = app
        self.service_name = service_name

    @property
    def routes(self):
        """Preserve Starlette route introspection for service wiring and tests."""
        inner = self.app
        while inner is not None:
            routes = getattr(inner, "routes", None)
            if routes is not None:
                return routes
            inner = getattr(inner, "app", None)
        return []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            route_name = getattr(route, "path", "unmatched")
            attrs = {"service": self.service_name, "method": scope.get("method", "OTHER"), "route": route_name, "status_code": str(status)}
            HTTP_REQUESTS.add(1, attrs)
            HTTP_DURATION.record((time.perf_counter() - started) * 1000, attrs)
            if status >= 400:
                HTTP_ERRORS.add(1, attrs)


class _ASGIHeaderGetter:
    """Read W3C headers from an ASGI scope without attaching the carrier to spans."""

    def get(self, carrier, key):
        for header, value in carrier.get("headers", []):
            if header.decode("latin1").lower() == key.lower():
                return [value.decode("latin1")]
        return None

    def keys(self, carrier):
        return [key.decode("latin1").lower() for key, _ in carrier.get("headers", [])]


class _PrivacyTracingMiddleware:
    """Create request spans with only method, normalized route, and response status."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        parent = propagate.extract(scope, getter=_ASGIHeaderGetter())
        status = 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message.get("status", 500))
            await send(message)

        attributes = {"http.request.method": scope.get("method", "OTHER")}
        with _HTTP_TRACER.start_as_current_span(
            "http.server.request", context=parent, kind=SpanKind.SERVER,
            attributes=attributes, record_exception=False, set_status_on_exception=False,
        ) as span:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("error.type", type(exc).__name__)
                raise
            finally:
                route = scope.get("route")
                route_name = getattr(route, "path", "unmatched")
                span.set_attribute("http.route", route_name)
                span.set_attribute("http.response.status_code", status)
                if status >= 500:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))


def instrument_fastapi(app, service_name: str) -> None:
    configure_telemetry(service_name)
    instrument_http_client()
    app.add_middleware(_PrivacyTracingMiddleware)
    app.add_middleware(_HTTPMetricsMiddleware, service_name=os.getenv("OTEL_SERVICE_NAME", service_name))


def instrument_asgi(app, service_name: str):
    configure_telemetry(service_name)
    instrument_http_client()
    return _HTTPMetricsMiddleware(_PrivacyTracingMiddleware(app), os.getenv("OTEL_SERVICE_NAME", service_name))
