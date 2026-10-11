"""Unit tests for the Requirement Agent."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.hospital import Hospital
from app.agents.requirement_agent import RequirementAgent


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session with a seeded test hospital."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed hospital with hospital_id = 1
    hospital = Hospital(
        name="Apex Test Care Hospital",
        latitude=28.6139,
        longitude=77.2090,
        address="10 Medical Lane, Central Zone",
    )
    session.add(hospital)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# 1. Valid request
def test_requirement_agent_valid_request(db_session):
    """Test that a valid request passes validation and produces the expected output."""
    agent = RequirementAgent(db=db_session)
    input_data = {
        "request_id": 101,
        "hospital_id": 1,
        "blood_group": "o+",
        "units_required": 4,
        "urgency": "critical",
    }

    result = agent.process(input_data)

    assert result == {
        "request_id": 101,
        "blood_group": "O+",
        "units_required": 4,
        "urgency": "CRITICAL",
        "valid": True,
    }


# 2. Invalid blood group
def test_requirement_agent_invalid_blood_group(db_session):
    """Test that an unsupported blood group is rejected with an informative error."""
    agent = RequirementAgent(db=db_session)
    input_data = {
        "request_id": 102,
        "hospital_id": 1,
        "blood_group": "Z+",
        "units_required": 2,
        "urgency": "HIGH",
    }

    result = agent.process(input_data)

    assert result["valid"] is False
    assert any("Unsupported blood group" in err for err in result["errors"])


# 3. Invalid urgency
def test_requirement_agent_invalid_urgency(db_session):
    """Test that an unsupported urgency level is rejected with an informative error."""
    agent = RequirementAgent(db=db_session)
    input_data = {
        "request_id": 103,
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 2,
        "urgency": "SUPER_PANIC",
    }

    result = agent.process(input_data)

    assert result["valid"] is False
    assert any("Unsupported urgency level" in err for err in result["errors"])


# 4. Invalid units (zero or negative)
def test_requirement_agent_invalid_units(db_session):
    """Test that zero or negative units are rejected."""
    agent = RequirementAgent(db=db_session)

    # Test zero units
    res_zero = agent.process({
        "request_id": 104,
        "hospital_id": 1,
        "blood_group": "B+",
        "units_required": 0,
        "urgency": "MEDIUM",
    })
    assert res_zero["valid"] is False
    assert any("greater than zero" in err for err in res_zero["errors"])

    # Test negative units
    res_neg = agent.process({
        "request_id": 105,
        "hospital_id": 1,
        "blood_group": "B+",
        "units_required": -3,
        "urgency": "MEDIUM",
    })
    assert res_neg["valid"] is False
    assert any("greater than zero" in err for err in res_neg["errors"])


# 5. Missing hospital (missing in payload or not found in DB)
def test_requirement_agent_missing_hospital(db_session):
    """Test rejection when hospital_id is omitted or does not exist in the database."""
    agent = RequirementAgent(db=db_session)

    # Case A: hospital_id missing from payload
    res_omitted = agent.process({
        "request_id": 106,
        "blood_group": "O-",
        "units_required": 1,
        "urgency": "LOW",
    })
    assert res_omitted["valid"] is False
    assert any("hospital_id is required" in err for err in res_omitted["errors"])

    # Case B: hospital_id does not exist in DB
    res_not_found = agent.process({
        "request_id": 107,
        "hospital_id": 9999,
        "blood_group": "O-",
        "units_required": 1,
        "urgency": "LOW",
    })
    assert res_not_found["valid"] is False
    assert any("Hospital with ID 9999 does not exist" in err for err in res_not_found["errors"])


# 6. Normalization
def test_requirement_agent_normalization(db_session):
    """Test that casing and whitespace are properly normalized."""
    agent = RequirementAgent(db=db_session)
    input_data = {
        "request_id": 108,
        "hospital_id": 1,
        "blood_group": "  ab-  ",
        "units_required": 3,
        "urgency": "  medium  ",
    }

    result = agent.process(input_data)

    assert result["valid"] is True
    assert result["blood_group"] == "AB-"
    assert result["urgency"] == "MEDIUM"


# 7. Missing request_id
def test_requirement_agent_missing_request_id(db_session):
    """Test that missing request_id is handled cleanly without exceptions."""
    agent = RequirementAgent(db=db_session)
    input_data = {
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 1,
        "urgency": "LOW",
    }

    result = agent.process(input_data)

    assert result["valid"] is False
    assert any("request_id is required" in err for err in result["errors"])
