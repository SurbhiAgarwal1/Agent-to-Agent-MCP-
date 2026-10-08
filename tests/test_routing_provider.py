"""Unit and Integration Tests for Part 11 Routing Provider Service."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.services.routing_provider import (
    HaversineRoutingProvider,
    RealRoutingProvider,
    get_routing_provider,
)
from app.agents.location_agent import LocationAgent


def test_haversine_provider_schema():
    """Verify Haversine provider produces valid approximation schema."""
    provider = HaversineRoutingProvider()
    res = provider.route(28.6139, 77.2090, 28.7000, 77.2090)

    assert "distance_km" in res
    assert res["distance_km"] > 0
    assert res["eta_minutes"] is None
    assert res["source"] == "HAVERSINE_APPROXIMATION"
    assert "approx straight-line" in res["estimated_time"]


def test_real_provider_success_mocked():
    """Verify RealRoutingProvider formats distance and real ETA when API succeeds."""
    mock_osrm_response = {
        "code": "Ok",
        "routes": [
            {
                "distance": 6200.0,  # 6.2 km
                "duration": 780.0,   # 13 minutes
            }
        ],
    }

    provider = RealRoutingProvider(api_url="http://mock-osrm.local/route/v1/driving")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_osrm_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = provider.route(28.6139, 77.2090, 28.7000, 77.2090)

        assert res["distance_km"] == 6.2
        assert res["eta_minutes"] == 13
        assert res["source"] == "REAL_ROUTING"
        assert "road routing" in res["estimated_time"]


def test_real_provider_failure_fallback_to_haversine():
    """Verify RealRoutingProvider gracefully falls back to Haversine on timeout or error."""
    provider = RealRoutingProvider(api_url="http://unreachable-osrm.local/route/v1/driving")

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        res = provider.route(28.6139, 77.2090, 28.7000, 77.2090)

        # Fallback should succeed seamlessly without crashing
        assert res["distance_km"] > 0
        assert res["eta_minutes"] is None
        assert res["source"] == "HAVERSINE_APPROXIMATION"
        assert "fallback_reason" in res


def test_routing_provider_selection_via_config(monkeypatch):
    """Verify factory returns RealRoutingProvider or HaversineRoutingProvider based on env var."""
    monkeypatch.setenv("ROUTING_PROVIDER", "real")
    p_real = get_routing_provider()
    assert isinstance(p_real, RealRoutingProvider)

    monkeypatch.setenv("ROUTING_PROVIDER", "haversine")
    p_hav = get_routing_provider()
    assert isinstance(p_hav, HaversineRoutingProvider)

    # Defaults to Haversine if unset
    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    p_def = get_routing_provider()
    assert isinstance(p_def, HaversineRoutingProvider)


def test_location_agent_integration_with_routing_provider():
    """Verify LocationAgent uses configured RoutingProvider and exposes get_route()."""
    mock_provider = MagicMock()
    mock_provider.route.return_value = {
        "distance_km": 7.5,
        "eta_minutes": 18,
        "source": "REAL_ROUTING",
        "estimated_time": "18 mins (road routing)",
    }

    agent = LocationAgent(routing_provider=mock_provider)
    res = agent.get_route(28.6139, 77.2090, 28.7000, 77.2090)

    assert res["distance_km"] == 7.5
    assert res["eta_minutes"] == 18
    assert res["source"] == "REAL_ROUTING"
    mock_provider.route.assert_called_once()
