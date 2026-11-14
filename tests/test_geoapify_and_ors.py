"""Geoapify place discovery and OpenRouteService road routing."""
import httpx
import pytest

from app.agents.location_agent import LocationAgent
from app.mcp.tools.location_tool import handle_calculate_distances_batch
from app.services import geoapify_discovery, osm_discovery
from app.services.geoapify_discovery import classify, discover_nearby_blood_banks, parse_features
from app.services.routing_provider import (
    HaversineRoutingProvider, OpenRouteServiceProvider, RoutingProvider, get_routing_provider,
)

KEY = "SECRETKEY123"


def _feature(name, lat, lon, distance, categories=("healthcare.hospital",), phone=None):
    props = {"name": name, "lat": lat, "lon": lon, "distance": distance, "categories": list(categories),
             "formatted": f"{name}, Bengaluru", "place_id": f"id-{name}"}
    if phone:
        props["contact"] = {"phone": phone}
    return {"type": "Feature", "properties": props}


FEATURES = [
    _feature("Apollo Hospital", 12.97, 77.60, 1500),
    _feature("Smile Dental", 12.971, 77.601, 200, ("healthcare.dentist",)),
    _feature("Rotary Blood Bank", 12.98, 77.61, 4200, ("healthcare",), phone="+91 80 1111"),
    _feature("Karnataka Raktkosh Centre", 12.99, 77.62, 6100, ("healthcare",)),
    {"type": "Feature", "properties": {"lat": 1, "lon": 1, "categories": ["healthcare.hospital"]}},  # no name
]


def test_classification_and_ordering_put_blood_banks_before_hospitals_and_drop_noise():
    places = parse_features(FEATURES)
    assert [p["name"] for p in places] == ["Rotary Blood Bank", "Karnataka Raktkosh Centre", "Apollo Hospital"]
    assert [p["facility_type"] for p in places] == ["blood_bank", "blood_bank", "hospital"]
    assert places[0]["phone"] == "+91 80 1111" and places[0]["distance_km"] == 4.2
    assert "may have an in-house blood bank" in places[2]["note"]
    assert classify({"name": "Smile Dental", "categories": ["healthcare.dentist"]}) == "other_healthcare"


def test_geoapify_sends_circle_filter_and_returns_places(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", KEY)
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"features": FEATURES})

    result = discover_nearby_blood_banks(12.9716, 77.5946, 20, 2, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["available"] and result["count"] == 2 and result["source"] == "geoapify"
    assert seen["params"]["filter"] == "circle:77.594600,12.971600,20000"
    assert seen["params"]["categories"] == "healthcare" and seen["params"]["apiKey"] == KEY


def test_missing_key_and_http_errors_never_raise_or_leak_the_key(monkeypatch):
    assert discover_nearby_blood_banks(1, 1)["available"] is False
    monkeypatch.setenv("GEOAPIFY_API_KEY", KEY)
    for status in (401, 429, 500):
        out = discover_nearby_blood_banks(1, 1, client=httpx.Client(transport=httpx.MockTransport(lambda r, s=status: httpx.Response(s))))
        assert out["available"] is False and KEY not in out["error"]
    assert "check GEOAPIFY_API_KEY" in discover_nearby_blood_banks(1, 1, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))["error"]


def test_auto_provider_prefers_geoapify_then_falls_back_to_overpass(monkeypatch):
    monkeypatch.setattr(osm_discovery, "discover_via_overpass", lambda *a, **k: {"source": "openstreetmap", "available": True, "places": [], "count": 0})
    assert osm_discovery.discover_nearby_blood_banks(1, 1)["source"] == "openstreetmap"          # no key
    monkeypatch.setenv("GEOAPIFY_API_KEY", KEY)
    monkeypatch.setattr(geoapify_discovery, "discover_nearby_blood_banks", lambda *a, **k: {"source": "geoapify", "available": True, "places": []})
    assert osm_discovery.discover_nearby_blood_banks(1, 1)["source"] == "geoapify"
    monkeypatch.setattr(geoapify_discovery, "discover_nearby_blood_banks", lambda *a, **k: {"source": "geoapify", "available": False, "error": "boom", "places": []})
    assert osm_discovery.discover_nearby_blood_banks(1, 1)["source"] == "openstreetmap"          # auto falls back
    monkeypatch.setenv("PLACES_PROVIDER", "geoapify")
    assert osm_discovery.discover_nearby_blood_banks(1, 1)["available"] is False                  # explicit: no fallback


