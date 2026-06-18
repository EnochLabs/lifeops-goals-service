"""
Action Service — business logic for actions within phases.

Actions are completed, skipped, rescheduled, and can contribute to goal progress.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.constants.goals import ActionStatus, ActionType, PhaseStatus
from app.constants.limits import MAX_ACTIONS_PER_PHASE
from app.core.exceptions.base import (
    ActionNotFoundError,
    GoalNotFoundError,
    InvalidActionStateError,
    InvalidPhaseStateError,
    PhaseNotFoundError,
    ActionLimitExceededError,
)
from app.events.event_types import ActionEvents
from app.events.publisher import publish_action_event
from app.models.action import Action, Recurrence
from app.repositories.action_repository import ActionRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.phase_repository import PhaseRepository


async def create_action(
    user_id: str,
    goal_id: str,
    phase_id: str,
    title: str,
    action_type: str,
    description: Optional[str] = None,
    due_date: Optional[datetime] = None,
    estimated_minutes: Optional[int] = None,
    contributes_value: Optional[float] = None,
    recurrence: Optional[dict] = None,
) -> Action:
    """Create a new action within a phase.
    
    Enforces MAX_ACTIONS_PER_PHASE.
    HABIT actions can have recurrence config.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    phase = await PhaseRepository.get_by_id(phase_id)
    if not phase or phase.goal_id != PydanticObjectId(goal_id):
        raise PhaseNotFoundError(phase_id)
    
    # Enforce max actions limit
    action_count = await ActionRepository.count_for_phase(phase_id)
    if action_count >= MAX_ACTIONS_PER_PHASE:
        raise ActionLimitExceededError()
    
    # Build action
    order = action_count
    action_kwargs = {
        "goal_id": PydanticObjectId(goal_id),
        "phase_id": PydanticObjectId(phase_id),
        "user_id": PydanticObjectId(user_id),
        "title": title,
        "action_type": action_type,
        "description": description,
        "due_date": due_date,
        "estimated_minutes": estimated_minutes,
        "contributes_value": contributes_value,
        "order": order,
        "status": ActionStatus.PENDING,
    }
    
    # Handle recurrence for HABIT actions
    if action_type == ActionType.HABIT and recurrence:
        action_kwargs["recurrence"] = Recurrence(**recurrence)
        # For habits, next_due is set based on due_date
        action_kwargs["next_due"] = due_date
        action_kwargs["status"] = ActionStatus.PENDING
    
    action = Action(**action_kwargs)
    await action.insert()
    
    # Publish event
    await publish_action_event(
        event_type=ActionEvents.CREATED,
        action_id=str(action.id),
        goal_id=goal_id,
        phase_id=phase_id,
        user_id=user_id,
        payload={
            "action_id": str(action.id),
            "goal_id": goal_id,
            "phase_id": phase_id,
            "user_id": user_id,
            "title": title,
            "action_type": action_type,
            "due_date": due_date.isoformat() if due_date else None,
        },
    )
    
    return action


async def complete_action(
    user_id: str,
    action_id: str,
    completion_note: Optional[str] = None,
) -> Action:
    """Mark an action as completed.
    
    If contributes_value is set, increments the goal's current_value.
    If this completes a MILESTONE and it's the last incomplete action in the phase,
    auto-completes the phase.
    
    Publishes action.completed event.
    """
    action = await ActionRepository.get_by_id(action_id)
    if not action:
        raise ActionNotFoundError(action_id)
    
    if action.user_id != PydanticObjectId(user_id):
        raise ActionNotFoundError(action_id)
    
    if action.status == ActionStatus.COMPLETED:
        return action  # Already completed, idempotent
    
    if action.status not in (ActionStatus.PENDING, ActionStatus.IN_PROGRESS):
        raise InvalidActionStateError(
            f"Cannot complete action in {action.status} status."
        )
    
    # Mark as completed
    action.status = ActionStatus.COMPLETED
    action.completed_at = datetime.utcnow()
    action.completion_note = completion_note
    action.updated_at = datetime.utcnow()
    await action.save()
    
    # Update goal progress if this action contributes value
    if action.contributes_value:
        from app.services.goal_service import update_goal_progress
        goal = await GoalRepository.get_by_id(str(action.goal_id))
        if goal:
            new_current_value = (goal.current_value or 0.0) + action.contributes_value
            await update_goal_progress(user_id, str(action.goal_id), new_current_value)
    
    # Publish event
    await publish_action_event(
        event_type=ActionEvents.COMPLETED,
        action_id=action_id,
        goal_id=str(action.goal_id),
        phase_id=str(action.phase_id),
        user_id=user_id,
        payload={
            "action_id": action_id,
            "goal_id": str(action.goal_id),
            "phase_id": str(action.phase_id),
            "user_id": user_id,
            "title": action.title,
            "action_type": action.action_type,
            "contributes_value": action.contributes_value,
        },
    )
    
    # Check if this was a MILESTONE that completes the phase
    if action.action_type == ActionType.MILESTONE:
        phase = await PhaseRepository.get_by_id(str(action.phase_id))
        if phase and phase.status == PhaseStatus.ACTIVE:
            # Check if all other actions in phase are completed
            all_actions = await ActionRepository.list_for_phase(str(action.phase_id))
            incomplete_count = sum(
                1 for a in all_actions
                if a.status not in (ActionStatus.COMPLETED, ActionStatus.SKIPPED)
            )
            if incomplete_count == 0:
                from app.services.phase_service import complete_phase
                await complete_phase(user_id, str(action.phase_id))
    
    return action


