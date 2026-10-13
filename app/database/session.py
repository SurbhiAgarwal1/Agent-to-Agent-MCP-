"""SQLAlchemy database engine, session management, and initialization."""

from typing import Generator
from sqlalchemy import create_engine, inspect, text
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
    ensure_schema(engine)


# Columns added after the first release: table -> [(column, SQL type)].
# create_all() never alters existing tables, so older databases get them added here.
_ADDED_COLUMNS = {
    "matches": [("units", "INTEGER"), ("blood_group", "VARCHAR(5)")],
}


def ensure_schema(bind) -> None:
    """Add any known columns missing from existing tables (lightweight, idempotent migration)."""
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        with bind.begin() as conn:
            for name, sql_type in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def drop_db() -> None:
    """Drop all tables registered on Base metadata (useful for test resets)."""
    import app.models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
