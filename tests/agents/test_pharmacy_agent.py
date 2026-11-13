import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base, ensure_schema
from app.database.seed import seed_database
from app.agents.pharmacy_agent import PharmacyAgent
from app.agents.a2a.bus import MessageBus
from app.agents.a2a.message import A2AMessage, A2AMessageType


@pytest.fixture(scope="module")
def db_session(tmp_path_factory):
    test_engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('pharmacy') / 'test.db'}")
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=test_engine)
    ensure_schema(test_engine)
    test_session = sessionmaker(bind=test_engine)
    db = test_session()
    seed_database(db)
    yield db
    db.close()
    test_engine.dispose()


def test_pharmacy_agent_check_stock_a2a(db_session):
    agent = PharmacyAgent(db=db_session)
    msg = A2AMessage(
        sender_agent="CoordinatorAgent",
        receiver_agent="PharmacyAgent",
        message_type=A2AMessageType.REQUEST.value,
        payload={"action": "check_stock", "medicine_name": "Dolo 650", "quantity": 2},
    )

    resp = agent.handle_a2a_message(msg)
    assert resp.message_type == A2AMessageType.RESPONSE.value
    assert resp.payload["success"] is True
    assert resp.payload["available"] is True
    assert resp.payload["allocated_medicine"] == "Dolo 650"


def test_pharmacy_agent_find_substitutes_a2a(db_session):
    agent = PharmacyAgent(db=db_session)
    msg = A2AMessage(
        sender_agent="CoordinatorAgent",
        receiver_agent="PharmacyAgent",
        message_type=A2AMessageType.REQUEST.value,
        payload={"action": "find_substitutes", "medicine_name": "Dolo 650"},
    )

    resp = agent.handle_a2a_message(msg)
    assert resp.message_type == A2AMessageType.RESPONSE.value
    assert resp.payload["success"] is True
    assert resp.payload["substitutes_count"] >= 1
    brands = [s["brand_name"] for s in resp.payload["substitutes"]]
    assert "Calpol 650" in brands


def test_pharmacy_agent_fulfill_order_a2a(db_session):
    agent = PharmacyAgent(db=db_session)
    msg = A2AMessage(
        sender_agent="CoordinatorAgent",
        receiver_agent="PharmacyAgent",
        message_type=A2AMessageType.REQUEST.value,
        payload={
            "action": "fulfill_order",
            "delivery_address": "St. Jude Emergency Care Center",
            "items": [{"name": "Dolo 650", "quantity": 1, "allow_substitute": True}],
            "urgency": "HIGH",
        },
    )

    resp = agent.handle_a2a_message(msg)
    assert resp.message_type == A2AMessageType.RESPONSE.value
    assert resp.payload["success"] is True
    assert resp.payload["order_id"] is not None
    assert resp.payload["status"] == "MATCHED"
