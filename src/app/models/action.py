"""
Action — the atomic unit of work within a Phase.

Can be a one-off Task, a recurring Habit, a Milestone, a Reflection prompt,
a Learning item, or a Challenge.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import beanie
from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.constants.goals import ActionStatus, ActionType, RecurrencePattern


class Recurrence(BaseModel):
    """Recurrence config — only present for HABIT actions.

    Plain embedded value object, not a top-level document. `beanie.UnionDoc`
    is for polymorphic top-level collections and cannot be used as a nested
    field type — embedding it previously broke Pydantic schema generation
    for the whole `Action` model at import time.
    """

    pattern: str = Field(default=RecurrencePattern.DAILY)
    # For CUSTOM pattern: e.g. [0, 2, 4] = Mon, Wed, Fri (weekday indices)
    days_of_week: List[int] = Field(default_factory=list)
    # How many times this habit has been generated
    generation_count: int = 0


class Action(Document):
    # ── Parent references ──────────────────────────────────────
    goal_id: beanie.PydanticObjectId
    phase_id: beanie.PydanticObjectId
    user_id: beanie.PydanticObjectId

    # For recurring actions: links back to the "template" action
    parent_action_id: Optional[beanie.PydanticObjectId] = None

    # ── Core ───────────────────────────────────────────────────
    title: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    action_type: str = Field(default=ActionType.TASK)
    status: str = Field(default=ActionStatus.PENDING)
    order: int = Field(default=0, ge=0)

    # ── Scheduling ─────────────────────────────────────────────
    due_date: Optional[datetime] = None
    next_due: Optional[datetime] = None  # for HABIT actions
    recurrence: Optional[Recurrence] = None  # only for HABIT actions
    estimated_minutes: Optional[int] = Field(None, ge=1)
    contributes_value: Optional[float] = Field(
        None, ge=0, description="When completed, increments parent goal's current_value"
    )

    # ── Completion ─────────────────────────────────────────────
    completed_at: Optional[datetime] = None
    completion_note: Optional[str] = Field(None, max_length=2000)

    # ── Metadata ───────────────────────────────────────────────
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "actions"
        indexes = [
            IndexModel([("goal_id", ASCENDING), ("phase_id", ASCENDING), ("order", ASCENDING)]),
            IndexModel([("goal_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("goal_id", ASCENDING), ("action_type", ASCENDING)]),
            # Worker index: find overdue habits fast
            IndexModel(
                [("action_type", ASCENDING), ("status", ASCENDING), ("next_due", ASCENDING)]
            ),
            IndexModel([("completed_at", DESCENDING)]),
        ]
