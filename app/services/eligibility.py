"""Safety rules deciding whether blood stock or a donor may be dispatched.

* Stock past its expiry date is never usable (the expiry day itself is still OK).
* Stock with no recorded expiry is treated as usable, so legacy rows keep working;
  an expiry that cannot be parsed is treated as unsafe.
* A donor must wait ``DONOR_MIN_GAP_DAYS`` (default 56, the common whole-blood
  interval) after their last donation. Confirm the figure with your clinical lead.
"""

import os
from datetime import date, datetime
from typing import Any, Optional

DEFAULT_DONOR_MIN_GAP_DAYS = 56
_MAX_GAP_DAYS = 365


def _to_date(value: Any) -> Optional[date]:
    """Convert date/datetime/ISO string to a date; raise ValueError if unreadable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.strip()).date()
    raise ValueError(f"unsupported date value: {value!r}")


def is_stock_usable(expiry_date: Any, today: Optional[date] = None) -> bool:
    """True if a batch with this expiry date may still be dispatched."""
    if expiry_date is None:
        return True
    try:
        expiry = _to_date(expiry_date)
    except (ValueError, TypeError):
        return False
    return expiry >= (today or date.today())


def get_donor_min_gap_days() -> int:
    """Minimum days between donations, from DONOR_MIN_GAP_DAYS (1..365) or the default."""
    raw = os.environ.get("DONOR_MIN_GAP_DAYS", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DONOR_MIN_GAP_DAYS
    if value < 1 or value > _MAX_GAP_DAYS:
        return DEFAULT_DONOR_MIN_GAP_DAYS
    return value


def is_donor_eligible(
    last_donation_date: Any,
    today: Optional[date] = None,
    min_gap_days: Optional[int] = None,
) -> bool:
    """True if enough time has passed since the donor's last donation."""
    if last_donation_date is None:
        return True
    try:
        last = _to_date(last_donation_date)
    except (ValueError, TypeError):
        return False
    today = today or date.today()
    gap = min_gap_days if min_gap_days is not None else get_donor_min_gap_days()
    days_since = (today - last).days
    if days_since < 0:  # a donation dated in the future is bad data
        return False
    return days_since >= gap
