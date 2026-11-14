"""Spoken blood-group forms understood by the deterministic reasoner."""

import pytest as _pytest


@_pytest.mark.parametrize("text,group", [
    ("we need 2 units of A positive blood urgently at AIIMS", "A+"),
    ("need 3 units of O negative at AIIMS", "O-"),
    ("urgent 1 unit AB pos blood at AIIMS", "AB+"),
    ("need 2 units of B-negative at AIIMS", "B-"),
    ("need 2 units of A+ at AIIMS", "A+"),
])
def test_mock_reasoner_understands_spoken_blood_groups(text, group):
    from app.llm.reasoners import MockReasoner
    plan = MockReasoner().generate_plan(text)
    data = plan if isinstance(plan, dict) else plan.model_dump()
    data = data.get("plan", data)
    assert data["blood_group"] == group
