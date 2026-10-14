"""Shared pytest fixtures for Blood Donation Matching System test suite."""

import os
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.session import Base, get_db
from app.models.user import User
from app.auth.utils import hash_password, create_access_token


def make_user(db, email, role, password="Passw0rd!x", *, hospital_ids=(), bank_ids=()):
    """Insert a user directly into the database using hash_password and return it."""
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.models.membership import HospitalMembership, BloodBankMembership
    db.add_all([HospitalMembership(user_id=user.id, hospital_id=org_id) for org_id in hospital_ids])
    db.add_all([BloodBankMembership(user_id=user.id, bank_id=org_id) for org_id in bank_ids])
    if hospital_ids or bank_ids:
        db.commit()
        db.refresh(user)
    return user


def auth_headers(user):
    """Return Bearer token Authorization headers for a given user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def db_session():
    """Create an isolated unseeded in-memory SQLite database session."""
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


@pytest.fixture(autouse=True)
def use_mock_llm_for_all_tests(monkeypatch):
    """Prevent the test suite from ever selecting a live LLM provider."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("LLM_FALLBACK_PROVIDER", raising=False)


@pytest.fixture
def client(db_session):
    """Create an unseeded FastAPI TestClient sharing the in-memory SQLite database with db_session."""
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
