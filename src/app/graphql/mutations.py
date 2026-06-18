"""
GraphQL mutations for the Goals Service.

Thin resolvers — business logic lives in the services layer.
Each mutation delegates to a service function and converts the result
to a GQL type using the shared converters from queries.py.
"""

from __future__ import annotations

from typing import List

import strawberry
from strawberry.types import Info

from app.core.exceptions.base import UnauthenticatedError
from app.graphql.inputs import (
    CompleteActionInput,
    CreateActionInput,
    CreateGoalInput,
    CreatePhaseInput,
    ReorderPhasesInput,
    RescheduleActionInput,
    SkipActionInput,
    UpdateGoalInput,
)
from app.graphql.queries import _action_to_type, _goal_to_type, _phase_to_type
from app.graphql.types import ActionGQLType, GoalGQLType, PhaseGQLType

# ── Goal mutations ───────────────────────────────────────────────────────────


@strawberry.type
class Mutation:

    # ── createGoal ───────────────────────────────────────────────
    @strawberry.mutation(description="Create a new goal in DRAFT status.")
    async def create_goal(self, info: Info, input: CreateGoalInput) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import create_goal

        goal = await create_goal(
            user_id=user.user_id,
            title=input.title,
            description=input.description,
            category=input.category.value,
            horizon=input.horizon.value,
            priority=input.priority.value,
            target_date=input.target_date,
            plan_tier=user.plan,
            target_value=input.target_value,
            current_value=input.current_value,
            unit=input.unit,
        )
        return _goal_to_type(goal)

    # ── updateGoal ───────────────────────────────────────────────
    @strawberry.mutation(description="Update mutable fields on a goal.")
    async def update_goal(
        self, info: Info, goal_id: strawberry.ID, input: UpdateGoalInput
    ) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from beanie import PydanticObjectId

        from app.core.exceptions.base import GoalNotFoundError
        from app.repositories.goal_repository import GoalRepository

        goal = await GoalRepository.get_by_id(str(goal_id))
        if not goal or goal.user_id != PydanticObjectId(user.user_id):
            raise GoalNotFoundError(str(goal_id))

        from datetime import datetime

        if input.title is not None:
            goal.title = input.title
        if input.description is not None:
            goal.description = input.description
        if input.category is not None:
            goal.category = input.category.value
        if input.horizon is not None:
            goal.horizon = input.horizon.value
        if input.priority is not None:
            goal.priority = input.priority.value
        if input.target_date is not None:
            goal.target_date = input.target_date
        if input.target_value is not None:
            goal.target_value = input.target_value
        if input.unit is not None:
            goal.unit = input.unit
        if input.note is not None:
            goal.note = input.note

        goal.updated_at = datetime.utcnow()
        await goal.save()

        return _goal_to_type(goal)

    # ── activateGoal ─────────────────────────────────────────────
    @strawberry.mutation(description="Move a DRAFT goal to ACTIVE status.")
    async def activate_goal(self, info: Info, goal_id: strawberry.ID) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import activate_goal

        goal = await activate_goal(user.user_id, str(goal_id))
        return _goal_to_type(goal)

    # ── pauseGoal ────────────────────────────────────────────────
    @strawberry.mutation(description="Pause an active goal (freezes momentum tracking).")
    async def pause_goal(self, info: Info, goal_id: strawberry.ID) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import pause_goal

        goal = await pause_goal(user.user_id, str(goal_id))
        return _goal_to_type(goal)

    # ── resumeGoal ───────────────────────────────────────────────
    @strawberry.mutation(description="Resume a paused goal.")
    async def resume_goal(self, info: Info, goal_id: strawberry.ID) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import resume_goal

        goal = await resume_goal(user.user_id, str(goal_id))
        return _goal_to_type(goal)

    # ── completeGoal ─────────────────────────────────────────────
    @strawberry.mutation(description="Mark a goal as completed.")
    async def complete_goal(self, info: Info, goal_id: strawberry.ID) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import complete_goal

        goal = await complete_goal(user.user_id, str(goal_id))
        return _goal_to_type(goal)

    # ── abandonGoal ──────────────────────────────────────────────
    @strawberry.mutation(
        description=(
            "Archive a goal as abandoned. "
            "Data is preserved — abandoning is never a deletion. "
            "No shame: life changes, priorities shift."
        )
    )
    async def abandon_goal(
        self,
        info: Info,
        goal_id: strawberry.ID,
        reason: str | None = None,
    ) -> GoalGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.goal_service import abandon_goal

        goal = await abandon_goal(user.user_id, str(goal_id), reason)
        return _goal_to_type(goal)

    # ── Phase mutations ──────────────────────────────────────────

    @strawberry.mutation(
        description=(
            "Create a phase within a goal. "
            "The first phase is ACTIVE immediately; subsequent phases are LOCKED "
            "until the previous one completes."
        )
    )
    async def create_phase(self, info: Info, input: CreatePhaseInput) -> PhaseGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.phase_service import create_phase

        phase = await create_phase(
            user_id=user.user_id,
            goal_id=str(input.goal_id),
            title=input.title,
            description=input.description,
        )
        return _phase_to_type(phase)

    @strawberry.mutation(description="Complete the current active phase, unlocking the next one.")
    async def complete_phase(self, info: Info, phase_id: strawberry.ID) -> PhaseGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.phase_service import complete_phase

        phase = await complete_phase(user.user_id, str(phase_id))
        return _phase_to_type(phase)

    @strawberry.mutation(description="Skip a phase, unlocking the next one without completing it.")
    async def skip_phase(
        self,
        info: Info,
        phase_id: strawberry.ID,
        reason: str | None = None,
    ) -> PhaseGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.phase_service import skip_phase

        phase = await skip_phase(user.user_id, str(phase_id), reason)
        return _phase_to_type(phase)

    @strawberry.mutation(
        description=(
            "Reorder phases within a goal by providing the full ordered list of phase IDs. "
            "Rate-limited to prevent accidental thrashing."
        )
    )
    async def reorder_phases(self, info: Info, input: ReorderPhasesInput) -> List[PhaseGQLType]:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.phase_service import reorder_phases

        phases = await reorder_phases(
            user_id=user.user_id,
            goal_id=str(input.goal_id),
            ordered_phase_ids=[str(pid) for pid in input.ordered_phase_ids],
        )
        return [_phase_to_type(p) for p in phases]

    # ── Action mutations ─────────────────────────────────────────

    @strawberry.mutation(description="Create an action (task, habit, milestone, etc.) in a phase.")
    async def create_action(self, info: Info, input: CreateActionInput) -> ActionGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        recurrence_dict = None
        if input.recurrence is not None:
            recurrence_dict = {
                "pattern": input.recurrence.pattern.value,
                "days_of_week": list(input.recurrence.days_of_week or []),
            }

        from app.services.action_service import create_action

        action = await create_action(
            user_id=user.user_id,
            goal_id=str(input.goal_id),
            phase_id=str(input.phase_id),
            title=input.title,
            action_type=input.action_type.value,
            description=input.description,
            due_date=input.due_date,
            estimated_minutes=input.estimated_minutes,
            contributes_value=input.contributes_value,
            recurrence=recurrence_dict,
        )
        return _action_to_type(action)

    @strawberry.mutation(description="Mark an action as completed.")
    async def complete_action(self, info: Info, input: CompleteActionInput) -> ActionGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.action_service import complete_action

        action = await complete_action(
            user_id=user.user_id,
            action_id=str(input.action_id),
            completion_note=input.completion_note,
        )
        return _action_to_type(action)

    @strawberry.mutation(
        description=(
            "Skip an action without completing it. "
            "No shame — circumstances change and the app should support that."
        )
    )
    async def skip_action(self, info: Info, input: SkipActionInput) -> ActionGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.action_service import skip_action

        action = await skip_action(
            user_id=user.user_id,
            action_id=str(input.action_id),
            reason=input.reason,
        )
        return _action_to_type(action)

    @strawberry.mutation(
        description="Reschedule an action to a new due date (user-initiated or auto-rescheduled)."
    )
    async def reschedule_action(self, info: Info, input: RescheduleActionInput) -> ActionGQLType:
        user = info.context.get("user")
        if not user:
            raise UnauthenticatedError()

        from app.services.action_service import reschedule_action

        action = await reschedule_action(
            user_id=user.user_id,
            action_id=str(input.action_id),
            new_due_date=input.new_due_date,
            reason=input.reason,
        )
        return _action_to_type(action)
