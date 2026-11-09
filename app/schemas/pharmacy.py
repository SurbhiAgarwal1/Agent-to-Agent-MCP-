"""Schemas for pharmacies, medicines, substitutes, and delivery orders.

Designed according to Apollo / Netmeds / Truemeds / Sanvivo architecture.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PharmacyBase(BaseModel):
    name: str = Field(..., description="Pharmacy name", examples=["Apollo Pharmacy - Sector 18"])
    license_number: str = Field(..., description="Pharmacy Drug License", examples=["DL-DEL-102938"])
    address: str = Field(..., description="Physical storefront address")
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    contact_phone: str = Field(..., description="Primary phone number")
    contact_email: Optional[str] = None
    delivery_radius_km: float = Field(default=10.0, description="Delivery coverage in km")
    is_active: bool = True


class PharmacyCreate(PharmacyBase):
    pass


class PharmacyResponse(PharmacyBase):
    pharmacy_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MedicineBase(BaseModel):
    brand_name: str = Field(..., description="Brand name of the medication", examples=["Dolo 650"])
    generic_name: str = Field(..., description="Active chemical salt/composition", examples=["Paracetamol 650mg"])
    manufacturer: str = Field(..., description="Pharmaceutical company", examples=["Micro Labs Ltd"])
    dosage_form: str = Field(..., description="Tablet, Syrup, Capsule, etc.", examples=["Tablet"])
    strength: str = Field(..., description="Dosage strength", examples=["650mg"])
    rx_required: bool = Field(default=False, description="Whether doctor prescription is required")
    description: Optional[str] = None


class MedicineCreate(MedicineBase):
    pass


class MedicineResponse(MedicineBase):
    medicine_id: int
    model_config = ConfigDict(from_attributes=True)


class MedicineSubstitute(BaseModel):
    """Truemeds-style cost-effective equivalent/substitute sharing the active salt."""
    medicine_id: int
    brand_name: str
    generic_name: str
    manufacturer: str
    dosage_form: str
    strength: str
    unit_price: float
    available_units: int
    savings_percentage: Optional[float] = 0.0


class StockItemResponse(BaseModel):
    inventory_id: int
    pharmacy_id: int
    pharmacy_name: str
    pharmacy_address: str
    distance_km: Optional[float] = None
    medicine_id: int
    brand_name: str
    generic_name: str
    unit_price: float
    units_available: int
    batch_number: str
    expiry_date: datetime
    model_config = ConfigDict(from_attributes=True)


class OrderItemInput(BaseModel):
    medicine_id: int
    quantity: int = Field(..., gt=0)
    allow_substitute: bool = Field(default=True, description="Allow Truemeds-style generic substitute if exact brand out of stock")


class MedicineOrderCreate(BaseModel):
    delivery_address: str
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    urgency: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")
    hospital_id: Optional[int] = None
    items: List[OrderItemInput]


class OrderItemResponse(BaseModel):
    item_id: int
    medicine_id: int
    brand_name: str
    generic_name: str
    quantity: int
    unit_price: float
    is_substitute: bool
    original_medicine_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class MedicineOrderResponse(BaseModel):
    order_id: int
    status: str
    urgency: str
    delivery_address: str
    pharmacy_id: Optional[int] = None
    pharmacy_name: Optional[str] = None
    estimated_eta_minutes: Optional[int] = None
    total_amount: float
    items: List[OrderItemResponse] = []
    created_at: datetime
    delivered_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
