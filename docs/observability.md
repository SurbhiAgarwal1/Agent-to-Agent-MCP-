# Phase 4: observability and operations boundary

**Observability is an internal administrative/operations capability and is not exposed to normal users or hospital staff.** No observability page, raw metric, trace, or LLM usage endpoint is routed through the public gateway.

## Architecture

The gateway, Coordinator A2A service, four specialized A2A services, and MCP Streamable HTTP service use the OpenTelemetry Python SDK. W3C Trace Context is used for propagation. HTTPX instrumentation propagates trace context across the actual A2A and MCP HTTP calls. The gateway/FastAPI and Starlette A2A/MCP servers create incoming HTTP spans; application spans cover `workflow.coordinate`, `llm.generate`, `a2a.request`, `agent.execute`, `mcp.list_tools`, `mcp.tool`, and `domain.operation`.

Traces use OTLP HTTP/protobuf to Jaeger. Each service exposes an OpenTelemetry Prometheus reader on port `9464`; Prometheus scrapes these endpoints by Docker Compose DNS. That port is container-network-only: it is not mapped to the host, exposed through the gateway, or registered as a public API route. Grafana is provisioned with Prometheus and Jaeger datasources and dashboards for system health, A2A, MCP, LLM, and workflows.

```text
User/API -> Gateway -> Coordinator --A2A HTTP--> Specialized Agent --MCP Streamable HTTP--> MCP Server -> Domain tool
                 |              |                        |                                  |
                 +--------------+------------------------+----------------------------------+
                            OpenTelemetry traces/metrics/log correlation
                               |                         |
                             Jaeger                 Prometheus -> Grafana
```

## Local startup and access

1. Copy `.env.example` to `.env` and set `JWT_SECRET_KEY` plus a unique `GRAFANA_ADMIN_PASSWORD`.
2. Start the Compose stack with `docker compose up --build`.
3. Open Grafana at `http://localhost:3001`, Prometheus at `http://localhost:9090`, or Jaeger at `http://localhost:16686` on the Compose host. Grafana requires its configured admin login. Prometheus and Jaeger provide no built-in login in this local stack; their UI ports are bound only to loopback.
4. In Jaeger, select `gateway`, `coordinator-agent`, or another service and find a recent `workflow.coordinate` trace. Expand its A2A, MCP, and `domain.operation` child spans. In Grafana, open the provisioned dashboards under **Operations**. Prometheus target health is also available under **Status → Targets**.

The Compose loopback binding is suitable only for a trusted developer machine. For any shared or hosted environment, keep the tools on a private operations network and put Grafana, Jaeger, and Prometheus behind the organization’s authenticated administrator access boundary (for example, SSO/VPN/reverse proxy). Do not publish the service metrics ports.

## Configuration

`OBSERVABILITY_ENABLED` defaults to `false` in application code and is enabled by Compose for local operations. With it disabled, services continue without an exporter or telemetry backend. Relevant settings are `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`, and `OBSERVABILITY_METRICS_PORT`. If you change the scrape port, update `observability/prometheus.yml` to match. OTLP trace export is batched; metrics are scraped on demand. Exporter initialization is best-effort and cannot stop business service startup.

## Metrics, traces, and logs

Metrics use bounded labels such as service, agent, target agent, operation, tool name, provider, model, status, HTTP method, normalized route, and status code. Counters and histograms cover HTTP requests/errors/latency, agent executions, A2A requests/errors/latency, MCP discovery/tool calls/errors/latency, LLM requests/errors/latency/provider-reported token counts, and workflow outcomes/latency. MockReasoner is visible in request and latency metrics; its token counts are zero. Gemini is not needed for local observability.

Logs are JSON on stdout with timestamp, service, level, and active trace/span IDs when present. The formatter does not attach exception objects. Audit and console-notification log messages omit user/resource IDs, recipients, and notification contents; Uvicorn access logs are disabled for internal protocol services. Instrumentation does not attach request bodies, MCP arguments, prompts, model responses, or credentials.

## Privacy and access boundary

Trace/metric attributes deliberately omit patient names, phone/email, medical identifiers, blood-request contents, donor details, auth tokens, API keys, prompts, completions, and chain-of-thought. Trace and span IDs are for log/trace correlation only and are never Prometheus labels. The metrics endpoint is internal to each container and the public gateway has no `/metrics` or LLM usage route.

The current application has no observability-specific admin UI or admin-authenticated proxy. The Compose operations UIs are therefore restricted by loopback binding for local development, with Grafana login enabled. This is not a deployment-grade identity boundary for a shared host. Future frontend role expectations are documented in [future-role-based-frontend-boundary.md](future-role-based-frontend-boundary.md); those screens are out of scope here.
