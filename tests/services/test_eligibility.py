"""Unit tests for stock-expiry and donor-eligibility rules."""

from datetime import date, datetime, timedelta

import pytest

from app.services.eligibility import (
    DEFAULT_DONOR_MIN_GAP_DAYS,
    get_donor_min_gap_days,
    is_donor_eligible,
    is_stock_usable,
)

TODAY = date(2026, 10, 11)


# ---------------------------------------------------------------- stock expiry
def test_expired_stock_is_not_usable():
    assert is_stock_usable(TODAY - timedelta(days=1), today=TODAY) is False


def test_stock_expiring_today_is_still_usable():
    assert is_stock_usable(TODAY, today=TODAY) is True


def test_future_stock_is_usable():
    assert is_stock_usable(TODAY + timedelta(days=30), today=TODAY) is True


def test_unknown_expiry_is_treated_as_usable_for_legacy_records():
    assert is_stock_usable(None, today=TODAY) is True


@pytest.mark.parametrize("value,expected", [
    ("2026-10-10", False),
    ("2026-10-11", True),
    (datetime(2026, 10, 10, 23, 59), False),
    (datetime(2026, 10, 11, 0, 1), True),
])
def test_expiry_accepts_strings_and_datetimes(value, expected):
    assert is_stock_usable(value, today=TODAY) is expected


def test_unparseable_expiry_is_not_usable():
    # An expiry we cannot read must never be dispatched.
    assert is_stock_usable("not-a-date", today=TODAY) is False


# ------------------------------------------------------------ donor eligibility
def test_default_gap_is_56_days():
    assert DEFAULT_DONOR_MIN_GAP_DAYS == 56


def test_never_donated_is_eligible():
    assert is_donor_eligible(None, today=TODAY, min_gap_days=56) is True


def test_recent_donation_is_not_eligible():
    assert is_donor_eligible(TODAY - timedelta(days=10), today=TODAY, min_gap_days=56) is False


def test_one_day_short_of_gap_is_not_eligible():
    assert is_donor_eligible(TODAY - timedelta(days=55), today=TODAY, min_gap_days=56) is False


def test_exactly_at_gap_is_eligible():
    assert is_donor_eligible(TODAY - timedelta(days=56), today=TODAY, min_gap_days=56) is True


def test_future_donation_date_is_invalid_and_not_eligible():
    assert is_donor_eligible(TODAY + timedelta(days=3), today=TODAY, min_gap_days=56) is False


def test_donation_date_accepts_strings():
    assert is_donor_eligible("2026-01-01", today=TODAY, min_gap_days=56) is True
    assert is_donor_eligible("2026-10-01", today=TODAY, min_gap_days=56) is False


def test_unparseable_donation_date_is_not_eligible():
    assert is_donor_eligible("garbage", today=TODAY, min_gap_days=56) is False


# --------------------------------------------------------------------- config
def test_gap_reads_environment(monkeypatch):
    monkeypatch.setenv("DONOR_MIN_GAP_DAYS", "90")
    assert get_donor_min_gap_days() == 90


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "1000", ""])
def test_invalid_gap_config_falls_back_to_default(monkeypatch, bad):
    monkeypatch.setenv("DONOR_MIN_GAP_DAYS", bad)
    assert get_donor_min_gap_days() == 56


def test_gap_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("DONOR_MIN_GAP_DAYS", raising=False)
    assert get_donor_min_gap_days() == 56
