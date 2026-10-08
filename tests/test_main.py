from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal

client = TestClient(app)


def test_read_root():
    """Verify GET / returns expected message and status."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Blood Donation Matching System API",
        "status": "running",
    }


def test_health_check():
    """Verify GET /health returns status healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
    }


def test_database_session_initialization():
    """Verify that the database session can be created and closed without errors."""
    db = SessionLocal()
    try:
        assert db is not None
    finally:
        db.close()
