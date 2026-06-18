"""
Goal Service — business logic layer for goal lifecycle.

Plain module-level functions (not classes) following the auth-service pattern.
All functions are async and use dependency injection for auth context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.constants.goals import GoalStatus
from app.constants.plans import MAX_GOALS_BY_PLAN, PlanTier
from app.core.exceptions.base import (
    DuplicateGoalError,
    GoalLimitExceededError,
    GoalNotFoundError,
    InvalidGoalStateError,
)
from app.events.event_types import GoalEvents
from app.events.publisher import publish_goal_event
from app.models.goal import Goal
from app.repositories.goal_repository import GoalRepository


async def create_goal(
    user_id: str,
    title: str,
    description: Optional[str],
    category: str,
    horizon: str,
    priority: int,
    target_date: Optional[datetime],
    plan_tier: str,
    target_value: Optional[float] = None,
    current_value: Optional[float] = None,
    unit: Optional[str] = None,
) -> Goal:
    """Create a new goal in DRAFT status.
    
    Enforces MAX_GOALS_BY_PLAN and checks for duplicate title.
    Publishes goal.created event.
    """
    user_oid = PydanticObjectId(user_id)
    
    # Enforce max goals limit
    active_goals = await Goal.find(
        Goal.user_id == user_oid,
        Goal.status == GoalStatus.ACTIVE,
    ).count()
    
    max_allowed = MAX_GOALS_BY_PLAN.get(plan_tier, MAX_GOALS_BY_PLAN[PlanTier.FREE])
    if active_goals >= max_allowed:
        raise GoalLimitExceededError(max_allowed, plan_tier)
    
    # Check for duplicate title (case-insensitive)
    existing = await Goal.find_one(
        Goal.user_id == user_oid,
        Goal.title == title,
    )
    if existing:
        raise DuplicateGoalError()
    
    # Create goal in DRAFT
    goal = Goal(
        user_id=user_oid,
        title=title,
        description=description,
        category=category,
        horizon=horizon,
        priority=priority,
        target_date=target_date,
        target_value=target_value,
        current_value=current_value or 0.0,
        unit=unit,
        status=GoalStatus.DRAFT,
    )
    await goal.insert()
    
    # Publish event
    await publish_goal_event(
        event_type=GoalEvents.CREATED,
        goal_id=str(goal.id),
        user_id=user_id,
        payload={
            "goal_id": str(goal.id),
            "user_id": user_id,
            "title": title,
            "category": category,
            "horizon": horizon,
        },
    )
    
    return goal


async def activate_goal(user_id: str, goal_id: str) -> Goal:
    """Transition a goal from DRAFT to ACTIVE.
    
    Publishes goal.activated event.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)  # Don't leak existence
    
    if goal.status != GoalStatus.DRAFT:
        raise InvalidGoalStateError(
            f"Cannot activate goal in {goal.status} status. Only DRAFT goals can be activated."
        )
    
    goal.status = GoalStatus.ACTIVE
    goal.activated_at = datetime.utcnow()
    goal.updated_at = datetime.utcnow()
    await goal.save()
    
    await publish_goal_event(
        event_type=GoalEvents.ACTIVATED,
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "goal_id": goal_id,
            "user_id": user_id,
            "title": goal.title,
        },
    )
    
    return goal


async def pause_goal(user_id: str, goal_id: str) -> Goal:
    """Pause an active goal, freezing its momentum."""
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    if goal.status not in (GoalStatus.ACTIVE, GoalStatus.RESUMED):
        raise InvalidGoalStateError(
            f"Cannot pause goal in {goal.status} status. Only ACTIVE or RESUMED goals can be paused."
        )
    
    goal.status = GoalStatus.PAUSED
    goal.paused_at = datetime.utcnow()
    goal.updated_at = datetime.utcnow()
    await goal.save()
    
    await publish_goal_event(
        event_type=GoalEvents.PAUSED,
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "goal_id": goal_id,
            "user_id": user_id,
            "title": goal.title,
        },
    )
    
    return goal


async def resume_goal(user_id: str, goal_id: str) -> Goal:
    """Resume a paused goal."""
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    if goal.status != GoalStatus.PAUSED:
        raise InvalidGoalStateError(
            f"Cannot resume goal in {goal.status} status. Only PAUSED goals can be resumed."
        )
    
    goal.status = GoalStatus.RESUMED
    goal.updated_at = datetime.utcnow()
    await goal.save()
    
    await publish_goal_event(
        event_type=GoalEvents.RESUMED,
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "goal_id": goal_id,
            "user_id": user_id,
            "title": goal.title,
        },
    )
    
    return goal


async def complete_goal(user_id: str, goal_id: str) -> Goal:
    """Mark a goal as completed.
    
    Publishes goal.completed event with celebration data.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    if goal.status not in (GoalStatus.ACTIVE, GoalStatus.PAUSED, GoalStatus.RESUMED):
        raise InvalidGoalStateError(
            f"Cannot complete goal in {goal.status} status."
        )
    
    goal.status = GoalStatus.COMPLETED
    goal.completed_at = datetime.utcnow()
    goal.updated_at = datetime.utcnow()
    await goal.save()
    
    # Get phase count for celebration card
    from app.repositories.phase_repository import PhaseRepository
    phase_count = await PhaseRepository.count_for_goal(goal_id)
    
    await publish_goal_event(
        event_type=GoalEvents.COMPLETED,
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "goal_id": goal_id,
            "user_id": user_id,
            "title": goal.title,
            "completion_date": goal.completed_at.isoformat(),
            "phase_count": phase_count,
            "category": goal.category,
        },
    )
    
    return goal


async def abandon_goal(user_id: str, goal_id: str, reason: Optional[str] = None) -> Goal:
    """Archive a goal as abandoned (no shame, just archive).
    
    This is for goals the user is no longer pursuing, and is a positive
    alternative to deletion — the data is preserved for learning.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    goal.status = GoalStatus.ABANDONED
    goal.updated_at = datetime.utcnow()
    if reason:
        goal.note = f"Abandoned: {reason}"
    await goal.save()
    
    await publish_goal_event(
        event_type=GoalEvents.ABANDONED,
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "goal_id": goal_id,
            "user_id": user_id,
            "title": goal.title,
            "reason": reason,
        },
    )
    
    return goal


async def update_goal_progress(
    user_id: str, 
    goal_id: str, 
    new_current_value: float,
) -> Goal:
    """Update the current progress value of a goal.
    
    Usually called by action_service when an action with contributes_value is completed.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)
    
    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)
    
    goal.current_value = new_current_value
    goal.updated_at = datetime.utcnow()
    await goal.save()
    
    return goal
