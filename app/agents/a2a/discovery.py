"""Bootstrap-based Agent Card discovery with official A2A card validation."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

# Kept only for legacy URL helpers. Dynamic routing does not select agents from this map.
DEFAULT_AGENT_URLS: Dict[str, str] = {
    "coordinator": "http://127.0.0.1:8100", "requirement": "http://127.0.0.1:8101",
    "matching": "http://127.0.0.1:8102", "location": "http://127.0.0.1:8103",
    "notification": "http://127.0.0.1:8104", "communication": "http://127.0.0.1:8105",
    "calling": "http://127.0.0.1:8106", "pharmacy": "http://127.0.0.1:8107",
    "emergency-priority": "http://127.0.0.1:8108",
}

SKILL_BY_AGENT: Dict[str, str] = {
    "coordinator": "coordinate-blood-request", "requirement": "validate-blood-request",
    "matching": "find-compatible-blood-sources", "location": "calculate-source-distance",
    "notification": "dispatch-fulfillment-notifications", "communication": "coordinate-donor-outreach",
    "calling": "place-emergency-calls", "pharmacy": "fulfill-pharmacy-order",
    "emergency-priority": "evaluate-emergency-priority",
}
AGENT_BY_SKILL: Dict[str, str] = {value: key for key, value in SKILL_BY_AGENT.items()}


def normalize_agent_key(agent: str) -> str:
    cleaned = (agent or "").strip().lower()
    return cleaned[:-5] if cleaned.endswith("agent") else cleaned


def agent_env_prefix(agent: str) -> str:
    return f"{normalize_agent_key(agent).replace('-', '_').upper()}AGENT"


def default_skill_for_agent(agent: str) -> Optional[str]:
    return SKILL_BY_AGENT.get(normalize_agent_key(agent))


def resolve_agent_base_url(agent: str, *, port: Optional[int] = None) -> str:
    prefix = agent_env_prefix(agent)
    explicit = os.getenv(f"{prefix}_BASE_URL", "").strip() or os.getenv(f"{prefix}_A2A_URL", "").strip()
    if explicit:
        base = explicit.rstrip("/")
        return base[:-4].rstrip("/") if base.endswith("/a2a") else base
    if port is not None:
        return f"http://127.0.0.1:{port}"
    return DEFAULT_AGENT_URLS.get(normalize_agent_key(agent), "")


def configured_candidate_urls(preferred_agent: Optional[str] = None, *, port: Optional[int] = None) -> List[str]:
    """Read only bootstrap endpoints from configuration; Agent Cards choose capabilities."""
    candidates: List[str] = []

    def add(value: Optional[str]) -> None:
        if not value:
            return
        cleaned = value.strip().rstrip("/")
        if cleaned.endswith("/a2a"):
            cleaned = cleaned[:-4].rstrip("/")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    if preferred_agent:
        add(resolve_agent_base_url(preferred_agent, port=port))
    for value in os.getenv("A2A_AGENT_URLS", "").split(","):
        add(value)
    raw = os.getenv("A2A_AGENT_REGISTRY", "").strip()
    if raw:
        try:
            registry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("A2A_AGENT_REGISTRY must be valid JSON") from exc
        entries = registry.values() if isinstance(registry, dict) else registry
        if not isinstance(entries, (list, tuple, type({}.values()))):
            raise ValueError("A2A_AGENT_REGISTRY must be an object or array")
        for entry in entries:
            if isinstance(entry, str):
                add(entry)
            elif isinstance(entry, dict):
                add(entry.get("base_url") or entry.get("url") or entry.get("endpoint"))
            else:
                raise ValueError("A2A_AGENT_REGISTRY entries must be URLs or objects containing base_url")
    # Per-agent URLs are bootstrap hints only; the requested skill is always verified against the card.
    for key, value in os.environ.items():
        if key.endswith("AGENT_BASE_URL") or key.endswith("AGENT_A2A_URL"):
            add(value)
    return candidates


def card_matches_skill(card: Dict[str, Any], skill: str) -> bool:
    target = (skill or "").strip().lower()
    if not target:
        return False
    for item in card.get("skills") or []:
        if not isinstance(item, dict):
            continue
        values = [item.get("id"), item.get("name"), *(item.get("tags") or [])]
        if target in {str(value).strip().lower() for value in values if value}:
            return True
    return False


async def _get(client: Optional[httpx.AsyncClient], url: str, timeout: float):
    if client is not None:
        return await client.get(url)
    async with httpx.AsyncClient(timeout=timeout) as owned:
        return await owned.get(url)


async def fetch_agent_card(base_url: str, *, http_client: Optional[httpx.AsyncClient] = None, timeout: float = 5.0) -> Dict[str, Any]:
    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    response = await _get(http_client, card_url, timeout)
    response.raise_for_status()
    card = response.json()
    if not isinstance(card, dict) or not card.get("name") or not card.get("skills"):
        raise ValueError(f"Invalid Agent Card at {card_url}; missing name or skills")

    metadata = card.get("metadata") or {}
    if metadata.get("availability") and metadata["availability"] not in {"available", "healthy", "ok"}:
        raise ValueError(f"Agent Card at {card_url} reports unavailable")

    health_url = metadata.get("healthUrl")
    if health_url:
        try:
            health = await _get(http_client, health_url, timeout)
            health.raise_for_status()
            health_data = health.json()
            if isinstance(health_data, dict) and health_data.get("status") not in {"healthy", "available", "ok"}:
                raise ValueError(f"Agent health check failed at {health_url}")
        except Exception as exc:
            raise ValueError(f"Agent health check failed at {health_url}: {exc}") from exc

    return card


async def discover_agents(*, candidate_urls: Optional[List[str]] = None, http_client: Optional[httpx.AsyncClient] = None, timeout: float = 5.0) -> list[Tuple[str, Dict[str, Any]]]:
    results = []
    for url in candidate_urls if candidate_urls is not None else configured_candidate_urls():
        try:
            results.append((url.rstrip("/"), await fetch_agent_card(url, http_client=http_client, timeout=timeout)))
        except Exception:
            continue
    return results


async def discover_agent_by_skill(skill: str, *, preferred_agent: Optional[str] = None, port: Optional[int] = None, candidate_urls: Optional[List[str]] = None, http_client: Optional[httpx.AsyncClient] = None, timeout: float = 5.0) -> Tuple[str, Dict[str, Any]]:
    urls = candidate_urls if candidate_urls is not None else configured_candidate_urls(preferred_agent, port=port)
    last_error: Optional[Exception] = None
    for base_url, card in await discover_agents(candidate_urls=urls, http_client=http_client, timeout=timeout):
        if card_matches_skill(card, skill):
            interfaces = card.get("supportedInterfaces") or []
            interface = next((item for item in interfaces if isinstance(item, dict) and item.get("protocolBinding") == "JSONRPC"), None)
            if interface and interface.get("url"):
                parsed = urlparse(interface["url"])
                return f"{parsed.scheme}://{parsed.netloc}", card
            return base_url, card
    if not urls:
        raise RuntimeError("No A2A bootstrap endpoints are configured; set A2A_AGENT_URLS or A2A_AGENT_REGISTRY")
    raise RuntimeError(f"No available A2A agent advertises capability '{skill}' from configured bootstrap endpoints: {urls}") from last_error
