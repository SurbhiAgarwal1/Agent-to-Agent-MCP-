"""Tests for architectural upgrades: Steps 1, 4, 5, 6, and 7."""

import asyncio
from datetime import date, timedelta

from app.agents.a2a.discovery import (
    card_matches_skill,
    discover_agent_by_skill,
    resolve_agent_base_url,
)
from app.agents.coordinator_agent import CoordinatorAgent
from app.agents.coordinator_helpers import (
    invoke_coordinator_from_gateway,
    resolve_hospital_by_location,
)
from app.agents.nl_interface import NLInterfaceAgent
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.security.service_auth import service_auth_headers


def test_step1_hospital_lookup_exact_match_and_ambiguity_detection(db_session):
    """Exact hospital names resolve immediately; ambiguous substring matches require clarification."""
    h1 = Hospital(hospital_id=1, name="City Hospital", latitude=28.60, longitude=77.20, address="North Road")
    h2 = Hospital(hospital_id=2, name="City Hospital Annex", latitude=28.61, longitude=77.21, address="South Road")
    h3 = Hospital(hospital_id=3, name="Metro Clinic", latitude=28.62, longitude=77.22, address="Central")
    db_session.add_all([h1, h2, h3])
    db_session.commit()

    # Exact match wins even when another hospital contains it as a prefix
    exact, matches = resolve_hospital_by_location(db_session, "City Hospital")
    assert exact is not None and exact.hospital_id == 1
    assert len(matches) == 1

    # Ambiguous substring ("City") matches both City Hospital and City Hospital Annex
    ambiguous, matches = resolve_hospital_by_location(db_session, "City")
    assert ambiguous is None
    assert [h.name for h in matches] == ["City Hospital", "City Hospital Annex"]

    nl = NLInterfaceAgent(db=db_session)
    parsed = nl.parse_text("Urgently need 2 units of A+ at City")
    assert parsed["success"] is False
    assert parsed["is_ambiguous"] is True
    assert "City Hospital" in parsed["clarification_question"]
    assert "City Hospital Annex" in parsed["clarification_question"]


def test_step1_coordinate_text_preview_uses_no_999_placeholder(db_session):
    """Previewing natural language requests does not inject a fake request_id=999."""
    h = Hospital(hospital_id=1, name="General Hospital", latitude=28.60, longitude=77.20, address="Main")
    b = BloodBank(bank_id=1, name="Central Bank", latitude=28.61, longitude=77.21, address="Bank Rd")
    inv = BloodInventory(
        bank_id=1,
        blood_group="O+",
        units_available=4,
        expiry_date=date.today() + timedelta(days=15),
    )
    db_session.add_all([h, b, inv])
    db_session.commit()

    coord = CoordinatorAgent(db=db_session)
    res = coord.coordinate_text("Urgently need 1 unit of O+ at General Hospital", persist=False)
    assert res["success"] is True
    assert res["request_id"] is None
    assert res["requirement"]["request_id"] is None


def test_step4_service_auth_headers_and_mounted_middleware(monkeypatch):
    """ServiceAuthenticationMiddleware is mounted on A2A and MCP apps and headers attach Bearer token."""
    monkeypatch.setenv("SERVICE_TO_SERVICE_TOKEN", "s" * 40)
    assert service_auth_headers() == {"Authorization": f"Bearer {'s' * 40}"}
    monkeypatch.delenv("SERVICE_TO_SERVICE_TOKEN", raising=False)
    assert service_auth_headers() == {}


def test_step5_agent_card_skill_discovery(monkeypatch):
    """Agent Card discovery matches advertised skill tags and IDs."""
    card = {
        "name": "MatchingAgent",
        "skills": [{"id": "matchingagent", "name": "MatchingAgent", "tags": ["find-sources", "blood-donation"]}],
    }
    assert card_matches_skill(card, "find-sources") is True
    assert card_matches_skill(card, "calculate-distance") is False

    async def fake_get(self, url):
        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                if "8102" in url:
                    return card
                return {"name": "OtherAgent", "skills": [{"id": "other", "tags": ["other-skill"]}]}

        return Resp()

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    base_url, discovered_card = asyncio.run(
        discover_agent_by_skill(
            "find-sources",
            candidate_urls=["http://127.0.0.1:8101", "http://127.0.0.1:8102"],
        )
    )
    assert base_url == "http://127.0.0.1:8102"
    assert discovered_card["name"] == "MatchingAgent"
    assert resolve_agent_base_url("RequirementAgent").endswith("8101")


def test_step6_gateway_calls_coordinator_over_a2a_when_configured(monkeypatch, db_session):
    """Gateway helper routes through Coordinator A2A client when configured on non-memory DB."""
    monkeypatch.setattr("app.agents.coordinator_helpers.is_in_memory_db", lambda _db: False)
    monkeypatch.setenv("COORDINATORAGENT_BASE_URL", "http://127.0.0.1:8100")
    captured = {}

    async def fake_call_remote_agent(agent, payload, *, port=None, skill=None, operation="message"):
        captured["agent"] = agent
        captured["payload"] = payload
        captured["skill"] = skill
        captured["operation"] = operation
        return {"success": True, "request_id": payload["request_id"], "ranked_matches": []}

    monkeypatch.setattr("app.agents.a2a.client.call_remote_agent", fake_call_remote_agent)
    out = invoke_coordinator_from_gateway(db_session, request_id=42, persist=False, mode="coordinate")
    assert out["success"] is True
    assert captured["agent"] == "COORDINATORAGENT"
    assert captured["skill"] == "coordinate"
    assert captured["operation"] == "COORDINATE_REQUEST"
    assert captured["payload"]["request_id"] == 42


def test_step7_peer_to_peer_matching_to_location_collaboration(db_session):
    """When peer_to_peer=True, MatchingAgent collaborates directly with LocationAgent over the bus."""
    db_session.add(Hospital(hospital_id=1, name="H1", latitude=28.60, longitude=77.20, address="x"))
    db_session.add(BloodBank(bank_id=1, name="Bank", latitude=28.61, longitude=77.21, address="x"))
    db_session.add(
        BloodInventory(
            bank_id=1,
            blood_group="A+",
            units_available=6,
            expiry_date=date.today() + timedelta(days=9),
        )
    )
    db_session.add(
        BloodRequest(
            request_id=1,
            hospital_id=1,
            blood_group="A+",
            units_required=2,
            urgency="HIGH",
            status="PENDING",
        )
    )
    db_session.commit()

    coord = CoordinatorAgent(db=db_session, peer_to_peer=True)
    res = coord.coordinate(1, persist=False)
    assert res["success"] is True
    assert len(res["ranked_matches"]) == 1
    assert res["ranked_matches"][0]["distance_km"] > 0
    trace_pairs = [(m["sender"], m["receiver"]) for m in res["a2a_trace"]]
    assert ("MatchingAgent", "LocationAgent") in trace_pairs
    assert ("LocationAgent", "MatchingAgent") in trace_pairs
