"""SQLAlchemy database engine, session management, and initialization."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

settings = get_settings()

# SQLite requires check_same_thread=False when used across multiple threads in FastAPI
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it when request handling finishes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables registered on Base metadata."""
    import app.models  # noqa: F401 (Ensure all models are registered)
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables registered on Base metadata (useful for test resets)."""
    import app.models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
