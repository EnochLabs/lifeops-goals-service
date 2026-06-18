"""
Strawberry GraphQL input types for the Goals Service.

These wrap the Pydantic DTOs in schemas/ so GraphQL validation
produces the same error messages as direct service-layer validation.
"""

from datetime import datetime
from typing import List, Optional

import strawberry

from app.graphql.enums import (
    ActionTypeEnum,
    GoalCategoryEnum,
    GoalHorizonEnum,
    PriorityEnum,
    RecurrencePatternEnum,
)

# ── Goal Inputs ──────────────────────────────────────────────────────────────


@strawberry.input
class CreateGoalInput:
    """Input for the createGoal mutation."""

    title: str
    category: GoalCategoryEnum = GoalCategoryEnum.CUSTOM
    horizon: GoalHorizonEnum = GoalHorizonEnum.MEDIUM
    priority: PriorityEnum = PriorityEnum.MEDIUM
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    # Numeric progress fields (optional — only for measurable goals)
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    unit: Optional[str] = None


@strawberry.input
class UpdateGoalInput:
    """Input for the updateGoal mutation — all fields optional."""

    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[GoalCategoryEnum] = None
    horizon: Optional[GoalHorizonEnum] = None
    priority: Optional[PriorityEnum] = None
    target_date: Optional[datetime] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None


# ── Phase Inputs ─────────────────────────────────────────────────────────────


@strawberry.input
class CreatePhaseInput:
    """Input for the createPhase mutation."""

    goal_id: strawberry.ID
    title: str
    description: Optional[str] = None


@strawberry.input
class ReorderPhasesInput:
    """Ordered list of phase IDs for the reorderPhases mutation."""

    goal_id: strawberry.ID
    ordered_phase_ids: List[strawberry.ID]


# ── Action Inputs ────────────────────────────────────────────────────────────


@strawberry.input
class RecurrenceInput:
    """Recurrence configuration for HABIT-type actions."""

    pattern: RecurrencePatternEnum = RecurrencePatternEnum.DAILY
    days_of_week: Optional[List[int]] = None


@strawberry.input
class CreateActionInput:
    """Input for the createAction mutation."""

    phase_id: strawberry.ID
    goal_id: strawberry.ID
    title: str
    action_type: ActionTypeEnum = ActionTypeEnum.TASK
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    contributes_value: Optional[float] = None
    recurrence: Optional[RecurrenceInput] = None


@strawberry.input
class CompleteActionInput:
    """Input for the completeAction mutation."""

    action_id: strawberry.ID
    completion_note: Optional[str] = None


@strawberry.input
class SkipActionInput:
    """Input for the skipAction mutation."""

    action_id: strawberry.ID
    reason: Optional[str] = None


@strawberry.input
class RescheduleActionInput:
    """Input for the rescheduleAction mutation."""

    action_id: strawberry.ID
    new_due_date: datetime
    reason: Optional[str] = None
