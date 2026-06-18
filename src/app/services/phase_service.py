"""
Phase Service — business logic for goal phases.

Phases unlock sequentially and can be completed/skipped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.constants.goals import PhaseStatus
from app.constants.limits import MAX_PHASES_PER_GOAL
from app.core.exceptions.base import (
    GoalNotFoundError,
    InvalidPhaseStateError,
    PhaseLimitExceededError,
    PhaseNotFoundError,
)
from app.events.event_types import PhaseEvents
from app.events.publisher import publish_phase_event
from app.models.phase import Phase
from app.repositories.goal_repository import GoalRepository
from app.repositories.phase_repository import PhaseRepository


async def create_phase(
    user_id: str,
    goal_id: str,
    title: str,
    description: Optional[str],
) -> Phase:
    """Create a new phase for a goal.

    The first phase is automatically set to ACTIVE.
    Subsequent phases are LOCKED and unlock when the previous one completes.

    Enforces MAX_PHASES_PER_GOAL.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)

    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)

    # Enforce max phases limit
    phase_count = await PhaseRepository.count_for_goal(goal_id)
    if phase_count >= MAX_PHASES_PER_GOAL:
        raise PhaseLimitExceededError()

    # Determine order and initial status
    order = phase_count
    initial_status = PhaseStatus.ACTIVE if order == 0 else PhaseStatus.LOCKED

    # Create phase
    phase = Phase(
        goal_id=PydanticObjectId(goal_id),
        user_id=PydanticObjectId(user_id),
        title=title,
        description=description,
        order=order,
        status=initial_status,
    )

    if initial_status == PhaseStatus.ACTIVE:
        phase.unlocked_at = datetime.utcnow()

    await phase.insert()

    # Publish event
    await publish_phase_event(
        event_type=(
            PhaseEvents.UNLOCKED if initial_status == PhaseStatus.ACTIVE else "phase.created"
        ),
        phase_id=str(phase.id),
        goal_id=goal_id,
        user_id=user_id,
        payload={
            "phase_id": str(phase.id),
            "goal_id": goal_id,
            "user_id": user_id,
            "title": title,
            "order": order,
            "status": initial_status,
        },
    )

    return phase


async def complete_phase(user_id: str, phase_id: str) -> Phase:
    """Complete a phase and auto-unlock the next one.

    If this is the last phase and the goal is ACTIVE, the goal is also completed.
    """
    phase = await PhaseRepository.get_by_id(phase_id)
    if not phase:
        raise PhaseNotFoundError(phase_id)

    if phase.user_id != PydanticObjectId(user_id):
        raise PhaseNotFoundError(phase_id)

    if phase.status not in (PhaseStatus.ACTIVE, PhaseStatus.LOCKED):
        raise InvalidPhaseStateError(f"Cannot complete phase in {phase.status} status.")

    # Mark phase as completed
    phase.status = PhaseStatus.COMPLETED
    phase.completed_at = datetime.utcnow()
    phase.updated_at = datetime.utcnow()
    await phase.save()

    # Try to unlock the next phase
    next_phase = await PhaseRepository.get_next_locked_phase(str(phase.goal_id))
    if next_phase:
        next_phase.status = PhaseStatus.ACTIVE
        next_phase.unlocked_at = datetime.utcnow()
        next_phase.updated_at = datetime.utcnow()
        await next_phase.save()

        await publish_phase_event(
            event_type=PhaseEvents.UNLOCKED,
            phase_id=str(next_phase.id),
            goal_id=str(phase.goal_id),
            user_id=user_id,
            payload={
                "phase_id": str(next_phase.id),
                "goal_id": str(phase.goal_id),
                "user_id": user_id,
                "title": next_phase.title,
                "order": next_phase.order,
            },
        )

    # Publish completion event
    await publish_phase_event(
        event_type=PhaseEvents.COMPLETED,
        phase_id=phase_id,
        goal_id=str(phase.goal_id),
        user_id=user_id,
        payload={
            "phase_id": phase_id,
            "goal_id": str(phase.goal_id),
            "user_id": user_id,
            "title": phase.title,
            "order": phase.order,
        },
    )

    return phase


async def skip_phase(user_id: str, phase_id: str, reason: Optional[str] = None) -> Phase:
    """Skip a phase and unlock the next one.

    Skipped phases are not counted towards goal progress but can be revisited.
    """
    phase = await PhaseRepository.get_by_id(phase_id)
    if not phase:
        raise PhaseNotFoundError(phase_id)

    if phase.user_id != PydanticObjectId(user_id):
        raise PhaseNotFoundError(phase_id)

    if phase.status not in (PhaseStatus.ACTIVE, PhaseStatus.LOCKED):
        raise InvalidPhaseStateError(f"Cannot skip phase in {phase.status} status.")

    phase.status = PhaseStatus.SKIPPED
    phase.updated_at = datetime.utcnow()
    if reason:
        phase.note = f"Skipped: {reason}"
    await phase.save()

    # Unlock next phase if this was ACTIVE
    if phase.status == PhaseStatus.ACTIVE:
        next_phase = await PhaseRepository.get_next_locked_phase(str(phase.goal_id))
        if next_phase:
            next_phase.status = PhaseStatus.ACTIVE
            next_phase.unlocked_at = datetime.utcnow()
            next_phase.updated_at = datetime.utcnow()
            await next_phase.save()

            await publish_phase_event(
                event_type=PhaseEvents.UNLOCKED,
                phase_id=str(next_phase.id),
                goal_id=str(phase.goal_id),
                user_id=user_id,
                payload={
                    "phase_id": str(next_phase.id),
                    "goal_id": str(phase.goal_id),
                    "user_id": user_id,
                    "title": next_phase.title,
                    "order": next_phase.order,
                },
            )

    await publish_phase_event(
        event_type=PhaseEvents.SKIPPED,
        phase_id=phase_id,
        goal_id=str(phase.goal_id),
        user_id=user_id,
        payload={
            "phase_id": phase_id,
            "goal_id": str(phase.goal_id),
            "user_id": user_id,
            "title": phase.title,
            "reason": reason,
        },
    )

    return phase


async def reorder_phases(user_id: str, goal_id: str, ordered_phase_ids: list[str]) -> list[Phase]:
    """Reorder phases within a goal.

    Accepts a list of phase IDs in the new desired order.
    """
    goal = await GoalRepository.get_by_id(goal_id)
    if not goal:
        raise GoalNotFoundError(goal_id)

    if goal.user_id != PydanticObjectId(user_id):
        raise GoalNotFoundError(goal_id)

    # Get all phases and verify ownership
    phases = {}
    for phase_id in ordered_phase_ids:
        phase = await PhaseRepository.get_by_id(phase_id)
        if not phase or phase.goal_id != PydanticObjectId(goal_id):
            raise PhaseNotFoundError(phase_id)
        phases[phase_id] = phase

    # Update order
    for new_order, phase_id in enumerate(ordered_phase_ids):
        phase = phases[phase_id]
        phase.order = new_order
        phase.updated_at = datetime.utcnow()
        await phase.save()

    # Return phases in new order
    return [phases[pid] for pid in ordered_phase_ids]
