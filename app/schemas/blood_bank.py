"""Pydantic schemas for BloodBank."""

from pydantic import BaseModel, ConfigDict, Field


class BloodBankBase(BaseModel):
    name: str = Field(..., max_length=150, examples=["Central Red Cross Blood Bank"])
    latitude: float = Field(..., ge=-90.0, le=90.0, examples=[28.6180])
    longitude: float = Field(..., ge=-180.0, le=180.0, examples=[77.2150])
    address: str = Field(..., max_length=255, examples=["44 Healthcare Avenue, North Zone"])


class BloodBankCreate(BloodBankBase):
    pass


class BloodBankResponse(BloodBankBase):
    bank_id: int

    model_config = ConfigDict(from_attributes=True)
