"""Tests for conserving scarce O- blood (universal donor) when other compatible blood exists."""

import pytest

from app.agents.coordinator_agent import CoordinatorAgent
from app.services.optimization_service import OptimizationService
from app.services.scarce_blood_policy import conservation_factor


# ------------------------------------------------------------------ the policy
def test_no_penalty_when_recipient_is_o_negative():
    assert conservation_factor("O-", "O-", "LOW") == 0.0


def test_no_penalty_for_non_o_negative_sources():
    assert conservation_factor("O+", "A+", "LOW") == 0.0
    assert conservation_factor("A+", "A+", "LOW") == 0.0


@pytest.mark.parametrize("urgency,expected", [
    ("LOW", 1.0), ("MEDIUM", 1.0), ("HIGH", 0.3), ("CRITICAL", 0.0), ("low", 1.0), (None, 1.0),
])
def test_penalty_shrinks_as_urgency_rises(urgency, expected):
    assert conservation_factor("O-", "A+", urgency) == expected


def test_unknown_groups_get_no_penalty():
    assert conservation_factor(None, "A+", "LOW") == 0.0
    assert conservation_factor("O-", None, "LOW") == 0.0


# ------------------------------------------------------------------ optimizer
def _cands(o_neg_km, a_pos_km):
    return [
        {"source_type": "BLOOD_BANK", "source_id": 1, "blood_group": "O-", "units_available": 5, "distance_km": o_neg_km},
        {"source_type": "BLOOD_BANK", "source_id": 2, "blood_group": "A+", "units_available": 5, "distance_km": a_pos_km},
    ]


def test_optimizer_prefers_exact_blood_over_nearer_o_negative_for_routine_request():
    plan = OptimizationService().optimize(1, 2, "MEDIUM", _cands(1.0, 20.0), recipient_blood_group="A+")
    assert plan["plan"][0]["source_id"] == 2  # A+ even though 19 km farther


def test_optimizer_uses_nearer_o_negative_when_critical():
    plan = OptimizationService().optimize(1, 2, "CRITICAL", _cands(1.0, 20.0), recipient_blood_group="A+")
    assert plan["plan"][0]["source_id"] == 1


def test_optimizer_still_uses_o_negative_when_nothing_else_exists():
    only_o_neg = [_cands(1.0, 20.0)[0]]
    plan = OptimizationService().optimize(1, 2, "LOW", only_o_neg, recipient_blood_group="A+")
    assert plan["total_units"] == 2 and plan["plan"][0]["source_id"] == 1


def test_optimizer_without_recipient_group_behaves_as_before():
    plan = OptimizationService().optimize(1, 2, "MEDIUM", _cands(1.0, 20.0))
    assert plan["plan"][0]["source_id"] == 1


def test_o_negative_recipient_is_not_penalised():
    plan = OptimizationService().optimize(1, 2, "LOW", _cands(1.0, 20.0), recipient_blood_group="O-")
    assert plan["plan"][0]["source_id"] == 1


# ---------------------------------------------------------------- coordinator
def test_coordinator_scores_o_negative_lower_for_routine_request():
    coord = CoordinatorAgent()
    common = dict(distance_km=2.0, source_type="BLOOD_BANK", is_exact_match=False, urgency="MEDIUM")
    plain = coord.calculate_priority_score(**common)
    conserving = coord.calculate_priority_score(**common, source_blood_group="O-", recipient_blood_group="A+")
    assert conserving < plain


def test_coordinator_does_not_penalise_critical_requests():
    coord = CoordinatorAgent()
    common = dict(distance_km=2.0, source_type="BLOOD_BANK", is_exact_match=False, urgency="CRITICAL")
    assert coord.calculate_priority_score(**common, source_blood_group="O-", recipient_blood_group="A+") == \
        coord.calculate_priority_score(**common)
