"""Pydantic schemas for BloodInventory."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import BloodGroup


class BloodInventoryBase(BaseModel):
    bank_id: int
    blood_group: BloodGroup
    units_available: int = Field(default=0, ge=0)
    expiry_date: Optional[date] = None


class BloodInventoryCreate(BloodInventoryBase):
    pass


class BloodInventoryResponse(BloodInventoryBase):
    inventory_id: int

    model_config = ConfigDict(from_attributes=True)
