"""Pydantic schemas for authentication and tokens (Part 15)."""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """Registration request payload."""
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6, description="Password with min 6 characters")
    role: str = Field(default="HOSPITAL_STAFF", description="Role: HOSPITAL_STAFF, BLOOD_BANK_STAFF, ADMIN")


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
