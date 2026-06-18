"""
GraphQL queries for the Goals Service.

Converters (_goal_to_type, _phase_to_type, _action_to_type) live here
and are imported by mutations to avoid duplication.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

import strawberry
from strawberry.types import Info

from app.core.exceptions.base import GoalNotFoundError, UnauthenticatedError
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
from app.graphql.types import (
    ActionGQLType,
    GoalGQLType,
    PhaseGQLType,
    RecurrenceGQLType,
)
from app.repositories.action_repository import ActionRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.phase_repository import PhaseRepository

# ── Converter helpers ────────────────────────────────────────────────────────


def _recurrence_to_type(rec: Any) -> RecurrenceGQLType:
    return RecurrenceGQLType(
        pattern=RecurrencePatternEnum(rec.pattern),
        days_of_week=list(rec.days_of_week or []),
        generation_count=rec.generation_count,
    )


def _action_to_type(action: Any) -> ActionGQLType:
    return ActionGQLType(
        id=str(action.id),
        goal_id=str(action.goal_id),
        phase_id=str(action.phase_id),
        user_id=str(action.user_id),
        parent_action_id=str(action.parent_action_id) if action.parent_action_id else None,
        title=action.title,
        description=action.description,
        action_type=ActionTypeEnum(action.action_type),
        status=ActionStatusEnum(action.status),
        order=action.order,
        due_date=action.due_date,
        next_due=action.next_due,
        estimated_minutes=action.estimated_minutes,
        contributes_value=action.contributes_value,
        recurrence=_recurrence_to_type(action.recurrence) if action.recurrence else None,
        completed_at=action.completed_at,
        completion_note=action.completion_note,
        tags=list(action.tags or []),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


def _phase_to_type(phase: Any, actions: Optional[List[Any]] = None) -> PhaseGQLType:
    action_types = [_action_to_type(a) for a in actions] if actions is not None else None
    return PhaseGQLType(
        id=str(phase.id),
        goal_id=str(phase.goal_id),
        user_id=str(phase.user_id),
        title=phase.title,
        description=phase.description,
        order=phase.order,
        status=PhaseStatusEnum(phase.status),
        unlocked_at=phase.unlocked_at,
        completed_at=phase.completed_at,
        note=phase.note,
        created_at=phase.created_at,
        updated_at=phase.updated_at,
        actions=action_types,
    )


def _compute_progress_percent(goal: Any) -> Optional[float]:
    """Return current_value / target_value * 100, null-safe."""
    if goal.target_value and goal.target_value > 0 and goal.current_value is not None:
        raw = (goal.current_value / goal.target_value) * 100
        return round(float(raw), 2)
    return None


def _goal_to_type(goal: Any, phases: Optional[List[Any]] = None) -> GoalGQLType:
    """Convert a Goal document to GoalGQLType.

    phases may be raw Phase documents (converted via _phase_to_type)
    or already-converted PhaseGQLType objects (when the caller has
    pre-loaded actions for the single-round-trip pattern in GS-2.6).
    """
    phase_types: Optional[List[PhaseGQLType]] = None
    if phases is not None:
        phase_types = [p if isinstance(p, PhaseGQLType) else _phase_to_type(p) for p in phases]
    return GoalGQLType(
        id=str(goal.id),
        user_id=str(goal.user_id),
        title=goal.title,
        description=goal.description,
        category=GoalCategoryEnum(goal.category),
        horizon=GoalHorizonEnum(goal.horizon),
        priority=PriorityEnum(goal.priority),
        status=GoalStatusEnum(goal.status),
        target_date=goal.target_date,
        activated_at=goal.activated_at,
        completed_at=goal.completed_at,
        paused_at=goal.paused_at,
        target_value=goal.target_value,
        current_value=goal.current_value,
        unit=goal.unit,
        progress_percent=_compute_progress_percent(goal),
        momentum_score=goal.momentum_score,
        last_momentum_calc=goal.last_momentum_calc,
        decomposition_state=DecompositionStateEnum(goal.decomposition_state),
        decomposition_error=goal.decomposition_error,
        tags=list(goal.tags or []),
        note=goal.note,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        phases=phase_types,
    )


# ── Query class ──────────────────────────────────────────────────────────────


@strawberry.type
class Query:
    @strawberry.field(description="List all goals for the authenticated user.")
    async def goals(
        self,
        info: Info,
        status: Optional[GoalStatusEnum] = None,
    ) -> List[GoalGQLType]:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from beanie import PydanticObjectId

        from app.models.goal import Goal

        query = Goal.find(Goal.user_id == PydanticObjectId(user.user_id))
        if status is not None:
            query = query.find(Goal.status == status.value)

        goals = await query.sort("-created_at").to_list()
        return [_goal_to_type(g) for g in goals]

    @strawberry.field(
        description=(
            "Retrieve a single goal by ID. "
            "Returns a not-found error if the goal doesn't exist or isn't owned by the caller "
            "(never leaks existence to other users)."
        )
    )
    async def goal(
        self,
        info: Info,
        goal_id: strawberry.ID,
    ) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        goal = await GoalRepository.get_by_id(str(goal_id))
        if not goal:
            raise GoalNotFoundError(str(goal_id))

        from beanie import PydanticObjectId

        # Ownership check — 404 not 403 (don't leak existence)
        if goal.user_id != PydanticObjectId(user.user_id):
            raise GoalNotFoundError(str(goal_id))

        phases = await PhaseRepository.list_for_goal(str(goal.id))
        # Eagerly load actions for each phase — single logical round-trip per
        # GS-2.6: Goal.phases and Phase.actions resolve in one query.
        phases_with_actions = []
        for phase in phases:
            actions = await ActionRepository.list_for_phase(str(phase.id))
            phases_with_actions.append((phase, actions))
        phase_types = [_phase_to_type(p, acts) for p, acts in phases_with_actions]
        return _goal_to_type(goal, phase_types)

    @strawberry.field(
        description=(
            "All pending / in-progress actions due today or overdue, "
            "across all active goals for the authenticated user."
        )
    )
    async def todays_actions(self, info: Info) -> List[ActionGQLType]:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.action_service import list_todays_actions

        actions = await list_todays_actions(user.user_id, datetime.utcnow())
        return [_action_to_type(a) for a in actions]
