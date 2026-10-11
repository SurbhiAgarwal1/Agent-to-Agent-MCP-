"""Tests for synthetic dataset seeding."""

import pytest
from app.database.seed import seed_database
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor


def test_seed_database_counts(db_session):
    """Verify that seed_database populates 3 hospitals, 4 blood banks, 15 synthetic donors, and inventories."""
    result = seed_database(db_session)
    assert result["status"] == "success"
    assert result["hospitals"] == 3
    assert result["blood_banks"] == 4
    assert result["donors"] == 15
    assert result["inventories"] > 0

    # Query directly to verify persisted counts
    assert db_session.query(Hospital).count() == 3
    assert db_session.query(BloodBank).count() == 4
    assert db_session.query(Donor).count() == 15
    assert db_session.query(BloodInventory).count() == result["inventories"]


def test_seed_database_idempotent(db_session):
    """Verify that running seed_database twice does not duplicate records."""
    res1 = seed_database(db_session)
    assert res1["status"] == "success"

    res2 = seed_database(db_session)
    assert res2["status"] == "already_seeded"
    assert db_session.query(Hospital).count() == 3
    assert db_session.query(Donor).count() == 15
