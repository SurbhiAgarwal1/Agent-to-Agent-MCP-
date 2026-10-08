"""Pydantic schemas for Hospital."""

from pydantic import BaseModel, ConfigDict, Field


class HospitalBase(BaseModel):
    name: str = Field(..., max_length=150, examples=["City General Hospital"])
    latitude: float = Field(..., ge=-90.0, le=90.0, examples=[28.6139])
    longitude: float = Field(..., ge=-180.0, le=180.0, examples=[77.2090])
    address: str = Field(..., max_length=255, examples=["12 Medical Square, Central District"])


class HospitalCreate(HospitalBase):
    pass


class HospitalResponse(HospitalBase):
    hospital_id: int

    model_config = ConfigDict(from_attributes=True)
