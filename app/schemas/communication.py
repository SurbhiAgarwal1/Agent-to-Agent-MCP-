"""Pydantic schemas for the Communication Agent and interactive outreach."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CommunicationOutreachCreate(BaseModel):
    """Payload to initiate an interactive communication outreach session."""

    request_id: int = Field(..., description="ID of the blood request")
    hospital_id: Optional[int] = Field(default=None, description="Requesting hospital ID")
    urgency: Optional[str] = Field(default="MEDIUM", description="Urgency: LOW, MEDIUM, HIGH, CRITICAL")
    fulfillment_plan: Optional[Dict[str, Any]] = Field(default=None, description="Fulfillment plan details")
    hospital_name: Optional[str] = Field(default=None, description="Hospital display name")
    custom_message: Optional[str] = Field(default=None, description="Optional custom notes or instructions")


class CommunicationResponseInput(BaseModel):
    """Payload from a donor, blood bank, or hospital responding to an outreach message."""

    session_id: str = Field(..., description="Active communication session UUID")
    recipient_type: str = Field(..., description="Recipient type: DONOR, BLOOD_BANK, HOSPITAL")
    recipient_id: int = Field(..., description="Recipient unique identifier")
    response_status: str = Field(..., description="Response status: CONFIRMED, DECLINED, DELAYED, EN_ROUTE")
    response_notes: Optional[str] = Field(default=None, description="Optional notes or reasons")
    eta_minutes: Optional[int] = Field(default=None, description="Estimated arrival time in minutes if confirming")


class CommunicationMessageItem(BaseModel):
    """Schema representing an individual dispatched message and response status."""

    message_id: str
    recipient_type: str
    recipient_id: int
    channel: str
    title: str
    body: str
    units_requested: int
    delivery_status: str
    response_status: str
    response_notes: Optional[str] = None
    eta_minutes: Optional[int] = None
    sent_at: datetime
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CommunicationSessionResponse(BaseModel):
    """Detailed response schema for a communication session."""

    session_id: str
    request_id: int
    hospital_id: Optional[int] = None
    urgency: str
    status: str
    total_targets: int
    confirmed_count: int
    declined_count: int
    pending_count: int
    sla_minutes: int
    sla_expires_at: Optional[datetime] = None
    is_escalated: bool
    escalation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[CommunicationMessageItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EscalationTriggerResponse(BaseModel):
    """Schema returned when an SLA escalation evaluation or manual trigger occurs."""

    session_id: str
    request_id: int
    escalated: bool
    escalation_reason: Optional[str] = None
    unresponsive_recipients: List[Dict[str, Any]] = Field(default_factory=list)
    escalated_at: Optional[datetime] = None


class CommunicationStatsResponse(BaseModel):
    """Aggregated metrics and KPIs for the Communication Agent subsystem."""

    total_sessions: int
    active_sessions: int
    fully_confirmed_sessions: int
    escalated_sessions: int
    total_messages_dispatched: int
    confirmed_responses: int
    declined_responses: int
    pending_responses: int
    confirmation_rate_pct: float
    escalation_rate_pct: float
