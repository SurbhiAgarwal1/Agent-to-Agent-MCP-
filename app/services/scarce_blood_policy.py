"""Policy for conserving O- (universal donor) blood.

O- can be given to anyone, so using it on a patient who has another compatible
option can leave nothing for a patient who truly needs it. For routine requests
we therefore penalise O- sources; as urgency rises the penalty fades, and for
CRITICAL requests speed matters more than conservation. O- is never excluded -
it is only ranked lower - so it still gets used when nothing else exists.
"""

from typing import Optional

SCARCE_GROUP = "O-"

# Share of the full penalty applied at each urgency level.
_URGENCY_FACTOR = {"LOW": 1.0, "MEDIUM": 1.0, "HIGH": 0.3, "CRITICAL": 0.0}

# Full penalty expressed in "km-equivalents" for the optimizer (distance units)
# and in score points for the coordinator's 0-100 priority score.
PENALTY_KM_EQUIVALENT = 30.0
PENALTY_SCORE_POINTS = 15.0


def _norm(group: Optional[str]) -> Optional[str]:
    return group.strip().upper() if isinstance(group, str) and group.strip() else None


def conservation_factor(
    source_blood_group: Optional[str],
    recipient_blood_group: Optional[str],
    urgency: Optional[str],
) -> float:
    """Return 0.0-1.0: how much of the O- penalty applies to this source."""
    source = _norm(source_blood_group)
    recipient = _norm(recipient_blood_group)
    if source != SCARCE_GROUP or recipient is None or recipient == SCARCE_GROUP:
        return 0.0
    return _URGENCY_FACTOR.get((urgency or "MEDIUM").strip().upper(), 1.0)
