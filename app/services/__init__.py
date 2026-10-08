"""Business logic and domain services."""

from app.services.compatibility import (
    RBC_COMPATIBILITY_MATRIX,
    get_compatible_donor_groups,
    is_compatible,
)

__all__ = [
    "RBC_COMPATIBILITY_MATRIX",
    "get_compatible_donor_groups",
    "is_compatible",
]
