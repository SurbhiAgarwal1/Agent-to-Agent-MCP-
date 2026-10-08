"""Unit and integration tests for Part 16 Observability and Metrics."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.observability.metrics import get_metrics_snapshot, increment_metric


def test_metrics_snapshot_structure():
    """Verify metrics snapshot schema and fields."""
    snapshot = get_metrics_snapshot()
    assert snapshot["status"] == "UP"
    assert "uptime_seconds" in snapshot
    assert "requests" in snapshot
    assert "agents" in snapshot
    assert "total" in snapshot["requests"]
    assert "errors" in snapshot["requests"]


def test_metrics_increment_metric():
    """Verify manual incrementing of operational counters."""
    initial = get_metrics_snapshot()["agents"]["coordinator_executions"]
    increment_metric("coordinator_executions", 1)
    updated = get_metrics_snapshot()["agents"]["coordinator_executions"]
    assert updated == initial + 1


def test_metrics_api_endpoint():
    """Verify GET /metrics HTTP endpoint returns status 200 and live metrics."""
    client = TestClient(app)
    # Perform a request first to ensure counter increments
    client.get("/health")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UP"
    assert data["requests"]["total"] >= 1
    assert "/health" in data["requests"]["by_endpoint"]
