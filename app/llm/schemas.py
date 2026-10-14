"""Validated application plan returned by all LLM providers."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import BloodGroup, UrgencyLevel


class Capability(str, Enum):
    REQUIREMENT_VALIDATION = "requirement_validation"
    BLOOD_MATCHING = "blood_matching"
    LOCATION_CALCULATION = "location_calculation"
    NOTIFICATION = "notification"


ALLOWED_CAPABILITIES = [item.value for item in Capability]


class BloodRequestPlan(BaseModel):
    """Small, allowlisted plan. It deliberately has no tool or endpoint fields."""

    model_config = ConfigDict(extra="forbid")

    blood_group: str | None
    units_required: int | None = Field(ge=1)
    location: str | None
    urgency: UrgencyLevel
    required_capabilities: list[Capability]

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
    def require_supported_workflow(self):
        selected = {capability.value for capability in self.required_capabilities}
        missing = set(ALLOWED_CAPABILITIES) - selected
        if missing:
            raise ValueError(f"required_capabilities is missing: {', '.join(sorted(missing))}")
        return self


class ReasoningResult(BaseModel):
    """Provider output metadata; `plan` stays untrusted until validated by Coordinator."""

    plan: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, int | None | str | bool]
    fallback_used: bool = False

