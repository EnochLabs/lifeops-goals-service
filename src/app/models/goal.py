"""
Goal — the top-level aggregate in the Goals Service.

Each Goal belongs to one user, has 1-N Phases, and tracks a momentum score.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import beanie
from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.constants.goals import (
    DecompositionState,
    GoalCategory,
    GoalHorizon,
    GoalStatus,
    Priority,
)


class Goal(Document):
    # ── Ownership ──────────────────────────────────────────────
    user_id: beanie.PydanticObjectId = Field(..., description="Owner user ID")

    # ── Core ───────────────────────────────────────────────────
    title: str = Field(..., max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    category: str = Field(default=GoalCategory.CUSTOM)
    horizon: str = Field(default=GoalHorizon.MEDIUM)
    priority: int = Field(default=Priority.MEDIUM)
    status: str = Field(default=GoalStatus.DRAFT)

    # ── Dates ──────────────────────────────────────────────────
    target_date: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None

    # ── Momentum ───────────────────────────────────────────────
    momentum_score: Optional[float] = Field(None, ge=0, le=100)
    last_momentum_calc: Optional[datetime] = None

    # ── AI Decomposition ───────────────────────────────────────
    decomposition_state: str = Field(default=DecompositionState.NONE)
    decomposition_error: Optional[str] = None

    # ── Metadata ───────────────────────────────────────────────
    tags: list[str] = Field(default_factory=list)
    note: Optional[str] = Field(None, max_length=5000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "goals"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("category", ASCENDING)]),
            IndexModel([("status", ASCENDING), ("momentum_score", ASCENDING)]),
            IndexModel([("decomposition_state", ASCENDING)]),
        ]
