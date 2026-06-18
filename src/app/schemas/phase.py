"""Phase schemas — Pydantic DTOs for validation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.constants.limits import MAX_GOAL_DESCRIPTION_LENGTH, MAX_PHASE_TITLE_LENGTH


class PhaseCreateData(BaseModel):
    """Input for creating a phase."""

    title: str = Field(..., min_length=1, max_length=MAX_PHASE_TITLE_LENGTH)
    description: Optional[str] = Field(None, max_length=MAX_GOAL_DESCRIPTION_LENGTH)


class PhaseResponse(BaseModel):
    """Serialized phase for API responses."""

    id: str
    goal_id: str
    user_id: str
    title: str
    description: Optional[str]
    order: int
    status: str
    unlocked_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
