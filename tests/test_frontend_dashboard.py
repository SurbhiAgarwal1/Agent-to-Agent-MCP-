"""Smoke and API integration tests for Part 13 Frontend Emergency Command Center."""

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


@pytest.fixture
def client():
    """Create a test client with an isolated in-memory SQLite database."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    with TestingSession() as seed_session:
        h = Hospital(hospital_id=1, name="General Hospital", latitude=28.6139, longitude=77.2090, address="New Delhi")
        b = BloodBank(bank_id=1, name="City Central Blood Bank", latitude=28.6200, longitude=77.2100, address="Connaught Place")
        inv = BloodInventory(inventory_id=1, bank_id=1, blood_group="A+", units_available=5)
        seed_session.add_all([h, b, inv])
        seed_session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_dashboard_route_serves_html(client):
    """Verify GET /dashboard and GET /ui serve the HTML dashboard."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "html" in resp.headers.get("content-type", "").lower()

    resp_ui = client.get("/ui")
    assert resp_ui.status_code == 200
    assert "html" in resp_ui.headers.get("content-type", "").lower()


def test_frontend_create_request_api_flow(client):
    """Verify create-request API flow used by frontend form."""
    client = TestClient(app)
    payload = {
        "hospital_id": 1,
        "blood_group": "A+",
        "units_required": 2,
        "urgency": "HIGH",
    }
    create_resp = client.post("/api/v1/blood-requests", json=payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["blood_group"] == "A+"
    assert created_data["status"] == "PENDING"
    req_id = created_data["request_id"]

    # Test list endpoint polled by frontend table
    list_resp = client.get("/api/v1/blood-requests")
    assert list_resp.status_code == 200
    req_list = list_resp.json()
    assert any(r["request_id"] == req_id for r in req_list)

    # Test coordinate action button endpoint from dashboard
    coord_resp = client.post(f"/api/v1/blood-requests/{req_id}/coordinate")
    assert coord_resp.status_code == 200
    coord_data = coord_resp.json()
    assert coord_data["success"] is True
    assert "fulfillment_plan" in coord_data