async def skip_action(
    user_id: str,
    action_id: str,
    reason: Optional[str] = None,
) -> Action:
    """Skip an action without completing it.
    
    The action is marked SKIPPED and not counted towards goal progress.
    No shame — this is a healthy way to move forward.
    """
    action = await ActionRepository.get_by_id(action_id)
    if not action:
        raise ActionNotFoundError(action_id)
    
    if action.user_id != PydanticObjectId(user_id):
        raise ActionNotFoundError(action_id)
    
    if action.status == ActionStatus.SKIPPED:
        return action  # Already skipped
    
    if action.status not in (ActionStatus.PENDING, ActionStatus.IN_PROGRESS):
        raise InvalidActionStateError(
            f"Cannot skip action in {action.status} status."
        )
    
    action.status = ActionStatus.SKIPPED
    action.completion_note = reason
    action.updated_at = datetime.utcnow()
    await action.save()
    
    await publish_action_event(
        event_type=ActionEvents.SKIPPED,
        action_id=action_id,
        goal_id=str(action.goal_id),
        phase_id=str(action.phase_id),
        user_id=user_id,
        payload={
            "action_id": action_id,
            "goal_id": str(action.goal_id),
            "phase_id": str(action.phase_id),
            "user_id": user_id,
            "title": action.title,
            "reason": reason,
        },
    )
    
    return action


async def reschedule_action(
    user_id: str,
    action_id: str,
    new_due_date: datetime,
    reason: Optional[str] = None,
) -> Action:
    """Reschedule an action to a new due date.
    
    Called by auto-rescheduling logic (e.g., when user has low energy)
    or by user directly via MFE.
    """
    action = await ActionRepository.get_by_id(action_id)
    if not action:
        raise ActionNotFoundError(action_id)
    
    if action.user_id != PydanticObjectId(user_id):
        raise ActionNotFoundError(action_id)
    
    if action.status == ActionStatus.COMPLETED:
        raise InvalidActionStateError("Cannot reschedule a completed action.")
    
    old_due = action.due_date
    action = await ActionRepository.update_due_date(action_id, new_due_date)
    
    # Publish event (not a formal event type, but useful for logging)
    await publish_action_event(
        event_type="action.rescheduled",
        action_id=action_id,
        goal_id=str(action.goal_id),
        phase_id=str(action.phase_id),
        user_id=user_id,
        payload={
            "action_id": action_id,
            "goal_id": str(action.goal_id),
            "phase_id": str(action.phase_id),
            "user_id": user_id,
            "title": action.title,
            "old_due_date": old_due.isoformat() if old_due else None,
            "new_due_date": new_due_date.isoformat(),
            "reason": reason,
        },
    )
    
    return action


async def list_todays_actions(user_id: str, as_of: datetime) -> list[Action]:
    """Retrieve all pending/in-progress actions due today or overdue.
    
    Sorted by goal priority, then by due date.
    """
    from app.constants.goals import GoalStatus
    
    user_oid = PydanticObjectId(user_id)
    
    # Get all active goals for user
    goals = await GoalRepository.list_by_status(GoalStatus.ACTIVE)
    goal_ids = [g.id for g in goals if g.user_id == user_oid]
    
    if not goal_ids:
        return []
    
    # Get all actions due today or earlier, not completed
    actions = await Action.find(
        Action.goal_id.in_([PydanticObjectId(str(gid)) for gid in goal_ids]),
        Action.status.in_([ActionStatus.PENDING, ActionStatus.IN_PROGRESS]),
        Action.due_date <= as_of,
    ).sort([(Action.due_date, 1)]).to_list()
    
    return actions
