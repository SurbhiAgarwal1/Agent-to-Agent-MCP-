"""Pydantic schemas for synthetic Donor."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import BloodGroup


class DonorBase(BaseModel):
    name: str = Field(..., max_length=120, examples=["Synthetic Donor Alpha"])
    blood_group: BloodGroup
    latitude: float = Field(..., ge=-90.0, le=90.0, examples=[28.6145])
    longitude: float = Field(..., ge=-180.0, le=180.0, examples=[77.2105])
    available: bool = True
    last_donation_date: Optional[date] = None


class DonorCreate(DonorBase):
    pass


class DonorResponse(DonorBase):
    donor_id: int

    model_config = ConfigDict(from_attributes=True)
