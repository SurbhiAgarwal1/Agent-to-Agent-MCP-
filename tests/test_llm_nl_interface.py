"""Unit and Integration Tests for Part 14 Natural Language LLM Interface."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.session import Base, get_db
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.llm.nl_interface import NLInterfaceAgent


@pytest.fixture
def client_with_data():
    """Create test client with isolated database seed."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    with TestingSession() as session:
        h = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
        b = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
        inv = BloodInventory(inventory_id=1, bank_id=1, blood_group="A+", units_available=5)
        session.add_all([h, b, inv])
        session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSession()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_nl_interface_clear_input_extraction(client_with_data):
    """Verify clear, well-formed natural text is accurately parsed."""
    _, session = client_with_data
    agent = NLInterfaceAgent(db=session)

    text = "We urgently need 2 units of A+ at General Hospital"
    res = agent.parse_text(text)

    assert res["success"] is True
    assert res["is_ambiguous"] is False
    assert res["clarification_question"] is None
    extracted = res["extracted"]
    assert extracted["blood_group"] == "A+"
    assert extracted["units_required"] == 2
    assert extracted["urgency"] == "HIGH"
    assert extracted["hospital_id"] == 1


def test_nl_interface_ambiguous_input_clarification(client_with_data):
    """Verify ambiguous or incomplete input requests clarification without guessing."""
    _, session = client_with_data
    agent = NLInterfaceAgent(db=session)

    # Missing units required
    text = "We need some A+ blood at General Hospital immediately"
    res = agent.parse_text(text)

    assert res["success"] is False
    assert res["is_ambiguous"] is True
    assert res["clarification_question"] is not None
    assert "units" in res["clarification_question"].lower()

    # Missing blood group
    text_no_group = "Please send 3 units to General Hospital"
    res2 = agent.parse_text(text_no_group)
    assert res2["is_ambiguous"] is True
    assert "blood group" in res2["clarification_question"].lower()


def test_nl_interface_end_to_end_pipeline(client_with_data):
    """Verify natural language request feeds directly through validated coordinator pipeline."""
    _, session = client_with_data
    agent = NLInterfaceAgent(db=session)

    text = "Urgent: 2 units of A+ needed at General Hospital"
    res = agent.process_request(text)

    assert res["success"] is True
    assert "structured_result" in res
    assert res["structured_result"]["current_state"] == "COMPLETED"
    assert "Successfully processed request" in res["message"]


def test_nl_interface_api_endpoint(client_with_data):
    """Verify POST /api/v1/nl-request FastAPI endpoint."""
    client, _ = client_with_data

    # 1. Successful request
    resp = client.post(
        "/api/v1/nl-request",
        json={"text": "We urgently need 2 units of A+ at General Hospital"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "structured_result" in data

    # 2. Ambiguous request returning clarification prompt
    resp_ambiguous = client.post(
        "/api/v1/nl-request",
        json={"text": "Need blood fast"},
    )
    assert resp_ambiguous.status_code == 200
    amb_data = resp_ambiguous.json()
    assert amb_data["success"] is False
    assert amb_data["status"] == "NEEDS_CLARIFICATION"
    assert "clarify" in amb_data["message"].lower()
