"""Pydantic schemas for the Calling Agent voice dispatch and IVR interactions."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class VoiceCallCreate(BaseModel):
    """Payload to dispatch an automated emergency voice call."""

    request_id: int = Field(..., description="ID of the blood request")
    recipient_type: str = Field(default="DONOR", description="Recipient classification: DONOR, BLOOD_BANK, HOSPITAL")
    recipient_id: int = Field(..., description="Recipient identifier")
    recipient_phone: str = Field(..., description="E.164 format phone number or standard mobile number")
    recipient_name: Optional[str] = Field(default=None, description="Name of the recipient")
    hospital_id: Optional[int] = Field(default=None, description="Hospital identifier")
    hospital_name: Optional[str] = Field(default=None, description="Requesting hospital name")
    blood_group: Optional[str] = Field(default="O+", description="Required blood group")
    units_required: Optional[int] = Field(default=1, description="Units required")
    urgency: Optional[str] = Field(default="CRITICAL", description="Urgency: CRITICAL, HIGH, MEDIUM, LOW")
    custom_prompt: Optional[str] = Field(default=None, description="Custom voice prompt to synthesize")


class VoiceCallWebhookInput(BaseModel):
    """Payload received from telephony carrier / IVR touch-tone callback."""

    call_id: str = Field(..., description="Unique call session UUID")
    call_status: str = Field(default="COMPLETED", description="Status: RINGING, IN_PROGRESS, COMPLETED, NO_ANSWER, BUSY, FAILED")
    digits_pressed: Optional[str] = Field(default=None, description="DTMF touchtone pressed: 1=Confirm, 2=Decline, 3=Delay")
    duration_seconds: Optional[int] = Field(default=0, description="Call duration in seconds")


class CallSessionResponse(BaseModel):
    """Response schema representing a voice call session."""

    call_id: str
    request_id: int
    hospital_id: Optional[int] = None
    recipient_type: str
    recipient_id: int
    recipient_phone: str
    recipient_name: Optional[str] = None
    status: str
    duration_seconds: int
    dtmf_input: Optional[str] = None
    response_status: str
    tts_script: str
    telephony_provider: str
    initiated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CallingStatsResponse(BaseModel):
    """Aggregated telephony performance metrics for the Calling Agent."""

    total_calls: int
    completed_calls: int
    confirmed_count: int
    declined_count: int
    no_answer_count: int
    avg_duration_seconds: float
    voice_confirmation_rate_pct: float
