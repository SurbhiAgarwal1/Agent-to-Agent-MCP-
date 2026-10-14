"""Uvicorn factory for independently deployable A2A agent services."""

import os

from app.agents.a2a.protocol_server import AGENT_APPS


def create_service():
    name = os.getenv("A2A_AGENT", "coordinator").strip().lower()
    try:
        return AGENT_APPS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown A2A_AGENT '{name}'. Choose one of {', '.join(AGENT_APPS)}") from exc
