"""Lightweight startup migration for databases created before the units/blood_group columns."""

from sqlalchemy import create_engine, inspect, text

from app.database.session import ensure_schema

LEGACY_DDL = """
CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_id INTEGER NOT NULL,
    distance_km FLOAT,
    estimated_time VARCHAR(50),
    priority_score FLOAT,
    status VARCHAR(20) NOT NULL
)
"""


def legacy_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(LEGACY_DDL))
        conn.execute(text("INSERT INTO matches (request_id, source_type, source_id, status) "
                          "VALUES (1, 'BLOOD_BANK', 2, 'PROPOSED')"))
    return engine


def columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("matches")}


def test_missing_columns_are_added_and_rows_preserved():
    engine = legacy_engine()
    assert "units" not in columns(engine)
    ensure_schema(engine)
    assert {"units", "blood_group"} <= columns(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT source_id, units, blood_group FROM matches")).one()
    assert tuple(row) == (2, None, None)


def test_migration_is_idempotent():
    engine = legacy_engine()
    ensure_schema(engine)
    ensure_schema(engine)
    assert {"units", "blood_group"} <= columns(engine)


def test_missing_table_is_ignored():
    ensure_schema(create_engine("sqlite:///:memory:"))
