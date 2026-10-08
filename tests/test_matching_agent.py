"""Unit tests for the Matching Agent and Compatibility Service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.enums import BloodGroup, MatchSourceType
from app.agents.matching_agent import MatchingAgent
from app.services.compatibility import (
    RBC_COMPATIBILITY_MATRIX,
    get_compatible_donor_groups,
    is_compatible,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# -----------------------------------------------------------------------------
# 1. Compatibility Service Tests
# -----------------------------------------------------------------------------

def test_compatibility_exact_match_priority():
    """Verify that exact blood group is always the first compatible group."""
    for bg in BloodGroup:
        compatible = get_compatible_donor_groups(bg.value)
        assert len(compatible) >= 1
        assert compatible[0] == bg.value, f"Exact group must be index 0 for {bg.value}"


def test_compatibility_o_negative_universal_donor():
    """O- blood must be compatible with every single recipient blood group."""
    for bg in BloodGroup:
        assert is_compatible(donor_group="O-", recipient_group=bg.value) is True


def test_compatibility_ab_positive_universal_recipient():
    """AB+ recipient can receive red blood cells from every blood group."""
    for bg in BloodGroup:
        assert is_compatible(donor_group=bg.value, recipient_group="AB+") is True


def test_compatibility_incompatible_cases():
    """Verify standard medical incompatibilities."""
    # O- recipient can ONLY receive O-
    assert is_compatible("O+", "O-") is False
    assert is_compatible("A+", "O-") is False
    assert is_compatible("B-", "O-") is False

    # A+ cannot receive B+ or AB+
    assert is_compatible("B+", "A+") is False
    assert is_compatible("AB+", "A+") is False


# -----------------------------------------------------------------------------
# 2. Matching Agent In-Memory / Decoupled Tests
# -----------------------------------------------------------------------------

def test_exact_blood_group_match():
    """Test matching when exact blood group is available at a bank and donor."""
    agent = MatchingAgent()
    request_data = {
        "request_id": 101,
        "blood_group": "B+",
        "units_required": 2,
    }

    mock_inventories = [
        {"bank_id": 1, "blood_group": "B+", "units_available": 5},
    ]
    mock_donors = [
        {"donor_id": 10, "blood_group": "B+", "available": True},
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=mock_inventories,
        donors=mock_donors,
    )

    assert result["request_id"] == 101
    assert len(result["matches"]) == 2

    # Both must be B+ and have correct source info
    assert result["matches"][0] == {
        "source_type": MatchSourceType.BLOOD_BANK.value,
        "source_id": 1,
        "blood_group": "B+",
        "units_available": 5,
    }
    assert result["matches"][1] == {
        "source_type": MatchSourceType.DONOR.value,
        "source_id": 10,
        "blood_group": "B+",
        "units_available": 1,
    }


def test_incompatible_blood_group():
    """Test that sources with medically incompatible blood groups are rejected."""
    agent = MatchingAgent()
    # Recipient is O-, which can only accept O-
    request_data = {
        "request_id": 102,
        "blood_group": "O-",
        "units_required": 1,
    }

    mock_inventories = [
        {"bank_id": 1, "blood_group": "A+", "units_available": 10},
        {"bank_id": 2, "blood_group": "B-", "units_available": 4},
        {"bank_id": 3, "blood_group": "O+", "units_available": 8},
    ]
    mock_donors = [
        {"donor_id": 1, "blood_group": "AB+", "available": True},
        {"donor_id": 2, "blood_group": "A-", "available": True},
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=mock_inventories,
        donors=mock_donors,
    )

    assert result["request_id"] == 102
    assert result["matches"] == []


def test_unavailable_donor():
    """Test that donors who are not available (available=False) are excluded."""
    agent = MatchingAgent()
    request_data = {"request_id": 103, "blood_group": "A+"}

    mock_donors = [
        {"donor_id": 5, "blood_group": "A+", "available": False},  # Matching but unavailable
        {"donor_id": 6, "blood_group": "A+", "available": True},   # Matching and available
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=[],
        donors=mock_donors,
    )

    assert len(result["matches"]) == 1
    assert result["matches"][0]["source_id"] == 6
    assert result["matches"][0]["units_available"] == 1


def test_insufficient_inventory():
    """Test that blood bank inventory with 0 or negative units is excluded."""
    agent = MatchingAgent()
    request_data = {"request_id": 104, "blood_group": "O+"}

    mock_inventories = [
        {"bank_id": 1, "blood_group": "O+", "units_available": 0},   # Zero stock
        {"bank_id": 2, "blood_group": "O+", "units_available": -2},  # Invalid/depleted stock
        {"bank_id": 3, "blood_group": "O+", "units_available": 4},   # Valid stock
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=mock_inventories,
        donors=[],
    )

    assert len(result["matches"]) == 1
    assert result["matches"][0]["source_id"] == 3
    assert result["matches"][0]["units_available"] == 4


def test_multiple_possible_matches_with_prioritization():
    """Test multiple matches where exact matches are prioritized over compatible alternatives."""
    agent = MatchingAgent()
    # Recipient is O+ -> compatible with O+ (exact) and O- (compatible alternative)
    request_data = {"request_id": 105, "blood_group": "O+"}

    mock_inventories = [
        {"bank_id": 1, "blood_group": "O-", "units_available": 3},  # Compatible alternative
        {"bank_id": 2, "blood_group": "O+", "units_available": 6},  # Exact match
        {"bank_id": 3, "blood_group": "AB+", "units_available": 9}, # Incompatible
    ]
    mock_donors = [
        {"donor_id": 8, "blood_group": "O+", "available": True},   # Exact match donor
        {"donor_id": 9, "blood_group": "O-", "available": True},   # Compatible donor
        {"donor_id": 10, "blood_group": "B+", "available": True},  # Incompatible donor
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=mock_inventories,
        donors=mock_donors,
    )

    assert result["request_id"] == 105
    matches = result["matches"]
    assert len(matches) == 4

    # 1. Exact Blood Bank: Bank 2 (O+)
    assert matches[0] == {
        "source_type": MatchSourceType.BLOOD_BANK.value,
        "source_id": 2,
        "blood_group": "O+",
        "units_available": 6,
    }
    # 2. Exact Donor: Donor 8 (O+)
    assert matches[1] == {
        "source_type": MatchSourceType.DONOR.value,
        "source_id": 8,
        "blood_group": "O+",
        "units_available": 1,
    }
    # 3. Compatible Blood Bank: Bank 1 (O-)
    assert matches[2] == {
        "source_type": MatchSourceType.BLOOD_BANK.value,
        "source_id": 1,
        "blood_group": "O-",
        "units_available": 3,
    }
    # 4. Compatible Donor: Donor 9 (O-)
    assert matches[3] == {
        "source_type": MatchSourceType.DONOR.value,
        "source_id": 9,
        "blood_group": "O-",
        "units_available": 1,
    }


def test_no_matches():
    """Test scenario where no compatible sources exist in the system."""
    agent = MatchingAgent()
    request_data = {"request_id": 106, "blood_group": "AB-"}

    mock_inventories = [
        {"bank_id": 1, "blood_group": "AB+", "units_available": 5},  # Incompatible
        {"bank_id": 2, "blood_group": "B+", "units_available": 4},   # Incompatible
    ]
    mock_donors = [
        {"donor_id": 1, "blood_group": "O+", "available": True},     # Incompatible
        {"donor_id": 2, "blood_group": "A+", "available": True},     # Incompatible
    ]

    result = agent.find_matches(
        request_data=request_data,
        inventories=mock_inventories,
        donors=mock_donors,
    )

    assert result == {"request_id": 106, "matches": []}


# -----------------------------------------------------------------------------
# 3. Database Session Integration Test
# -----------------------------------------------------------------------------

def test_matching_agent_with_database_session(db_session):
    """Test Matching Agent reading directly from SQLite database models."""
    # Seed blood banks
    bank = BloodBank(
        name="Metro Central Blood Bank",
        latitude=28.6139,
        longitude=77.2090,
        address="10 Medical Center Way",
    )
    db_session.add(bank)
    db_session.commit()

    # Seed inventories: 1 matching O+, 1 matching O-, 1 out-of-stock O+, 1 incompatible B+
    db_session.add_all([
        BloodInventory(bank_id=bank.bank_id, blood_group="O+", units_available=8),
        BloodInventory(bank_id=bank.bank_id, blood_group="O-", units_available=2),
        BloodInventory(bank_id=bank.bank_id, blood_group="O+", units_available=0),  # Out of stock
        BloodInventory(bank_id=bank.bank_id, blood_group="B+", units_available=15), # Incompatible
    ])

    # Seed synthetic donors: 1 available O+, 1 unavailable O+, 1 available A+
    db_session.add_all([
        Donor(name="Synthetic Donor 1", blood_group="O+", latitude=28.62, longitude=77.21, available=True),
        Donor(name="Synthetic Donor 2", blood_group="O+", latitude=28.63, longitude=77.22, available=False),
        Donor(name="Synthetic Donor 3", blood_group="A+", latitude=28.64, longitude=77.23, available=True),
    ])
    db_session.commit()

    agent = MatchingAgent(db=db_session)
    request_data = {"request_id": 201, "blood_group": "O+"}

    result = agent.find_matches(request_data=request_data)

    assert result["request_id"] == 201
    matches = result["matches"]

    # We expect:
    # 1. BloodBank O+ (8 units)
    # 2. Donor 1 O+ (1 unit)
    # 3. BloodBank O- (2 units)
    assert len(matches) == 3
    assert matches[0]["source_type"] == "BLOOD_BANK"
    assert matches[0]["blood_group"] == "O+"
    assert matches[0]["units_available"] == 8

    assert matches[1]["source_type"] == "DONOR"
    assert matches[1]["blood_group"] == "O+"
    assert matches[1]["units_available"] == 1

    assert matches[2]["source_type"] == "BLOOD_BANK"
    assert matches[2]["blood_group"] == "O-"
    assert matches[2]["units_available"] == 2
