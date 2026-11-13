"""Deterministic emergency triage advice used by the capability-discovered agent."""
from __future__ import annotations

from typing import Any

from app.agents.a2a.message import A2AMessage, A2AMessageType


class EmergencyPriorityAgent:
    """Evaluate urgency and recommend escalation without making medical compatibility decisions."""

    _RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        urgency = str(payload.get("urgency", "MEDIUM")).strip().upper()
        if urgency not in self._RANK:
            raise ValueError("urgency must be LOW, MEDIUM, HIGH, or CRITICAL")
        group = str(payload.get("blood_group", "")).strip().upper()
        units = payload.get("units_required")
        if isinstance(units, bool) or not isinstance(units, int) or units < 1:
            raise ValueError("units_required must be a positive integer")
        score = self._RANK[urgency] * 25 + (10 if units >= 4 else 0)
        return {
            "urgency": urgency,
            "priority_score": min(score, 100),
            "escalation_recommended": urgency in {"HIGH", "CRITICAL"},
            "prioritize_first": urgency == "CRITICAL",
            "blood_group": group,
            "units_required": units,
            "reason": "Critical requests are prioritized; high and critical requests are recommended for escalation.",
        }

    def handle_a2a_message(self, message: A2AMessage) -> A2AMessage:
        if message.message_type not in {
            A2AMessageType.EMERGENCY_PRIORITY_EVALUATE_REQUEST,
            A2AMessageType.REQUEST,
        }:
            return message.create_error("emergency-priority", f"Unsupported message type: {message.message_type}")
        try:
            result = self.evaluate(message.payload)
        except (TypeError, ValueError) as exc:
            return message.create_error("emergency-priority", str(exc))
        return message.create_response(
            "emergency-priority", A2AMessageType.EMERGENCY_PRIORITY_EVALUATED_EVENT, result
        )
