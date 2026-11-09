"""Validated application plan returned by all LLM providers for Blood and Medicine requests."""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import BloodGroup, UrgencyLevel


class Capability(str, Enum):
    REQUIREMENT_VALIDATION = "requirement_validation"
    BLOOD_MATCHING = "blood_matching"
    LOCATION_CALCULATION = "location_calculation"
    NOTIFICATION = "notification"
    MEDICINE_DISCOVERY = "medicine_discovery"
    SUBSTITUTE_MATCHING = "substitute_matching"
    PHARMACY_ROUTING = "pharmacy_routing"


ALLOWED_CAPABILITIES = [item.value for item in Capability]
BASE_CAPABILITIES = [
    Capability.REQUIREMENT_VALIDATION.value,
    Capability.BLOOD_MATCHING.value,
    Capability.LOCATION_CALCULATION.value,
    Capability.NOTIFICATION.value,
]


class MedicineRequestItem(BaseModel):
    """Specific medicine extracted from user prompt."""
    name: str
    quantity: int = Field(default=1, ge=1)
    allow_substitute: bool = True


class BloodRequestPlan(BaseModel):
    """Allowlisted plan covering emergency blood units and online medicine delivery."""

    model_config = ConfigDict(extra="forbid")

    request_type: str = Field(default="blood", description="'blood', 'medicine', or 'combined'")
    blood_group: str | None = None
    units_required: int | None = Field(default=None, ge=1)
    medicines: List[MedicineRequestItem] = Field(default_factory=list)
    location: str | None = None
    urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    required_capabilities: list[Capability] = Field(default_factory=lambda: [Capability(c) for c in BASE_CAPABILITIES])

    @field_validator("blood_group")
    @classmethod
    def normalize_blood_group(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {group.value for group in BloodGroup}:
            raise ValueError("blood_group must be a supported ABO/Rh blood group")
        return normalized

    @field_validator("urgency", mode="before")
    @classmethod
    def normalize_urgency(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"URGENT", "ASAP", "EMERGENCY"}:
                return UrgencyLevel.HIGH
            if normalized in {"STAT", "IMMEDIATE", "IMMEDIATELY"}:
                return UrgencyLevel.CRITICAL
            return normalized
        return value

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @model_validator(mode="after")
    def validate_plan_requirements(self):
        # Validate that basic capabilities exist
        selected = {capability.value for capability in self.required_capabilities}
        base_set = set(BASE_CAPABILITIES)
        missing_base = base_set - selected
        if missing_base:
            # Auto-populate missing base capabilities for backwards compatibility
            self.required_capabilities.extend([Capability(m) for m in missing_base])

        # If medicines are included, ensure pharmacy capabilities are tagged
        if self.medicines:
            self.request_type = "combined" if self.blood_group else "medicine"
            for med_cap in [Capability.MEDICINE_DISCOVERY, Capability.SUBSTITUTE_MATCHING, Capability.PHARMACY_ROUTING]:
                if med_cap not in self.required_capabilities:
                    self.required_capabilities.append(med_cap)
        return self


class ReasoningResult(BaseModel):
    """Provider output metadata; `plan` stays untrusted until validated by Coordinator."""

    plan: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, int | None | str | bool]
    fallback_used: bool = False
