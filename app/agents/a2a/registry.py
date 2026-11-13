"""Capability registry shared by local MessageBus adapters and remote A2A discovery."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Any, Callable

from app.agents.a2a.message import A2AMessage


@dataclass(frozen=True)
class LocalAgent:
    agent_id: str
    name: str
    skills: frozenset[str]
    handler: Callable[[A2AMessage], A2AMessage]


class LocalAgentRegistry:
    """Runtime registration and capability selection for the in-process development bus."""

    def __init__(self, bus: Any):
        self.bus = bus
        self._agents: dict[str, LocalAgent] = {}

    def register(self, agent_id: str, name: str, skills: list[str], handler: Callable[[A2AMessage], A2AMessage]) -> None:
        if not agent_id.strip() or not name.strip() or not skills:
            raise ValueError("Local agent registration requires an ID, name, and at least one skill")
        if agent_id in self._agents:
            raise ValueError(f"Duplicate local A2A agent ID: {agent_id}")
        agent = LocalAgent(agent_id, name, frozenset(skill.strip().lower() for skill in skills), handler)
        self._agents[agent_id] = agent
        self.bus.register_agent(agent_id, handler)

    def select(self, capability: str) -> LocalAgent:
        matches = [agent for agent in self._agents.values() if capability.lower() in agent.skills]
        if not matches:
            raise LookupError(f"No locally registered agent advertises capability '{capability}'")
        return sorted(matches, key=lambda item: item.agent_id)[0]

    def discover(self) -> list[dict[str, Any]]:
        return [
            {"agent_id": item.agent_id, "name": item.name, "skills": sorted(item.skills), "available": True}
            for item in self._agents.values()
        ]


def build_local_agent_registry(db: Any, bus: Any) -> LocalAgentRegistry:
    """Register bundled local agents, then configured plugins implementing register_agents()."""
    from app.agents.calling_agent import CallingAgent
    from app.agents.communication_agent import CommunicationAgent
    from app.agents.emergency_priority_agent import EmergencyPriorityAgent
    from app.agents.location_agent import LocationAgent
    from app.agents.matching_agent import MatchingAgent
    from app.agents.notification_agent import NotificationAgent
    from app.agents.pharmacy_agent import PharmacyAgent
    from app.agents.requirement_agent import RequirementAgent

    registry = LocalAgentRegistry(bus)
    bundled = (
        ("requirement", "RequirementAgent", ["validate-blood-request"], RequirementAgent(db=db, bus=bus)),
        ("matching", "MatchingAgent", ["find-compatible-blood-sources"], MatchingAgent(db=db, bus=bus)),
        ("location", "LocationAgent", ["calculate-source-distance"], LocationAgent(bus=bus)),
        ("notification", "NotificationAgent", ["dispatch-fulfillment-notifications"], NotificationAgent(bus=bus)),
        ("communication", "CommunicationAgent", ["coordinate-donor-outreach"], CommunicationAgent(db=db, bus=bus)),
        ("calling", "CallingAgent", ["place-emergency-calls"], CallingAgent(db=db, bus=bus)),
        ("pharmacy", "PharmacyAgent", ["fulfill-pharmacy-order"], PharmacyAgent(db=db)),
        ("emergency-priority", "EmergencyPriorityAgent", [
            "evaluate-emergency-priority", "recommend-emergency-escalation", "prioritize-critical-requests",
        ], EmergencyPriorityAgent()),
    )
    for agent_id, name, skills, agent in bundled:
        if hasattr(agent, "bus"):
            agent.bus = bus
        registry.register(agent_id, name, skills, agent.handle_a2a_message)

    for module_path in filter(None, (value.strip() for value in os.getenv("A2A_LOCAL_AGENT_PLUGINS", "").split(","))):
        module = importlib.import_module(module_path)
        register_agents = getattr(module, "register_agents", None)
        if not callable(register_agents):
            raise ValueError(f"Local agent plugin '{module_path}' must define register_agents(registry, db, bus)")
        register_agents(registry, db, bus)
    return registry
