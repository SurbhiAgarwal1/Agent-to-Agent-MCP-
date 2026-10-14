"""Observability boundary, instrumentation, and W3C propagation checks."""

import os
import socket
import subprocess
import sys
import threading
import asyncio
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from opentelemetry import trace
from opentelemetry.propagate import get_global_textmap
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import app
from app.observability import tracing


def test_observability_routes_are_not_part_of_the_public_gateway(client):
    assert client.get("/metrics").status_code == 404
    assert client.get("/llm/usage").status_code == 404
    assert client.get("/health").status_code == 200
    routes = {getattr(route, "path", "") for route in app.routes}
    assert "/metrics" not in routes
    assert "/llm/usage" not in routes


def test_telemetry_can_be_disabled_without_affecting_application(monkeypatch, client):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "false")
    tracing.configure_telemetry("test-service")
    assert client.get("/health").status_code == 200


def test_otel_metrics_are_recorded_with_bounded_attributes():
    reader = InMemoryMetricReader()
    provider = MeterProvider(resource=Resource.create({"service.name": "test"}), metric_readers=[reader])
    counter = provider.get_meter("test").create_counter("test.requests")
    counter.add(1, {"status": "success", "service": "test"})
    data = reader.get_metrics_data()
    assert data is not None
    assert data.resource_metrics[0].scope_metrics[0].metrics[0].name == "test.requests"
    point = data.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
    assert dict(point.attributes) == {"status": "success", "service": "test"}
    provider.shutdown()


def test_w3c_trace_context_round_trips_between_http_boundaries():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    carrier = {}
    with tracer.start_as_current_span("gateway.request") as parent:
        expected_trace_id = parent.get_span_context().trace_id
        get_global_textmap().inject(carrier)
    extracted = get_global_textmap().extract(carrier)
    with tracer.start_as_current_span("remote.agent", context=extracted):
        pass
    spans = exporter.get_finished_spans()
    assert spans[0].name == "gateway.request"
    assert spans[1].name == "remote.agent"
    assert spans[0].context.trace_id == spans[1].context.trace_id == expected_trace_id
    provider.shutdown()


def test_httpx_instrumentation_injects_w3c_context(monkeypatch):
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setattr(tracing, "_http_instrumented", False)
    observed = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.update(self.headers)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_):
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    provider = TracerProvider()
    tracer = provider.get_tracer("http-propagation-test")
    tracing.instrument_http_client()
    try:
        with tracer.start_as_current_span("gateway.request") as parent:
            expected_trace_id = f"{parent.get_span_context().trace_id:032x}"
            with httpx.Client() as client:
                assert client.get(f"http://127.0.0.1:{server.server_port}/a2a").status_code == 200
        assert observed["traceparent"].split("-")[1] == expected_trace_id
    finally:
        HTTPXClientInstrumentor().uninstrument()
        monkeypatch.setattr(tracing, "_http_instrumented", False)
        server.shutdown()
        server.server_close()
        provider.shutdown()


def test_asgi_server_extracts_w3c_trace_context():
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    carrier = {}
    with provider.get_tracer("server-parent-test").start_as_current_span("parent") as parent:
        expected = parent.get_span_context().trace_id
        get_global_textmap().inject(carrier)
    observed = {}

    async def endpoint(scope, receive, send):
        observed["trace_id"] = trace.get_current_span().get_span_context().trace_id
        scope["route"] = SimpleNamespace(path="/health")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = tracing.instrument_asgi(endpoint, "asgi-test")
    scope = {
        "type": "http", "method": "GET",
        "headers": [(b"traceparent", carrier["traceparent"].encode("ascii"))],
    }
    extracted = tracing.propagate.extract(scope, getter=tracing._ASGIHeaderGetter())
    assert trace.get_current_span(extracted).get_span_context().trace_id == expected
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(_message):
        return None

    asyncio.run(wrapped(scope, receive, send))
    assert observed["trace_id"] == expected
    provider.shutdown()


def test_core_instrumentation_families_are_defined():
    assert tracing.HTTP_REQUESTS is not None
    assert tracing.A2A_REQUESTS is not None
    assert tracing.MCP_CALLS is not None
    assert tracing.LLM_REQUESTS is not None
    assert tracing.WORKFLOWS is not None


def test_internal_prometheus_scrape_endpoint_serves_otel_metrics():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    code = """
import time, urllib.request
from app.observability import tracing as telemetry
configure_telemetry = telemetry.configure_telemetry
configure_telemetry('metrics-test')
for instrument, labels in [
    (telemetry.HTTP_REQUESTS, {'service':'metrics-test','method':'GET','route':'/health','status_code':'200'}),
    (telemetry.A2A_REQUESTS, {'source_agent':'coordinator','target_agent':'requirement','operation':'REQUIREMENT_VALIDATE_REQUEST','status':'success'}),
    (telemetry.MCP_CALLS, {'tool':'validate_blood_request','status':'success'}),
    (telemetry.LLM_REQUESTS, {'provider':'mock','model':'deterministic-mock','status':'success'}),
    (telemetry.WORKFLOWS, {'status':'success'}),
    (telemetry.AGENT_REQUESTS, {'agent':'requirement','status':'success'}),
]:
    instrument.add(1, labels)
telemetry.A2A_DURATION.record(12, {'source_agent':'coordinator','target_agent':'requirement','operation':'REQUIREMENT_VALIDATE_REQUEST','status':'success'})
telemetry.MCP_DURATION.record(12, {'tool':'validate_blood_request','status':'success'})
telemetry.LLM_DURATION.record(12, {'provider':'mock','model':'deterministic-mock','status':'success'})
telemetry.WORKFLOW_DURATION.record(12, {'status':'success'})
telemetry.LLM_INPUT_TOKENS.add(0, {'provider':'mock','model':'deterministic-mock'})
for _ in range(30):
    try:
        body = urllib.request.urlopen('http://127.0.0.1:%s/metrics', timeout=1).read().decode()
        assert 'http_server_request_count_total' in body
        assert 'a2a_requests_total' in body
        assert 'mcp_tool_calls_total' in body
        assert 'llm_requests_total' in body
        assert 'llm_input_tokens_total' in body
        assert 'workflow_requests_total' in body
        assert 'agent_requests_total' in body
        assert 'workflow_duration_milliseconds_bucket' in body
        assert 'route=\"/health\"' in body
        break
    except OSError:
        time.sleep(0.1)
else:
    raise AssertionError('Prometheus scrape endpoint did not start')
""" % port
    env = os.environ.copy()
    env.update({
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_METRICS_PORT": str(port),
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "prometheus",
    })
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
