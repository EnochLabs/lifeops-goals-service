"""
Phase — an ordered stage within a Goal.

Phases unlock sequentially: the next phase becomes ACTIVE only after the
current one is COMPLETED (unless the user explicitly skips).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import beanie
from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.constants.goals import PhaseStatus


class Phase(Document):
    # ── Parent references ──────────────────────────────────────
    goal_id: beanie.PydanticObjectId
    user_id: beanie.PydanticObjectId

    # ── Core ───────────────────────────────────────────────────
    title: str = Field(..., max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    order: int = Field(..., ge=0, description="Zero-based display order within the goal")
    status: str = Field(default=PhaseStatus.LOCKED)

    # ── Dates ──────────────────────────────────────────────────
    unlocked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # ── Metadata ───────────────────────────────────────────────
    note: Optional[str] = Field(None, max_length=5000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "phases"
        indexes = [
            IndexModel([("goal_id", ASCENDING), ("order", ASCENDING)]),
            IndexModel([("goal_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
        ]
