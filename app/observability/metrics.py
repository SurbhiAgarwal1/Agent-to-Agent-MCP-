"""Observability and Operational Metrics (Part 16).

Tracks request counts, error rates, average latency, and agent execution stats.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# In-memory metrics store
METRICS = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "requests_total": 0,
    "requests_by_status": {},
    "requests_by_endpoint": {},
    "errors_total": 0,
    "coordinator_executions": 0,
    "agent_dispatch_events": 0,
    "total_duration_ms": 0.0,
}


def increment_metric(key: str, count: int = 1):
    """Safely increment an operational counter."""
    if key in METRICS:
        METRICS[key] += count


def get_metrics_snapshot() -> Dict[str, Any]:
    """Retrieve formatted observability metrics dictionary."""
    total_reqs = max(1, METRICS["requests_total"])
    avg_latency = round(METRICS["total_duration_ms"] / total_reqs, 2)
    return {
        "status": "UP",
        "started_at": METRICS["started_at"],
        "uptime_seconds": round(time.time() - datetime.fromisoformat(METRICS["started_at"]).timestamp(), 1),
        "requests": {
            "total": METRICS["requests_total"],
            "errors": METRICS["errors_total"],
            "error_rate_pct": round((METRICS["errors_total"] / total_reqs) * 100, 2),
            "avg_latency_ms": avg_latency,
            "by_status_code": METRICS["requests_by_status"],
            "by_endpoint": METRICS["requests_by_endpoint"],
        },
        "agents": {
            "coordinator_executions": METRICS["coordinator_executions"],
            "agent_dispatch_events": METRICS["agent_dispatch_events"],
        },
    }


class MetricsMiddleware(BaseHTTPMiddleware):
    """ASGI Middleware recording request statistics and latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        path = request.url.path

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000.0

            # Update metrics
            METRICS["requests_total"] += 1
            METRICS["total_duration_ms"] += duration_ms

            status_str = str(response.status_code)
            METRICS["requests_by_status"][status_str] = METRICS["requests_by_status"].get(status_str, 0) + 1
            METRICS["requests_by_endpoint"][path] = METRICS["requests_by_endpoint"].get(path, 0) + 1

            if response.status_code >= 400:
                METRICS["errors_total"] += 1

            return response
        except Exception as exc:
            METRICS["requests_total"] += 1
            METRICS["errors_total"] += 1
            raise exc
