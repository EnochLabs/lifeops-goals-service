"""
Strawberry GraphQL object types for the Goals Service.

Naming: GoalGQLType / PhaseGQLType / ActionGQLType
(avoids import collision with app.constants.goals.ActionType).
"""

from datetime import datetime
from typing import List, Optional

import strawberry

from app.graphql.enums import (
    ActionStatusEnum,
    ActionTypeEnum,
    DecompositionStateEnum,
    GoalCategoryEnum,
    GoalHorizonEnum,
    GoalStatusEnum,
    PhaseStatusEnum,
    PriorityEnum,
    RecurrencePatternEnum,
)


@strawberry.type
class RecurrenceGQLType:
    """Recurrence configuration embedded in HABIT actions."""

    pattern: RecurrencePatternEnum
    days_of_week: List[int]
    generation_count: int


@strawberry.type
class ActionGQLType:
    """An atomic unit of work within a Phase."""

    id: strawberry.ID
    goal_id: strawberry.ID
    phase_id: strawberry.ID
    user_id: strawberry.ID
    parent_action_id: Optional[strawberry.ID]

    title: str
    description: Optional[str]
    action_type: ActionTypeEnum
    status: ActionStatusEnum
    order: int

    due_date: Optional[datetime]
    next_due: Optional[datetime]
    estimated_minutes: Optional[int]
    contributes_value: Optional[float]
    recurrence: Optional[RecurrenceGQLType]

    completed_at: Optional[datetime]
    completion_note: Optional[str]
    tags: List[str]

    created_at: datetime
    updated_at: datetime


@strawberry.type
class PhaseGQLType:
    """An ordered stage within a Goal — phases unlock sequentially."""

    id: strawberry.ID
    goal_id: strawberry.ID
    user_id: strawberry.ID

    title: str
    description: Optional[str]
    order: int
    status: PhaseStatusEnum

    unlocked_at: Optional[datetime]
    completed_at: Optional[datetime]
    note: Optional[str]

    created_at: datetime
    updated_at: datetime

    # Resolved lazily — populated by the actions field resolver
    actions: Optional[List[ActionGQLType]] = None


@strawberry.type
class GoalGQLType:
    """Top-level goal aggregate — tracks lifecycle, momentum, and progress."""

    id: strawberry.ID
    user_id: strawberry.ID

    title: str
    description: Optional[str]
    category: GoalCategoryEnum
    horizon: GoalHorizonEnum
    priority: PriorityEnum
    status: GoalStatusEnum

    target_date: Optional[datetime]
    activated_at: Optional[datetime]
    completed_at: Optional[datetime]
    paused_at: Optional[datetime]

    # Numeric progress (optional — toggled on by the user during creation)
    target_value: Optional[float]
    current_value: Optional[float]
    unit: Optional[str]
    progress_percent: Optional[float]  # computed: current_value / target_value * 100

    # Momentum (0–100, computed by background worker)
    momentum_score: Optional[float]
    last_momentum_calc: Optional[datetime]

    # AI decomposition lifecycle
    decomposition_state: DecompositionStateEnum
    decomposition_error: Optional[str]

    tags: List[str]
    note: Optional[str]

    created_at: datetime
    updated_at: datetime

    # Resolved lazily
    phases: Optional[List[PhaseGQLType]] = None