# ---- OpenRouteService routing -------------------------------------------------------------

def _ors(handler, key=KEY):
    return OpenRouteServiceProvider(api_key=key, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_ors_uses_one_matrix_request_for_all_destinations():
    calls = []

    def handler(request):
        import json
        body = json.loads(request.content)
        calls.append((request.url.path, request.headers["authorization"], body))
        return httpx.Response(200, json={"distances": [[5200.0, 12800.0, None]], "durations": [[600.0, 1500.0, None]]})

    results = _ors(handler).route_many(12.97, 77.59, [(12.98, 77.60), (13.05, 77.70), (13.2, 77.9)])
    assert len(calls) == 1 and calls[0][0].endswith("/matrix/driving-car") and calls[0][1] == KEY
    assert calls[0][2]["locations"][0] == [77.59, 12.97] and calls[0][2]["destinations"] == [1, 2, 3]
    assert results[0] == {"distance_km": 5.2, "eta_minutes": 10, "estimated_time": "10 mins (road routing, OpenRouteService)", "source": "OPENROUTESERVICE"}
    assert results[1]["distance_km"] == 12.8 and results[1]["eta_minutes"] == 25
    assert results[2]["source"] == "HAVERSINE_APPROXIMATION" and results[2]["fallback_reason"] == "no road route found"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_ors_failures_fall_back_to_straight_line_with_a_reason(status):
    results = _ors(lambda r: httpx.Response(status)).route_many(12.97, 77.59, [(12.98, 77.60)])
    assert results[0]["source"] == "HAVERSINE_APPROXIMATION" and "OpenRouteService unavailable" in results[0]["fallback_reason"]
    assert results[0]["distance_km"] > 0


def test_ors_without_a_key_makes_no_request():
    out = _ors(lambda r: pytest.fail("must not call"), key="").route_many(12.97, 77.59, [(12.98, 77.60)])
    assert out[0]["fallback_reason"] == "ORS_API_KEY is not set"


def test_factory_selects_ors(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", KEY)
    assert isinstance(get_routing_provider("ors"), OpenRouteServiceProvider)
    assert isinstance(get_routing_provider("haversine"), HaversineRoutingProvider)


class CountingProvider(RoutingProvider):
    def __init__(self):
        self.many_calls = 0

    def route(self, *a):
        raise AssertionError("per-candidate route() must not be used")

    def route_many(self, olat, olon, destinations):
        self.many_calls += 1
        return [{"distance_km": float(i + 1), "estimated_time": f"{i + 1} mins", "source": "OPENROUTESERVICE"} for i, _ in enumerate(destinations)]


def test_location_agent_routes_all_candidates_with_a_single_call():
    from app.agents.a2a.message import A2AMessage, A2AMessageType
    provider = CountingProvider()
    agent = LocationAgent(routing_provider=provider)
    candidates = [{"source_type": "BLOOD_BANK", "source_id": i, "latitude": 12.9 + i / 100, "longitude": 77.5} for i in range(5)]
    candidates.append({"source_type": "DONOR", "source_id": 9, "latitude": None, "longitude": None})
    candidates.append({"source_type": "DONOR", "source_id": 10, "latitude": 999, "longitude": 1})
    message = A2AMessage.create(correlation_id="c-1", sender_agent="Coordinator", receiver_agent="LocationAgent", message_type=A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST,
                                payload={"hospital_id": 1, "hospital_coords": {"hospital_id": 1, "name": "H", "address": "x", "latitude": 12.9, "longitude": 77.5}, "candidates": candidates})
    reply = agent.handle_a2a_message(message)
    assert provider.many_calls == 1
    out = reply.payload["candidates"]
    assert len(out) == 7 and sum(c["distance_km"] is not None for c in out) == 5
    bad = next(c for c in out if c["source_id"] == 10)
    assert bad["distance_km"] is None and "location_error" in bad


def test_mcp_batch_tool_validates_input(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "haversine")
    out = handle_calculate_distances_batch({"origin_latitude": 12.9, "origin_longitude": 77.5, "destinations": [{"latitude": 13.0, "longitude": 77.6}]})
    assert out["results"][0]["distance_km"] > 0
    for bad in ({"origin_latitude": 1, "origin_longitude": 1, "destinations": []}, {"origin_latitude": 1, "origin_longitude": 1, "destinations": "x"}):
        with pytest.raises(ValueError):
            handle_calculate_distances_batch(bad)
