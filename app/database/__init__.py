"""Database package re-exports."""

from app.database.session import Base, SessionLocal, engine, get_db, init_db, drop_db

def seed_database(*args, **kwargs):
    """Lazy wrapper for seed_database to avoid circular import during model loading."""
    from app.database.seed import seed_database as _seed_func
    return _seed_func(*args, **kwargs)

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
    "drop_db",
    "seed_database",
]
