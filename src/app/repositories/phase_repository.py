"""
Phase Repository — data access layer for Phase documents.

All database logic for phases lives here; services never touch the ORM directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, cast

from beanie import PydanticObjectId

from app.models.phase import Phase


class PhaseRepository:
    """Data access layer for Phase documents."""

    @staticmethod
    async def get_by_id(phase_id: str) -> Optional[Any]:
        """Retrieve a phase by ID."""
        return await Phase.get(PydanticObjectId(phase_id))

    @staticmethod
    async def list_for_goal(goal_id: str) -> List[Any]:
        """Return all phases for a goal, ordered."""
        return cast(
            List[Any],
            await Phase.find(Phase.goal_id == PydanticObjectId(goal_id))
            .sort([(Phase.order, 1)])
            .to_list(),
        )

    @staticmethod
    async def get_active_phase(goal_id: str) -> Optional[Any]:
        """Return the currently active phase for a goal."""
        from app.constants.goals import PhaseStatus

        return await Phase.find_one(
            Phase.goal_id == PydanticObjectId(goal_id),
            Phase.status == PhaseStatus.ACTIVE,
        )

    @staticmethod
    async def get_next_locked_phase(goal_id: str, after_order: int = -1) -> Optional[Any]:
        """Return the next LOCKED phase with order > after_order.

        Pass `after_order` = the just-completed phase's order so the lookup
        is independent of whether there is currently an ACTIVE phase.
        When called with the default -1, returns the first LOCKED phase.
        """
        from app.constants.goals import PhaseStatus

        phases = await PhaseRepository.list_for_goal(goal_id)
        for phase in phases:
            if phase.order > after_order and phase.status == PhaseStatus.LOCKED:
                return phase

        return None

    @staticmethod
    async def create(
        goal_id: str,
        user_id: str,
        title: str,
        description: Optional[str],
        order: int,
    ) -> Any:
        """Create a new phase."""
        from app.constants.goals import PhaseStatus

        phase = Phase(
            goal_id=PydanticObjectId(goal_id),
            user_id=PydanticObjectId(user_id),
            title=title,
            description=description,
            order=order,
            status=PhaseStatus.LOCKED,
        )
        await phase.insert()
        return phase

    @staticmethod
    async def update_status(phase_id: str, new_status: str) -> Optional[Any]:
        """Update a phase's status and set appropriate timestamp."""
        from app.constants.goals import PhaseStatus

        phase = await Phase.get(PydanticObjectId(phase_id))
        if not phase:
            return None

        phase.status = new_status
        phase.updated_at = datetime.utcnow()

        # Set timestamp based on new status
        if new_status == PhaseStatus.ACTIVE:
            phase.unlocked_at = phase.unlocked_at or datetime.utcnow()
        elif new_status == PhaseStatus.COMPLETED:
            phase.completed_at = phase.completed_at or datetime.utcnow()

        await phase.save()
        return phase

    @staticmethod
    async def count_for_goal(goal_id: str) -> int:
        """Count total phases in a goal."""
        return cast(
            int,
            await Phase.find(Phase.goal_id == PydanticObjectId(goal_id)).count(),
        )

    @staticmethod
    async def delete_all_for_goal(goal_id: str) -> None:
        """Delete all phases for a goal (cascade)."""
        await Phase.find(Phase.goal_id == PydanticObjectId(goal_id)).delete()
