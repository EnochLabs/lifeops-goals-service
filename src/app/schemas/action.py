"""Action schemas — Pydantic DTOs for validation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.constants.limits import (
    MAX_ACTION_TITLE_LENGTH,
    MAX_GOAL_DESCRIPTION_LENGTH,
    MAX_NOTE_LENGTH,
)


class RecurrenceData(BaseModel):
    """Recurrence configuration for habit actions."""

    pattern: str
    days_of_week: Optional[list[int]] = Field(default_factory=list)


class ActionCreateData(BaseModel):
    """Input for creating an action."""

    title: str = Field(..., min_length=1, max_length=MAX_ACTION_TITLE_LENGTH)
    action_type: str
    description: Optional[str] = Field(None, max_length=MAX_GOAL_DESCRIPTION_LENGTH)
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)
    contributes_value: Optional[float] = Field(None, ge=0)
    recurrence: Optional[RecurrenceData] = None


class ActionUpdateData(BaseModel):
    """Input for updating an action."""

    title: Optional[str] = Field(None, min_length=1, max_length=MAX_ACTION_TITLE_LENGTH)
    description: Optional[str] = Field(None, max_length=MAX_GOAL_DESCRIPTION_LENGTH)
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)


class ActionCompleteData(BaseModel):
    """Input for completing an action."""

    completion_note: Optional[str] = Field(None, max_length=MAX_NOTE_LENGTH)


class ActionSkipData(BaseModel):
    """Input for skipping an action."""

    reason: Optional[str] = Field(None, max_length=MAX_NOTE_LENGTH)


class ActionRescheduleData(BaseModel):
    """Input for rescheduling an action."""

    new_due_date: datetime
    reason: Optional[str] = Field(None, max_length=MAX_NOTE_LENGTH)


class ActionResponse(BaseModel):
    """Serialized action for API responses."""

    id: str
    goal_id: str
    phase_id: str
    user_id: str
    title: str
    action_type: str
    description: Optional[str]
    status: str
    due_date: Optional[datetime]
    next_due: Optional[datetime]
    estimated_minutes: Optional[int]
    contributes_value: Optional[float]
    completed_at: Optional[datetime]
    completion_note: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
