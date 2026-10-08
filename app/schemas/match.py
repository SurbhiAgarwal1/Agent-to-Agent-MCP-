"""Pydantic schemas for Match."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import MatchSourceType, MatchStatus


class MatchBase(BaseModel):
    request_id: int
    source_type: MatchSourceType
    source_id: int
    distance_km: Optional[float] = Field(default=None, ge=0.0)
    estimated_time: Optional[str] = None
    priority_score: Optional[float] = None
    status: MatchStatus = MatchStatus.PROPOSED


class MatchCreate(MatchBase):
    pass


class MatchResponse(MatchBase):
    match_id: int

    model_config = ConfigDict(from_attributes=True)
