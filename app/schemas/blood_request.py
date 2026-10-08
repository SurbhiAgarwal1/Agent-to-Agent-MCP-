"""Pydantic schemas for BloodRequest creation, status updates, and responses."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import BloodGroup, UrgencyLevel, RequestStatus


class BloodRequestCreate(BaseModel):
    """Schema for hospitals to submit an emergency blood request."""
    hospital_id: int = Field(..., description="ID of the requesting hospital", examples=[1])
    blood_group: BloodGroup = Field(..., description="Required ABO/Rh blood group (e.g. O+, A-)", examples=[BloodGroup.O_POS])
    units_required: int = Field(..., gt=0, description="Number of blood units required (must be > 0)", examples=[4])
    urgency: UrgencyLevel = Field(default=UrgencyLevel.MEDIUM, description="Urgency level (LOW, MEDIUM, HIGH, CRITICAL)", examples=[UrgencyLevel.CRITICAL])


class BloodRequestStatusUpdate(BaseModel):
    """Schema for updating the lifecycle status of a blood request."""
    status: RequestStatus = Field(..., description="New lifecycle status for the request", examples=[RequestStatus.FULFILLED])


class BloodRequestResponse(BaseModel):
    """Schema returned to clients representing a blood request."""
    request_id: int = Field(..., description="Unique identifier of the blood request")
    hospital_id: int = Field(..., description="ID of the hospital that placed the request")
    blood_group: BloodGroup = Field(..., description="Requested blood group")
    units_required: int = Field(..., description="Units of blood requested")
    urgency: UrgencyLevel = Field(..., description="Urgency classification")
    status: RequestStatus = Field(..., description="Current request status")
    created_at: datetime = Field(..., description="Timestamp when request was registered")

    model_config = ConfigDict(from_attributes=True)
