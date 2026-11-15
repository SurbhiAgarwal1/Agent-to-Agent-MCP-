"""Pydantic schemas for authentication and tokens (Part 15)."""

from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """Registration request payload for public self-service registration."""
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6, description="Password with min 6 characters")
    role: Optional[str] = Field(default="HOSPITAL_STAFF", description="Role: HOSPITAL_STAFF or ADMIN for self-registration")
    admin_signup_key: Optional[str] = Field(default=None, description="Required only when self-registering an ADMIN account")
    # Role-specific profile (donor / blood bank / hospital)
    name: Optional[str] = Field(default=None, max_length=120)
    age: Optional[int] = Field(default=None, ge=18, le=65)
    blood_group: Optional[str] = Field(default=None, max_length=3)
    city: Optional[str] = Field(default=None, max_length=80)
    district: Optional[str] = Field(default=None, max_length=80)
    state: Optional[str] = Field(default=None, max_length=80)
    pin_code: Optional[str] = Field(default=None, max_length=8)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    organization_name: Optional[str] = Field(default=None, max_length=150)
    address: Optional[str] = Field(default=None, max_length=255)
    contact_number: Optional[str] = Field(default=None, max_length=32)
    initial_stock: Optional[dict[str, int]] = None


class UserCreate(BaseModel):
    """User creation payload for admin user management endpoint."""
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6, description="Password with min 6 characters")
    role: str = Field(..., description="Role: USER, HOSPITAL_STAFF, BLOOD_BANK_STAFF, ADMIN")


class UserLogin(BaseModel):
    """Login credentials payload."""
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class Token(BaseModel):
    """Bearer token response."""
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int


class UserResponse(BaseModel):
    """User profile response."""
    id: int
    email: str
    role: str
    hospital_ids: List[int] = Field(default_factory=list)
    bank_ids: List[int] = Field(default_factory=list)


class MembershipGrant(BaseModel):
    organization_id: int = Field(gt=0)
    membership_type: str = Field(default="STAFF", min_length=1, max_length=40)
