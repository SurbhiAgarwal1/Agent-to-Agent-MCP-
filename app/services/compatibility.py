"""Blood Group Compatibility Service.

Implements standard Red Blood Cell (RBC) transfusion compatibility rules
defined by medical hematology standards (ABO and Rh factor).

Exact blood matches are always prioritized first, followed by compatible
alternative donor groups.
"""

from typing import List, Set
from app.models.enums import BloodGroup


# Standard Red Blood Cell (RBC) transfusion compatibility matrix:
# recipient_blood_group -> list of compatible donor groups (exact match first)
RBC_COMPATIBILITY_MATRIX: dict[str, List[str]] = {
    BloodGroup.O_NEG.value: [
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.O_POS.value: [
        BloodGroup.O_POS.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.A_NEG.value: [
        BloodGroup.A_NEG.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.A_POS.value: [
        BloodGroup.A_POS.value,
        BloodGroup.A_NEG.value,
        BloodGroup.O_POS.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.B_NEG.value: [
        BloodGroup.B_NEG.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.B_POS.value: [
        BloodGroup.B_POS.value,
        BloodGroup.B_NEG.value,
        BloodGroup.O_POS.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.AB_NEG.value: [
        BloodGroup.AB_NEG.value,
        BloodGroup.A_NEG.value,
        BloodGroup.B_NEG.value,
        BloodGroup.O_NEG.value,
    ],
    BloodGroup.AB_POS.value: [
        BloodGroup.AB_POS.value,
        BloodGroup.AB_NEG.value,
        BloodGroup.A_POS.value,
        BloodGroup.A_NEG.value,
        BloodGroup.B_POS.value,
        BloodGroup.B_NEG.value,
        BloodGroup.O_POS.value,
        BloodGroup.O_NEG.value,
    ],
}


def get_compatible_donor_groups(recipient_group: str) -> List[str]:
    """Return ordered list of compatible donor blood groups for a given recipient.
    
    The recipient's exact blood group is always the first element in the returned list.
    
    Args:
        recipient_group: Normalized blood group string (e.g. "O+", "AB-")
        
    Returns:
        List of compatible donor blood groups, or empty list if group is unknown.
    """
    clean_group = recipient_group.strip().upper() if recipient_group else ""
    return RBC_COMPATIBILITY_MATRIX.get(clean_group, [])


def is_compatible(donor_group: str, recipient_group: str) -> bool:
    """Check if donor blood is medically compatible with recipient.
    
    Args:
        donor_group: Blood group of donor or blood bank unit
        recipient_group: Blood group of the recipient patient
        
    Returns:
        True if compatible, False otherwise.
    """
    compatible_groups: Set[str] = set(get_compatible_donor_groups(recipient_group))
    clean_donor = donor_group.strip().upper() if donor_group else ""
    return clean_donor in compatible_groups
