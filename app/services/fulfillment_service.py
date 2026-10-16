"""Closing the loop on a coordinated request: confirm delivery or reject a source.

A coordinated plan creates ACCEPTED matches ("holds") that reserve units. They stay
reserved until a person confirms delivery (complete) or the source falls through
(reject). Only completion changes real stock or donor records.
"""

from datetime import date
from threading import RLock
from typing import Optional

from sqlalchemy.orm import Session

from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.enums import MatchSourceType, MatchStatus, RequestStatus
from app.models.match import Match
from app.services.eligibility import is_stock_usable

# One lock for everything that reads or changes holds and stock. SQLite and this
# in-process lock are only safe for a single server process; use a database with
# row locking (e.g. PostgreSQL SELECT ... FOR UPDATE) before running several workers.
COORDINATION_LOCK = RLock()


class FulfillmentError(Exception):
    """Base class for lifecycle errors."""


class MatchNotFound(FulfillmentError):
    pass


class InvalidMatchState(FulfillmentError):
    pass


class InsufficientStock(FulfillmentError):
    pass


def _get_match(db: Session, request_id: int, match_id: int) -> Match:
    match = db.query(Match).filter(Match.match_id == match_id, Match.request_id == request_id).first()
    if match is None:
        raise MatchNotFound(f"Match {match_id} not found for request {request_id}.")
    return match


def refresh_request_status(db: Session, request_id: int) -> Optional[str]:
    """Recompute a request's status from its matches. Closed requests are left alone."""
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first()
    if request is None or request.status in (RequestStatus.CANCELLED.value, RequestStatus.FULFILLED.value):
        return request.status if request else None
    matches = db.query(Match).filter(Match.request_id == request_id).all()
    delivered = sum(m.units or 0 for m in matches if m.status == MatchStatus.COMPLETED.value)
    holding = any(m.status == MatchStatus.ACCEPTED.value and m.units for m in matches)
    if delivered >= request.units_required:
        request.status = RequestStatus.FULFILLED.value
    elif delivered > 0:
        request.status = RequestStatus.PARTIALLY_FULFILLED.value
    elif holding:
        request.status = RequestStatus.PROCESSING.value
    else:
        request.status = RequestStatus.PENDING.value
    return request.status


def _take_from_inventory(db: Session, bank_id: int, blood_group: str, units: int, today: date) -> None:
    batches = (
        db.query(BloodInventory)
        .filter(BloodInventory.bank_id == bank_id,
                BloodInventory.blood_group == blood_group,
                BloodInventory.units_available > 0)
        .all()
    )
    usable = [b for b in batches if is_stock_usable(b.expiry_date, today=today)]
    # earliest expiry first; batches with no recorded expiry last
    usable.sort(key=lambda b: (b.expiry_date is None, b.expiry_date or date.max))
    if sum(b.units_available for b in usable) < units:
        raise InsufficientStock(
            f"Bank {bank_id} no longer has {units} usable unit(s) of {blood_group}.")
    remaining = units
    for batch in usable:
        take = min(batch.units_available, remaining)
        batch.units_available -= take
        remaining -= take
        if remaining == 0:
            break


def complete_match(db: Session, request_id: int, match_id: int, today: Optional[date] = None) -> dict:
    """Confirm a held match was delivered: update stock/donor and the request status."""
    today = today or date.today()
    with COORDINATION_LOCK:
        match = _get_match(db, request_id, match_id)
        if match.status != MatchStatus.ACCEPTED.value:
            raise InvalidMatchState(f"Only ACCEPTED matches can be completed (this one is {match.status}).")
        if not match.units or not match.blood_group:
            raise InvalidMatchState("This match has no reserved units (created before reservations existed). Re-run coordination.")
        try:
            if match.source_type == MatchSourceType.BLOOD_BANK.value:
                _take_from_inventory(db, match.source_id, match.blood_group, match.units, today)
            else:
                donor = db.query(Donor).filter(Donor.donor_id == match.source_id).first()
                if donor is None:
                    raise InvalidMatchState(f"Donor {match.source_id} no longer exists.")
                donor.available = False
                donor.last_donation_date = today
            match.status = MatchStatus.COMPLETED.value
            request_status = refresh_request_status(db, request_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"match_id": match_id, "match_status": MatchStatus.COMPLETED.value, "request_status": request_status}


def reject_match(db: Session, request_id: int, match_id: int, reason: Optional[str] = None) -> dict:
    """Reject a proposed/held match, releasing its reserved units."""
    with COORDINATION_LOCK:
        match = _get_match(db, request_id, match_id)
        if match.status not in (MatchStatus.ACCEPTED.value, MatchStatus.PROPOSED.value):
            raise InvalidMatchState(f"Only PROPOSED or ACCEPTED matches can be rejected (this one is {match.status}).")
        try:
            match.status = MatchStatus.REJECTED.value
            request_status = refresh_request_status(db, request_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"match_id": match_id, "match_status": MatchStatus.REJECTED.value,
            "request_status": request_status, "reason": reason}
