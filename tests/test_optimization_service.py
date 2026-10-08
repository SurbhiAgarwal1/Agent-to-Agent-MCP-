"""Unit and Integration Tests for Part 10 Optimization Engine."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.blood_request import BloodRequest
from app.models.match import Match
from app.services.optimization_service import (
    FulfillmentStatus,
    OptimizationService,
)
from app.agents.coordinator_agent import CoordinatorAgent

# Test engine
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """Create a pristine database schema for test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        h1 = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
        b1 = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
        inv1 = BloodInventory(inventory_id=1, bank_id=1, blood_group="A+", units_available=3)
        req = BloodRequest(request_id=1, hospital_id=1, blood_group="A+", units_required=2, urgency="HIGH", status="PENDING")
        session.add_all([h1, b1, inv1, req])
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def test_optimization_single_source_sufficient():
    """Test scenario where a single blood bank can fulfill the full units requested."""
    service = OptimizationService()
    candidates = [
        {"source_type": "BLOOD_BANK", "source_id": 1, "units_available": 5, "distance_km": 3.2},
        {"source_type": "DONOR", "source_id": 10, "units_available": 1, "distance_km": 1.5},
    ]

    plan_result = service.optimize(
        request_id=101,
        units_required=3,
        urgency="MEDIUM",
        candidates=candidates,
    )

    assert plan_result["request_id"] == 101
    assert plan_result["fulfilled"] is True
    assert plan_result["status"] == FulfillmentStatus.FULLY_FULFILLED.value
    assert plan_result["total_units"] == 3
    assert len(plan_result["plan"]) >= 1


def test_optimization_multi_source_combination_needed():
    """Test scenario where combining blood bank and donor is required."""
    service = OptimizationService()
    candidates = [
        {"source_type": "BLOOD_BANK", "source_id": 2, "units_available": 2, "distance_km": 4.1},
        {"source_type": "DONOR", "source_id": 8, "units_available": 1, "distance_km": 6.7},
        {"source_type": "DONOR", "source_id": 9, "units_available": 1, "distance_km": 8.0},
    ]

    plan_result = service.optimize(
        request_id=102,
        units_required=4,
        urgency="HIGH",
        candidates=candidates,
    )

    assert plan_result["fulfilled"] is True
    assert plan_result["status"] == FulfillmentStatus.FULLY_FULFILLED.value
    assert plan_result["total_units"] == 4
    # Sources should combine 2 units from bank, 1 from donor 8, 1 from donor 9
    assert len(plan_result["plan"]) == 3
    sources = {p["source_id"]: p["units"] for p in plan_result["plan"]}
    assert sources[2] == 2
    assert sources[8] == 1
    assert sources[9] == 1


def test_optimization_insufficient_total_units_partial():
    """Test scenario where total available units across all sources is less than requested."""
    service = OptimizationService()
    candidates = [
        {"source_type": "BLOOD_BANK", "source_id": 2, "units_available": 2, "distance_km": 4.0},
        {"source_type": "DONOR", "source_id": 3, "units_available": 1, "distance_km": 5.0},
    ]

    plan_result = service.optimize(
        request_id=103,
        units_required=10,
        urgency="CRITICAL",
        candidates=candidates,
    )

    assert plan_result["fulfilled"] is False
    assert plan_result["status"] == FulfillmentStatus.PARTIALLY_FULFILLED.value
    assert plan_result["total_units"] == 3
    assert plan_result["details"]["units_shortage"] == 7


def test_optimization_urgency_prioritization():
    """Test that CRITICAL urgency penalizes distance and prioritizes closest sources first."""
    service = OptimizationService()
    candidates = [
        {"source_type": "DONOR", "source_id": 1, "units_available": 1, "distance_km": 1.2},
        {"source_type": "BLOOD_BANK", "source_id": 2, "units_available": 10, "distance_km": 15.0},
    ]

    plan_result = service.optimize(
        request_id=104,
        units_required=1,
        urgency="CRITICAL",
        candidates=candidates,
    )

    assert plan_result["fulfilled"] is True
    assert len(plan_result["plan"]) == 1
    # Closest donor picked for urgent 1-unit request over far blood bank
    assert plan_result["plan"][0]["source_id"] == 1


def test_optimization_zero_candidates():
    """Test edge case where candidates list is empty."""
    service = OptimizationService()
    plan_result = service.optimize(
        request_id=105,
        units_required=4,
        urgency="LOW",
        candidates=[],
    )

    assert plan_result["fulfilled"] is False
    assert plan_result["status"] == FulfillmentStatus.UNFULFILLED.value
    assert plan_result["total_units"] == 0
    assert plan_result["plan"] == []


def test_optimization_coordinator_integration(db_session):
    """Test that CoordinatorAgent returns the fulfillment plan in coordinate()."""
    coordinator = CoordinatorAgent(db=db_session)
    res = coordinator.coordinate(request_input=1, persist=False)

    assert res["success"] is True
    assert "fulfillment_plan" in res
    plan = res["fulfillment_plan"]
    assert plan["request_id"] == 1
    assert "plan" in plan
    assert plan["status"] in [
        FulfillmentStatus.FULLY_FULFILLED.value,
        FulfillmentStatus.PARTIALLY_FULFILLED.value,
        FulfillmentStatus.UNFULFILLED.value,
    ]
