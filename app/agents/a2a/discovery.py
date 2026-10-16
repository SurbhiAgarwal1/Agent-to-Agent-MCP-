"""Dynamic Agent Card discovery and skill-based endpoint resolution for A2A agents."""

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

DEFAULT_AGENT_URLS: Dict[str, str] = {
    "coordinator": "http://127.0.0.1:8100",
    "requirement": "http://127.0.0.1:8101",
    "matching": "http://127.0.0.1:8102",
    "location": "http://127.0.0.1:8103",
    "notification": "http://127.0.0.1:8104",
}

SKILL_BY_AGENT: Dict[str, str] = {
    "coordinator": "coordinate",
    "requirement": "validate-request",
    "matching": "find-sources",
    "location": "calculate-distance",
    "notification": "notify",
}

AGENT_BY_SKILL: Dict[str, str] = {v: k for k, v in SKILL_BY_AGENT.items()}


def normalize_agent_key(agent: str) -> str:
    """Normalize an agent identifier (e.g. 'RequirementAgent' or 'REQUIREMENTAGENT') to its short key."""
    cleaned = (agent or "").strip().lower()
    if cleaned.endswith("agent"):
        cleaned = cleaned[:-5]
    return cleaned


def agent_env_prefix(agent: str) -> str:
    """Return the uppercase environment variable prefix (e.g. 'REQUIREMENTAGENT')."""
    short = normalize_agent_key(agent)
    return f"{short.upper()}AGENT"


def default_skill_for_agent(agent: str) -> Optional[str]:
    """Return the primary advertised skill tag for a domain agent."""
    return SKILL_BY_AGENT.get(normalize_agent_key(agent))


def resolve_agent_base_url(agent: str, *, port: Optional[int] = None) -> str:
    """Resolve the base URL for an agent from environment configuration or defaults without hardcoded caller ports."""
    prefix = agent_env_prefix(agent)
    short = normalize_agent_key(agent)

    explicit_base = os.getenv(f"{prefix}_BASE_URL", "").strip()
    if explicit_base:
        return explicit_base.rstrip("/")

    explicit_a2a = os.getenv(f"{prefix}_A2A_URL", "").strip()
    if explicit_a2a:
        base = explicit_a2a.rstrip("/")
        if base.endswith("/a2a"):
            base = base[:-4]
        return base.rstrip("/")

    if port is not None:
        return f"http://127.0.0.1:{port}"

    return DEFAULT_AGENT_URLS.get(short, "http://127.0.0.1:8100")


def configured_candidate_urls(preferred_agent: Optional[str] = None, *, port: Optional[int] = None) -> List[str]:
    """Return ordered candidate base URLs for Agent Card discovery."""
    candidates: List[str] = []

    def _add(url: Optional[str]) -> None:
        if not url:
            return
        cleaned = url.strip().rstrip("/")
        if cleaned.endswith("/a2a"):
            cleaned = cleaned[:-4].rstrip("/")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    if preferred_agent:
        _add(resolve_agent_base_url(preferred_agent, port=port))

    extra_urls = os.getenv("A2A_AGENT_URLS", "").strip()
    if extra_urls:
        for item in extra_urls.split(","):
            _add(item)

    for short in DEFAULT_AGENT_URLS:
        prefix = f"{short.upper()}AGENT"
        _add(os.getenv(f"{prefix}_BASE_URL"))
        _add(os.getenv(f"{prefix}_A2A_URL"))

    for short, default_url in DEFAULT_AGENT_URLS.items():
        _add(default_url)

    return candidates


def card_matches_skill(card: Dict[str, Any], skill: str) -> bool:
    """Return True if the Agent Card advertises the requested skill ID, name, or tag."""
    target = (skill or "").strip().lower()
    if not target:
        return True
    skills = card.get("skills") or []
    for item in skills:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).lower() == target:
            return True
        if str(item.get("name", "")).lower() == target:
            return True
        tags = [str(tag).lower() for tag in (item.get("tags") or [])]
        if target in tags:
            return True
    return False


async def fetch_agent_card(
    base_url: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Fetch and parse /.well-known/agent-card.json from an agent base URL."""
    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    if http_client is not None:
        response = await http_client.get(card_url)
        response.raise_for_status()
        card = response.json()
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            card = response.json()
    if not isinstance(card, dict) or not card.get("name"):
        raise ValueError(f"Invalid Agent Card at {card_url}")
    return card


async def discover_agent_by_skill(
    skill: str,
    *,
    preferred_agent: Optional[str] = None,
    port: Optional[int] = None,
    candidate_urls: Optional[List[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    timeout: float = 5.0,
) -> Tuple[str, Dict[str, Any]]:
    """Discover an agent endpoint by reading Agent Cards and matching advertised skills.

    Args:
        skill: Required skill tag or ID (e.g. 'validate-request', 'find-sources', 'calculate-distance', 'notify').
        preferred_agent: Optional agent name hint to check first.
        port: Optional legacy port hint.
        candidate_urls: Optional explicit list of base URLs to probe.
        http_client: Optional shared httpx.AsyncClient.
        timeout: Discovery request timeout in seconds.

    Returns:
        Tuple of (resolved_base_url, agent_card_dict).
    """
    if preferred_agent is None and skill in AGENT_BY_SKILL:
        preferred_agent = AGENT_BY_SKILL[skill]

    urls = candidate_urls if candidate_urls is not None else configured_candidate_urls(preferred_agent, port=port)
    last_error: Optional[Exception] = None

    for base_url in urls:
        try:
            card = await fetch_agent_card(base_url, http_client=http_client, timeout=timeout)
            if card_matches_skill(card, skill):
                return base_url.rstrip("/"), card
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(
        f"No A2A agent advertising skill '{skill}' could be discovered from {urls}: {last_error}"
    ) from last_error
