"""
Goal schemas — Pydantic DTOs for validation.

These are used by the service layer, NOT by GraphQL.
GraphQL has its own Strawberry input types that wrap these.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.constants.limits import (
    MAX_GOAL_DESCRIPTION_LENGTH,
    MAX_GOAL_TITLE_LENGTH,
)


class GoalCreateData(BaseModel):
    """Input for creating a goal."""

    title: str = Field(..., min_length=1, max_length=MAX_GOAL_TITLE_LENGTH)
    description: Optional[str] = Field(None, max_length=MAX_GOAL_DESCRIPTION_LENGTH)
    category: str
    horizon: str
    priority: int = Field(default=2, ge=1, le=4)
    target_date: Optional[datetime] = None
    target_value: Optional[float] = Field(None, ge=0)
    current_value: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=50)


class GoalUpdateData(BaseModel):
    """Input for updating a goal."""

    title: Optional[str] = Field(None, min_length=1, max_length=MAX_GOAL_TITLE_LENGTH)
    description: Optional[str] = Field(None, max_length=MAX_GOAL_DESCRIPTION_LENGTH)
    category: Optional[str] = None
    horizon: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=4)
    target_date: Optional[datetime] = None
    target_value: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=50)
    note: Optional[str] = None


class GoalResponse(BaseModel):
    """Serialized goal for API responses."""

    id: str
    user_id: str
    title: str
    description: Optional[str]
    category: str
    horizon: str
    priority: int
    status: str
    target_date: Optional[datetime]
    target_value: Optional[float]
    current_value: Optional[float]
    unit: Optional[str]
    momentum_score: Optional[float]
    progress_percent: Optional[float]
    decomposition_state: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
