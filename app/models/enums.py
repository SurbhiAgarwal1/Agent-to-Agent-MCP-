"""Enumerations for blood groups, urgency levels, and request/match statuses.

All enums inherit from str to serialize cleanly in JSON and SQLite.
"""

from enum import Enum


class BloodGroup(str, Enum):
    """Standard ABO and Rh blood group classifications."""
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"


class UrgencyLevel(str, Enum):
    """Urgency level for an emergency blood request."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RequestStatus(str, Enum):
    """Lifecycle status of a blood request."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class MatchSourceType(str, Enum):
    """Source entity fulfilling a blood match."""
    BLOOD_BANK = "BLOOD_BANK"
    DONOR = "DONOR"


class MatchStatus(str, Enum):
    """Status of an individual candidate match."""
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
