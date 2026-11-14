"""OpenStreetMap (Overpass) discovery of nearby blood banks."""
from datetime import date, timedelta

import httpx
import pytest

from app.agents.coordinator_agent import CoordinatorAgent
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.services import osm_discovery
from app.services.osm_discovery import build_query, discover_nearby_blood_banks, parse_elements

OVERPASS_REPLY = {"elements": [
    {"type": "node", "id": 1, "lat": 28.62, "lon": 77.21,
     "tags": {"name": "City Blood Bank", "amenity": "blood_bank", "phone": "+91 11 0000", "addr:street": "Ring Road", "addr:city": "Delhi"}},
    {"type": "way", "id": 2, "center": {"lat": 28.605, "lon": 77.201}, "tags": {"healthcare": "blood_donation", "operator": "Red Cross"}},
    {"type": "node", "id": 1, "lat": 28.62, "lon": 77.21, "tags": {"name": "duplicate"}},
    {"type": "relation", "id": 3, "tags": {"name": "no coordinates"}},
]}


@pytest.fixture(autouse=True)
def _fresh_cache():
    osm_discovery.clear_cache()
    yield
    osm_discovery.clear_cache()


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_sorts_nearest_first_dedupes_and_skips_missing_coordinates():
    places = parse_elements(OVERPASS_REPLY["elements"], 28.60, 77.20)
    assert [p["osm_id"] for p in places] == ["way/2", "node/1"]
    assert places[0]["name"] == "Red Cross" and places[0]["inventory_known"] is False
    assert places[1]["address"] == "Ring Road, Delhi" and places[1]["phone"] == "+91 11 0000"
    assert places[0]["distance_km"] < places[1]["distance_km"]


def test_query_targets_blood_bank_tags_around_the_point():
    query = build_query(28.6, 77.2, 25000)
    assert '"amenity"="blood_bank"' in query and '"healthcare"="blood_donation"' in query
    assert "around:25000,28.600000,77.200000" in query


def test_discovery_calls_overpass_and_caches():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=OVERPASS_REPLY)

    http = _client(handler)
    first = discover_nearby_blood_banks(28.60, 77.20, 25, 10, client=http)
    second = discover_nearby_blood_banks(28.60, 77.20, 25, 10, client=http)
    assert first["available"] and first["count"] == 2 and first["cached"] is False
    assert second["cached"] is True and len(calls) == 1
    assert "OpenStreetMap" in first["attribution"]


def test_limit_is_applied():
    http = _client(lambda r: httpx.Response(200, json=OVERPASS_REPLY))
    assert discover_nearby_blood_banks(28.60, 77.20, 25, 1, client=http)["count"] == 1


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(429, text="busy"),
    lambda r: httpx.Response(200, text="not json"),
    lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")),
])
def test_overpass_failure_degrades_without_raising(handler):
    result = discover_nearby_blood_banks(28.60, 77.20, client=_client(handler))
    assert result["available"] is False and result["places"] == [] and result["error"]


def test_invalid_coordinates_are_rejected_without_a_request():
    result = discover_nearby_blood_banks(120, 10, client=_client(lambda r: pytest.fail("must not call")))
    assert result["available"] is False


@pytest.fixture
def world(db_session):
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add(BloodBank(bank_id=1, name="Bank", latitude=28.61, longitude=77.21, address="x"))
    db_session.add(BloodInventory(bank_id=1, blood_group="A+", units_available=6, expiry_date=date.today() + timedelta(days=9)))
    db_session.add(BloodRequest(request_id=1, hospital_id=1, blood_group="A+", units_required=2, urgency="HIGH", status="PENDING"))
    db_session.commit()
    return db_session


def test_coordinator_attaches_osm_facilities_when_enabled(world, monkeypatch):
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    http = _client(lambda r: httpx.Response(200, json=OVERPASS_REPLY))
    real = osm_discovery.discover_nearby_blood_banks
    monkeypatch.setattr(osm_discovery, "discover_nearby_blood_banks", lambda *a, **k: real(*a, client=http, **k))
    result = CoordinatorAgent(db=world).coordinate(1, persist=False)
    assert result["success"]
    osm = result["osm_nearby_blood_banks"]
    assert osm["available"] and [p["name"] for p in osm["places"]] == ["Red Cross", "City Blood Bank"]
    assert result["ranked_matches"], "inventory-backed matches are unaffected"


def test_osm_is_off_by_default_and_failures_never_break_the_request(world, monkeypatch):
    assert CoordinatorAgent(db=world).coordinate(1, persist=False)["osm_nearby_blood_banks"] is None
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    broken = _client(lambda r: httpx.Response(503))
    real = osm_discovery.discover_nearby_blood_banks
    monkeypatch.setattr(osm_discovery, "discover_nearby_blood_banks", lambda *a, **k: real(*a, client=broken, **k))
    result = CoordinatorAgent(db=world).coordinate(1, persist=False)
    assert result["success"] and result["osm_nearby_blood_banks"]["available"] is False


def test_network_location_agent_helper_calls_the_mcp_tool(monkeypatch):
    import asyncio
    from app.agents.a2a.protocol_server import _discover_osm
    import app.mcp.client as mcp_client
    seen = {}

    async def fake_call(name, arguments):
        seen.update(name=name, arguments=arguments)
        return {"available": True, "places": [{"name": "x"}]}

    monkeypatch.setattr(mcp_client, "call_remote_tool", fake_call)
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    result = asyncio.run(_discover_osm({"latitude": 12.9, "longitude": 77.5}))
    assert result["available"] and seen["name"] == "discover_osm_blood_banks" and seen["arguments"]["latitude"] == 12.9
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "false")
    assert asyncio.run(_discover_osm({"latitude": 1, "longitude": 1}))["available"] is False

    async def boom(name, arguments):
        raise RuntimeError("mcp down")

    monkeypatch.setattr(mcp_client, "call_remote_tool", boom)
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    assert asyncio.run(_discover_osm({"latitude": 1, "longitude": 1}))["available"] is False
